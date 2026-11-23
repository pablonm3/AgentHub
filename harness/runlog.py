"""Run log writer (spec 5.5): workflow_logs/<run-id>.log, an index built from state.json."""

from __future__ import annotations

import re
from pathlib import Path

from .config import Workflow
from .naming import cost_line
from .paths import Layout
from .state import State, fmt_duration, parse_iso, seconds_between


def _local(iso: str | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    d = parse_iso(iso)
    return d.astimezone().strftime(fmt) if d else "–"


def _hms(iso: str | None) -> str:
    return _local(iso, "%H:%M:%S")


_WALL_RE = re.compile(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?")


def _wall_seconds(text: str | None) -> int:
    if not text:
        return 0
    m = _WALL_RE.search(text.strip())
    if not m or not any(m.groups()):
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def build_log(layout: Layout, state: State, wf: Workflow, commit_count: int | None = None) -> str:
    d = state.data
    tel = d.get("telemetry") or {}
    tel_text = "on" if tel.get("active") else "off"
    if tel.get("since_step") and not tel.get("active"):
        tel_text = f"off since step {tel['since_step']}"
    elif not tel.get("active") and tel.get("reason"):
        tel_text = f"off ({tel['reason']})"

    lines = [
        f"run        {d['run_id']}",
        f"workflow   {d['workflow']}",
        f"feature    {d['feature']}      ticket: tickets/{d['feature']}.md",
        f"project    {d['project']}    base: {d['base_branch']}    branch: {d['branch']}",
        f"harness    {d['harness_commit']}",
        f"telemetry  {tel_text}",
        "",
    ]

    total = state.total_seconds()
    wait = state.human_wait_seconds()
    agent = (total - wait) if total is not None else None
    proj_wall = 0
    proj_llm: list[str] = []
    for exe in d["executions"]:
        cost = exe.get("project_cost") or {}
        if (cost.get("runs") or "none").strip().lower() != "none":
            proj_wall += _wall_seconds(cost.get("wall_time"))
            if cost.get("llm_usage"):
                proj_llm.append(cost["llm_usage"])
    lines += [
        f"started    {_local(d['started'])}",
        f"ended      {_local(d.get('ended'))}",
        f"duration   {fmt_duration(total)}   (agent {fmt_duration(agent)}, waiting on human {fmt_duration(wait)})",
        f"project    wall {fmt_duration(proj_wall)} · LLM {'; '.join(proj_llm) if proj_llm else 'none reported'}",
        f"status     {d['status']}" + (f"   ({d['error']})" if d.get("error") else ""),
        "",
    ]

    # one block per execution in run order; gates interleaved by time
    events: list[tuple[float, str]] = []
    for idx, exe in enumerate(d["executions"]):
        step = wf.step(exe["step"]) if wf.has_step(exe["step"]) else None
        label = exe.get("skill") or (step.label if step else exe["step"])
        iter_txt = f"(iter {exe['iteration']})" if step and _in_loop(wf, exe["step"]) else ""
        elapsed = seconds_between(exe["started"], exe.get("ended"))
        dur = fmt_duration(elapsed - (exe.get("waited_s") or 0) if elapsed is not None else None)
        if (exe.get("attempts") or 1) > 1:
            dur += f", {exe['attempts']} attempts in one session"
        head = f"── {exe['step']:>2}  {label:<26} {iter_txt:<9} {_hms(exe['started'])} → {_hms(exe.get('ended'))}  ({dur})"
        if exe.get("outcome"):
            head += f"   {exe['outcome']}"
        if exe.get("status") not in ("done", None):
            head += f"   [{exe['status']}]"
        block = [head]
        if exe.get("in"):
            block.append(f"    in   {', '.join(exe['in'])}")
        if exe.get("commits") is not None:
            block.append(f"    out  {exe['commits']} commit(s) on {d['branch']}")
        if exe.get("out"):
            block.append(f"    out  {', '.join(exe['out'])}")
        block.append(f"    cost {cost_line(exe.get('project_cost'))}")
        if exe.get("cost_usd") is not None:
            block.append(f"    harness ${exe['cost_usd']:.2f}" + (f" · {exe['num_turns']} turns" if exe.get("num_turns") else ""))
        if exe.get("transcript"):
            block.append(f"    log  {exe['transcript']}")
        events.append((float(idx), "\n".join(block)))
    for sid, entries in d.get("gates", {}).items():
        step = wf.step(sid) if wf.has_step(sid) else None
        for e in entries:
            waited = fmt_duration(seconds_between(e.get("reached"), e.get("released")))
            label = step.label if step else f"gate {sid}"
            events.append(
                (float(e.get("after_execution", len(d["executions"]))) - 0.5,
                 f"── {sid:>2}  H {label:<24}           {_hms(e['reached'])} → {_hms(e.get('released'))}  (waited {waited})")
            )
    events.sort(key=lambda t: t[0])
    lines += [b for _, b in events]
    lines.append("")

    run_dir = f"runs/{d['run_id']}"
    report = _find_out(d, "final_report_")
    diff = _find_out(d, "explain_diff_")
    commits_txt = f"({d['base_branch']}..{d['branch']}, {commit_count} commits)" if commit_count is not None else ""
    lines += [
        "outputs",
        f"   report   {report or '–'}",
        f"   diff     {diff or '–'}",
        f"   branch   {d['branch']}   {commits_txt}".rstrip(),
        f"   run dir  {run_dir}/",
        "",
    ]
    decisions = [o for exe in d["executions"] for o in (exe.get("out") or []) if "/decision_" in o]
    if decisions:
        lines.append("decisions")
        lines += [f"   {p}" for p in decisions]
        lines.append("")
    if d.get("gates"):
        lines.append("gates")
        for sid, entries in d["gates"].items():
            for e in entries:
                lines.append(f"   {sid}  reached {_local(e['reached'])}   released {_local(e.get('released'))}")
    return "\n".join(lines).rstrip() + "\n"


def _in_loop(wf: Workflow, sid: str) -> bool:
    return any(g.loop and sid in g.steps for g in wf.groups)


def _find_out(d: dict, prefix: str) -> str | None:
    for exe in reversed(d["executions"]):
        for o in exe.get("out") or []:
            if o.rsplit("/", 1)[-1].startswith(prefix):
                return o
    return None


def write_log(layout: Layout, state: State, wf: Workflow, commit_count: int | None = None) -> Path:
    path = layout.workflow_log(state.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_log(layout, state, wf, commit_count))
    return path

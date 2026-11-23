"""Console rendering of a run (spec 5.3): `agenthub-harness status <run-id>` and before every step."""

from __future__ import annotations

from datetime import datetime, timezone
from string import Template

from .config import Workflow
from .naming import severities_line
from .observability import env_flag_summary
from .state import State, fmt_duration, parse_iso, seconds_between

GLYPH = {
    "done": "✔",
    "running": "▶",
    "pending": "○",
    "failed": "✖",
    "waiting": "⏸",
    "skipped": "–",
}


def _local_hm(iso: str | None) -> str:
    d = parse_iso(iso)
    if not d:
        return ""
    return d.astimezone().strftime("%H:%M")


def header(state: State) -> str:
    tel = state.get("telemetry") or {}
    tel_text = env_flag_summary(bool(tel.get("active")), tel.get("reason"))
    if not tel.get("active") and tel.get("since_step"):
        tel_text += f", missing since step {tel['since_step']}"
    return (
        f"run {state.run_id} · workflow {state['workflow']} · feature {state.feature} · "
        f"{state['project']} · base: {state['base_branch']} · "
        f"iteration {state['iteration']}/{state['max_iterations']} · {tel_text} · status: {state.status}"
    )


def _detail(state: State, step_id: str, wf: Workflow) -> str:
    st = state.step(step_id)
    step = wf.step(step_id)
    status = st.get("status", "pending")
    if step.actor == "human" and step.gate:
        if status == "done" and st.get("released"):
            return f"released {_local_hm(st['released'])}"
        if status == "waiting":
            return f"waiting since {_local_hm(st.get('reached'))}"
        return ""
    if step.actor in ("human", "orchestrator") and step.display:
        return Template(step.display).safe_substitute(
            feature=state.feature, n=state.n, run_id=state.run_id, project=state["project"]
        )
    if status == "skipped":
        return f"skipped ({st.get('reason', '')})"
    if status == "running":
        started = st.get("started")
        elapsed = seconds_between(started, datetime.now(timezone.utc).isoformat()) if started else None
        return f"running {fmt_duration(elapsed)}"
    parts = []
    outs = st.get("out") or []
    if step.writes_commit and st.get("commits") is not None:
        runs = st.get("runs") or 1
        parts.append(f"{st['commits']} commit(s)" + (f" ({runs} iterations)" if runs > 1 else ""))
    if outs:
        # show the primary output path plus the others' basenames
        first = outs[0]
        rest = [o.rsplit("/", 1)[-1] for o in outs[1:]]
        parts.append(", ".join([first, *rest]))
    outcome = st.get("outcome")
    if outcome and not (step.writes_commit and outcome.endswith("commit(s)")):
        parts.append(f"({outcome})")
    exe_runs = st.get("runs")
    if exe_runs and exe_runs > 1 and status == "done":
        parts.append(f"×{exe_runs}")
    return " ".join(parts)


def render(state: State, wf: Workflow) -> str:
    lines = [header(state), ""]
    for group in wf.groups:
        title = f" {group.name}"
        if group.loop and state["iteration"] > 1:
            title += f"  ↻ {state['iteration']}"
        lines.append(title)
        for sid in group.steps:
            if not wf.has_step(sid):
                continue
            step = wf.step(sid)
            st = state.step(sid)
            status = st.get("status", "pending")
            glyph = GLYPH.get(status, "○")
            actor = "H " if step.actor == "human" else ""
            label = f"{actor}{step.label}"
            lines.append(f"   {glyph} {sid:>2} {label:<26} {_detail(state, sid, wf)}".rstrip())
    lines.append("")
    cur = state.current
    if state.status in ("done", "failed", "blocked"):
        lines.append(f"ended: {state.status}" + (f" — {state['error']}" if state.get("error") else ""))
    elif state.status == "paused":
        pc = state.get("pending_chat") or {}
        lines.append(f"paused at {cur}: {pc.get('reason', 'waiting for `agenthub-harness resume`')}")
    elif state.get("limit_wait"):
        until = datetime.fromtimestamp(state["limit_wait"]["until"]).strftime("%H:%M")
        lines.append(f"waiting at {cur}: usage limit reached, the step continues in its session at {until}")
    elif cur:
        nxt = wf.next_after(cur)
        lines.append(f"next: {cur} → {nxt}" if nxt else f"at: {cur}")
    return "\n".join(lines)


def severity_outcome(counts: dict[str, int]) -> str:
    return severities_line(counts)

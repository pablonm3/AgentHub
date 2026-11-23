#!/usr/bin/env python3
"""A stand-in for the `claude` binary used by the tests (HARNESS_CLAUDE_BIN).

Print mode (`-p`): writes the output files named in the prompt with frontmatter the
orchestrator understands, commits when the skill is a building one, and emits stream-json.
Interactive mode (no `-p`): simulates the human chat according to the scenario.

Scenario: JSON file at FAKE_CLAUDE_SCENARIO, e.g.
  {"triage": ["new_plan", "done"], "context_status": "reproduced",
   "chat": {"7": "nothing", "14": "write_plan", "4": "answer"}, "tests": {"passed": 8, "total": 10},
   "chat_stay_open": {"7": 60}}
`chat_stay_open` maps a chat step to seconds: after its action the chat runs the Stop hooks of its
--settings file, as Claude Code does when a reply ends, then stays open that long, as a real chat
waits for the human. It leaves `chat_<step>_open` next to the scenario file and, when nobody ended
it before the time was up, `chat_<step>_exited_by_itself`.
Sequential values are consumed through a counter file next to it (FAKE_CLAUDE_SCENARIO + ".state").

`faults` maps a step id to what its successive print-mode calls do instead of the work, in call order
(a continued session counts as a call); once the list is used up the step works normally:
  "rate_limit"    the account's usage limit rejects a request: no output, exit 1
  "die"           the process dies after the session started: no result event, no output, exit 1
  "no_output"     the session ends normally without writing its output
  "session_gone"  the session named by --resume cannot be opened: nothing on stdout, exit 1
A fresh call is session `fake-<step>-<execution>`; with `--resume <id>` the call continues `<id>`.
Each prompt is kept next to the scenario as prompts/<step>_<execution>.txt, the message of a
continued session as prompts/<step>_<execution>_resumed.txt with a first line `[resume <id>]`.
The reasoning effort each call was launched at (CLAUDE_CODE_EFFORT_LEVEL) is kept beside it as `<same name>.effort`,
its telemetry resource attributes (OTEL_RESOURCE_ATTRIBUTES, "" when telemetry is off) as `<same name>.attrs`.
Every result event reports a `modelUsage` of two models (the step's and a subagent's) worth 1,000 tokens
(model_usage); the trailing empty result after a usage-limit rejection reports the running total of 2,000.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PATH_RE = re.compile(r"(/[^\s`'\"<>]+?\.(?:md|html|csv))")


def load_scenario() -> tuple[dict, dict, Path | None]:
    p = os.environ.get("FAKE_CLAUDE_SCENARIO")
    if not p:
        return {}, {}, None
    sc = json.loads(Path(p).read_text())
    sp = Path(p + ".state")
    st = json.loads(sp.read_text()) if sp.exists() else {}
    return sc, st, sp


def save_state(st: dict, sp: Path | None) -> None:
    if sp:
        sp.write_text(json.dumps(st))


def take(sc: dict, st: dict, key: str, default):
    seq = sc.get(key)
    if isinstance(seq, list):
        i = st.get(key, 0)
        st[key] = i + 1
        return seq[min(i, len(seq) - 1)] if seq else default
    return seq if seq is not None else default


def fm(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if isinstance(v, dict):
            lines.append(f"{k}: " + json.dumps(v))
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif v is None:
            lines.append(f"{k}:")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def write(path: Path, front: dict, body: str, cost: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = fm(front) + body
    if cost and path.suffix == ".md":
        text += "\n## Run cost\n- project runs:    none\n"
    path.write_text(text)


def commit(cwd: Path, message: str) -> None:
    marker = cwd / "fake_changes.txt"
    with open(marker, "a") as f:
        f.write(message + "\n")
    subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=fake", "-c", "user.email=fake@example.com", "commit", "-q", "-m", message],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def prompt_paths(prompt: str) -> list[Path]:
    run_dir = os.environ.get("HARNESS_RUN_DIR", "")
    return [Path(p) for p in PATH_RE.findall(prompt) if run_dir and p.startswith(run_dir)]


def model_usage(k: int = 1) -> dict:
    """A result's modelUsage: k times 1,000 tokens (5 input, 145 output, 250 cache creation, 600 cache read)."""
    return {
        "model-main": {"inputTokens": 4 * k, "outputTokens": 96 * k, "cacheCreationInputTokens": 200 * k,
                       "cacheReadInputTokens": 500 * k, "costUSD": 0.01 * k},
        "model-subagent": {"inputTokens": 1 * k, "outputTokens": 49 * k, "cacheCreationInputTokens": 50 * k,
                           "cacheReadInputTokens": 100 * k, "costUSD": 0.0},
    }


def emit(*events: dict) -> None:
    for e in events:
        sys.stdout.write(json.dumps(e) + "\n")


def fail_as(fault: str, session: str, sc: dict) -> int:
    """Act out one entry of the scenario's `faults` (module docstring)."""
    init = {"type": "system", "subtype": "init", "session_id": session}
    if fault == "session_gone":
        sys.stderr.write(f"No conversation found with session ID: {session}\n")
        return 1
    if fault == "die":
        emit(init)
        return 1
    if fault == "no_output":
        emit(init, {"type": "result", "subtype": "success", "is_error": False, "result": "done", "total_cost_usd": 0.01,
                    "num_turns": 1, "session_id": session, "modelUsage": model_usage()})
        return 0
    assert fault == "rate_limit", fault
    message = "You've hit your 5-hour limit · resets 3:20pm (America/Buenos_Aires)"
    resets_at = int(time.time()) + int(sc.get("limit_resets_in_s", 3600))
    emit(
        init,
        {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": resets_at, "rateLimitType": "five_hour"}},
        {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 429, "result": message,
         "total_cost_usd": 0.02, "num_turns": 3, "session_id": session, "modelUsage": model_usage()},
        # a real session can end with one more, empty result after the one that failed
        {"type": "result", "subtype": "success", "is_error": False, "result": "", "total_cost_usd": 0.02, "num_turns": 0,
         "session_id": session, "modelUsage": model_usage(2)},
    )
    return 1


def print_mode(prompt: str, resume: str | None = None) -> int:
    sc, st, sp = load_scenario()
    skill = os.environ.get("HARNESS_SKILL", "")
    step = os.environ.get("HARNESS_STEP", "")
    run_id = os.environ.get("HARNESS_RUN_ID", "")
    execution = os.environ.get("HARNESS_EXECUTION", "")
    session = resume or f"fake-{step}-{execution}"
    cwd = Path.cwd()
    if sp:
        # kept for tests that assert on what a step was asked
        kept = sp.parent / "prompts" / (f"{step}_{execution}" + ("_resumed" if resume else "") + ".txt")
        kept.parent.mkdir(exist_ok=True)
        kept.write_text((f"[resume {resume}]\n" if resume else "") + prompt)
        # the reasoning effort the process was launched at: <same name>.effort ("" when none was set)
        kept.with_suffix(".effort").write_text(os.environ.get("CLAUDE_CODE_EFFORT_LEVEL", ""))
        kept.with_suffix(".attrs").write_text(os.environ.get("OTEL_RESOURCE_ATTRIBUTES", ""))
    faults = (sc.get("faults") or {}).get(step) or []
    call = st.get(f"faults_{step}", 0)
    st[f"faults_{step}"] = call + 1
    if call < len(faults) and faults[call]:
        save_state(st, sp)
        return fail_as(faults[call], session, sc)
    paths = prompt_paths(prompt)
    new_paths = [p for p in paths if not p.exists()]
    base = {"run_id": run_id, "step": step, "skill": skill}
    summary = f"fake {skill}"
    answer_seen = "Answer from the human" in prompt

    def out(prefix: str) -> Path | None:
        for p in new_paths:
            if p.name.startswith(prefix):
                return p
        return None

    if skill == "build-context":
        status = take(sc, st, "context_status", "reproduced")
        if answer_seen:
            status = "reproduced"
        front = {**base, "status": status, "summary": f"context {status}"}
        if status == "not_reproduced":
            front["question"] = "Which filter value reproduces the issue?"
        write(out("context_"), front, "# context\n\n## Current behaviour\nfake\n")
    elif skill == "spec":
        write(out("spec_"), {**base, "version": 1, "acceptance_criteria": 3, "open_questions": 0, "summary": "3 criteria"},
              "# spec\n\n## Acceptance criteria\nAC1. WHEN x THEN y\nAC2. WHEN a THEN b\nAC3. WHEN c THEN d\n")
    elif skill == "plan":
        write(out("plan_short_"), {**base, "summary": "short plan"}, "# short plan\n", cost=False)
        write(out("plan_"), {**base, "summary": "plan"}, "# plan\n")
    elif skill == "testcase-builder":
        write(out("testing_"), {**base, "cases": 5, "summary": "5 cases"}, "# cases\n")
    elif skill == "build-plan":
        commit(cwd, f"Build iteration ({run_id})")
    elif skill == "code-review":
        write(out("review_"), {**base, "counts": {"high": 1, "medium": 2, "low": 0}, "summary": "1 high, 2 medium"},
              "# review\n\n### [HIGH] bug\n\n### [MEDIUM] a\n\n### [MEDIUM] b\n")
    elif skill == "readability-review":
        write(out("readability_"), {**base, "counts": {"high": 0, "medium": 1, "low": 1}, "summary": "1 medium, 1 low"}, "# readability\n")
    elif skill == "apply-reviews":
        commit(cwd, f"Apply reviews ({run_id})")
        write(out("reviews_applied_"), {**base, "applied": {"review": 1, "readability": 1}, "skipped": {"review": 2, "readability": 1}},
              "# applied\n")
    elif skill == "run-tests":
        t = sc.get("tests") or {"passed": 10, "total": 10}
        write(out("testing_feedback_"), {**base, "passed": t["passed"], "failed": t["total"] - t["passed"], "blocked": 0, "total": t["total"],
                                          "summary": f"{t['passed']}/{t['total']} pass"}, "# results\n")
    elif skill == "run-tests-ui":
        u = sc.get("ui_tests") or {"passed": 0, "total": 0}
        write(out("testing_feedback_ui_"), {**base, "passed": u["passed"], "failed": u["total"] - u["passed"], "blocked": 0,
                                             "total": u["total"], "scope": "ui", "browser": "none",
                                             "summary": "no UI cases" if u["total"] == 0 else f"{u['passed']}/{u['total']} UI pass"}, "# ui results\n")
    elif skill == "triage":
        decision = take(sc, st, "triage", "done")
        if answer_seen and sc.get("triage_after_answer"):
            decision = sc["triage_after_answer"]
        front = {**base, "decision": decision, "summary": f"decision {decision}"}
        if decision == "spec_issue":
            front["question"] = "AC2 contradicts the observed behaviour; which one is right?"
        write(out("decision_"), front, "# decision\n")
        if decision == "new_plan":
            m = re.search(r"write the next plan version at: (\S+)", prompt)
            if m:
                write(Path(m.group(1)), {**base, "summary": "next plan"}, "# plan vNext\n")
            m2 = re.search(r"matching short plan at (\S+?)\)", prompt)
            if m2:
                write(Path(m2.group(1)), {**base, "summary": "next short plan"}, "# short\n", cost=False)
    elif skill == "regression-testing-report":
        r = sc.get("regression") or {"status": "not_applicable", "suites": 0}
        csv_path = next((p for p in new_paths if p.suffix == ".csv"), None)
        if csv_path:
            csv_path.write_text("suite,cases,repetitions,acc_baseline,acc_modified,acc_delta,time_baseline_s,time_modified_s,time_delta_s,baseline_report,modified_report\n")
        write(out("regression_report_"), {**base, "status": r["status"], "suites": r["suites"], "regressions": 0, "upload": "skipped",
                                           "summary": "no eval suites to compare" if r["status"] == "not_applicable" else f"{r['suites']} suites, 0 regressions"},
              "# regression\n")
    elif skill == "langsmith-cleanup":
        write(out("langsmith_cleanup_"), {**base, "status": "done", "owner": run_id, "deleted": 0, "remaining": 0,
                                           "summary": "0 scratch datasets deleted"}, "# cleanup\n")
    elif skill == "fix_ai_comments":
        commit(cwd, f"Clean up comments ({run_id})")
    elif skill == "final-report":
        write(out("final_report_"), {**base, "iterations": 1, "spec_revisions": 0, "summary": "all criteria met"}, "# report\n\n## Feedback\nnone\n")
    elif skill == "explain-diff-html":
        p = out("explain_diff_")
        p.write_text("<!doctype html><html><body>fake</body></html>\n")
    else:
        for p in new_paths:
            write(p, {**base, "summary": summary}, "# fake\n")
    save_state(st, sp)

    emit(
        {"type": "system", "subtype": "init", "session_id": session},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": f"fake {skill} done"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": summary, "total_cost_usd": 0.01,
         "duration_ms": 1200, "num_turns": 2, "session_id": session, "modelUsage": model_usage()},
    )
    return 0


def next_version_path(run_dir: Path, stem: str) -> Path:
    best = 0
    base = None
    for p in run_dir.glob(f"{stem}_*.md"):
        m = re.match(rf"^{re.escape(stem)}_(.+?)(?:_v(\d+))?\.md$", p.name)
        if not m:
            continue
        # skip other stems that share the prefix (plan_short vs plan)
        if stem == "plan" and p.name.startswith("plan_short_"):
            continue
        k = int(m.group(2) or 1)
        if k >= best:
            best = k
            base = run_dir / f"{stem}_{m.group(1)}.md"
    assert base is not None, f"no {stem} artifact in {run_dir}"
    return base.with_name(f"{base.stem}_v{best + 1}{base.suffix}")


def run_stop_hooks(argv: list[str]) -> None:
    if "--settings" not in argv:
        return
    settings = json.loads(Path(argv[argv.index("--settings") + 1]).read_text())
    for group in (settings.get("hooks") or {}).get("Stop") or []:
        for hook in group.get("hooks") or []:
            subprocess.run(hook["command"], shell=True, check=True)


def chat_mode(prompt: str, argv: list[str]) -> int:
    sc, st, sp = load_scenario()
    chat_step = os.environ.get("HARNESS_CHAT_STEP", "")
    run_dir = Path(os.environ.get("HARNESS_RUN_DIR", "."))
    action = take(sc, st, f"chat_{chat_step}", None)
    if action is None:
        action = (sc.get("chat") or {}).get(chat_step, "nothing")
    m = re.search(r"(/\S+/decision_\S+?\.md)", prompt)
    decision_file = Path(m.group(1)) if m else None
    front = {"run_id": os.environ.get("HARNESS_RUN_ID", ""), "step": chat_step, "answered": action != "nothing", "summary": f"chat {action}"}
    if action == "write_spec":
        p = next_version_path(run_dir, "spec")
        write(p, {"run_id": front["run_id"], "step": "5", "skill": "spec", "acceptance_criteria": 3, "open_questions": 0, "summary": "spec revised in chat"}, "# spec v2\n")
    elif action == "write_plan":
        p = next_version_path(run_dir, "plan")
        write(p, {"run_id": front["run_id"], "step": "6", "skill": "plan", "summary": "plan revised in chat"}, "# plan from chat\n")
    elif action == "write_ticket":
        p = next_version_path(run_dir, "ticket")
        p.write_text("---\nproject: demo\nbase_branch: dev\n---\n# ticket revised\n")
    if decision_file and action != "nothing":
        write(decision_file, front, "# decision\n\n## Answer\nUse filter value 42.\n")
    save_state(st, sp)
    sys.stdout.write(f"[fake chat] step {chat_step} action {action}\n")
    sys.stdout.flush()
    stay_open = (sc.get("chat_stay_open") or {}).get(chat_step)
    if stay_open:
        run_stop_hooks(argv)
        flags = Path(os.environ["FAKE_CLAUDE_SCENARIO"]).parent
        (flags / f"chat_{chat_step}_open").write_text("")
        time.sleep(stay_open)
        (flags / f"chat_{chat_step}_exited_by_itself").write_text("")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    prompt = argv[-1] if argv else ""
    if "-p" in argv or "--print" in argv:
        return print_mode(prompt, argv[argv.index("--resume") + 1] if "--resume" in argv else None)
    return chat_mode(prompt, argv)


if __name__ == "__main__":
    sys.exit(main())

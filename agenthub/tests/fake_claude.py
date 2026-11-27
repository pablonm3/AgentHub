#!/usr/bin/env python3
"""A stand-in for the `claude` binary in AgentHub's tests and fake mode (AGENTHUB_CLAUDE_BIN).

- `claude auth status`: JSON of a stored login (or none with the `not_logged_in` switch).
- `claude -p … --json-schema …` (an AI user's turn): emits stream-json events — init, assistant
  text, a tool call when a command runs, and a `result` with `structured_output` and a `modelUsage`
  whose total grows per session — and keeps every prompt of a session in
  `$AGENTHUB_FAKE_DIR/sessions/<id>.json`, so a reply can say how many messages the session has seen.
- `claude -p …` without `--json-schema` (a step of a harness run): handed to the harness's own fake.

Scenario: `$AGENTHUB_FAKE_DIR/scenario.json`, read on every call. Top-level keys apply to every turn;
`turns` is a list of per-call overrides consumed in call order (a counter file beside it).
`by_ai_user` maps an AI user's handle (`AGENTHUB_AI_USER`) to a scenario laid over the top-level keys
for that AI user's calls only; a `turns` list inside it has its own counter (`scenario.counter.<handle>`):
  status                "waiting_on_user" (default) or "done"
  message, title        the structured output's fields (defaults: an echo of the input)
  sleep                 seconds to wait before answering (a turn to stop)
  commands              shell commands run in the session's folder with its environment
  report                session total to report, instead of 100 tokens per turn of the session
  not_logged_in         `auth status` says logged out and every turn fails as Claude does
  session_gone          a call with --resume finds no session: stderr message, exit 1
  no_structured_output  the result carries no structured_output
  rate_limit_info       an object emitted as a `rate_limit_event` right after `init` (the account's limits)
Every call is appended to `$AGENTHUB_FAKE_DIR/calls.jsonl` (argv, cwd, selected environment).
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

HARNESS_FAKE = Path(__file__).resolve().parents[2] / "harness" / "tests" / "fake_claude.py"
LOGGED_ENV = ("AGENTHUB_TASK_ID", "AGENTHUB_AI_USER", "AGENTHUB_URL", "AGENTHUB_REPORTS_DIR", "HARNESS_PROTECTED_PATHS",
              "OTEL_RESOURCE_ATTRIBUTES", "HARNESS_ROOT", "HARNESS_PRIVATE_ROOT", "HARNESS_DATA_ROOT")


def fake_dir() -> Path:
    d = Path(os.environ.get("AGENTHUB_FAKE_DIR") or Path.cwd() / ".fake_claude")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_turn(sc: dict, counter: Path) -> dict:
    """`sc` without its `turns`, with the next entry of `turns` laid over it."""
    turns = sc.get("turns")
    if not isinstance(turns, list):
        return sc
    i = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(i + 1))
    base = {k: v for k, v in sc.items() if k != "turns"}
    return {**base, **turns[i]} if i < len(turns) else base


def scenario(d: Path) -> dict:
    path = d / "scenario.json"
    sc = json.loads(path.read_text()) if path.exists() else {}
    own = (sc.pop("by_ai_user", None) or {}).get(os.environ.get("AGENTHUB_AI_USER", ""))
    if isinstance(own, dict):
        handle = os.environ["AGENTHUB_AI_USER"]
        top = {k: v for k, v in sc.items() if k != "turns"}
        return {**top, **_next_turn(own, d / f"scenario.counter.{handle}")}
    return _next_turn(sc, d / "scenario.counter")


def arg(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def emit(ev: dict) -> None:
    print(json.dumps(ev), flush=True)


def main() -> int:
    argv = sys.argv[1:]
    if argv[:2] == ["auth", "status"]:
        sc = scenario_peek()
        if sc.get("not_logged_in"):
            print(json.dumps({"loggedIn": False, "authMethod": "none"}))
        else:
            print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max",
                              "loginExpiresAt": "2099-01-01T00:00:00.000Z"}))
        return 0
    if "-p" in argv and "--json-schema" not in argv:
        os.execv(sys.executable, [sys.executable, str(HARNESS_FAKE), *argv])
    d = fake_dir()
    sc = scenario(d)
    with open(d / "calls.jsonl", "a") as log:
        log.write(json.dumps({"argv": argv, "cwd": os.getcwd(),
                              "env": {k: os.environ[k] for k in LOGGED_ENV if k in os.environ}}) + "\n")
    prompt = argv[-1]
    resume = arg(argv, "--resume")
    if sc.get("not_logged_in"):
        emit({"type": "result", "subtype": "error", "is_error": True, "result": "Not logged in · Please run /login"})
        return 1
    if resume and sc.get("session_gone"):
        print(f"No conversation found with session ID: {resume}", file=sys.stderr)
        return 1
    session = resume or str(uuid.uuid4())
    sessions = d / "sessions"
    sessions.mkdir(exist_ok=True)
    spath = sessions / f"{session}.json"
    seen = json.loads(spath.read_text()) if spath.exists() else []
    seen.append(prompt)
    spath.write_text(json.dumps(seen))
    model = arg(argv, "--model") or "opus"
    emit({"type": "system", "subtype": "init", "session_id": session, "model": model})
    if sc.get("rate_limit_info") is not None:
        emit({"type": "rate_limit_event", "session_id": session, "rate_limit_info": sc["rate_limit_info"]})
    emit({"type": "assistant", "session_id": session,
          "message": {"content": [{"type": "text", "text": f"Working on it ({len(seen)} messages in this session)."}]}})
    outputs = []
    for command in sc.get("commands") or []:
        emit({"type": "assistant", "session_id": session,
              "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": command}}]}})
        r = subprocess.run(command, shell=True, capture_output=True, text=True, env=os.environ)
        outputs.append((r.stdout + r.stderr).strip())
    if sc.get("sleep"):
        time.sleep(float(sc["sleep"]))
    total = int(sc["report"]) if "report" in sc else 100 * len(seen)
    usage = {"input": total // 2, "output": total - total // 2}
    last = prompt.strip().splitlines()[-1] if prompt.strip() else ""
    message = sc.get("message") or (
        f"Fake reply {len(seen)} ({len(seen)} messages seen in this session). Last line received: {last[:160]}"
        + ("".join(f"\n\n{o}" for o in outputs if o))
    )
    result = {
        "type": "result", "subtype": "success", "is_error": False, "session_id": session,
        "result": message, "num_turns": 1, "duration_ms": 10, "total_cost_usd": 0.001 * len(seen),
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "modelUsage": {f"claude-{model}": {"inputTokens": usage["input"], "outputTokens": usage["output"],
                                           "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}},
    }
    if not sc.get("no_structured_output"):
        result["structured_output"] = {"message": message, "status": sc.get("status") or "waiting_on_user",
                                       "title": sc.get("title") or "Fake task title"}
    emit({"type": "assistant", "session_id": session, "message": {"content": [{"type": "text", "text": message}]}})
    emit(result)
    return 0


def scenario_peek() -> dict:
    path = fake_dir() / "scenario.json"
    return json.loads(path.read_text()) if path.exists() else {}


if __name__ == "__main__":
    sys.exit(main())

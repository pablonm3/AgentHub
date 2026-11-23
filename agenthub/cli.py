"""`agenthub serve`, and the commands an AI user's session runs to reach the server.

Inside a session, `AGENTHUB_URL` and `AGENTHUB_TASK_TOKEN` say which server and which task:
`agenthub title "<text>"`, `agenthub search "<phrase>"`, `agenthub harness start|status|resume`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _call(method: str, path: str, body: dict | None = None) -> dict:
    url = os.environ.get("AGENTHUB_URL")
    token = os.environ.get("AGENTHUB_TASK_TOKEN")
    if not url or not token:
        raise SystemExit("agenthub: AGENTHUB_URL and AGENTHUB_TASK_TOKEN are not set; this command runs inside an AgentHub task")
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url.rstrip("/") + path, data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read()).get("message")
        except (json.JSONDecodeError, AttributeError):
            message = None
        raise SystemExit(f"agenthub: refused ({e.code}): {message or e.reason}")
    except urllib.error.URLError as e:
        raise SystemExit(f"agenthub: the AgentHub server at {url} does not answer: {e.reason}")


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app
    from .config import Config

    config = Config.from_env(port=args.port)
    app = create_app(config)
    print(f"AgentHub on {config.base_url}  (data: {config.data_dir}; Ctrl+C stops it)")
    uvicorn.run(app, host="127.0.0.1", port=config.port, log_level=args.log_level)
    return 0


def cmd_title(args: argparse.Namespace) -> int:
    out = _call("POST", "/internal/title", {"title": " ".join(args.text)})
    print(f"title: {out['title']}" + ("" if out["applied"] else " (kept: Pablo edited the title)"))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    phrase = " ".join(args.phrase)
    out = _call("GET", "/internal/search?" + urllib.parse.urlencode({"q": phrase}))
    if not out["hits"]:
        print(f"no ticket, comment or task chat contains {phrase!r}")
        return 0
    for hit in out["hits"]:
        ticket = hit["ticket"]
        where = f"{ticket['key']} \"{ticket['title']}\"" if ticket else "no ticket"
        line = f"- {hit['where']} · ticket {where}"
        task = hit["task"]
        if task:
            line += f" · task {task['id']} \"{task['title'] or '(untitled)'}\" ({task['ai_user']}, {task['status']})"
        print(line)
        print(f"  {hit['snippet']}")
        for t in hit["tasks_of_ticket"]:
            print(f"  attached task {t['id']} \"{t['title'] or '(untitled)'}\" ({t['ai_user']}, {t['status']})")
    return 0


def cmd_harness(args: argparse.Namespace) -> int:
    if args.action == "start":
        if not args.feature or not args.ticket_file:
            raise SystemExit("agenthub harness start needs --feature <kebab-name> and --ticket-file <path>")
        text = Path(args.ticket_file).read_text()
        out = _call("POST", "/internal/harness/start", {
            "feature": args.feature, "ticket_text": text, "project": args.project, "workflow": args.workflow,
        })
        print(f"run {out['run_id']} started; its files are in {out['run_dir']}. AgentHub watches it and tells you when it stops.")
    elif args.action == "status":
        runs = _call("GET", "/internal/harness/status")["runs"]
        if not runs:
            print("this task has started no harness run")
        for r in runs:
            print(f"- {r['run_id']} · {r['project']} · {r['status']} · step {r['current_step']} · "
                  f"pending {r['pending_kind'] or 'none'} · tokens {r['tokens']} · {r['run_dir']}")
            if r["decision_file"]:
                print(f"  decision file: {r['decision_file']}")
    else:
        if not args.run_id:
            raise SystemExit("agenthub harness resume needs a run id")
        out = _call("POST", "/internal/harness/resume", {"run_id": args.run_id})
        print(f"run {out['run_id']} resumed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agenthub", description="AgentHub server and the commands of an AI user's session")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="start the web app on 127.0.0.1")
    s.add_argument("--port", type=int, default=None, help="default AGENTHUB_PORT or 8787")
    s.add_argument("--log-level", default="warning")
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("title", help="set this task's title")
    s.add_argument("text", nargs="+")
    s.set_defaults(fn=cmd_title)
    s = sub.add_parser("search", help="search tickets, comments and task chats, archived tasks included")
    s.add_argument("phrase", nargs="+")
    s.set_defaults(fn=cmd_search)
    s = sub.add_parser("harness", help="start, inspect or resume a run of AgentHub's harness copy")
    s.add_argument("action", choices=["start", "status", "resume"])
    s.add_argument("run_id", nargs="?")
    s.add_argument("--feature")
    s.add_argument("--ticket-file")
    s.add_argument("--project", help="only for a task without a ticket; a ticket's task runs on the ticket's project")
    s.add_argument("--workflow", default="feature-v1")
    s.set_defaults(fn=cmd_harness)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

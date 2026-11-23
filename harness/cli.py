"""`agenthub-harness` command line: run | resume | status | obs | link | project | verify-auth."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .config import load_manifest, load_workflow, parse_override
from .link import link_worktree
from .naming import split_run_id
from .observability import Observability
from .orchestrator import Orchestrator
from .paths import Layout, layout_from_env
from .project import project_add, project_list
from .render import render
from .state import State


def _layout(args: argparse.Namespace) -> Layout:
    return layout_from_env(Path(args.root) if getattr(args, "root", None) else None)


def _refuse_inside_a_task(command: str, instead: str) -> bool:
    """An AI user's session starts and resumes runs through AgentHub, which checks the project rules
    and, at a gate, that Pablo replied; its environment carries the task token."""
    if not os.environ.get("AGENTHUB_TASK_TOKEN"):
        return False
    print(f"agenthub-harness {command}: not available inside an AgentHub task; use `{instead}` instead", file=sys.stderr)
    return True


# ------------------------------------------------------------------ commands
def cmd_run(args: argparse.Namespace) -> int:
    if _refuse_inside_a_task("run", "agenthub harness start"):
        return 2
    layout = _layout(args)
    overrides = dict(parse_override(s) for s in (args.set or []))
    orch = Orchestrator.start(layout, args.workflow, args.feature, overrides, quiet=args.quiet)
    if orch.state.status != "running":
        return 2
    status = orch.run()
    print(f"\nrun {orch.state.run_id}: {status}")
    return 0 if status in ("done", "paused", "waiting_on_human") else 1


def cmd_resume(args: argparse.Namespace) -> int:
    if _refuse_inside_a_task("resume", "agenthub harness resume <run-id>"):
        return 2
    layout = _layout(args)
    orch = Orchestrator.resume(layout, args.run_id, quiet=args.quiet)
    status = orch.run()
    print(f"\nrun {orch.state.run_id}: {status}")
    return 0 if status in ("done", "paused", "waiting_on_human") else 1


def _list_runs(layout: Layout) -> int:
    runs = sorted(p for p in layout.runs.iterdir() if (p / "state.json").is_file()) if layout.runs.is_dir() else []
    if not runs:
        print("no runs")
        return 0
    for p in runs:
        st = State.load(p / "state.json")
        print(f"{st.run_id:<28} {st.status:<17} step {st.current or '-':<3} iteration {st['iteration']}/{st['max_iterations']}  {st['workflow']}  started {st['started']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    layout = _layout(args)
    if not args.run_id:
        return _list_runs(layout)
    split_run_id(args.run_id)
    if args.log:
        step = str(args.log).zfill(2)
        logs = sorted(layout.run_log_dir(args.run_id).glob(f"{step}*.jsonl"))
        if not logs:
            print(f"no transcript for step {step}")
            return 1
        return subprocess.call(["tail", "-f", str(logs[-1])])
    while True:
        st = State.load(layout.state_file(args.run_id))
        wf = load_workflow(layout, st["workflow"])
        text = render(st, wf)
        if args.watch:
            print("\033[2J\033[H" + text)
            if st.status in ("done", "failed", "blocked"):
                return 0
            time.sleep(2)
        else:
            print(text)
            return 0


def cmd_obs(args: argparse.Namespace) -> int:
    layout = _layout(args)
    manifest = load_manifest(layout)
    obs = Observability(layout, manifest.observability)
    if args.action == "status":
        print(obs.status_text())
        return 0
    if args.action == "mcp-config":
        print(json.dumps(obs.mcp_config(), indent=2))
        return 0
    return 1


def cmd_link(args: argparse.Namespace) -> int:
    layout = _layout(args)
    manifest = load_manifest(layout)
    report = link_worktree(layout, manifest, args.project, Path(args.worktree).resolve(), codex=args.codex)
    for line in report:
        print(line)
    if not report:
        print("links already in place")
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    layout = _layout(args)
    if args.action == "add":
        project_add(layout, args.name, args.repo, args.base, no_chat=args.no_chat)
        return 0
    if args.action == "list":
        project_list(layout)
        return 0
    return 1


def cmd_verify_auth(args: argparse.Namespace) -> int:
    from .claude_runner import verify_account_auth

    layout = _layout(args)
    ok, detail = verify_account_auth(layout)
    print(("auth ok: " if ok else "auth FAILED: ") + detail)
    return 0 if ok else 1


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agenthub-harness", description="Coding harness orchestrator of AgentHub (docs/WORKFLOW_SPEC.md)")
    p.add_argument(
        "--root",
        help="where to look for the code root when HARNESS_ROOT is unset (default: the nearest harness.yaml); "
        "HARNESS_PRIVATE_ROOT and HARNESS_DATA_ROOT name the other two roots",
    )
    p.add_argument("--version", action="version", version=f"agenthub-harness {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run", help="start a run: agenthub-harness run <workflow> <feature>")
    s.add_argument("workflow")
    s.add_argument("feature")
    s.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a defaults.yaml value for this run")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("resume", help="resume a paused, failed or interrupted run")
    s.add_argument("run_id")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser("status", help="render a run (no run id: list runs)")
    s.add_argument("run_id", nargs="?")
    s.add_argument("--watch", action="store_true", help="redraw every 2 s")
    s.add_argument("--log", metavar="STEP", help="tail that step's transcript")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("obs", help="telemetry collector (external; never started by the harness)")
    s.add_argument("action", choices=["status", "mcp-config"])
    s.set_defaults(func=cmd_obs)

    s = sub.add_parser("link", help="link the skills and instructions into a worktree: link <project> <worktree>")
    s.add_argument("project")
    s.add_argument("worktree")
    s.add_argument("--codex", action="store_true", help="also create .agents/skills and AGENTS.md links")
    s.set_defaults(func=cmd_link)

    s = sub.add_parser("project", help="projects: add <name> --repo <url> --base <branch> | list")
    s.add_argument("action", choices=["add", "list"])
    s.add_argument("name", nargs="?")
    s.add_argument("--repo")
    s.add_argument("--base")
    s.add_argument("--no-chat", action="store_true", help="skip the onboard-project session")
    s.set_defaults(func=cmd_project)

    s = sub.add_parser("verify-auth", help="check the logged-in Claude credential works from a launched process")
    s.set_defaults(func=cmd_verify_auth)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "project" and args.action == "add" and not args.name:
        print("agenthub-harness project add <name> --repo <git url> --base <branch>")
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

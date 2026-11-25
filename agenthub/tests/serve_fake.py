"""Fake mode: the app on a temp data folder and a temp clone of the private folder, with fake
`claude` and fake `gh`, so nothing reaches Claude, GitHub or `AgentHub-private`.

    uv run python -m agenthub.tests.serve_fake --port 8799

The temp folder is deleted when the server stops. The pytest fixtures build their folders with
`build_fake_environment` too.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FAKE_CLAUDE = HERE / "fake_claude.py"
FAKE_GH = HERE / "fake_gh.py"

DEMO_AGENTS_MD = """# demo — instructions for agents

## How to run the app and check a change

`python -m demo`.

## How to run tests

`pytest`.

## How to run evals or regression suites

none

## Companion repos and tools

none

## Secrets and config

none

## Data access rules

none

## Branching rules

Base branch `main`.
"""


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", "-c", "user.name=AgentHub test", "-c", "user.email=test@example.invalid", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def make_bare_repo(path: Path, files: dict[str, str], branch: str = "main") -> Path:
    """A bare repository with one commit holding `files`."""
    work = path.with_name(path.name + ".work")
    work.mkdir(parents=True)
    _git("init", "-q", "-b", branch, str(work))
    for rel, text in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    _git("add", "-A", cwd=work)
    _git("commit", "-q", "-m", "initial", cwd=work)
    _git("clone", "-q", "--bare", str(work), str(path))
    shutil.rmtree(work)
    return path


def synthetic_private(base: Path, project_remote: Path) -> Path:
    """A private-folder remote with two projects: `demo` (ready) and `draft` (its AGENTS.md is the template)."""
    from harness.project import agents_template

    manifest = (
        "observability: external\n"
        "projects:\n"
        f"  demo:\n    repo: {project_remote}\n    default_base: main\n"
        "    agentsmd: agentmds/demo/AGENTS.md\n    skills: skills/projects/demo\n    setup: []\n"
        f"  draft:\n    repo: {project_remote}\n    default_base: main\n"
        "    agentsmd: agentmds/draft/AGENTS.md\n    skills: skills/projects/draft\n    setup: []\n"
    )
    return make_bare_repo(base / "private-remote.git", {
        "README.md": "# private (test)\n",
        "agents.md": "# private folder rules (test)\n\nEvery change here is committed and pushed to main.\n",
        "harness.yaml": manifest,
        "agentmds/demo/AGENTS.md": DEMO_AGENTS_MD,
        "agentmds/draft/AGENTS.md": agents_template("draft"),
        "skills/projects/demo/.gitkeep": "",
        "skills/projects/draft/.gitkeep": "",
        "skills/agents/.gitkeep": "",
    })


def _executable(path: Path) -> str:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def build_fake_environment(base: Path, private_source: Path | None = None) -> dict[str, str]:
    """Temp data folder, private clone with a temp bare `origin`, fake dirs; returns the variables to set.

    With `private_source` (a checkout of the private folder) its committed content is cloned, so the
    project dropdown shows its projects; without it a synthetic private folder is made.
    """
    base.mkdir(parents=True, exist_ok=True)
    if private_source is not None and (private_source / ".git").exists():
        remote = base / "private-remote.git"
        _git("clone", "-q", "--bare", str(private_source), str(remote))
    else:
        project_remote = make_bare_repo(base / "demo-remote.git", {"README.md": "# demo\n"})
        remote = synthetic_private(base, project_remote)
    private = base / "private"
    _git("clone", "-q", str(remote), str(private))
    for name in ("fake-claude", "fake-gh", "data"):
        (base / name).mkdir(exist_ok=True)
    (base / "fake-claude" / "harness_scenario.json").write_text("{}")  # the harness's fake, for run steps
    return {
        "AGENTHUB_DATA_DIR": str(base / "data"),
        "AGENTHUB_PRIVATE_DIR": str(private),
        "AGENTHUB_CLAUDE_BIN": _executable(FAKE_CLAUDE),
        "AGENTHUB_GH_BIN": _executable(FAKE_GH),
        "AGENTHUB_FAKE_DIR": str(base / "fake-claude"),
        "AGENTHUB_FAKE_GH_DIR": str(base / "fake-gh"),
        "FAKE_CLAUDE_SCENARIO": str(base / "fake-claude" / "harness_scenario.json"),
    }


def default_scenario() -> dict:
    """What fake mode's `claude` reports: the `rate_limit_event` of a real `fable` session, Week 22% and
    Fable week 37% used, both resetting 4 days after the start."""
    resets_at = int(time.time()) + 4 * 86400
    windows = {
        "seven_day": {"utilization": 0.22, "resetsAt": resets_at, "status": "allowed"},
        "seven_day_overage_included": {"utilization": 0.37, "resetsAt": resets_at, "status": "allowed"},
    }
    return {"rate_limit_info": {"status": "allowed", "resetsAt": resets_at, "rateLimitType": "seven_day",
                                "overageStatus": "rejected", "isUsingOverage": False, "unifiedWindows": windows}}


def main() -> int:
    p = argparse.ArgumentParser(description="AgentHub in fake mode (fake claude, fake gh, temp data and private folders)")
    p.add_argument("--port", type=int, default=8799)
    p.add_argument("--private", default=str(REPO / "private"), help="private-folder checkout to clone (default: private/)")
    args = p.parse_args()
    base = Path(tempfile.mkdtemp(prefix="agenthub-fake-"))
    try:
        env = build_fake_environment(base, Path(args.private))
        (base / "fake-claude" / "scenario.json").write_text(json.dumps(default_scenario(), indent=2))
        os.environ.update(env)
        os.environ["AGENTHUB_PORT"] = str(args.port)
        import uvicorn

        from agenthub.api import create_app
        from agenthub.config import Config

        config = Config.from_env(port=args.port)
        print(f"AgentHub (fake mode) on {config.base_url}; temp folder {base} is deleted on Ctrl+C")
        uvicorn.run(create_app(config), host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

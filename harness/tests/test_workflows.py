"""Every workflow directory of the repo, and one fake run of `research-v1`.

The completeness check reads the repo's own `workflows/` and `skills/general/`. The fake run builds a
scratch harness root with `workflows/research-v1` copied in, starts it through the CLI with all three
roots pointed at the scratch root, and runs it with the fake `claude` (no API calls, temp data only).
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from harness import cli
from harness.config import load_workflow
from harness.paths import Layout
from harness.state import State

REPO = Path(__file__).resolve().parents[2]
FAKE = Path(__file__).resolve().parent / "fake_claude.py"
WORKFLOWS = sorted(p.parent.name for p in (REPO / "workflows").glob("*/workflow.yaml"))
TEMPLATE_RE = re.compile(r"\$\{templates\}/([\w.-]+)")


def _git(args, cwd) -> str:
    out = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                         cwd=cwd, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def _bare_remote(tmp_path: Path) -> Path:
    """A bare remote on branch `dev` whose repo holds a README and a pyproject.toml."""
    seed, remote = tmp_path / "seed", tmp_path / "remote.git"
    seed.mkdir()
    (seed / "README.md").write_text("demo\n")
    (seed / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = []\n')
    _git(["init", "-q", "-b", "dev"], seed)
    _git(["add", "."], seed)
    _git(["commit", "-q", "-m", "init"], seed)
    _git(["clone", "-q", "--bare", str(seed), str(remote)], tmp_path)
    return remote


def _scratch_harness(r: Path, remote: Path) -> None:
    """Lay out and commit a harness root at `r`: research-v1, project `demo` on `remote`, and a ticket."""
    for d in ("tickets", "runs", "workflow_logs", "archived", "agentmds/demo", "skills/general", "skills/projects/demo"):
        (r / d).mkdir(parents=True)
    shutil.copytree(REPO / "workflows" / "research-v1", r / "workflows" / "research-v1")
    (r / "harness.yaml").write_text(
        "observability: off\nprojects:\n  demo:\n"
        f"    repo: {remote}\n    default_base: dev\n    agentsmd: agentmds/demo/AGENTS.md\n"
        "    skills: skills/projects/demo\n    setup:\n      - echo ok > .setup_ok\n"
    )
    (r / "agentmds" / "demo" / "AGENTS.md").write_text("# demo\n\nRun tests with `true`.\n")
    (r / "tickets" / "demo-topic.md").write_text(
        "---\nproject: demo\nbase_branch: dev\n---\n# Queue waiting times\n\n"
        "## Questions\n1. What is the mean wait of an M/M/1 queue at load 0.8?\n2. How does it grow as the load nears 1?\n"
    )
    _git(["init", "-q"], r)
    _git(["add", "."], r)
    _git(["commit", "-q", "-m", "scratch harness"], r)


@pytest.fixture
def research_root(tmp_path, monkeypatch):
    """A scratch harness root holding research-v1, a project `demo` whose repo has a dependency file, and a ticket."""
    r = tmp_path / "harness"
    _scratch_harness(r, _bare_remote(tmp_path))

    # inside a harness step the three roots point at the live harness: all three must move to the scratch root
    for var in ("HARNESS_ROOT", "HARNESS_PRIVATE_ROOT", "HARNESS_DATA_ROOT"):
        monkeypatch.setenv(var, str(r))
    monkeypatch.delenv("AGENTHUB_TASK_TOKEN", raising=False)
    monkeypatch.setenv("HARNESS_CLAUDE_BIN", str(FAKE))
    monkeypatch.setenv("HARNESS_NO_NOTIFY", "1")
    monkeypatch.setenv("HARNESS_NO_TELEMETRY", "1")
    os.chmod(FAKE, 0o755)
    return r


def _launch_model(run_dir: Path, step: str) -> str:
    argv = json.loads((run_dir / "log" / f"{step}.jsonl").read_text().splitlines()[0])["argv"]
    return argv[argv.index("--model") + 1]


def test_research_run_goes_through_its_three_steps_and_ends_done(research_root):
    # Constraint: `agenthub-harness run research-v1` runs 20 → 21 → 22 → 18 after the start step with fable, opus, fable,
    #             stops at no gate, and leaves the project with no commit, no pushed branch and no changed tracked file.
    # Input: a ticket with two questions on a project whose repo holds a pyproject.toml; the CLI with the fake `claude`
    # Expected output: exit 0; state done; executions 2, 20, 21, 22, 18; no gate; the three models in order; research
    #                  context, answers and final report written; the run log names the report; worktree clean, 0 commits
    assert cli.main(["run", "research-v1", "demo-topic", "--quiet"]) == 0
    layout = Layout(research_root)
    st = State.load(layout.state_file("demo-topic_1"))
    assert st.status == "done", st.get("error")
    assert st["workflow"] == "research-v1"
    assert [e["step"] for e in st["executions"]] == ["2", "20", "21", "22", "18"]
    assert not st.get("gates")
    run_dir = layout.run_dir("demo-topic_1")
    assert [_launch_model(run_dir, s) for s in ("20", "21", "22")] == ["fable", "opus", "fable"]
    for name in ("research_context", "answers", "final_report"):
        assert (run_dir / f"{name}_demo-topic_1.md").is_file(), name
    log = layout.workflow_log("demo-topic_1").read_text()
    assert "status     done" in log
    assert "final_report_demo-topic_1.md" in log

    worktree = layout.worktree("demo", "demo-topic_1")
    assert (worktree / ".setup_ok").exists()
    assert _git(["rev-list", "--count", "origin/dev..HEAD"], worktree) == "0"
    assert _git(["status", "--porcelain", "--untracked-files=no"], worktree) == ""
    assert _git(["branch", "--list", "demo-topic_1"], research_root.parent / "remote.git") == ""


@pytest.mark.parametrize("name", WORKFLOWS)
def test_a_workflow_names_only_prompts_skills_and_templates_that_exist(name):
    # Constraint: a workflow directory is complete: every prompt file, skill and template it names exists, and every
    #             step is in a group. A fake run cannot catch a missing skill or template; this does.
    # Input: one directory of the repo's workflows/ (each of them in turn)
    # Expected output: no prompt file, skill folder or template is missing, and no step is outside the groups
    wf = load_workflow(Layout(REPO), name)
    prompts = [wf.raw.get(k) for k in ("setup_chat_prompt", "continue_prompt")]
    prompts += [p for s in wf.steps for p in (s.prompt, s.incremental_prompt, s.chat_prompt)]
    prompts = [p for p in prompts if p]
    assert [p for p in prompts if not (wf.dir / p).is_file()] == []

    skills = {k for s in wf.steps for k in (s.skill, s.chat_skill) if k}
    assert sorted(k for k in skills if not (REPO / "skills" / "general" / k / "SKILL.md").is_file()) == []

    templates = {t for p in prompts for t in TEMPLATE_RE.findall((wf.dir / p).read_text())}
    assert sorted(t for t in templates if not (wf.dir / "templates" / t).is_file()) == []

    grouped = {sid for g in wf.groups for sid in g.steps}
    assert [s.id for s in wf.steps if s.id not in grouped] == []


def test_research_workflow_cannot_pause_commit_or_push():
    # Constraint: research-v1 never waits on the human, never commits and never pushes, and no output's content can
    #             route the run, so a failed simulation cannot end it anywhere but done.
    # Input: the repo's workflows/research-v1/workflow.yaml
    # Expected output: no step with a gate, writes_commit, a push action, on_status or on_decision; the AI steps are
    #                  research-context, research-answers, research-report, in that order
    wf = load_workflow(Layout(REPO), "research-v1")
    assert [s.id for s in wf.steps if s.gate or s.writes_commit or s.action == "push_branch" or s.on_status or s.on_decision] == []
    assert [s.skill for s in wf.steps if s.actor == "ai"] == ["research-context", "research-answers", "research-report"]

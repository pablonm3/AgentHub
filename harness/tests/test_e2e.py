"""End-to-end runs of the orchestrator against a fake `claude` and a local git project.

No API calls, no Docker, no notifications. Each test builds a scratch harness root with the
real feature-v1 workflow copied in. Most tests answer gates and questions in the terminal chat
(`on_question: chat`, CHAT); the tests of the AgentHub flow pause, record the answer in the
decision file and release gates with HARNESS_GATE_RELEASE.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from harness import cli
from harness.config import load_workflow
from harness.naming import highest_version, read_frontmatter
from harness.orchestrator import Orchestrator, pending_question
from harness.paths import Layout
from harness.render import render
from harness.state import State

HARNESS_ROOT = Path(__file__).resolve().parents[2]
FAKE = Path(__file__).resolve().parent / "fake_claude.py"
CHAT = {"on_question": "chat"}  # gates and questions open the (fake) terminal chat instead of pausing
TOKENS_1000 = {"input": 5, "output": 145, "cache_creation": 250, "cache_read": 600}  # fake_claude.model_usage()


def _git(args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True, capture_output=True)


def _remote(tmp_path: Path) -> Path:
    """A "remote" repo with a dev branch."""
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "README.md").write_text("demo\n")
    _git(["init", "-q", "-b", "dev"], seed)
    _git(["add", "."], seed)
    _git(["commit", "-q", "-m", "init"], seed)
    _git(["clone", "-q", "--bare", str(seed), str(remote)], tmp_path)
    return remote


@pytest.fixture
def root(tmp_path, monkeypatch):
    remote = _remote(tmp_path)
    r = tmp_path / "harness"
    for d in ("tickets", "runs", "workflow_logs", "archived", "agentmds/demo", "skills/general", "skills/projects/demo", "observability"):
        (r / d).mkdir(parents=True)
    shutil.copytree(HARNESS_ROOT / "workflows" / "feature-v1", r / "workflows" / "feature-v1")
    (r / "harness.yaml").write_text(
        "observability: off\nprojects:\n  demo:\n"
        f"    repo: {remote}\n    default_base: dev\n    agentsmd: agentmds/demo/AGENTS.md\n"
        "    skills: skills/projects/demo\n    setup:\n      - echo ok > .setup_ok\n"
    )
    (r / "agentmds" / "demo" / "AGENTS.md").write_text("# demo\n\nRun tests with `true`.\n")
    (r / "tickets" / "demo-feat.md").write_text("---\nproject: demo\nbase_branch: dev\n---\n# Demo feature\n\nDo the thing.\n")
    _git(["init", "-q"], r)
    _git(["add", "."], r)
    _git(["commit", "-q", "-m", "scratch harness"], r)

    monkeypatch.setenv("HARNESS_CLAUDE_BIN", str(FAKE))
    monkeypatch.setenv("HARNESS_NO_NOTIFY", "1")
    monkeypatch.setenv("HARNESS_NO_TELEMETRY", "1")
    os.chmod(FAKE, 0o755)
    return r


def _scenario(root: Path, monkeypatch, data: dict) -> None:
    p = root / "scenario.json"
    p.write_text(json.dumps(data))
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", str(p))


def _run(root: Path, overrides=None) -> State:
    layout = Layout(root)
    orch = Orchestrator.start(layout, "feature-v1", "demo-feat", {**CHAT, **(overrides or {})}, quiet=True)
    orch.run()
    return State.load(layout.state_file("demo-feat_1"))


def _project_defaults(root: Path, values: dict) -> None:
    """Give the demo project a `defaults` block in the scratch harness.yaml."""
    manifest = root / "harness.yaml"
    block = "".join(f"      {key}: {value}\n" for key, value in values.items())
    manifest.write_text(manifest.read_text() + "    defaults:\n" + block)


def _commits(root: Path) -> int:
    wt = root / "worktrees" / "demo" / "demo-feat_1"
    out = subprocess.run(["git", "rev-list", "--count", "origin/dev..HEAD"], cwd=wt, capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def _head(root: Path) -> str:
    wt = root / "worktrees" / "demo" / "demo-feat_1"
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True, check=True).stdout.strip()


def _remote_sha(root: Path) -> str | None:
    """Commit of the run's branch on the remote, None when the branch was never pushed."""
    out = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "refs/heads/demo-feat_1"],
        cwd=root.parent / "remote.git", capture_output=True, text=True,
    )
    return out.stdout.strip() or None


def test_happy_path(root, monkeypatch):
    # Constraint: a run with no failures goes through every step once and ends done with a run log.
    # Input: triage decides done, gates change nothing
    # Expected output: status done, iteration 1, one execution per AI step, 3 commits, artifacts and log present
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root)
    assert st.status == "done", st.get("error")
    assert st["iteration"] == 1
    run_dir = root / "runs" / "demo-feat_1"
    for name in ["ticket", "context", "spec", "plan", "plan_short", "testing", "review", "readability", "reviews_applied", "testing_feedback", "testing_feedback_ui", "decision", "regression_report", "langsmith_cleanup", "final_report"]:
        matches = list(run_dir.glob(f"{name}_demo-feat_1*.md"))
        assert matches, f"missing {name}"
    assert (run_dir / "explain_diff_demo-feat_1.html").exists()
    assert (run_dir / "regression_demo-feat_1.csv").read_text().startswith("suite,cases,repetitions,acc_baseline")
    assert (run_dir / "decision_demo-feat_1_v1.md").exists()
    assert (run_dir / "log" / "04.jsonl").exists()
    assert (run_dir / "log" / "02-setup.txt").exists()
    assert (root / "worktrees" / "demo" / "demo-feat_1" / ".setup_ok").exists()
    assert (root / "worktrees" / "demo" / "demo-feat_1" / "CLAUDE.md").read_text().strip().endswith("agentmds/demo/AGENTS.md")
    assert _commits(root) == 3  # build-plan, apply-reviews, fix_ai_comments
    log = (root / "workflow_logs" / "demo-feat_1.log").read_text()
    assert "status     done" in log
    assert "final_report_demo-feat_1.md" in log
    assert "── 14  triage" in log
    assert st.step("10")["outcome"] == "1 high, 2 medium"
    assert st.step("13")["outcome"] == "10/10 pass"
    assert st.step("13b")["outcome"] == "no UI cases"
    assert (run_dir / "log" / "13b.jsonl").exists()
    # step 13b gets the Playwright MCP server, its output dir resolved into the run log; no other step gets one
    mcp = json.loads((run_dir / "log" / "mcp_13b.json").read_text())["mcpServers"]["playwright"]
    assert mcp["args"][-1] == f"{run_dir}/log/playwright_13b_iter1"
    launch = json.loads((run_dir / "log" / "13b.jsonl").read_text().splitlines()[0])["argv"]
    assert launch[launch.index("--mcp-config") + 1] == str(run_dir / "log" / "mcp_13b.json")
    assert sorted(p.name for p in (run_dir / "log").glob("mcp_*.json")) == ["mcp_13b.json"]
    assert st.step("15b")["outcome"] == "no eval suites to compare"
    assert (run_dir / "log" / "15b.jsonl").exists()
    assert st.step("15c")["outcome"] == "0 scratch datasets deleted"
    assert "7" in st["gates"] and st["gates"]["7"][0]["released"]
    assert "19" in st["gates"]
    # every AI step execution keeps its session's tokens next to its cost
    assert st.executions_of("4")[0]["tokens"] == TOKENS_1000
    assert all(e["tokens"] == TOKENS_1000 for e in st["executions"] if e.get("transcript"))


def test_branch_is_pushed_before_gate2(root, monkeypatch):
    # Constraint: step 18b pushes the feature branch to origin before the run stops at GATE 2, and not earlier.
    # Input: on_question pause; one resume past GATE 1, so the run pauses again at GATE 2
    # Expected output: nothing on the remote at GATE 1; at GATE 2 (reached, not released) the remote branch is
    #                  at the worktree HEAD, the local branch tracks it, step 18b is done with the pushed commit
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root, {"on_question": "pause"})
    assert st.current == "7"
    assert _remote_sha(root) is None
    layout = Layout(root)
    _record_answer(root, st)
    _release_gate(monkeypatch, st)
    Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "paused" and st.current == "19", st.get("error")
    assert st["gates"]["19"][0]["released"] is None
    assert _remote_sha(root) == _head(root)
    upstream = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "demo-feat_1@{upstream}"],
        cwd=root / "worktrees" / "demo" / "demo-feat_1", capture_output=True, text=True, check=True,
    )
    assert upstream.stdout.strip() == "origin/demo-feat_1"
    assert st.step("18b")["status"] == "done"
    prefix, sha = st.step("18b")["outcome"].rsplit(" ", 1)
    assert prefix == "pushed origin/demo-feat_1 at"
    assert _head(root).startswith(sha)


def test_push_never_skips_step_18b(root, monkeypatch):
    # Constraint: defaults.push: never skips step 18b; the run still finishes and the remote gets no branch.
    # Input: triage decides done, override push=never
    # Expected output: status done, step 18b skipped, no demo-feat_1 branch on the remote
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root, {"push": "never"})
    assert st.status == "done", st.get("error")
    assert st.step("18b")["status"] == "skipped"
    assert _remote_sha(root) is None


def test_failed_push_fails_run_then_resume_retries(root, monkeypatch):
    # Constraint: a push git rejects fails the run at step 18b, before GATE 2; resume retries the push.
    # Input: origin's push URL points at a missing repository during the run, then is restored
    # Expected output: status failed at 18b with git's message and no gate 19; after resume status done,
    #                  step 18b executed twice, the remote branch at the worktree HEAD
    _scenario(root, monkeypatch, {"triage": ["done"]})
    layout = Layout(root)
    orch = Orchestrator.start(layout, "feature-v1", "demo-feat", dict(CHAT), quiet=True)
    base = layout.base_clone("demo")
    _git(["remote", "set-url", "--push", "origin", str(root / "no-such-remote.git")], base)
    orch.run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "failed"
    assert st.current == "18b"
    assert "git push" in st["error"] and "no-such-remote.git" in st["error"]
    assert st.step("18b")["status"] == "failed"
    assert "19" not in st["gates"]
    assert _remote_sha(root) is None
    _git(["config", "--unset", "remote.origin.pushurl"], base)
    Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "done", st.get("error")
    assert st.execution_count("18b") == 2
    assert _remote_sha(root) == _head(root)


def test_rejects_unknown_push_value(root):
    # Constraint: defaults.push accepts only always|never; anything else stops the run before it is created.
    # Input: override push=sometimes
    # Expected output: SystemExit naming defaults.push, no run folder
    with pytest.raises(SystemExit, match="defaults.push"):
        Orchestrator.start(Layout(root), "feature-v1", "demo-feat", {"push": "sometimes"}, quiet=True)
    assert not (root / "runs" / "demo-feat_1").exists()


def test_regression_never_skips_step_15b(root, monkeypatch):
    # Constraint: defaults.regression: never skips step 15b; the run still finishes and writes no regression files.
    # Input: triage decides done, override regression=never
    # Expected output: status done, step 15b skipped, no regression_* file, final report present
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root, {"regression": "never"})
    assert st.status == "done", st.get("error")
    assert st.step("15b")["status"] == "skipped"
    run_dir = root / "runs" / "demo-feat_1"
    assert not list(run_dir.glob("regression_*"))
    assert list(run_dir.glob("final_report_demo-feat_1*.md"))


def test_project_defaults_skip_step_15c(root, monkeypatch):
    # Constraint: a tunable in the project's `defaults` block of harness.yaml applies to its runs;
    #             langsmith_cleanup: never skips step 15c and the run still finishes.
    # Input: triage decides done, the project has langsmith_cleanup: never, no per-run override
    # Expected output: status done, step 15c skipped, no langsmith_cleanup_* file, final report present
    _scenario(root, monkeypatch, {"triage": ["done"]})
    _project_defaults(root, {"langsmith_cleanup": "never"})
    st = _run(root)
    assert st.status == "done", st.get("error")
    assert st.step("15c")["status"] == "skipped"
    run_dir = root / "runs" / "demo-feat_1"
    assert not list(run_dir.glob("langsmith_cleanup_*"))
    assert list(run_dir.glob("final_report_demo-feat_1*.md"))


def test_run_override_wins_over_project_defaults(root, monkeypatch):
    # Constraint: a per-run override wins over the project's `defaults` block.
    # Input: triage decides done, the project has langsmith_cleanup: never, override langsmith_cleanup=always
    # Expected output: status done, step 15c executed once, its report present
    _scenario(root, monkeypatch, {"triage": ["done"]})
    _project_defaults(root, {"langsmith_cleanup": "never"})
    st = _run(root, {"langsmith_cleanup": "always"})
    assert st.status == "done", st.get("error")
    assert st.execution_count("15c") == 1
    assert list((root / "runs" / "demo-feat_1").glob("langsmith_cleanup_demo-feat_1*.md"))


def test_rejects_unknown_langsmith_cleanup_value(root):
    # Constraint: langsmith_cleanup accepts only always|never, also when the value comes from the project's
    #             `defaults` block; anything else stops the run before it is created.
    # Input: the project has langsmith_cleanup: sometimes
    # Expected output: SystemExit naming defaults.langsmith_cleanup, no run folder
    _project_defaults(root, {"langsmith_cleanup": "sometimes"})
    with pytest.raises(SystemExit, match="defaults.langsmith_cleanup"):
        Orchestrator.start(Layout(root), "feature-v1", "demo-feat", {}, quiet=True)
    assert not (root / "runs" / "demo-feat_1").exists()


def test_loop_then_cap_chat_writes_plan(root, monkeypatch):
    # Constraint: new_plan loops back to build with a new plan version; at the cap a chat opens and a plan
    #             written in the chat re-enters at build without resetting the iteration.
    # Input: max_iterations 2, triage new_plan, new_plan, done; cap chat writes a plan
    # Expected output: iteration 2, plan versions up to v4, build-plan executed 3 times, status done
    _scenario(root, monkeypatch, {"triage": ["new_plan", "new_plan", "done"], "chat": {"14": "write_plan"}})
    st = _run(root, {"max_iterations": 2})
    assert st.status == "done", st.get("error")
    assert st["iteration"] == 2
    run_dir = root / "runs" / "demo-feat_1"
    assert highest_version(run_dir / "plan_demo-feat_1.md") == 4  # v2, v3 by triage; v4 by the cap chat
    assert st.execution_count("9") == 3
    assert st.execution_count("14") == 3
    assert (run_dir / "review_demo-feat_1_v3.md").exists()
    assert (run_dir / "decision_demo-feat_1_v3.md").exists()
    # the cap chat's decision file is v3 (written by the chat, after triage's v2)
    log = (root / "workflow_logs" / "demo-feat_1.log").read_text()
    assert "(iter 2)" in log


def _step_prompt(root: Path, step: str, execution: int) -> str:
    """The prompt the fake claude received for one execution of a step."""
    return (root / "prompts" / f"{step}_{execution}.txt").read_text()


def test_repeated_review_covers_only_the_commits_since_the_last_one(root, monkeypatch):
    # Constraint: a code review repeated by the build loop is incremental: it compares against the commit the
    #             last finished review covered and gets that review's report as an input.
    # Input: triage new_plan then done; share limit 1.0, because the fake commits are one line each
    # Expected output: review 1 covers the whole branch; review 2 is incremental since review 1's commit, over the
    #                  2 commits (apply-reviews, second build) of 1 line each, with review v1 named in its prompt
    _scenario(root, monkeypatch, {"triage": ["new_plan", "done"]})
    st = _run(root, {"review_incremental_max_share": 1.0})
    assert st.status == "done", st.get("error")
    first, second = st.executions_of("10")
    assert first["scope"]["kind"] == "full"
    assert second["scope"]["kind"] == "incremental"
    assert second["scope"]["since"] == first["scope"]["head"]
    report_v1 = str(root / "runs" / "demo-feat_1" / "review_demo-feat_1.md")
    whole_branch_prompt = _step_prompt(root, "10", 1)
    assert "Comparison ref: `origin/dev`" in whole_branch_prompt
    assert "previous_report" not in whole_branch_prompt
    incremental_prompt = _step_prompt(root, "10", 2)
    assert f"Comparison ref: the commit `{first['scope']['head']}`" in incremental_prompt
    assert f"- previous_report: {report_v1}" in incremental_prompt
    assert "2 commit(s) changed 2 line(s)" in incremental_prompt
    assert "${" not in incremental_prompt
    assert report_v1.removeprefix(str(root) + "/") in second["in"]
    assert second["outcome"] == f"1 high, 2 medium · incremental since {first['scope']['head'][:8]}"


@pytest.mark.parametrize(
    "overrides, reason_start",
    [
        ({"review_incremental_max_lines": 1}, "2 lines changed since the last review"),
        ({"review_scope": "full"}, "defaults.review_scope: full"),
    ],
)
def test_repeated_review_covers_the_whole_branch_when_incremental_is_ruled_out(root, monkeypatch, overrides, reason_start):
    # Constraint: a repeated review goes back to the whole branch when more lines changed since the last review
    #             than the limit allows, and when the run sets review_scope to full.
    # Input: triage new_plan then done; share limit 1.0 with (a) a line limit of 1 against a 2-line change,
    #        (b) review_scope full
    # Expected output: review 2 has scope full with the reason recorded and gets the whole-branch prompt
    _scenario(root, monkeypatch, {"triage": ["new_plan", "done"]})
    st = _run(root, {"review_incremental_max_share": 1.0, **overrides})
    assert st.status == "done", st.get("error")
    second = st.executions_of("10")[1]
    assert second["scope"]["kind"] == "full"
    assert second["scope"]["reason"].startswith(reason_start)
    assert "Comparison ref: `origin/dev`" in _step_prompt(root, "10", 2)
    assert second["outcome"] == "1 high, 2 medium"


def test_review_after_a_new_spec_version_covers_the_whole_branch(root, monkeypatch):
    # Constraint: a new spec version changes the requirements checklist, so the next review covers the whole
    #             branch however small the change since the last one.
    # Input: triage spec_issue then done; the chat at 14 writes spec v2; share limit 1.0
    # Expected output: review 2 has scope full and its reason names both spec versions
    _scenario(root, monkeypatch, {"triage": ["spec_issue", "done"], "chat": {"14": "write_spec"}})
    st = _run(root, {"review_incremental_max_share": 1.0})
    assert st.status == "done", st.get("error")
    second = st.executions_of("10")[1]
    assert second["scope"]["kind"] == "full"
    assert second["scope"]["reason"] == "the spec changed since the last review: v1 → v2"


def test_rejects_unknown_review_scope_value(root):
    # Constraint: defaults.review_scope accepts only incremental|full; anything else stops the run before it is created.
    # Input: override review_scope=partial
    # Expected output: SystemExit naming defaults.review_scope, no run folder
    with pytest.raises(SystemExit, match="defaults.review_scope"):
        Orchestrator.start(Layout(root), "feature-v1", "demo-feat", {"review_scope": "partial"}, quiet=True)
    assert not (root / "runs" / "demo-feat_1").exists()


def test_spec_issue_chat_rewrites_spec(root, monkeypatch):
    # Constraint: a spec written in a question chat re-enters at plan, reaches GATE 1 again and resets the loop.
    # Input: triage spec_issue then done; chat at 14 writes a new spec version
    # Expected output: spec v2 exists, plan v2 exists, spec_revisions 1, gate 7 reached twice, status done
    _scenario(root, monkeypatch, {"triage": ["spec_issue", "done"], "chat": {"14": "write_spec"}})
    st = _run(root)
    assert st.status == "done", st.get("error")
    run_dir = root / "runs" / "demo-feat_1"
    assert (run_dir / "spec_demo-feat_1_v2.md").exists()
    assert (run_dir / "plan_demo-feat_1_v2.md").exists()
    assert (run_dir / "testing_demo-feat_1_v2.md").exists()  # test cases regenerated after a spec change
    assert st["spec_revisions"] == 1
    assert st["iteration"] == 1
    assert len(st["gates"]["7"]) == 2
    assert st.execution_count("6") == 2


def test_not_reproduced_answer_reruns_context(root, monkeypatch):
    # Constraint: build-context not_reproduced opens a chat; an answer without file changes re-runs the step
    #             with the answer injected, writing context v2.
    # Input: context_status not_reproduced then reproduced; chat at 4 answers
    # Expected output: context v2 exists, decision v1 answered, status done
    _scenario(root, monkeypatch, {"context_status": ["not_reproduced", "reproduced"], "chat": {"4": "answer"}, "triage": ["done"]})
    st = _run(root)
    assert st.status == "done", st.get("error")
    run_dir = root / "runs" / "demo-feat_1"
    assert (run_dir / "context_demo-feat_1_v2.md").exists()
    assert "answered: true" in (run_dir / "decision_demo-feat_1_v1.md").read_text()
    assert st.execution_count("4") == 2
    assert st["injected_answer"] is None


def _record_answer(root: Path, st: State, answer: str = "Approved, continue.") -> None:
    """What an AI user does with the human's answer: fill in the orchestrator's question file."""
    p = root / st["pending_chat"]["decision_file"]
    question, _ = p.read_text().split("## Answer")
    assert "answered: false" in question
    p.write_text(question.replace("answered: false", "answered: true") + f"## Answer\n\n{answer}\n\n## Approved edits\n\nnone\n")


def _release_gate(monkeypatch, st: State) -> None:
    """What AgentHub does once the human replied at a gate: name its decision file in HARNESS_GATE_RELEASE."""
    monkeypatch.setenv("HARNESS_GATE_RELEASE", Path(st["pending_chat"]["decision_file"]).name)


def test_pause_mode_records_the_question_and_resume_keeps_an_unanswered_one_paused(root, monkeypatch):
    # Constraint: with on_question: pause a question stops the run with the question recorded, and resume never
    #             opens a terminal chat: without a recorded answer the run stays paused on the same question.
    # Input: on_question pause; build-context not_reproduced; two resumes with the decision file left unanswered
    # Expected output: paused at step 4 with decision v1 holding the question, kind question, answered false;
    #                  after each resume still paused at 4, the same pending question, step 4 run once, no chat
    _scenario(root, monkeypatch, {"context_status": ["not_reproduced", "reproduced"], "triage": ["done"]})
    st = _run(root, {"on_question": "pause"})
    assert (st.status, st.current) == ("paused", "4")
    decision = root / "runs" / "demo-feat_1" / "decision_demo-feat_1_v1.md"
    assert st["pending_chat"]["decision_file"] == "runs/demo-feat_1/decision_demo-feat_1_v1.md"
    fm = read_frontmatter(decision)
    assert (fm["kind"], fm["answered"]) == ("question", False)
    assert "Which filter value reproduces the issue?" in decision.read_text()
    _forbid_chats(monkeypatch)
    layout = Layout(root)
    for _ in range(2):
        Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
        after = State.load(layout.state_file("demo-feat_1"))
        assert (after.status, after.current) == ("paused", "4"), after.get("error")
        assert after["pending_chat"] == st["pending_chat"]
        assert after.execution_count("4") == 1


def test_a_gate_continues_only_when_agenthub_releases_it(root, monkeypatch):
    # Constraint: a recorded answer is not enough at a gate: the run passes it only when HARNESS_GATE_RELEASE names
    #             the gate's decision file, which AgentHub sets once the human replied.
    # Input: on_question pause; at GATE 1 the answer is recorded; resume with no release variable, then with the name
    #        of another decision file, then with the right one
    # Expected output: still paused at 7 with the gate unreleased after the first two; after the third the gate is
    #                  released and the run pauses next at GATE 2
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root, {"on_question": "pause"})
    assert (st.status, st.current) == ("paused", "7")
    _forbid_chats(monkeypatch)
    _record_answer(root, st)
    layout = Layout(root)
    monkeypatch.delenv("HARNESS_GATE_RELEASE", raising=False)
    for release in (None, "decision_demo-feat_1_v9.md"):
        if release:
            monkeypatch.setenv("HARNESS_GATE_RELEASE", release)
        Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
        after = State.load(layout.state_file("demo-feat_1"))
        assert (after.status, after.current) == ("paused", "7"), after.get("error")
        assert after["gates"]["7"][0]["released"] is None
        assert after["pending_chat"] == st["pending_chat"]
    _release_gate(monkeypatch, st)
    Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    after = State.load(layout.state_file("demo-feat_1"))
    assert (after.status, after.current) == ("paused", "19"), after.get("error")
    assert after["gates"]["7"][0]["released"]


@pytest.mark.parametrize(
    "argv, instead",
    [
        (["run", "feature-v1", "demo-feat"], "agenthub harness start"),
        (["resume", "demo-feat_1"], "agenthub harness resume"),
    ],
)
def test_run_and_resume_refuse_inside_an_agenthub_task(root, monkeypatch, capsys, argv, instead):
    # Constraint: inside an AI user's session (AGENTHUB_TASK_TOKEN set) runs start and resume only through AgentHub,
    #             which checks the project rules and the human's reply at a gate.
    # Input: a run paused at GATE 1 with its answer recorded and released; the task token set; run, then resume
    # Expected output: exit 2, a message naming the AgentHub command; no second run and the paused run untouched
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root, {"on_question": "pause"})
    _record_answer(root, st)
    _release_gate(monkeypatch, st)
    before = (root / "runs" / "demo-feat_1" / "state.json").read_text()
    monkeypatch.setenv("HARNESS_ROOT", str(root))
    monkeypatch.setenv("AGENTHUB_TASK_TOKEN", "task-token")
    assert cli.main(argv) == 2
    assert instead in capsys.readouterr().err
    assert not (root / "runs" / "demo-feat_2").exists()
    assert (root / "runs" / "demo-feat_1" / "state.json").read_text() == before


def _forbid_chats(monkeypatch) -> None:
    import harness.orchestrator as orch_mod

    def no_chat(**kwargs):
        raise AssertionError("a chat was opened although the answer was already recorded")

    monkeypatch.setattr(orch_mod, "run_chat", no_chat)


def test_resume_skips_the_chat_when_the_answer_is_recorded(root, monkeypatch):
    # Constraint: with the answer already in the decision file, resume opens no chat and routes the run from it.
    # Input: on_question pause; at GATE 1 and at GATE 2 the question file is filled in with answered: true
    # Expected output: no chat is launched; the first resume pauses at GATE 2, the second ends done;
    #                  both gates are released
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root, {"on_question": "pause"})
    assert st.status == "paused" and st.current == "7"
    _forbid_chats(monkeypatch)
    layout = Layout(root)
    for expected_status, expected_step in (("paused", "19"), ("done", "19")):
        _record_answer(root, st)
        _release_gate(monkeypatch, st)
        Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
        st = State.load(layout.state_file("demo-feat_1"))
        assert (st.status, st.current) == (expected_status, expected_step), st.get("error")
    assert st["gates"]["7"][0]["released"] and st["gates"]["19"][0]["released"]
    assert st["pending_chat"] is None


def test_resume_with_a_recorded_answer_reruns_the_asking_step(root, monkeypatch):
    # Constraint: a question answered in the decision file, with no chat, re-runs the asking step with the answer.
    # Input: on_question pause; build-context not_reproduced then reproduced; the answer recorded in the question file
    # Expected output: no chat is launched; step 4 runs a second time and writes context v2; the answer is
    #                  consumed and kept in the question history; the run pauses next at GATE 1
    _scenario(root, monkeypatch, {"context_status": ["not_reproduced", "reproduced"], "triage": ["done"]})
    st = _run(root, {"on_question": "pause"})
    assert st.status == "paused" and st.current == "4"
    _forbid_chats(monkeypatch)
    _record_answer(root, st, "Use filter value 42.")
    layout = Layout(root)
    Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "paused" and st.current == "7", st.get("error")
    assert (root / "runs" / "demo-feat_1" / "context_demo-feat_1_v2.md").exists()
    assert st.execution_count("4") == 2
    assert st["injected_answer"] is None
    assert [h["answered"] for h in st["question_history"]] == [True]


def test_chat_is_closed_once_the_answer_is_recorded(root, monkeypatch):
    # Constraint: a chat that recorded the human's answer is closed by the harness; nobody has to exit it.
    # Input: on_question chat; at GATE 1 the chat writes answered: true and then stays open for 60 s, as a
    #        real chat waits for the human
    # Expected output: the harness ends the chat before it ends by itself, removes the done marker, and the
    #                  run goes on to done
    _scenario(root, monkeypatch, {"triage": ["done"], "chat": {"7": "answer"}, "chat_stay_open": {"7": 60}})
    st = _run(root)
    assert st.status == "done", st.get("error")
    assert (root / "chat_7_open").exists()
    assert not (root / "chat_7_exited_by_itself").exists()
    assert not (root / "runs" / "demo-feat_1" / "log" / "chat_done").exists()
    assert st["gates"]["7"][0]["released"]


def test_chat_without_an_answer_is_left_for_the_human_to_end(root, monkeypatch):
    # Constraint: the harness closes a chat only on a recorded answer; without one the chat runs until it is exited.
    # Input: on_question chat; at GATE 1 the chat records nothing and ends by itself after 3 s (the human's /exit)
    # Expected output: the chat reached its own end; the gate is released and the run goes on to done
    _scenario(root, monkeypatch, {"triage": ["done"], "chat_stay_open": {"7": 3}})
    st = _run(root)
    assert st.status == "done", st.get("error")
    assert (root / "chat_7_exited_by_itself").exists()
    assert st["gates"]["7"][0]["released"]


def _resumed_prompt(root: Path, step: str, execution: int) -> str:
    """The message the fake claude received when a session of that execution was continued."""
    return (root / "prompts" / f"{step}_{execution}_resumed.txt").read_text()


def test_usage_limit_waits_then_continues_the_same_session(root, monkeypatch):
    # Constraint: a step stopped by the account's usage limit is not a failure: the run sleeps until the limit
    #             resets and then continues the step in its own session, as the same execution.
    # Input: step 8 hits the limit on its first attempt, reset one hour away; the sleep is replaced by a recorder
    # Expected output: status done; step 8 has one execution with 2 attempts and its output under the first name;
    #                  one sleep, until the reset plus the 60 s margin, during which status says the run is waiting;
    #                  the second attempt resumed session fake-8-1 with the reason and the output path
    import harness.orchestrator as orch_mod

    layout = Layout(root)
    sleeps, status_while_waiting = [], []

    def record_sleep(until):
        sleeps.append(until)
        status_while_waiting.append(render(State.load(layout.state_file("demo-feat_1")), load_workflow(layout, "feature-v1")))

    monkeypatch.setattr(orch_mod, "_sleep_until", record_sleep)
    _scenario(root, monkeypatch, {"triage": ["done"], "faults": {"8": ["rate_limit"]}})
    before = time.time()
    st = _run(root)
    assert st.status == "done", st.get("error")
    [exe] = st.executions_of("8")
    assert (exe["status"], exe["attempts"]) == ("done", 2)
    run_dir = root / "runs" / "demo-feat_1"
    assert (run_dir / "testing_demo-feat_1.md").exists()
    assert not (run_dir / "testing_demo-feat_1_v2.md").exists()
    [until] = sleeps
    assert before + 3600 + 59 <= until <= time.time() + 3600 + 61
    assert "waiting at 8: usage limit reached" in status_while_waiting[0]
    assert st.get("limit_wait") is None
    resumed = _resumed_prompt(root, "8", 1)
    assert resumed.startswith("[resume fake-8-1]\n")
    assert "the account's usage limit was reached" in resumed
    assert f"- testing: {run_dir / 'testing_demo-feat_1.md'}" in resumed
    assert "${" not in resumed
    # the stopped process reported 2,000 tokens, the continued one 1,000: a lower figure is added, not a running total
    assert exe["tokens"] == {kind: 3 * n for kind, n in TOKENS_1000.items()}


def test_usage_limit_in_pause_mode_ends_the_run_and_resume_continues_the_session(root, monkeypatch):
    # Constraint: with on_rate_limit pause the run ends at the usage limit, naming the limit and not a bare exit
    #             code, and `agenthub-harness resume` continues the step's session instead of starting the step over.
    # Input: step 8 hits the limit on its first attempt; on_rate_limit=pause; then one resume
    # Expected output: failed at step 8 with the limit and the resume command in the error; after resume done,
    #                  step 8 still one execution with 2 attempts, continued in session fake-8-1
    _scenario(root, monkeypatch, {"triage": ["done"], "faults": {"8": ["rate_limit"]}})
    st = _run(root, {"on_rate_limit": "pause"})
    assert (st.status, st.current) == ("failed", "8")
    assert st.step("8")["outcome"].startswith("usage limit reached, resets ")
    assert "usage limit reached" in st["error"] and "`agenthub-harness resume demo-feat_1`" in st["error"]
    layout = Layout(root)
    Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "done", st.get("error")
    [exe] = st.executions_of("8")
    assert (exe["status"], exe["attempts"]) == ("done", 2)
    assert _resumed_prompt(root, "8", 1).startswith("[resume fake-8-1]\n")


def test_resume_continues_a_step_whose_process_died(root, monkeypatch):
    # Constraint: a step whose process died is continued in its session on resume: same execution, same output
    #             name. The session id comes from the start of the stream, because a dead process reports no result.
    # Input: the claude process of step 10 dies after its session started; then one resume
    # Expected output: failed at step 10; after resume done, step 10 has one execution with 2 attempts, the review
    #                  under its first name, and the second attempt resumed session fake-10-1
    _scenario(root, monkeypatch, {"triage": ["done"], "faults": {"10": ["die"]}})
    st = _run(root)
    assert (st.status, st.current) == ("failed", "10")
    assert st.executions_of("10")[0]["session_id"] == "fake-10-1"
    layout = Layout(root)
    Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "done", st.get("error")
    [exe] = st.executions_of("10")
    assert (exe["status"], exe["attempts"]) == ("done", 2)
    run_dir = root / "runs" / "demo-feat_1"
    assert (run_dir / "review_demo-feat_1.md").exists()
    assert not (run_dir / "review_demo-feat_1_v2.md").exists()
    resumed = _resumed_prompt(root, "10", 1)
    assert resumed.startswith("[resume fake-10-1]\n")
    assert "the process ended with an error (claude exited 1)" in resumed


def test_step_that_ends_without_its_output_is_asked_for_it_once(root, monkeypatch):
    # Constraint: a session that ends normally without the step's output is asked for it in the same session,
    #             once. A second time the run fails, and resume starts the step over as the next _v<k>.
    # Input: step 5 ends without its spec twice, then works; one resume after the failure
    # Expected output: failed at step 5 after 2 attempts in one execution, the second one asked for the missing
    #                  file; after resume done with a second execution that wrote spec v2 in a new session
    _scenario(root, monkeypatch, {"triage": ["done"], "faults": {"5": ["no_output", "no_output"]}})
    st = _run(root)
    assert (st.status, st.current) == ("failed", "5")
    [exe] = st.executions_of("5")
    assert (exe["status"], exe["attempts"]) == ("failed", 2)
    assert "it ended without writing runs/demo-feat_1/spec_demo-feat_1.md" in _resumed_prompt(root, "5", 1)
    layout = Layout(root)
    Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "done", st.get("error")
    assert [e["status"] for e in st.executions_of("5")] == ["failed", "done"]
    assert (root / "runs" / "demo-feat_1" / "spec_demo-feat_1_v2.md").exists()
    assert not (root / "prompts" / "5_2_resumed.txt").exists()


@pytest.mark.parametrize(
    "faults, overrides, continuation_tried",
    [
        (["die", "session_gone"], {}, True),
        (["die"], {"step_continuations": 0}, False),
    ],
)
def test_resume_starts_the_step_over_when_its_session_is_not_continued(root, monkeypatch, faults, overrides, continuation_tried):
    # Constraint: resume falls back to a new execution in a new session, in the same resume, when the stopped
    #             session cannot be continued, and goes there directly when step_continuations is 0.
    # Input: the process of step 10 dies; (a) the continuation then fails because the session cannot be opened,
    #        (b) step_continuations=0; one resume
    # Expected output: after the one resume the run is done; step 10 has a failed and a done execution, the review
    #                  is v2, and a continuation was attempted only in (a)
    _scenario(root, monkeypatch, {"triage": ["done"], "faults": {"10": faults}})
    st = _run(root, overrides)
    assert (st.status, st.current) == ("failed", "10")
    layout = Layout(root)
    Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "done", st.get("error")
    assert [e["status"] for e in st.executions_of("10")] == ["failed", "done"]
    assert (root / "runs" / "demo-feat_1" / "review_demo-feat_1_v2.md").exists()
    assert (root / "prompts" / "10_1_resumed.txt").exists() is continuation_tried


def _launch_effort(root: Path, step: str) -> str | None:
    """The effort level the fake claude was launched at for the first execution of a step; None when none was set."""
    return (root / "prompts" / f"{step}_1.effort").read_text() or None


AI_STEPS = ["4", "5", "6", "8", "9", "10", "11", "12", "13", "13b", "14", "15", "15b", "15c", "16", "17"]


def test_each_step_is_launched_at_the_effort_the_workflow_gives_it(root, monkeypatch):
    # Constraint: a step's reasoning effort comes from defaults.effort, not from the human's own Claude Code
    #             settings: the level of the step when it is listed, the workflow default otherwise.
    # Input: the feature-v1 defaults, triage decides done
    # Expected output: plan and build launched at xhigh; build-context, spec, test cases, code review and triage
    #                  at high; every other AI step at medium, whatever level the launching shell had set
    monkeypatch.setenv("CLAUDE_CODE_EFFORT_LEVEL", "max")
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root)
    assert st.status == "done", st.get("error")
    expected = {step: "medium" for step in AI_STEPS}
    expected.update({"6": "xhigh", "9": "xhigh", "4": "high", "5": "high", "8": "high", "10": "high", "14": "high"})
    assert {step: _launch_effort(root, step) for step in AI_STEPS} == expected


@pytest.mark.parametrize("effort, launched_with", [("low", "low"), ({}, None)])
def test_effort_override_applies_to_every_step_and_an_empty_one_sets_no_level(root, monkeypatch, effort, launched_with):
    # Constraint: `effort` given as one level applies to every step; an empty `effort` sets no level, so steps
    #             run at the level of the human's own settings, as before the workflow set one.
    # Input: override effort=low, then effort={}; no level in the launching shell; triage decides done
    # Expected output: every AI step launched at low, respectively with no level set
    monkeypatch.delenv("CLAUDE_CODE_EFFORT_LEVEL", raising=False)
    _scenario(root, monkeypatch, {"triage": ["done"]})
    st = _run(root, {"effort": effort})
    assert st.status == "done", st.get("error")
    assert {_launch_effort(root, step) for step in AI_STEPS} == {launched_with}


def test_rejects_unknown_effort_level(root):
    # Constraint: every level in defaults.effort must be one Claude Code accepts; a typo stops the run before
    #             it is created, not at the step that would use it.
    # Input: override effort with step 10 at "hgih"
    # Expected output: SystemExit naming defaults.effort and the value, no run folder
    with pytest.raises(SystemExit, match="defaults.effort.*hgih"):
        Orchestrator.start(Layout(root), "feature-v1", "demo-feat", {"effort": {"default": "medium", "steps": {"10": "hgih"}}}, quiet=True)
    assert not (root / "runs" / "demo-feat_1").exists()


def test_rejects_unknown_on_rate_limit_value(root):
    # Constraint: defaults.on_rate_limit accepts only wait|pause; anything else stops the run before it is created.
    # Input: override on_rate_limit=retry
    # Expected output: SystemExit naming defaults.on_rate_limit, no run folder
    with pytest.raises(SystemExit, match="defaults.on_rate_limit"):
        Orchestrator.start(Layout(root), "feature-v1", "demo-feat", {"on_rate_limit": "retry"}, quiet=True)
    assert not (root / "runs" / "demo-feat_1").exists()


def test_interrupted_step_then_resume(root, monkeypatch):
    # Constraint: an interrupted step that never reported a session has nothing to continue: it is re-run from
    #             scratch on resume as the next _v<k>, never over the old output.
    # Input: the claude launch for step 4 is interrupted (Ctrl-C) on its first execution
    # Expected output: status paused at step 4 with the execution marked interrupted, then done after resume
    #                  with the context written as v2 (execution count 2) and no v1 on disk
    _scenario(root, monkeypatch, {"triage": ["done"]})
    import harness.orchestrator as orch_mod

    real_run_step = orch_mod.run_step
    calls = {"n": 0}

    def interrupting(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise KeyboardInterrupt
        return real_run_step(**kwargs)

    monkeypatch.setattr(orch_mod, "run_step", interrupting)
    layout = Layout(root)
    orch = Orchestrator.start(layout, "feature-v1", "demo-feat", dict(CHAT), quiet=True)
    orch.run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "paused"
    assert st.current == "4"
    orch2 = Orchestrator.resume(layout, "demo-feat_1", quiet=True)
    orch2.run()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "done", st.get("error")
    run_dir = root / "runs" / "demo-feat_1"
    assert (run_dir / "context_demo-feat_1_v2.md").exists()
    assert not (run_dir / "context_demo-feat_1.md").exists()
    assert st["executions"][1]["status"] == "interrupted"  # [0] is step 2
    assert st.execution_count("4") == 2


def test_refuses_placeholder_agentsmd(root, monkeypatch):
    # Constraint: a project whose AGENTS.md still has TODO(onboard) placeholders cannot start a run.
    # Input: AGENTS.md with a placeholder
    # Expected output: SystemExit mentioning the placeholder
    (root / "agentmds" / "demo" / "AGENTS.md").write_text("# demo\n\nTODO(onboard): fill me\n")
    with pytest.raises(SystemExit, match="TODO\\(onboard\\)"):
        Orchestrator.start(Layout(root), "feature-v1", "demo-feat", {}, quiet=True)


def _skill(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: {folder.name}\n---\n")


def test_agenthub_run_keeps_to_its_three_roots_and_waits_for_agenthub(tmp_path, monkeypatch):
    # Constraint: as AgentHub runs it: code, private and data roots apart, the manifest and project files read from
    #             the private root, every record under the data root; questions pause with a decision file that
    #             pending_question describes without writing anything; gates pass only once released; telemetry
    #             goes to an external collector, never through Docker; nothing is written under the home folder.
    # Input: code root with the feature-v1 workflow and a general skill; private root with harness.yaml
    #        (observability external, the collector's port in its .env), the project AGENTS.md, a project skill and
    #        agents.md; the ticket in the data root; HOME a temp folder; a failing fake `docker` first on PATH; a
    #        listening local socket as the collector; AgentHub's task and AI user in the environment; both gates
    #        answered in their decision file and released
    # Expected output: paused at GATE 1, pending_question gives kind gate, step 7, the decision file and the gate
    #                  prompt with AgentHub's resume command, and recreates no settings file; done after the two
    #                  releases; records, logs and worktree under the data root and nothing new in the code root;
    #                  both skills and three imports in the worktree; resource attributes app, task_id, ai_user;
    #                  tokens per execution; no <home>/.claude; docker never called
    code = tmp_path / "agenthub"
    private, data = code / "private", code / "data" / "orchestrator"
    shutil.copytree(HARNESS_ROOT / "workflows" / "feature-v1", code / "workflows" / "feature-v1")
    shutil.copytree(HARNESS_ROOT / "observability", code / "observability")
    (code / "agentmds").mkdir()
    (code / "agentmds" / "GENERAL.md").write_text("# general\n")
    _skill(code / "skills" / "general" / "plan")
    _skill(private / "skills" / "projects" / "demo" / "deploy")
    (private / "agentmds" / "demo").mkdir(parents=True)
    (private / "agentmds" / "demo" / "AGENTS.md").write_text("# demo\n\nRun tests with `true`.\n")
    (private / "agents.md").write_text("# private rules\n")
    (private / "harness.yaml").write_text(
        "observability: external\nprojects:\n  demo:\n"
        f"    repo: {_remote(tmp_path)}\n    default_base: dev\n    agentsmd: agentmds/demo/AGENTS.md\n"
        "    skills: skills/projects/demo\n    setup:\n      - echo ok > .setup_ok\n"
    )
    (data / "tickets").mkdir(parents=True)
    (data / "tickets" / "demo-feat.md").write_text("---\nproject: demo\nbase_branch: dev\n---\n# Demo feature\n\nDo the thing.\n")
    code_root_before = sorted(p.name for p in code.iterdir())

    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_called = tmp_path / "docker_called"
    (bin_dir / "docker").write_text(f"#!/bin/sh\necho \"$@\" >> {docker_called}\nexit 1\n")
    (bin_dir / "docker").chmod(0o755)
    collector = socket.socket()
    collector.bind(("127.0.0.1", 0))
    collector.listen()
    (private / ".env").write_text(f"OTLP_GRPC_PORT={collector.getsockname()[1]}\n")
    for var, value in {
        "HOME": str(home), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "HARNESS_CLAUDE_BIN": str(FAKE),
        "HARNESS_NO_NOTIFY": "1", "AGENTHUB_TASK_ID": "task-7", "AGENTHUB_AI_USER": "Engineer",
    }.items():
        monkeypatch.setenv(var, value)
    for var in ("HARNESS_NO_TELEMETRY", "HARNESS_GATE_RELEASE", "AGENTHUB_TASK_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    _scenario(tmp_path, monkeypatch, {"triage": ["done"]})

    layout = Layout(code, private_root=private, data_root=data)
    try:
        Orchestrator.start(layout, "feature-v1", "demo-feat", {}, quiet=True).run()
        st = State.load(layout.state_file("demo-feat_1"))
        assert (st.status, st.current) == ("paused", "7"), st.get("error")
        run_dir = data / "runs" / "demo-feat_1"
        settings = run_dir / "log" / "step_settings.json"
        settings.unlink()
        question = pending_question(layout, "demo-feat_1")
        assert not settings.exists()
        assert (question["kind"], question["step"], question["reason"]) == ("gate", "7", "GATE 1")
        assert question["decision_file"] == str(run_dir / "decision_demo-feat_1_v1.md")
        assert question["question"].startswith("Review spec_demo-feat_1.md")
        prompt = question["chat_prompt"]
        assert "at GATE 1" in prompt and question["decision_file"] in prompt
        assert "agenthub harness resume demo-feat_1" in prompt and "${" not in prompt
        _forbid_chats(monkeypatch)
        for gate in ("7", "19"):
            st = State.load(layout.state_file("demo-feat_1"))
            assert (st.status, st.current) == ("paused", gate), st.get("error")
            _record_answer(code, st)
            _release_gate(monkeypatch, st)
            Orchestrator.resume(layout, "demo-feat_1", quiet=True).run()
    finally:
        collector.close()
    st = State.load(layout.state_file("demo-feat_1"))
    assert st.status == "done", st.get("error")
    assert pending_question(layout, "demo-feat_1") is None
    assert (run_dir / "final_report_demo-feat_1.md").exists()
    assert (data / "workflow_logs" / "demo-feat_1.log").exists()
    worktree = data / "worktrees" / "demo" / "demo-feat_1"
    assert (worktree / ".setup_ok").exists()
    assert sorted(p.name for p in code.iterdir()) == code_root_before
    assert sorted(p.name for p in (worktree / ".claude" / "skills").iterdir()) == ["deploy", "plan"]
    assert (worktree / "CLAUDE.md").read_text().splitlines() == [
        f"@{code / 'agentmds' / 'GENERAL.md'}", f"@{private / 'agentmds' / 'demo' / 'AGENTS.md'}", f"@{private / 'agents.md'}",
    ]
    assert st["telemetry"]["active"] is True
    attrs = dict(a.split("=", 1) for a in (tmp_path / "prompts" / "4_1.attrs").read_text().split(","))
    assert (attrs["app"], attrs["task_id"], attrs["ai_user"], attrs["run_id"]) == ("agenthub", "task-7", "Engineer", "demo-feat_1")
    assert st.executions_of("4")[0]["tokens"] == TOKENS_1000
    assert not (home / ".claude").exists()
    assert not docker_called.exists()

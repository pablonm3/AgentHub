"""Unit tests for the pure parts: naming rules, frontmatter, run cost, run numbers, hook."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harness import naming
from harness.paths import Layout

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "deny_harness_write.py"


def test_split_and_versioned(tmp_path):
    # Constraint: _v<k> suffix parsing and generation are inverses; version 1 has no suffix.
    # Input: plan_f_1_v3.md and plan_f_1.md
    # Expected output: (base, 3) and (base, 1); versioned(base, 1) == base
    base = tmp_path / "plan_f_1.md"
    assert naming.split_version(tmp_path / "plan_f_1_v3.md") == (str(base), 3)
    assert naming.split_version(base) == (str(base), 1)
    assert naming.versioned(base, 1) == base
    assert naming.versioned(base, 2).name == "plan_f_1_v2.md"


def test_highest_next_and_latest(tmp_path):
    # Constraint: highest version reflects disk; next version is unique and >= execution count.
    # Input: plan v1 and v3 on disk, execution count 2 then 5
    # Expected output: highest 3, latest v3, next 4 then 5
    base = tmp_path / "plan_f_1.md"
    base.write_text("x")
    (tmp_path / "plan_f_1_v3.md").write_text("x")
    (tmp_path / "plan_short_f_1_v9.md").write_text("x")  # different stem, must not interfere
    assert naming.highest_version(base) == 3
    assert naming.latest(base).name == "plan_f_1_v3.md"
    assert naming.next_version(base, 2) == 4
    assert naming.next_version(base, 5) == 5
    assert naming.highest_version(tmp_path / "spec_f_1.md") == 0


def test_resolve_reads_latest_per_stem(tmp_path):
    # Constraint: a *.md reads pattern resolves to the highest version per stem only.
    # Input: spec v1, v2; plan v1; testing_feedback v1, v2, v3
    # Expected output: spec_v2, plan, testing_feedback_v3
    d = tmp_path / "runs" / "f_1"
    d.mkdir(parents=True)
    for n in ["spec_f_1.md", "spec_f_1_v2.md", "plan_f_1.md", "testing_feedback_f_1.md", "testing_feedback_f_1_v2.md", "testing_feedback_f_1_v3.md"]:
        (d / n).write_text("x")
    got = sorted(p.name for p in naming.resolve_reads(tmp_path, "runs/f_1/*_f_1*.md"))
    assert got == ["plan_f_1.md", "spec_f_1_v2.md", "testing_feedback_f_1_v3.md"]
    html = naming.resolve_reads(tmp_path, "runs/f_1/*.html")
    assert html == []


def test_next_run_number(tmp_path):
    # Constraint: run number is one more than the highest found in workflow_logs, runs and archived.
    # Input: runs/f_1, workflow_logs/f_3.log, archived/2026-01-01_f_5, unrelated feature g_9
    # Expected output: 6 for f, 1 for h
    layout = Layout(tmp_path)
    (tmp_path / "runs" / "f_1").mkdir(parents=True)
    (tmp_path / "workflow_logs").mkdir()
    (tmp_path / "workflow_logs" / "f_3.log").write_text("")
    (tmp_path / "archived" / "2026-01-01_f_5").mkdir(parents=True)
    (tmp_path / "runs" / "g_9").mkdir()
    assert naming.next_run_number(layout, "f") == 6
    assert naming.next_run_number(layout, "h") == 1


def test_frontmatter_counts_and_cost(tmp_path):
    # Constraint: frontmatter fields, severity counts and the run-cost section parse from one artifact.
    # Input: a review file with counts in frontmatter and a run cost section
    # Expected output: counts from frontmatter, cost dict with four keys
    p = tmp_path / "review_f_1.md"
    p.write_text(
        "---\nstatus: reproduced\ncounts: {high: 2, medium: 5}\nsummary: ok\n---\n# r\n\n### [HIGH] a\n\n"
        "## Run cost\n- project runs:    app session\n- wall time:       11m 40s\n- LLM usage:       ~38 calls\n- source:          LangSmith\n"
    )
    fm = naming.read_frontmatter(p)
    assert fm["status"] == "reproduced"
    assert naming.count_severities(p) == {"high": 2, "medium": 5}
    cost = naming.parse_run_cost(p)
    assert cost == {"runs": "app session", "wall_time": "11m 40s", "llm_usage": "~38 calls", "source": "LangSmith"}
    assert naming.cost_line(cost) == "project wall 11m 40s · LLM ~38 calls (LangSmith)"
    assert naming.cost_line({"runs": "none"}) == "project none"


def test_frontmatter_survives_an_unquoted_colon_in_summary(tmp_path):
    # Constraint: a ": " inside an unquoted summary makes the block invalid YAML; triage v5 of
    # annotation-app-v2-alz_1 wrote one and the run failed with decision ''. Other keys must still read.
    # Input: decision, answered, a nested counts map and a summary containing "v4: a correction".
    # Expected output: every key parsed with its type; the summary kept as its raw text.
    p = tmp_path / "decision_f_1_v5.md"
    p.write_text(
        "---\nstep: \"14\"\ndecision: new_plan\nquestion:\nanswered: false\ncounts:\n  high: 0\n  medium: 1\n"
        "summary: new_plan. One MEDIUM lives in plan v4: a correction is dropped (`setBusy`).\n---\n# d\n"
    )
    fm = naming.read_frontmatter(p)
    assert fm["decision"] == "new_plan" and fm["step"] == "14"
    assert fm["answered"] is False and fm["question"] is None
    assert fm["counts"] == {"high": 0, "medium": 1}
    assert fm["summary"] == "new_plan. One MEDIUM lives in plan v4: a correction is dropped (`setBusy`)."


def test_count_severities_from_headings(tmp_path):
    # Constraint: without a counts field, severities are counted from ### [SEVERITY] headings.
    # Input: a file with one HIGH and two LOW headings
    # Expected output: {"high": 1, "low": 2}
    p = tmp_path / "readability_f_1.md"
    p.write_text("---\nsummary: x\n---\n### [HIGH] a\n### [LOW] b\n### [low] c\n")
    assert naming.count_severities(p) == {"high": 1, "low": 2}
    assert naming.severities_line({"high": 1, "low": 2}) == "1 high, 2 low"


def test_validate_feature():
    # Constraint: feature names are kebab-case.
    # Input: valid and invalid names
    # Expected output: valid returns, invalid raises SystemExit
    assert naming.validate_feature("filter-recovery") == "filter-recovery"
    with pytest.raises(SystemExit):
        naming.validate_feature("Filter_Recovery")


def _hook(payload: dict, protected: list[str]) -> int:
    env = dict(os.environ, HARNESS_PROTECTED_PATHS=os.pathsep.join(protected))
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True, env=env, capture_output=True)
    return r.returncode


def test_write_boundary_hook(tmp_path):
    # Constraint: the PreToolUse hook denies edits under protected paths and lets others through.
    # Input: Edit on skills/x, Write on runs/y, Bash sed -i on workflows, Bash cat on workflows
    # Expected output: 2, 0, 2, 0
    skills = tmp_path / "skills"
    workflows = tmp_path / "workflows"
    skills.mkdir()
    workflows.mkdir()
    protected = [str(skills), str(workflows)]
    assert _hook({"tool_name": "Edit", "tool_input": {"file_path": str(skills / "x" / "SKILL.md")}, "cwd": str(tmp_path)}, protected) == 2
    assert _hook({"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "runs" / "y.md")}, "cwd": str(tmp_path)}, protected) == 0
    assert _hook({"tool_name": "Bash", "tool_input": {"command": f"sed -i '' s/a/b/ {workflows}/feature-v1/defaults.yaml"}}, protected) == 2
    assert _hook({"tool_name": "Bash", "tool_input": {"command": f"cat {workflows}/feature-v1/defaults.yaml"}}, protected) == 0


@pytest.mark.parametrize(
    "command, expected",
    [
        # writes under a protected path: refused
        ("rm {root}/skills/general/plan/SKILL.md", 2),
        ("cd {root}/skills && rm x", 2),
        ("echo hi > {root}/harness/orchestrator.py", 2),
        ("cd {root} && echo hi >> harness/orchestrator.py", 2),
        ("cd {root} && mv workflows/feature-v1 workflows/old", 2),
        ("cp x.py --target-directory={root}/harness", 2),
        # a word that cannot be resolved is judged by its text: naming a protected folder is enough
        ("rm -rf $HARNESS_ROOT/skills/general", 2),
        ('cp notes.md "$(git rev-parse --show-toplevel)/workflows/x.md"', 2),
        ("cp notes.md $(git -C {root} rev-parse --show-toplevel)/workflows/x.md", 2),
        # same-named folders elsewhere: the worktree's own skills/ and harness/, a folder called ...-harness/
        ("rm -rf skills/general/plan && mkdir -p harness/tests && echo x > workflows/a.yaml", 0),
        ("cd {worktree} && rm harness/hooks/deny_harness_write.py", 0),
        ("echo x > {tmp}/my-harness/notes.md && rm {tmp}/coding-harness/skills/x", 0),
        # a commit message that names such folders
        ('git add -A && git commit -m "Copy skills/, workflows/ and harness/ (adapted)"', 0),
        # reading a protected path writes nothing
        ("cat {root}/skills/general/plan/SKILL.md | head -5", 0),
    ],
)
def test_bash_boundary_goes_by_where_a_path_points(tmp_path, command, expected):
    # Constraint: the Bash check refuses a write-like command only when a path in it lies under a protected path,
    #             resolved against the session's folder and every `cd` of the command; a word holding a variable
    #             or a command substitution counts when it names a protected path or folder. A worktree that is a
    #             copy of the harness has its own skills/, harness/ and workflows/, and those stay writable.
    # Input: protected skills, workflows and harness of a code root; the session in a worktree below the root's
    #        data folder that has the same folder names; each command of the table
    # Expected output: 2 (denied) or 0 (allowed) as listed
    root = tmp_path / "agenthub"
    worktree = root / "data" / "orchestrator" / "worktrees" / "demo" / "demo-feat_1"
    for d in ("skills/general/plan", "workflows/feature-v1", "harness/hooks"):
        (root / d).mkdir(parents=True)
        (worktree / d).mkdir(parents=True)
    protected = [str(root / "skills"), str(root / "workflows"), str(root / "harness")]
    cmd = command.format(root=root, worktree=worktree, tmp=tmp_path)
    assert _hook({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(worktree)}, protected) == expected

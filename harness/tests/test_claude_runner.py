"""Step and chat settings (spec 5.1, 6.1) and the chat's done hook (5.7)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from harness.claude_runner import (
    CHAT_DONE_HOOK,
    base_env,
    result_tokens,
    run_step,
    session_tokens,
    write_chat_settings,
    write_step_settings,
)
from harness.paths import Layout

FAKE = Path(__file__).resolve().parent / "fake_claude.py"
# the fake's modelUsage of one session (fake_claude.model_usage), summed over its two models
TOKENS_1000 = {"input": 5, "output": 145, "cache_creation": 250, "cache_read": 600}


def test_step_env_waits_for_background_subagents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Constraint: `claude -p` kills background subagents 10 min after its last turn unless told to wait;
    # code-review_2 of annotation-app-v2-alz_1 lost its synthesis that way. A value set by the human wins.
    # Input: base_env with the variable unset, then with it set to 600000.
    # Expected output: "0" (wait, bounded by the step timeout) when unset; the human's value when set.
    layout = Layout(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", raising=False)
    assert base_env(layout, "account")["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] == "0"
    monkeypatch.setenv("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "600000")
    assert base_env(layout, "account")["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] == "600000"


def test_step_settings_exclude_the_claude_md_of_the_root_and_its_ancestors(tmp_path: Path) -> None:
    # Constraint: the CLAUDE.md of the root and of every folder above it holds instructions for sessions opened
    #             there; the worktrees below the root must not load them into steps.
    # Input: a layout rooted at tmp_path/repo.
    # Expected output: claudeMdExcludes names CLAUDE.md of the root, then of each ancestor up to /; deny rules
    #                  still cover the protected paths.
    root = tmp_path / "repo"
    settings = json.loads(write_step_settings(Layout(root), tmp_path / "s.json").read_text())
    assert settings["claudeMdExcludes"] == [str(folder / "CLAUDE.md") for folder in (root, *root.parents)]
    assert settings["claudeMdExcludes"][:2] == [str(root / "CLAUDE.md"), str(tmp_path / "CLAUDE.md")]
    assert settings["claudeMdExcludes"][-1] == "/CLAUDE.md"
    assert any(rule.startswith("Edit(") and "skills" in rule for rule in settings["permissions"]["deny"])


def test_step_settings_take_a_protected_list_in_place_of_the_layouts(tmp_path: Path) -> None:
    # Constraint: AgentHub's sessions guard the app's own code folders, not the harness paths of the layout.
    # Input: write_step_settings with protected = two folders of an app.
    # Expected output: exactly one Edit deny rule per given folder, none for the layout's skills or workflows.
    web, app = tmp_path / "web", tmp_path / "agenthub"
    settings = json.loads(write_step_settings(Layout(tmp_path), tmp_path / "s.json", protected=[web, app]).read_text())
    assert settings["permissions"]["deny"] == [f"Edit(//{web}/**)", f"Edit(//{app}/**)"]


def test_base_env_names_the_three_roots(tmp_path: Path) -> None:
    # Constraint: a step's session knows where the code, the private files and the run data live, and the hook
    #             protects the project skills under the private root.
    # Input: base_env of a layout with a private root and a data root inside the code root.
    # Expected output: HARNESS_ROOT, HARNESS_PRIVATE_ROOT and HARNESS_DATA_ROOT name them; HARNESS_PROTECTED_PATHS
    #                  holds <private root>/skills/projects.
    root = tmp_path / "repo"
    layout = Layout(root, private_root=root / "private", data_root=root / "data" / "orchestrator")
    env = base_env(layout, "account")
    assert (env["HARNESS_ROOT"], env["HARNESS_PRIVATE_ROOT"], env["HARNESS_DATA_ROOT"]) == (
        str(root), str(root / "private"), str(root / "data" / "orchestrator"),
    )
    assert str(root / "private" / "skills" / "projects") in env["HARNESS_PROTECTED_PATHS"].split(os.pathsep)


def test_chat_settings_add_the_done_hook_to_the_step_settings(tmp_path: Path) -> None:
    # Constraint: a chat runs under the same write boundary as a step, plus the Stop hook that reports it is done.
    # Input: step and chat settings written for the same layout.
    # Expected output: identical except for hooks.Stop, which runs hooks/chat_done.py; steps have no Stop hook.
    layout = Layout(tmp_path)
    step = json.loads(write_step_settings(layout, tmp_path / "step.json").read_text())
    chat = json.loads(write_chat_settings(layout, tmp_path / "chat.json").read_text())
    assert "Stop" not in step["hooks"]
    [group] = chat["hooks"].pop("Stop")
    [hook] = group["hooks"]
    assert hook["type"] == "command" and hook["command"].endswith("chat_done.py")
    assert chat == step


@pytest.mark.parametrize(
    "decision, marker_expected",
    [
        ("---\nrun_id: r_1\nanswered: true\n---\n# Question\n\n## Answer\nyes\n", True),
        ("---\nrun_id: r_1\nanswered: false\n---\n# Question\n\nanswered: true\n", False),
        ("# no frontmatter\n\nanswered: true\n", False),
        (None, False),
    ],
)
def test_done_hook_creates_the_marker_only_for_a_recorded_answer(tmp_path: Path, decision, marker_expected) -> None:
    # Constraint: the marker that closes a chat appears only when the decision file's frontmatter says answered: true.
    # Input: the hook run as Claude Code runs it, with the decision file answered, unanswered (the words
    #        `answered: true` only in the body), without frontmatter, or missing.
    # Expected output: exit 0 and no output in every case; the marker exists only in the answered case.
    decision_file = tmp_path / "decision_r_1_v1.md"
    if decision is not None:
        decision_file.write_text(decision)
    marker = tmp_path / "chat_done"
    env = {**os.environ, "HARNESS_DECISION_FILE": str(decision_file), "HARNESS_CHAT_DONE_MARKER": str(marker)}
    r = subprocess.run([sys.executable, str(CHAT_DONE_HOOK)], env=env, input="{}", capture_output=True, text=True)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert marker.exists() is marker_expected


def test_step_with_mcp_servers_gets_its_mcp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Constraint: step 13b drives a browser only through the MCP server its workflow entry declares; every
    #             earlier UI round was blocked because the step session had no browser tool.
    # Input: run_step with an mcp_config file, a fake claude
    # Expected output: the launch event in the transcript carries `--mcp-config <file>`; without it, no flag
    monkeypatch.setenv("HARNESS_CLAUDE_BIN", str(FAKE))
    mcp = tmp_path / "mcp_13b.json"
    mcp.write_text(json.dumps({"mcpServers": {}}))

    def launch_argv(transcript: Path, **kw) -> list[str]:
        run_step(
            layout=Layout(tmp_path), prompt="do step 13b", cwd=tmp_path, transcript=transcript,
            settings_file=tmp_path / "settings.json", env=dict(os.environ), quiet=True, **kw,
        )
        return json.loads(transcript.read_text().splitlines()[0])["argv"]

    with_mcp = launch_argv(tmp_path / "a.jsonl", mcp_config=mcp)
    assert with_mcp[with_mcp.index("--mcp-config") + 1] == str(mcp)
    assert "--mcp-config" not in launch_argv(tmp_path / "b.jsonl")


def test_step_result_names_the_usage_limit_and_the_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Constraint: a step stopped by the usage limit reports the limit, its reset time and its session, also when
    #             the stream ends with one more, empty result (code-review_1 of filter-recovery-classifier_1
    #             showed a bare "claude exited 1" because only the last result was kept).
    # Input: a fake claude that emits init, a rejected rate_limit_event, a 429 error result, an empty result; exit 1
    # Expected output: not ok, rate_limited, resets_at about an hour away, the limit message as result_text,
    #                  the session id, which on_session received as well; the tokens of the last result (2,000),
    #                  not of the failed one
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps({"faults": {"8": ["rate_limit"]}}))
    monkeypatch.setenv("HARNESS_CLAUDE_BIN", str(FAKE))
    seen: list[str] = []
    res = run_step(
        layout=Layout(tmp_path),
        prompt="do step 8",
        cwd=tmp_path,
        transcript=tmp_path / "08.jsonl",
        settings_file=tmp_path / "settings.json",
        env={**os.environ, "FAKE_CLAUDE_SCENARIO": str(scenario), "HARNESS_STEP": "8", "HARNESS_EXECUTION": "1"},
        quiet=True,
        on_session=seen.append,
    )
    assert not res.ok and res.rate_limited
    assert 3500 < res.rate_limit_resets_at - time.time() <= 3600
    assert res.result_text.startswith("You've hit your 5-hour limit")
    assert res.session_id == "fake-8-1" and seen == ["fake-8-1"]
    assert res.tokens == {kind: 2 * n for kind, n in TOKENS_1000.items()}


def test_run_step_reads_no_user_settings_streams_events_and_reports_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Constraint: a step loads project and local settings only, never the user's own; AgentHub's sessions add
    #             flags of their own, follow the stream event by event and must be able to stop the process,
    #             which runs in its own session; the step's tokens are its session total over every model.
    # Input: run_step on the fake claude with extra_args, on_event, on_process and new_process_group
    # Expected output: argv carries `--setting-sources project,local` and ends with the extra args (the prompt
    #                  follows them); on_event got init, assistant and result in order; on_process got the
    #                  process, which led a session of its own; tokens are the modelUsage total of both models
    monkeypatch.setenv("HARNESS_CLAUDE_BIN", str(FAKE))
    events: list[dict] = []
    processes: list[tuple[subprocess.Popen, int]] = []
    transcript = tmp_path / "turn.jsonl"
    res = run_step(
        layout=Layout(tmp_path), prompt="do the turn", cwd=tmp_path, transcript=transcript,
        settings_file=tmp_path / "settings.json", env={**os.environ, "HARNESS_SKILL": "turn"}, quiet=True,
        extra_args=["--append-system-prompt", "You are the Engineer."],
        on_event=events.append,
        on_process=lambda proc: processes.append((proc, os.getsid(proc.pid))),
        new_process_group=True,
    )
    assert res.ok
    argv = json.loads(transcript.read_text().splitlines()[0])["argv"]
    assert argv[argv.index("--setting-sources") + 1] == "project,local"
    assert argv[-2:] == ["--append-system-prompt", "You are the Engineer."]
    assert [e["type"] for e in events] == ["system", "assistant", "result"]
    [(proc, sid)] = processes
    assert proc.returncode == 0 and sid == proc.pid
    assert res.tokens == TOKENS_1000


def test_session_tokens_replace_a_running_total_and_add_a_lower_figure() -> None:
    # Constraint: tokens of one execution follow the cost rule: a continued session reports its whole total, which
    #             replaces the earlier figure; a lower figure comes from a process that started over and is added.
    # Input: session_tokens over None, equal, higher and lower figures; result_tokens of a result without modelUsage
    # Expected output: the reported figure for a first, equal or higher one; the sum per kind for a lower one;
    #                  the earlier figure when nothing was reported; None for a result without modelUsage
    double = {kind: 2 * n for kind, n in TOKENS_1000.items()}
    assert session_tokens(None, None) is None
    assert session_tokens(None, TOKENS_1000) == TOKENS_1000
    assert session_tokens(TOKENS_1000, None) == TOKENS_1000
    assert session_tokens(TOKENS_1000, TOKENS_1000) == TOKENS_1000
    assert session_tokens(TOKENS_1000, double) == double
    assert session_tokens(double, TOKENS_1000) == {kind: 3 * n for kind, n in TOKENS_1000.items()}
    assert result_tokens({"type": "result", "total_cost_usd": 0.01}) is None

"""Launching Claude Code for a step (`claude -p`) or a chat (interactive) — spec 5.1, 5.7.

Every AI step is a fresh `claude -p` process in the worktree with the step prompt. Its
stream-json output is the step transcript (runs/<run-id>/log/<step>[_v<k>].jsonl). A
settings file denies Edit/Write on the harness paths and a PreToolUse hook enforces the
same boundary for Bash (write boundary, 5.1). Steps read project and local settings only,
never the user's own (`--setting-sources project,local`). A chat gets the same settings plus
a Stop hook that reports when the human's answer is recorded, so the harness can close the chat.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .paths import Layout

HOOK = Path(__file__).resolve().parent / "hooks" / "deny_harness_write.py"
CHAT_DONE_HOOK = Path(__file__).resolve().parent / "hooks" / "chat_done.py"

CHAT_POLL_S = 0.3         # how often the open chat is checked for the done marker
CHAT_CLOSE_DELAY_S = 1.0  # after the marker: time for the chat to finish drawing its last reply
CHAT_TERM_GRACE_S = 10.0  # after SIGTERM: time for the chat to clean up before SIGKILL


def claude_bin() -> str:
    override = os.environ.get("HARNESS_CLAUDE_BIN")
    if override:
        return override
    found = shutil.which("claude")
    if not found:
        raise SystemExit("harness: `claude` not found on PATH (set HARNESS_CLAUDE_BIN to override)")
    return found


def _hook_command(script: Path) -> dict:
    return {"type": "command", "command": f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"}


def _run_settings(layout: Layout, protected: list[Path] | None = None) -> dict:
    """Claude Code settings for runs: deny rules on protected paths plus the boundary hook.

    `protected` replaces the layout's protected paths, for a caller that guards other folders.
    """
    deny: list[str] = []
    for p in layout.protected_paths() if protected is None else protected:
        pattern = f"//{p}/**" if p.is_dir() or not p.suffix else f"//{p}"
        # Claude Code checks path rules only under Edit(...), which covers every file-editing tool;
        # the same rule under Write/NotebookEdit/MultiEdit is reported as never matching
        deny.append(f"Edit({pattern})")
    return {
        "permissions": {"deny": deny},
        # the CLAUDE.md of the root and of the folders above it hold instructions for sessions opened
        # there; a worktree below the root would load them into steps and chats, so exclude them all
        "claudeMdExcludes": [str(folder / "CLAUDE.md") for folder in (layout.root, *layout.root.parents)],
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
                    "hooks": [_hook_command(HOOK)],
                }
            ]
        },
    }


def _write_settings(settings: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


def write_step_settings(layout: Layout, path: Path, protected: list[Path] | None = None) -> Path:
    return _write_settings(_run_settings(layout, protected), path)


def write_chat_settings(layout: Layout, path: Path) -> Path:
    """Step settings plus the Stop hook that creates the done marker once the answer is recorded (5.7)."""
    settings = _run_settings(layout)
    settings["hooks"]["Stop"] = [{"hooks": [_hook_command(CHAT_DONE_HOOK)]}]
    return _write_settings(settings, path)


def base_env(layout: Layout, auth: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["HARNESS_ROOT"] = str(layout.root)
    env["HARNESS_PRIVATE_ROOT"] = str(layout.private_root)
    env["HARNESS_DATA_ROOT"] = str(layout.data_root)
    env["HARNESS_PROTECTED_PATHS"] = os.pathsep.join(str(p) for p in layout.protected_paths())
    # `claude -p` stops background subagents 10 min after its last turn, so a step that fans out to
    # slow subagents (code-review's specialists) exits before it writes its output; wait for them
    # instead. The step timeout in defaults.yaml still bounds the whole step.
    env.setdefault("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "0")
    if auth == "account":
        # account auth: the logged-in Claude Code credential; never let an API key leak in
        env.pop("ANTHROPIC_API_KEY", None)
    elif auth == "api_key" and not env.get("ANTHROPIC_API_KEY"):
        raise SystemExit("harness: defaults.auth is api_key but ANTHROPIC_API_KEY is not set")
    if extra:
        env.update(extra)
    return env


@dataclass
class StepResult:
    returncode: int
    is_error: bool
    result_text: str
    cost_usd: float | None
    duration_ms: int | None
    num_turns: int | None
    session_id: str | None
    timed_out: bool = False
    rate_limited: bool = False  # the step did not finish because the account's usage limit rejected a request
    rate_limit_resets_at: int | None = None  # epoch seconds, when that limit resets; None when the stream did not say
    tokens: dict[str, int] | None = None  # the session's total by kind (result_tokens of the last result)
    raw_result: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.is_error and not self.timed_out


TOKEN_KINDS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_creation": "cacheCreationInputTokens",
    "cache_read": "cacheReadInputTokens",
}


def result_tokens(result_event: dict) -> dict[str, int] | None:
    """Tokens of a `result` event, summed over the models of its `modelUsage`: the session's total
    so far, subagents included. None when the event reports no modelUsage."""
    usage = result_event.get("modelUsage")
    if not usage:
        return None
    return {kind: sum(int(m.get(key) or 0) for m in usage.values()) for kind, key in TOKEN_KINDS.items()}


def session_tokens(before: dict[str, int] | None, reported: dict[str, int] | None) -> dict[str, int] | None:
    """Tokens of an execution after one more attempt in its session, by the rule of the cost
    (orchestrator._session_cost): a total at or above the earlier one replaces it, a lower one
    cannot be a running total and is added."""
    if reported is None:
        return before
    if before is None or sum(reported.values()) >= sum(before.values()):
        return dict(reported)
    return {kind: before.get(kind, 0) + reported.get(kind, 0) for kind in TOKEN_KINDS}


def _short(text: str, n: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def run_step(
    *,
    layout: Layout,
    prompt: str,
    cwd: Path,
    transcript: Path,
    settings_file: Path,
    env: dict[str, str],
    mcp_config: Path | None = None,
    permission_mode: str = "bypassPermissions",
    model: str | None = None,
    max_budget_usd: float | None = None,
    timeout_s: float | None = None,
    quiet: bool = False,
    resume_session: str | None = None,
    on_session: Callable[[str], None] | None = None,
    extra_args: list[str] | None = None,
    on_event: Callable[[dict], None] | None = None,
    on_process: Callable[[subprocess.Popen], None] | None = None,
    new_process_group: bool = False,
) -> StepResult:
    """Run one `claude -p` step; stream its JSONL output to the transcript and the console.

    With `resume_session` the process continues that session (`--resume`) and `prompt` is the
    next message in it. `on_session` is called with the session id as soon as the stream names
    it, so the caller has it even when the process is killed before it reports a result.
    `extra_args` go before the prompt. `on_event` gets every parsed stream event, `on_process`
    the process right after it started (so the caller can stop it); `new_process_group` starts
    it in a session of its own, so a signal to the caller's group does not reach it.
    """
    cmd = [
        claude_bin(),
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        permission_mode,
        "--settings",
        str(settings_file),
        "--setting-sources",
        "project,local",
        "--add-dir",
        str(layout.root),
    ]
    if permission_mode == "bypassPermissions":
        cmd.append("--dangerously-skip-permissions")
    if mcp_config:
        cmd += ["--mcp-config", str(mcp_config)]
    if model:
        cmd += ["--model", model]
    if max_budget_usd:
        cmd += ["--max-budget-usd", str(max_budget_usd)]
    if resume_session:
        cmd += ["--resume", resume_session]
    cmd += extra_args or []
    cmd.append(prompt)

    transcript.parent.mkdir(parents=True, exist_ok=True)
    result: dict = {}
    first_error: dict = {}
    limit_rejection: dict | None = None
    session_id: str | None = None
    last_tokens: dict[str, int] | None = None
    is_error = False
    timed_out = False
    with open(transcript, "a") as out:
        out.write(json.dumps({"type": "harness", "event": "launch", "cwd": str(cwd), "argv": cmd[:-1]}) + "\n")
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            stdin=subprocess.DEVNULL,
            start_new_session=new_process_group,
        )
        if on_process:
            on_process(proc)

        def _timer():
            nonlocal timed_out
            timed_out = True
            proc.kill()

        timer = threading.Timer(timeout_s, _timer) if timeout_s else None
        if timer:
            timer.start()
        assert proc.stdout is not None
        for line in proc.stdout:
            out.write(line)
            out.flush()
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if on_event:
                on_event(ev)
            if not session_id and ev.get("session_id"):
                session_id = str(ev["session_id"])
                if on_session:
                    on_session(session_id)
            kind = ev.get("type")
            if kind == "result":
                result = ev
                last_tokens = result_tokens(ev) or last_tokens
                is_error = bool(ev.get("is_error"))
                if is_error and not first_error:
                    first_error = ev
            elif kind == "rate_limit_event":
                info = ev.get("rate_limit_info") or {}
                if info.get("status") == "rejected":
                    limit_rejection = info
            elif kind == "assistant" and not quiet:
                for block in (ev.get("message") or {}).get("content") or []:
                    if block.get("type") == "text" and block.get("text", "").strip():
                        print(f"   │ {_short(block['text'])}")
                    elif block.get("type") == "tool_use":
                        name = block.get("name", "tool")
                        inp = block.get("input") or {}
                        hint = inp.get("command") or inp.get("file_path") or inp.get("skill") or inp.get("pattern") or ""
                        print(f"   │ ▸ {name} {_short(str(hint), 100)}")
        stderr = proc.stderr.read() if proc.stderr else ""
        rc = proc.wait()
        if timer:
            timer.cancel()
        if stderr.strip():
            out.write(json.dumps({"type": "harness", "event": "stderr", "text": stderr[-4000:]}) + "\n")
        out.write(json.dumps({"type": "harness", "event": "exit", "returncode": rc, "timed_out": timed_out}) + "\n")
    if rc != 0 and not quiet and stderr.strip():
        print(f"   │ claude exited {rc}: {_short(stderr, 300)}")
    failed = rc != 0 or is_error or timed_out
    # a session emits one result per turn, and a turn started by a late background task can follow
    # the one that failed: the reason for the failure is in the first error result, not the last result
    reason = first_error if failed and first_error else result
    rate_limited = failed and not timed_out and (limit_rejection is not None or first_error.get("api_error_status") == 429)
    resets_at = (limit_rejection or {}).get("resetsAt") if rate_limited else None
    return StepResult(
        returncode=rc,
        is_error=is_error,
        result_text=str(reason.get("result") or ""),
        cost_usd=result.get("total_cost_usd"),
        duration_ms=result.get("duration_ms"),
        num_turns=result.get("num_turns"),
        session_id=session_id,
        timed_out=timed_out,
        rate_limited=rate_limited,
        rate_limit_resets_at=int(resets_at) if resets_at else None,
        tokens=last_tokens,
        raw_result=result,
    )


def run_chat(
    *,
    layout: Layout,
    prompt: str,
    cwd: Path,
    settings_file: Path | None,
    env: dict[str, str],
    permission_mode: str = "auto",
    model: str | None = None,
    name: str | None = None,
    done_marker: Path | None = None,
) -> int:
    """Open an interactive Claude session (spec 5.7). Returns when it ends.

    The human ends it with /exit or Ctrl+D. With `done_marker`, the harness also ends it itself
    as soon as that file appears (the chat's Stop hook creates it once the answer is recorded).
    """
    cmd = [claude_bin(), "--permission-mode", permission_mode, "--add-dir", str(layout.root)]
    if settings_file:
        cmd += ["--settings", str(settings_file)]
    if model:
        cmd += ["--model", model]
    if name:
        cmd += ["--name", name]
    cmd.append(prompt)
    if done_marker is None:
        return subprocess.run(cmd, cwd=cwd, env=env).returncode
    done_marker.unlink(missing_ok=True)
    tty = _tty_state()
    proc = subprocess.Popen(cmd, cwd=cwd, env=env)
    try:
        while proc.poll() is None:
            if done_marker.exists():
                time.sleep(CHAT_CLOSE_DELAY_S)
                _close_chat(proc, tty)
                break
            time.sleep(CHAT_POLL_S)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        done_marker.unlink(missing_ok=True)
    return proc.returncode


def _close_chat(proc: subprocess.Popen, tty: tuple[int, list] | None) -> None:
    """End a chat the human has finished: SIGTERM, SIGKILL only if it does not exit, then a sane terminal."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=CHAT_TERM_GRACE_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    _restore_tty(tty)
    print("\n💬 chat closed by the harness: the answer is recorded")


def _tty_state() -> tuple[int, list] | None:
    """Terminal settings before the chat takes the terminal over, None when stdin is not a terminal."""
    try:
        import termios

        fd = sys.stdin.fileno()
        return (fd, termios.tcgetattr(fd)) if os.isatty(fd) else None
    except Exception:
        return None


def _restore_tty(tty: tuple[int, list] | None) -> None:
    """Put the terminal back as it was, in case the chat was closed before it could do so itself."""
    if tty is None:
        return
    import termios

    fd, attrs = tty
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
    except termios.error:
        pass
    sys.stdout.write("\x1b[?25h\x1b[?2004l")  # show the cursor, leave bracketed-paste mode
    sys.stdout.flush()


def verify_account_auth(layout: Layout, cwd: Path | None = None) -> tuple[bool, str]:
    """Spec 5.1: check the logged-in credential is reachable from a launched process."""
    env = base_env(layout, "account")
    try:
        r = subprocess.run(
            [claude_bin(), "-p", "--output-format", "json", "Reply with the single word: ok"],
            cwd=cwd or layout.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[-400:]
    try:
        data = json.loads(r.stdout)
        if data.get("is_error"):
            return False, str(data.get("result"))[:400]
        return True, f"ok (session {data.get('session_id', '?')[:8]}, cost ${data.get('total_cost_usd', 0):.4f})"
    except json.JSONDecodeError:
        return True, r.stdout.strip()[:200]

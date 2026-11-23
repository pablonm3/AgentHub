"""One AI turn: the `claude -p` process of a task, its workspace, settings, environment and telemetry.

A turn runs through the harness copy's `run_step` launcher. The first turn of a task creates the
session; every later turn continues it with `--resume`. The turn ends with structured output
(`TURN_SCHEMA`) that says what Pablo reads and whether the task waits on him or is done.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from harness.claude_runner import base_env, run_step, write_step_settings
from harness.link import _symlink
from harness.observability import Observability

from .config import Config

PROMPTS = Path(__file__).parent / "prompts"

TURN_SCHEMA = {
    "type": "object",
    "required": ["message", "status", "title"],
    "additionalProperties": False,
    "properties": {
        "message": {"type": "string"},
        "title": {"type": "string"},
        "status": {"enum": ["waiting_on_user", "done"]},
    },
}

# inherited from whoever started the server (possibly another harness session): never passed on
DROP_PREFIXES = ("HARNESS_", "OTEL_", "CLAUDE_CODE_", "CLAUDECODE", "ANTHROPIC_")
KEEP_FROM_BASE_ENV = {"HARNESS_ROOT", "HARNESS_PRIVATE_ROOT", "HARNESS_DATA_ROOT"}

LOGIN_CACHE_S = 30


@dataclass
class TurnOutcome:
    ok: bool
    structured: dict | None = None
    result_text: str = ""
    session_id: str | None = None
    tokens: dict | None = None
    error: str | None = None
    rate_limit_resets_at: int | None = None
    session_lost: bool = False


def clean_env(env: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in env.items() if not k.startswith(DROP_PREFIXES) or k in KEEP_FROM_BASE_ENV}


def valid_structured(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    if not isinstance(value.get("message"), str) or value.get("status") not in ("waiting_on_user", "done"):
        return None
    return {"message": value["message"], "status": value["status"], "title": str(value.get("title") or "")}


def tool_hint(block: dict) -> str:
    inp = block.get("input") or {}
    hint = inp.get("command") or inp.get("file_path") or inp.get("skill") or inp.get("pattern") or inp.get("url") or ""
    text = " ".join(str(hint).split())
    return text if len(text) <= 160 else text[:159] + "…"


class Sessions:
    def __init__(self, config: Config):
        self.config = config
        self.layout = config.layout()
        self._login: tuple[float, dict] | None = None

    # ------------------------------------------------------------ prompts
    def compose_system_prompt(self, ai_user: dict) -> str:
        """Rules + private/agents.md + role prompt, fixed when the task is created (AC2)."""
        parts = [(PROMPTS / "ai_user_rules.md").read_text().strip()]
        agents_md = self.config.private_dir / "agents.md"
        if agents_md.is_file():
            parts.append("# The private folder (private/agents.md)\n\n" + agents_md.read_text().strip())
        parts.append(f"# Your role: {ai_user['name']}\n\n" + (ai_user.get("prompt") or "").strip())
        return "\n\n".join(parts) + "\n"

    # ------------------------------------------------------------ files of a task
    def task_dir(self, task_id: int) -> Path:
        return self.config.tasks_dir / str(task_id)

    def reports_dir(self, task_id: int) -> Path:
        return self.config.reports_dir / str(task_id)

    def reports_url(self, task_id: int) -> str:
        return f"{self.config.base_url}/reports/{task_id}"

    def workspace(self, task_id: int) -> Path:
        """data/tasks/<id>/workspace with the AI users' skills linked into .claude/skills."""
        ws = self.task_dir(task_id) / "workspace"
        skills = ws / ".claude" / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        report: list[str] = []
        for library in (
            self.config.root / "skills" / "agents",
            self.config.root / "skills" / "general",
            self.config.private_dir / "skills" / "agents",
        ):
            if library.is_dir():
                for skill in sorted(library.iterdir()):
                    if (skill / "SKILL.md").is_file():
                        _symlink(skill, skills / skill.name, report)
        self.reports_dir(task_id).mkdir(parents=True, exist_ok=True)
        return ws

    def env(self, task: dict, ai_user: dict, ticket_key: str | None) -> dict[str, str]:
        env = clean_env(base_env(self.layout, "account"))
        env["HARNESS_PROTECTED_PATHS"] = os.pathsep.join(str(p) for p in self.config.protected_code)
        env["HARNESS_NO_NOTIFY"] = "1"
        env["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] = "0"
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        env.update(
            {
                "AGENTHUB_URL": self.config.base_url,
                "AGENTHUB_TASK_ID": str(task["id"]),
                "AGENTHUB_TASK_TOKEN": task["token"],
                "AGENTHUB_AI_USER": ai_user["handle"],
                "AGENTHUB_REPORTS_DIR": str(self.reports_dir(task["id"])),
                "AGENTHUB_REPORTS_URL": self.reports_url(task["id"]),
            }
        )
        env.update(self.telemetry_env(task, ai_user, ticket_key))
        return env

    def telemetry_env(self, task: dict, ai_user: dict, ticket_key: str | None) -> dict[str, str]:
        """OTEL variables when the shared collector answers; none when it is down (AC33, AC34)."""
        obs = Observability(self.layout, "external")
        if not obs.collector_up():
            return {}
        return obs.step_env(
            {"app": "agenthub", "task_id": str(task["id"]), "ai_user": ai_user["handle"], "ticket": ticket_key or "none"}
        )

    # ------------------------------------------------------------ one turn
    def run_turn(
        self,
        task: dict,
        ai_user: dict,
        ticket_key: str | None,
        prompt: str,
        turn_n: int,
        resume_session: str | None,
        on_event: Callable[[dict], None],
        on_process: Callable[[subprocess.Popen], None],
        on_session: Callable[[str], None],
    ) -> TurnOutcome:
        tdir = self.task_dir(task["id"])
        ws = self.workspace(task["id"])
        settings = write_step_settings(self.layout, tdir / "settings.json", protected=self.config.protected_code)
        transcript = tdir / "log" / f"turn_{turn_n}.jsonl"
        # `--add-dir` takes several values, so it must not stand right before the prompt
        extra = [
            "--add-dir", str(self.config.private_dir),
            "--add-dir", str(self.config.orchestrator_dir),
            "--add-dir", str(self.reports_dir(task["id"])),
            "--json-schema", json.dumps(TURN_SCHEMA),
            "--append-system-prompt", task["system_prompt"],
        ]
        self.config.orchestrator_dir.mkdir(parents=True, exist_ok=True)
        structured: list[Any] = []

        def handle(ev: dict) -> None:
            if ev.get("type") == "result" and ev.get("structured_output") is not None:
                structured.append(ev["structured_output"])
            on_event(ev)

        try:
            res = run_step(
                layout=self.layout,
                prompt=prompt,
                cwd=ws,
                transcript=transcript,
                settings_file=settings,
                env=self.env(task, ai_user, ticket_key),
                permission_mode="bypassPermissions",
                model=task["model"],
                quiet=True,
                resume_session=resume_session,
                on_session=on_session,
                extra_args=extra,
                on_event=handle,
                on_process=on_process,
                new_process_group=True,
            )
        except (OSError, SystemExit) as e:
            return TurnOutcome(ok=False, error=f"could not start claude: {e}")
        out = valid_structured(res.raw_result.get("structured_output")) or (valid_structured(structured[-1]) if structured else None)
        stderr = _last_stderr(transcript)
        lost = bool(resume_session) and not res.ok and "no conversation found" in (stderr + res.result_text).lower()
        error = None
        if not res.ok:
            if res.rate_limited:
                when = _local_time(res.rate_limit_resets_at) if res.rate_limit_resets_at else "later"
                error = f"usage limit reached; it resets {when}"
            else:
                error = (res.result_text or stderr or f"claude exited with code {res.returncode}").strip()[-600:]
        return TurnOutcome(
            ok=res.ok,
            structured=out,
            result_text=res.result_text,
            session_id=res.session_id,
            tokens=res.tokens,
            error=error,
            rate_limit_resets_at=res.rate_limit_resets_at,
            session_lost=lost,
        )

    # ------------------------------------------------------------ login
    def login_status(self, fresh: bool = False) -> dict:
        """`claude auth status` of the login stored on this machine. Never raises (AC22)."""
        if not fresh and self._login and time.monotonic() - self._login[0] < LOGIN_CACHE_S:
            return self._login[1]
        status = self._read_login()
        self._login = (time.monotonic(), status)
        return status

    def _read_login(self) -> dict:
        out = {"logged_in": False, "method": None, "subscription": None, "expires_at": None, "detail": ""}
        try:
            r = subprocess.run(
                [self.config.claude_bin, "auth", "status"],
                capture_output=True, text=True, timeout=30, env=clean_env(dict(os.environ)), stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            out["detail"] = f"`{self.config.claude_bin}` was not found on this machine"
            return out
        except (subprocess.TimeoutExpired, OSError) as e:
            out["detail"] = f"`claude auth status` did not answer: {e}"
            return out
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            out["detail"] = (r.stdout or r.stderr).strip()[-300:] or f"`claude auth status` exited {r.returncode}"
            return out
        out["method"] = data.get("authMethod")
        out["subscription"] = data.get("subscriptionType")
        out["expires_at"] = data.get("loginExpiresAt")
        logged_in = bool(data.get("loggedIn"))
        if logged_in and out["expires_at"]:
            try:
                expiry = datetime.fromisoformat(str(out["expires_at"]).replace("Z", "+00:00"))
                if expiry <= datetime.now(timezone.utc):
                    logged_in = False
                    out["detail"] = "the stored Claude login has expired; run `claude auth login` in a terminal"
            except ValueError:
                pass
        if not data.get("loggedIn"):
            out["detail"] = "no Claude login is stored on this machine; run `claude auth login` in a terminal"
        out["logged_in"] = logged_in
        if logged_in:
            out["detail"] = "logged in"
        return out


def _last_stderr(transcript: Path) -> str:
    try:
        lines = transcript.read_text().splitlines()[-5:]
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "harness" and ev.get("event") == "stderr":
            return str(ev.get("text") or "")
    return ""


def _local_time(epoch: int) -> str:
    return "at " + datetime.fromtimestamp(epoch).strftime("%H:%M")

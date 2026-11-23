"""Commit and push the private folder (the `AgentHub-private` submodule) to its `main` (AC37)."""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

BRANCH = "main"


@dataclass
class SyncResult:
    changed: bool = False
    pushed: bool = False
    error: str | None = None


class PrivateSync:
    def __init__(self, private_dir: Path):
        self.dir = private_dir
        self._lock = threading.Lock()

    def _git(self, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=self.dir, capture_output=True, text=True, timeout=timeout,
            env={"GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes", **_base_env()},
        )

    def is_repo(self) -> bool:
        return (self.dir / ".git").exists()

    def prepare(self) -> None:
        """At app start: a checkout detached at or behind origin/main is put on main."""
        if not self.is_repo():
            return
        with self._lock:
            if self._git("symbolic-ref", "-q", "HEAD").returncode == 0:
                return
            if self._git("rev-parse", "--verify", "-q", f"origin/{BRANCH}").returncode != 0:
                return
            head = self._git("rev-parse", "HEAD").stdout.strip()
            behind = self._git("merge-base", "--is-ancestor", head, f"origin/{BRANCH}").returncode == 0
            if behind:
                self._git("checkout", "-q", "-B", BRANCH, f"origin/{BRANCH}")

    def sync(self, message: str) -> SyncResult:
        """Commit whatever changed and push it; a failure is returned, never raised, nothing is discarded."""
        if not self.is_repo():
            return SyncResult()
        with self._lock:
            try:
                return self._sync(message)
            except (subprocess.TimeoutExpired, OSError) as e:
                return SyncResult(error=str(e))

    def _sync(self, message: str) -> SyncResult:
        status = self._git("status", "--porcelain")
        if status.returncode != 0:
            return SyncResult(error=status.stderr.strip())
        changed = bool(status.stdout.strip())
        if changed:
            self._git("add", "-A")
            commit = self._git("commit", "-q", "-m", message or "update")
            if commit.returncode != 0:
                return SyncResult(changed=True, error=(commit.stderr or commit.stdout).strip()[-400:])
        has_upstream = self._git("rev-parse", "--verify", "-q", f"origin/{BRANCH}").returncode == 0
        if has_upstream:
            ahead = self._git("rev-list", "--count", f"origin/{BRANCH}..HEAD").stdout.strip()
            if ahead in ("", "0"):
                return SyncResult(changed=changed)
        push = self._git("push", "-q", "origin", f"HEAD:{BRANCH}")
        if push.returncode != 0:
            pull = self._git("pull", "-q", "--rebase", "origin", BRANCH)
            if pull.returncode != 0:
                self._git("rebase", "--abort")
                return SyncResult(changed=changed, error=(push.stderr or pull.stderr).strip()[-400:])
            push = self._git("push", "-q", "origin", f"HEAD:{BRANCH}")
            if push.returncode != 0:
                return SyncResult(changed=changed, error=push.stderr.strip()[-400:])
        return SyncResult(changed=changed, pushed=True)


def _base_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

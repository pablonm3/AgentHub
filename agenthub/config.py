"""Paths, port, models and external commands of one AgentHub server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from harness.paths import Layout

from .errors import HubError

REPO_ROOT = Path(__file__).resolve().parent.parent

MODELS = ["fable", "opus", "sonnet", "haiku"]  # aliases the `claude` CLI accepts for --model
DEFAULT_MODEL = "opus"
DEFAULT_PORT = 8787

# Folders of the app's own code that an AI user's session may not write: a change to AgentHub
# goes through a harness run in a worktree. `private/` and `data/` stay writable.
PROTECTED_CODE = ["harness", "agenthub", "web", "workflows", "skills", "agentmds/GENERAL.md"]


@dataclass
class Config:
    root: Path = REPO_ROOT
    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    private_dir: Path = field(default_factory=lambda: REPO_ROOT / "private")
    port: int = DEFAULT_PORT
    claude_bin: str = "claude"
    gh_bin: str = "gh"
    models: list[str] = field(default_factory=lambda: list(MODELS))

    @classmethod
    def from_env(cls, port: int | None = None) -> "Config":
        env = os.environ
        return cls(
            data_dir=Path(env.get("AGENTHUB_DATA_DIR") or REPO_ROOT / "data").resolve(),
            private_dir=Path(env.get("AGENTHUB_PRIVATE_DIR") or REPO_ROOT / "private").resolve(),
            port=port or int(env.get("AGENTHUB_PORT") or DEFAULT_PORT),
            claude_bin=env.get("AGENTHUB_CLAUDE_BIN") or "claude",
            gh_bin=env.get("AGENTHUB_GH_BIN") or "gh",
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "agenthub.db"

    @property
    def tasks_dir(self) -> Path:
        return self.data_dir / "tasks"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def orchestrator_dir(self) -> Path:
        """Data root of the harness copy: its tickets, runs, logs and worktrees."""
        return self.data_dir / "orchestrator"

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def protected_code(self) -> list[Path]:
        return [self.root / p for p in PROTECTED_CODE]

    def layout(self) -> Layout:
        return Layout(self.root, private_root=self.private_dir, data_root=self.orchestrator_dir)


def check_model(config: Config, model: object) -> None:
    """Refuse a model the `claude` CLI is not offered with (422)."""
    if model not in config.models:
        raise HubError(f"unknown model {model!r}; choices: {', '.join(config.models)}", 422)

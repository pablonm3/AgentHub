"""Harness root resolution and the fixed directory layout (spec section 3).

Three roots: the code root (harness source, workflows, general skills, GENERAL.md), the private
root (manifest, project AGENTS.md files and skills) and the data root (tickets, runs, logs,
worktrees, archive). The private and data roots default to the code root.
"""

from __future__ import annotations

import os
from pathlib import Path

MANIFEST = "harness.yaml"


def find_root(start: Path | None = None) -> Path:
    """Locate the harness root.

    Order: HARNESS_ROOT env var, then the first ancestor of `start` (default cwd)
    holding harness.yaml, then the parent of this package.
    """
    env = os.environ.get("HARNESS_ROOT")
    if env:
        return Path(env).resolve()
    cur = (start or Path.cwd()).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / MANIFEST).is_file():
            return cand
    pkg_parent = Path(__file__).resolve().parent.parent
    if (pkg_parent / MANIFEST).is_file():
        return pkg_parent
    raise SystemExit(
        f"harness: cannot find {MANIFEST}; run from inside the harness or set HARNESS_ROOT"
    )


class Layout:
    """Paths under the three roots. Every path is absolute."""

    def __init__(self, root: Path, private_root: Path | None = None, data_root: Path | None = None):
        self.root = root
        self.private_root = private_root or root
        self.data_root = data_root or root
        # code root
        self.general_md = root / "agentmds" / "GENERAL.md"
        self.skills = root / "skills"
        self.general_skills = root / "skills" / "general"
        self.workflows = root / "workflows"
        self.observability = root / "observability"
        self.docs = root / "docs"
        self.harness_src = root / "harness"
        # private root
        self.manifest = self.private_root / MANIFEST
        self.agentmds = self.private_root / "agentmds"
        self.project_skills = self.private_root / "skills" / "projects"
        # data root
        self.tickets = self.data_root / "tickets"
        self.runs = self.data_root / "runs"
        self.workflow_logs = self.data_root / "workflow_logs"
        self.worktrees = self.data_root / "worktrees"
        self.archived = self.data_root / "archived"

    def run_dir(self, run_id: str) -> Path:
        return self.runs / run_id

    def run_log_dir(self, run_id: str) -> Path:
        return self.runs / run_id / "log"

    def state_file(self, run_id: str) -> Path:
        return self.runs / run_id / "state.json"

    def workflow_log(self, run_id: str) -> Path:
        return self.workflow_logs / f"{run_id}.log"

    def ticket(self, feature: str) -> Path:
        return self.tickets / f"{feature}.md"

    def base_clone(self, project: str) -> Path:
        return self.worktrees / project / ".base"

    def worktree(self, project: str, run_id: str) -> Path:
        return self.worktrees / project / run_id

    def project_agentsmd(self, project: str) -> Path:
        return self.agentmds / project / "AGENTS.md"

    def project_skills_dir(self, project: str) -> Path:
        return self.project_skills / project

    def workflow_dir(self, name: str) -> Path:
        return self.workflows / name

    def private_path(self, rel: str | Path) -> Path:
        """A path of the manifest (a project's `agentsmd`, `skills`) under the private root."""
        return self.private_root / rel

    def rel(self, p: Path) -> str:
        """Path relative to the root when inside it, else as given."""
        try:
            return str(Path(p).resolve().relative_to(self.root))
        except ValueError:
            return str(p)

    # Paths a run may never write (spec 5.1, write boundary). Absolute.
    def protected_paths(self) -> list[Path]:
        paths = [self.skills, self.workflows, self.general_md, self.manifest, self.harness_src]
        if not self.project_skills.is_relative_to(self.skills):
            paths.insert(1, self.project_skills)
        return paths


def layout_from_env(start: Path | None = None) -> Layout:
    """The layout named by HARNESS_ROOT, HARNESS_PRIVATE_ROOT and HARNESS_DATA_ROOT.

    Without HARNESS_ROOT the code root is the parent of this package when a private root is set
    (the manifest lives there), and otherwise the root find_root locates from `start`.
    """
    private = os.environ.get("HARNESS_PRIVATE_ROOT")
    data = os.environ.get("HARNESS_DATA_ROOT")
    if os.environ.get("HARNESS_ROOT") or not private:
        root = find_root(start)
    else:
        root = Path(__file__).resolve().parent.parent
    return Layout(
        root,
        private_root=Path(private).resolve() if private else None,
        data_root=Path(data).resolve() if data else None,
    )

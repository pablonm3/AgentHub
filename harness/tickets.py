"""Ticket files: tickets/<feature>.md with frontmatter `project` and `base_branch` (spec 2, 3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .naming import read_frontmatter, validate_feature
from .paths import Layout


@dataclass
class Ticket:
    feature: str
    path: Path
    project: str
    base_branch: str | None
    title: str


def load_ticket(layout: Layout, feature: str) -> Ticket:
    validate_feature(feature)
    path = layout.ticket(feature)
    if not path.is_file():
        raise SystemExit(f"harness: no ticket at {layout.rel(path)}")
    fm = read_frontmatter(path)
    project = fm.get("project")
    if not project:
        raise SystemExit(f"harness: {layout.rel(path)} must state `project:` in its frontmatter")
    title = ""
    for line in path.read_text().splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    base = fm.get("base_branch")
    return Ticket(feature=feature, path=path, project=str(project), base_branch=str(base) if base else None, title=title)

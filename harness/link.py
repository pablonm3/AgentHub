"""`agenthub-harness link <project> <worktree>`: expose skills and instructions to Claude Code
through symlinks in the worktree (spec 6.1, 6.2). Nothing is written outside the worktree.

Skills:          <wt>/.claude/skills/<name> → skills/general/<name>, then
                 <wt>/.claude/skills/<name> → <private root>/skills/projects/<project>/<name>
                 (a project skill replaces a general one of the same name); `.claude/skills/`
                 goes into the worktree's git exclude
Instructions:    <wt>/CLAUDE.md importing GENERAL.md, the project AGENTS.md and
                 <private root>/agents.md when it exists
Codex (--codex): <wt>/.agents/skills/<name> links and <wt>/AGENTS.md link, skipping paths
                 the project already tracks.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import Manifest
from .paths import Layout
from .worktree import git

SKILLS_EXCLUDE = ".claude/skills/"


def _skill_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def _symlink(target: Path, link: Path, report: list[str]) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() == target.resolve():
            return
        link.unlink()
    elif link.exists():
        report.append(f"skip  {link} (exists and is not a symlink)")
        return
    os.symlink(target, link)
    report.append(f"link  {link} → {target}")


def _ensure_import_line(md: Path, import_path: Path, report: list[str]) -> None:
    line = f"@{import_path}"
    existing = md.read_text() if md.is_file() else ""
    if line in existing.splitlines():
        return
    md.parent.mkdir(parents=True, exist_ok=True)
    with open(md, "a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(line + "\n")
    report.append(f"import {line} in {md}")


def _exclude_skills(worktree: Path, report: list[str]) -> None:
    """Keep the skill links out of `git status`; a linked worktree shares the exclude file of its repository."""
    rel = git(["rev-parse", "--git-path", "info/exclude"], worktree).stdout.strip()
    exclude = worktree / rel
    existing = exclude.read_text() if exclude.is_file() else ""
    if SKILLS_EXCLUDE in existing.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with open(exclude, "a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(SKILLS_EXCLUDE + "\n")
    report.append(f"exclude {SKILLS_EXCLUDE} in {exclude}")


def link_worktree(layout: Layout, manifest: Manifest, project: str, worktree: Path, codex: bool = False) -> list[str]:
    proj = manifest.project(project)
    report: list[str] = []
    # a project skill replaces a general skill of the same name
    skills = {s.name: s for s in _skill_dirs(layout.general_skills) + _skill_dirs(layout.private_path(proj.skills))}
    for skill in skills.values():
        _symlink(skill, worktree / ".claude" / "skills" / skill.name, report)
    _exclude_skills(worktree, report)
    agentsmd = layout.private_path(proj.agentsmd)
    private_md = layout.private_root / "agents.md"
    imports = [layout.general_md, agentsmd] + ([private_md] if private_md.is_file() else [])
    text = "".join(f"@{p}\n" for p in imports)
    claude_md = worktree / "CLAUDE.md"
    if claude_md.exists() and not claude_md.is_symlink() and claude_md.read_text() != text:
        # keep a CLAUDE.md the project has, just add the imports
        for p in imports:
            _ensure_import_line(claude_md, p, report)
    elif not claude_md.exists() or claude_md.read_text() != text:
        claude_md.write_text(text)
        report.append(f"write {claude_md}")
    if codex:
        for skill in skills.values():
            _symlink(skill, worktree / ".agents" / "skills" / skill.name, report)
        _symlink(agentsmd, worktree / "AGENTS.md", report)
    return report

"""Git helpers: base clone, worktree creation, setup list, commit ranges (spec 6.3, step 2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Project
from .paths import Layout


class GitError(SystemExit):
    pass


def git(args: list[str], cwd: Path, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise GitError(f"harness: git {' '.join(args)} failed in {cwd}:\n{(r.stderr or r.stdout).strip()}")
    return r


def harness_commit(layout: Layout) -> str:
    """Short commit of the harness repo, with `-dirty` when the tree has changes."""
    try:
        sha = git(["rev-parse", "--short", "HEAD"], layout.root).stdout.strip()
        dirty = git(["status", "--porcelain", "--untracked-files=no"], layout.root).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (GitError, FileNotFoundError):
        return "unknown"


def ensure_base_clone(layout: Layout, project: Project) -> Path:
    base = layout.base_clone(project.name)
    if (base / ".git").exists():
        return base
    if not project.repo:
        raise GitError(f"harness: project {project.name} has no repo url in harness.yaml")
    base.parent.mkdir(parents=True, exist_ok=True)
    print(f"cloning {project.repo} → {layout.rel(base)}")
    subprocess.run(["git", "clone", project.repo, str(base)], check=True)
    return base


def fetch(base: Path) -> None:
    git(["fetch", "--prune", "origin"], base)


def ref_exists(base: Path, ref: str) -> bool:
    return git(["rev-parse", "--verify", "--quiet", ref], base, check=False).returncode == 0


def add_worktree(base: Path, worktree: Path, branch: str, base_branch: str) -> None:
    """Create worktree on a new branch from origin/<base_branch> (fallback: local branch)."""
    if worktree.exists():
        return
    start = f"origin/{base_branch}"
    if not ref_exists(base, start):
        if ref_exists(base, base_branch):
            start = base_branch
        else:
            raise GitError(f"harness: base branch {base_branch!r} not found in {base} (tried origin/{base_branch})")
    worktree.parent.mkdir(parents=True, exist_ok=True)
    if ref_exists(base, f"refs/heads/{branch}"):
        git(["worktree", "add", str(worktree), branch], base)
    else:
        git(["worktree", "add", str(worktree), "-b", branch, start], base)


def remove_worktree(base: Path, worktree: Path, force: bool = False) -> None:
    args = ["worktree", "remove", str(worktree)]
    if force:
        args.append("--force")
    git(args, base)


def run_setup(worktree: Path, commands: list[str], log_path: Path) -> tuple[bool, str, str]:
    """Run the project's setup list in order from the worktree root.

    Returns (ok, failing_command, tail_of_output). Output goes to log_path.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as log:
        for cmd in commands:
            log.write(f"\n$ {cmd}\n")
            log.flush()
            r = subprocess.run(cmd, shell=True, cwd=worktree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            log.write(r.stdout or "")
            log.write(f"\n[exit {r.returncode}]\n")
            if r.returncode != 0:
                return False, cmd, (r.stdout or "")[-2000:]
    return True, "", ""


def push_branch(worktree: Path, branch: str) -> str:
    """Publish the run's branch to origin and track it; returns the short commit pushed.

    A plain push, never forced: a remote branch that moved makes it fail.
    """
    git(["push", "--set-upstream", "origin", branch], worktree)
    return git(["rev-parse", "--short", branch], worktree).stdout.strip()


def head(worktree: Path) -> str:
    return git(["rev-parse", "HEAD"], worktree).stdout.strip()


def count_commits(worktree: Path, since: str, until: str = "HEAD") -> int:
    if not since:
        return 0
    r = git(["rev-list", "--count", f"{since}..{until}"], worktree, check=False)
    return int(r.stdout.strip() or 0) if r.returncode == 0 else 0


def merge_base_count(worktree: Path, base_branch: str) -> int:
    for ref in (f"origin/{base_branch}", base_branch):
        if ref_exists(worktree, ref):
            r = git(["rev-list", "--count", f"{ref}..HEAD"], worktree, check=False)
            if r.returncode == 0:
                return int(r.stdout.strip() or 0)
    return 0


def is_ancestor(worktree: Path, commit: str, of: str = "HEAD") -> bool:
    return git(["merge-base", "--is-ancestor", commit, of], worktree, check=False).returncode == 0


def changed_lines(worktree: Path, rev_range: str) -> int | None:
    """Lines added plus lines deleted by `git diff <rev_range>`; None when git cannot resolve the range."""
    r = git(["diff", "--numstat", rev_range], worktree, check=False)
    if r.returncode != 0:
        return None
    total = 0
    for line in r.stdout.splitlines():
        added, deleted = line.split("\t")[:2]
        # a binary file reports "-" for both counts
        total += (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
    return total


def branch_changed_lines(worktree: Path, base_branch: str) -> int | None:
    """`changed_lines` of the whole branch, from its merge base with the base branch to HEAD."""
    for ref in (f"origin/{base_branch}", base_branch):
        if ref_exists(worktree, ref):
            return changed_lines(worktree, f"{ref}...HEAD")
    return None


def is_dirty(worktree: Path) -> bool:
    return bool(git(["status", "--porcelain"], worktree).stdout.strip())

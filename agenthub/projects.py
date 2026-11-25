"""Projects registered in the harness copy's manifest (`private/harness.yaml`), and new ones.

A new project is registered with the copy's own `project_add`. Given a repo URL, that repository is
used (AC39); an empty one (no refs at all) first gets a commit on `main` holding only a README.md
that names the project. Without a URL, a private GitHub repository named after the project is
created first with the `gh` command this machine is logged in with (AC43), and only when
`gh auth status` says it can. The app never deletes a repository, nor a commit it pushed.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from harness.config import ConfigError, dump_yaml, load_manifest, load_yaml
from harness.project import has_placeholders, project_add

if TYPE_CHECKING:
    from .hub import Hub

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^\s]+$")  # user@host:path
FIRST_BRANCH = "main"  # the branch an empty repository's first commit is pushed to
FIRST_COMMIT_TIMEOUT_S = 60

CANNOT_CREATE = {
    "not_installed": "`gh` is not installed on this machine, so no GitHub repository can be created; "
                     "enter a repo URL instead",
    "not_logged_in": "`gh` is not logged in to github.com on this machine (run `gh auth login` there), "
                     "so no GitHub repository can be created; enter a repo URL instead",
    "unknown": "`gh` did not say whether it is logged in on this machine, so no GitHub repository "
               "was created; enter a repo URL instead",
}


class ProjectError(Exception):
    def __init__(self, message: str, status: int = 422, created_repo: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.created_repo = created_repo

    def with_created_repo(self, url: str) -> "ProjectError":
        """The same error, for a repository that was already created: it is kept, and named."""
        if self.created_repo:
            return self
        return ProjectError(
            f"{self.message} The GitHub repository {url} was created and is kept; "
            "enter its URL in the form to register it.",
            self.status,
            created_repo=url,
        )


class NoBranchError(ProjectError):
    """The repository answered, and its HEAD names no existing branch."""


def check_repo_url(url: str) -> str:
    """Accept https://…, ssh://… and user@host:path; refuse local paths, file:// and other transports."""
    url = url.strip()
    if not url or url.startswith("-") or any(c.isspace() for c in url):
        raise ProjectError("the repo URL is not a git URL AgentHub accepts (https://…, ssh://… or user@host:path)")
    if url.startswith("https://") or url.startswith("ssh://") or SCP_LIKE_RE.match(url):
        return url
    raise ProjectError("the repo URL is not a git URL AgentHub accepts (https://…, ssh://… or user@host:path)")


def _git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    return env


def _gh_env() -> dict[str, str]:
    return {**os.environ, "GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1"}


def _ls_remote(url: str, *patterns: str, symref: bool = False) -> str:
    """Stdout of `git ls-remote` for `url`. Raises ProjectError when the repository does not answer."""
    try:
        r = subprocess.run(
            ["git", "ls-remote", *(["--symref"] if symref else []), "--", url, *patterns],
            capture_output=True, text=True, timeout=30, env=_git_env(), stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise ProjectError(f"the repository {url} did not answer within 30 s")
    if r.returncode != 0:
        raise ProjectError(f"the repository {url} cannot be reached: {_tail(r)}")
    return r.stdout


def default_branch(url: str) -> str:
    """The repository's default branch, from `git ls-remote --symref`. Raises ProjectError."""
    for line in _ls_remote(url, "HEAD", symref=True).splitlines():
        m = re.match(r"^ref:\s+refs/heads/(\S+)\s+HEAD$", line.strip())
        if m:
            return m.group(1)
    raise NoBranchError(f"the repository {url} has no branch to start from")


def is_empty(url: str) -> bool:
    """True when the repository has no refs at all. Raises ProjectError."""
    return not _ls_remote(url).strip()


def push_first_commit(url: str, name: str) -> None:
    """Give an empty repository its first commit: a README.md naming the project, on `main`. Raises ProjectError.

    The commit carries this machine's git identity. The push is never forced, so a repository that
    got a ref in the meantime refuses it.
    """
    with tempfile.TemporaryDirectory(prefix="agenthub-first-commit-") as work:
        Path(work, "README.md").write_text(f"# {name}\n")
        for args in (
            ["init", "-q"],
            ["add", "README.md"],
            ["commit", "-q", "-m", "Initial commit"],
            ["push", "-q", "--", url, f"HEAD:refs/heads/{FIRST_BRANCH}"],
        ):
            reason = _git_step_failure(work, args)
            if reason:
                raise ProjectError(f"the first commit could not be pushed to the repository {url}: {reason}")


def _git_step_failure(cwd: str, args: list[str]) -> str | None:
    """Run `git <args>` in `cwd`; None when it worked, else git's reason."""
    try:
        r = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=FIRST_COMMIT_TIMEOUT_S, env=_git_env(), stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return f"`git {args[0]}` did not finish within {FIRST_COMMIT_TIMEOUT_S} s"
    if r.returncode == 0:
        return None
    return _tail(r) or f"`git {args[0]}` exited {r.returncode}"


def _tail(r: subprocess.CompletedProcess) -> str:
    """The end of what a failed git command said: its reason."""
    return (r.stderr or r.stdout).strip()[-300:]


class Projects:
    branch_retries = 5      # a repository can take a moment to answer after its creation
    branch_retry_wait_s = 2.0
    github_cache_s = 30.0   # how long an answer of `gh auth status` is kept
    github_timeout_s = 10.0

    def __init__(self, hub: "Hub"):
        self.hub = hub
        self.config = hub.config
        self.layout = hub.config.layout()
        self._lock = threading.Lock()
        self._github: tuple[float, dict] | None = None

    # ------------------------------------------------------------ reading
    def list_projects(self) -> list[dict]:
        if not self.layout.manifest.is_file():
            return []
        try:
            manifest = load_manifest(self.layout)
        except ConfigError:
            return []
        out = []
        for name, p in manifest.projects.items():
            agentsmd = self.layout.private_path(p.agentsmd)
            out.append({
                "name": name,
                "default_base": p.default_base,
                "repo": p.repo,
                "ready": agentsmd.is_file() and not has_placeholders(agentsmd),
            })
        return out

    def get(self, name: str | None) -> dict | None:
        if not name:
            return None
        return next((p for p in self.list_projects() if p["name"] == name), None)

    # ------------------------------------------------------------ registration
    def register(self, name: str, repo_url: str | None = None) -> tuple[dict, str | None]:
        """Register a new project; returns (project, warning). Raises ProjectError, leaving nothing behind here."""
        name = (name or "").strip()
        repo_url = (repo_url or "").strip() or None
        with self._lock:
            self._check_name(name)
            created_web_url = None
            if repo_url:
                repo = check_repo_url(repo_url)
                base = self._base_of_given_repo(name, repo)
            else:
                self._require_github()
                repo, created_web_url = self._create_github_repo(name)
                try:
                    base = self._wait_for_branch(repo)
                except ProjectError as e:
                    raise e.with_created_repo(created_web_url)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    project_add(self.layout, name, repo, base, no_chat=True)
            except (SystemExit, subprocess.CalledProcessError, OSError, ConfigError) as e:
                self._remove_traces(name)
                error = ProjectError(f"the project {name} could not be registered: {_reason(e)}", 422)
                raise error.with_created_repo(created_web_url) if created_web_url else error
        sync = self.hub.private.sync(f"register project {name}")
        self.hub.events.publish("projects")
        return self.get(name), (f"the private folder could not be pushed: {sync.error}" if sync.error else None)

    def _check_name(self, name: str) -> None:
        if not NAME_RE.match(name):
            raise ProjectError("a project name has 1 to 64 letters, digits, '-' or '_', and starts with a letter or digit")
        if any(p["name"].lower() == name.lower() for p in self.list_projects()):
            raise ProjectError(f"a project named {name} is already registered", 409)

    def _base_of_given_repo(self, name: str, repo: str) -> str:
        """The branch the project starts from; an empty repository first gets a README commit on `main`."""
        try:
            return default_branch(repo)
        except NoBranchError:
            if not is_empty(repo):
                raise  # it has branches, but HEAD names a missing one: nothing is pushed to it
        push_first_commit(repo, name)
        return FIRST_BRANCH

    def _wait_for_branch(self, url: str) -> str:
        for attempt in range(self.branch_retries):
            try:
                return default_branch(url)
            except ProjectError:
                if attempt == self.branch_retries - 1:
                    raise
                time.sleep(self.branch_retry_wait_s)
        raise AssertionError("unreachable")

    def _remove_traces(self, name: str) -> None:
        """Undo a failed registration on this machine: manifest entry, private folders, base clone."""
        raw = load_yaml(self.layout.manifest)
        entry = (raw.get("projects") or {}).pop(name, None)
        if entry is not None:
            dump_yaml(raw, self.layout.manifest)
        for rel in (f"agentmds/{name}", f"skills/projects/{name}"):
            shutil.rmtree(self.layout.private_path(rel), ignore_errors=True)
        shutil.rmtree(self.layout.base_clone(name), ignore_errors=True)

    # ------------------------------------------------------------ GitHub
    def github_status(self, fresh: bool = False) -> dict:
        """Whether `gh` on this machine can create a GitHub repository, and why not. Never raises."""
        if not fresh and self._github and time.monotonic() - self._github[0] < self.github_cache_s:
            return self._github[1]
        status = self._read_github()
        self._github = (time.monotonic(), status)
        return status

    def _read_github(self) -> dict:
        # Not `--json`: with it `gh auth status` exits 0 whatever the login state.
        try:
            r = subprocess.run(
                [self.config.gh_bin, "auth", "status", "--hostname", "github.com"],
                capture_output=True, text=True, timeout=self.github_timeout_s, env=_gh_env(), stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return _cannot_create("not_installed")
        except (subprocess.TimeoutExpired, OSError):
            return _cannot_create("unknown")
        if r.returncode == 0:
            return {"can_create": True, "reason": None}
        # gh exits 1 for a failed command and 4 for "requires authentication".
        return _cannot_create("not_logged_in" if r.returncode in (1, 4) else "unknown")

    def _require_github(self) -> None:
        """Refuse a create without URL when `gh` cannot make the repository: the form's knowledge can be stale."""
        status = self.github_status(fresh=True)
        if not status["can_create"]:
            raise ProjectError(CANNOT_CREATE[status["reason"]], 502)

    def create_github_repo(self, name: str) -> str:
        """Create a private GitHub repository for the project; returns its clone URL."""
        return self._create_github_repo(name)[0]

    def _create_github_repo(self, name: str) -> tuple[str, str]:
        env = _gh_env()
        made = self._gh(
            ["repo", "create", name, "--private", "--add-readme", "--description", f"{name} (created by AgentHub)"],
            env, limit=60, creating=True,
        )
        lines = made.stdout.strip().splitlines()
        web_url = lines[-1].strip() if lines else ""
        if not web_url:
            raise ProjectError(f"`gh repo create` printed no URL; the repository {name} may exist on GitHub", 502)
        try:
            urls = json.loads(self._gh(["repo", "view", web_url, "--json", "sshUrl,url"], env, limit=30).stdout)
            protocol = self._gh(["config", "get", "git_protocol", "--host", "github.com"], env, limit=10).stdout.strip()
        except (ProjectError, json.JSONDecodeError) as e:
            error = e if isinstance(e, ProjectError) else ProjectError(f"`gh repo view` answered no JSON: {e}", 502)
            raise error.with_created_repo(web_url)
        return (urls["sshUrl"] if protocol == "ssh" else urls["url"]), web_url

    def _gh(self, args: list[str], env: dict[str, str], limit: float, creating: bool = False) -> subprocess.CompletedProcess:
        try:
            r = subprocess.run(
                [self.config.gh_bin, *args], capture_output=True, text=True, timeout=limit, env=env, stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            raise ProjectError(CANNOT_CREATE["not_installed"], 502)
        except subprocess.TimeoutExpired:
            extra = " The repository may exist on GitHub all the same." if creating else ""
            raise ProjectError(f"`gh {args[0]} {args[1]}` did not answer within {int(limit)} s.{extra}", 502)
        if r.returncode != 0:
            message = (r.stderr or r.stdout).strip()[-400:] or f"`gh {args[0]} {args[1]}` exited {r.returncode}"
            if creating and "already exists" in message.lower():
                message += " Enter that repository's URL in the form to register it."
            raise ProjectError(message, 502)
        return r


def _cannot_create(reason: str) -> dict:
    return {"can_create": False, "reason": reason}


def _reason(e: BaseException) -> str:
    if isinstance(e, subprocess.CalledProcessError):
        return f"`{' '.join(map(str, e.cmd[:2]))}` exited {e.returncode}"
    return str(e) or type(e).__name__

"""Projects registered in the harness copy's manifest (`private/harness.yaml`), and new ones.

A new project is registered with the copy's own `project_add`. Given a repo URL, that repository is
used (AC39). Without one, a private GitHub repository named after the project is created first with
the `gh` command this machine is logged in with (AC43). The app never deletes a repository.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import TYPE_CHECKING

from harness.config import ConfigError, dump_yaml, load_manifest, load_yaml
from harness.project import has_placeholders, project_add

if TYPE_CHECKING:
    from .hub import Hub

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^\s]+$")  # user@host:path


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


def default_branch(url: str) -> str:
    """The repository's default branch, from `git ls-remote --symref`. Raises ProjectError."""
    try:
        r = subprocess.run(
            ["git", "ls-remote", "--symref", "--", url, "HEAD"],
            capture_output=True, text=True, timeout=30, env=_git_env(), stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise ProjectError(f"the repository {url} did not answer within 30 s")
    if r.returncode != 0:
        raise ProjectError(f"the repository {url} cannot be reached: {(r.stderr or r.stdout).strip()[-300:]}")
    for line in r.stdout.splitlines():
        m = re.match(r"^ref:\s+refs/heads/(\S+)\s+HEAD$", line.strip())
        if m:
            return m.group(1)
    raise ProjectError(f"the repository {url} has no branch to start from")


class Projects:
    branch_retries = 5      # a repository can take a moment to answer after its creation
    branch_retry_wait_s = 2.0

    def __init__(self, hub: "Hub"):
        self.hub = hub
        self.config = hub.config
        self.layout = hub.config.layout()
        self._lock = threading.Lock()

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
                base = default_branch(repo)
            else:
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
    def create_github_repo(self, name: str) -> str:
        """Create a private GitHub repository for the project; returns its clone URL."""
        return self._create_github_repo(name)[0]

    def _create_github_repo(self, name: str) -> tuple[str, str]:
        env = {**os.environ, "GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1"}
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
            raise ProjectError("`gh` is not installed on this machine, so no GitHub repository can be created; enter a repo URL instead", 502)
        except subprocess.TimeoutExpired:
            extra = " The repository may exist on GitHub all the same." if creating else ""
            raise ProjectError(f"`gh {args[0]} {args[1]}` did not answer within {int(limit)} s.{extra}", 502)
        if r.returncode != 0:
            message = (r.stderr or r.stdout).strip()[-400:] or f"`gh {args[0]} {args[1]}` exited {r.returncode}"
            if creating and "already exists" in message.lower():
                message += " Enter that repository's URL in the form to register it."
            raise ProjectError(message, 502)
        return r


def _reason(e: BaseException) -> str:
    if isinstance(e, subprocess.CalledProcessError):
        return f"`{' '.join(map(str, e.cmd[:2]))}` exited {e.returncode}"
    return str(e) or type(e).__name__

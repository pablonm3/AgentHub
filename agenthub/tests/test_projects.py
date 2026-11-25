"""Registered projects and new ones, with a given repo URL (AC39) or a created private repo (AC43),
an empty repository's first commit, and whether `gh` can create a repository."""

import subprocess

import pytest
import yaml

from agenthub import projects as projects_module
from agenthub.projects import ProjectError, Projects, check_repo_url
from agenthub.tests.serve_fake import make_bare_repo, make_empty_repo


def _manifest(env):
    return yaml.safe_load((env.private / "harness.yaml").read_text())["projects"]


def _remote_files(env):
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"], cwd=env.private_remote,
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def _git_out(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def _refs(repo):
    return _git_out(repo, "for-each-ref", "--format=%(refname) %(objectname)")


def _commit_count(repo, ref="main"):
    return int(_git_out(repo, "rev-list", "--count", ref))


def _without_gh(app, tmp_path):
    """`gh` is not installed: the command it is started with does not exist."""
    app.config.gh_bin = str(tmp_path / "no-gh" / "gh")


def _state(app, env, name):
    layout = app.config.layout()
    return {
        "entry": name in _manifest(env),
        "agentsmd": (env.private / "agentmds" / name).exists(),
        "skills": (env.private / "skills" / "projects" / name).exists(),
        "clone": layout.base_clone(name).exists(),
    }


def test_list_projects_reports_repo_and_readiness(app):
    listed = {p["name"]: p for p in app.hub.projects.list_projects()}
    assert listed["demo"]["ready"] is True and listed["draft"]["ready"] is False
    assert listed["demo"]["repo"].endswith("demo-remote.git") and listed["demo"]["default_base"] == "main"


@pytest.mark.parametrize("url", ["https://github.com/a/b.git", "ssh://git@host/a/b.git", "git@github.com:a/b.git"])
def test_check_repo_url_accepts_the_three_forms(url):
    assert check_repo_url(url) == url


@pytest.mark.parametrize("url", ["/tmp/repo.git", "file:///tmp/repo.git", "ext::sh -c x", "-uhttps://x", "git://host/x", ""])
def test_check_repo_url_refuses_other_forms(url):
    with pytest.raises(ProjectError):
        check_repo_url(url)


@pytest.mark.parametrize("gh", ["fake", "missing"])
def test_register_with_a_url(app, env, monkeypatch, tmp_path, gh):
    if gh == "missing":
        _without_gh(app, tmp_path)
    remote = make_bare_repo(tmp_path / "given.git", {"README.md": "x"}, branch="trunk")
    monkeypatch.setattr(projects_module, "check_repo_url", lambda url: url)
    project, warning = app.hub.projects.register("demo3", str(remote))
    assert warning is None
    assert project == {"name": "demo3", "default_base": "trunk", "repo": str(remote), "ready": False}
    assert _state(app, env, "demo3") == {"entry": True, "agentsmd": True, "skills": True, "clone": True}
    assert "TODO(onboard)" in (env.private / "agentmds" / "demo3" / "AGENTS.md").read_text()
    assert "agentmds/demo3/AGENTS.md" in _remote_files(env)
    assert _commit_count(remote, "trunk") == 1  # no commit added to a repository that has a branch
    assert env.gh_log() == []


@pytest.mark.parametrize("gh", ["fake", "missing"])
def test_an_empty_repo_gets_a_first_readme_commit_on_main(app, env, monkeypatch, tmp_path, gh):
    if gh == "missing":
        _without_gh(app, tmp_path)
    remote = make_empty_repo(tmp_path / "empty.git")
    monkeypatch.setattr(projects_module, "check_repo_url", lambda url: url)
    project, warning = app.hub.projects.register("empty1", str(remote))
    assert warning is None
    assert project == {"name": "empty1", "default_base": "main", "repo": str(remote), "ready": False}
    assert _commit_count(remote) == 1
    assert _git_out(remote, "ls-tree", "-r", "--name-only", "main").splitlines() == ["README.md"]
    assert "empty1" in _git_out(remote, "show", "main:README.md")
    clone = app.config.layout().base_clone("empty1")
    assert _git_out(clone, "rev-parse", "origin/main") == _git_out(remote, "rev-parse", "main")
    assert env.gh_log() == []


def test_a_failed_first_push_registers_nothing(app, env, monkeypatch, tmp_path):
    remote = make_empty_repo(tmp_path / "declined.git")
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    monkeypatch.setattr(projects_module, "check_repo_url", lambda url: url)
    with pytest.raises(ProjectError) as e:
        app.hub.projects.register("declined", str(remote))
    assert str(remote) in e.value.message and "first commit could not be pushed" in e.value.message
    assert "pre-receive hook declined" in e.value.message
    assert _state(app, env, "declined") == {"entry": False, "agentsmd": False, "skills": False, "clone": False}
    assert _refs(remote) == ""


def test_a_repo_whose_head_names_a_missing_branch_is_refused_and_untouched(app, env, monkeypatch, tmp_path):
    remote = make_bare_repo(tmp_path / "dangling.git", {"README.md": "x"}, branch="dev")
    _git_out(remote, "symbolic-ref", "HEAD", "refs/heads/missing")
    before = _refs(remote)
    monkeypatch.setattr(projects_module, "check_repo_url", lambda url: url)
    with pytest.raises(ProjectError) as e:
        app.hub.projects.register("dangling", str(remote))
    assert e.value.status == 422 and "has no branch to start from" in e.value.message
    assert _refs(remote) == before
    assert _state(app, env, "dangling") == {"entry": False, "agentsmd": False, "skills": False, "clone": False}


def test_a_failed_registration_after_the_first_push_keeps_the_commit_and_a_retry_works(app, env, monkeypatch, tmp_path):
    remote = make_empty_repo(tmp_path / "retry.git")
    monkeypatch.setattr(projects_module, "check_repo_url", lambda url: url)
    real_project_add = projects_module.project_add

    def fail_clone(*args, **kwargs):
        raise subprocess.CalledProcessError(128, ["git", "clone"])

    monkeypatch.setattr(projects_module, "project_add", lambda layout, name, repo, base, no_chat=True: (
        _write_entry(env, name, repo), fail_clone()))
    with pytest.raises(ProjectError):
        app.hub.projects.register("retry", str(remote))
    assert _state(app, env, "retry") == {"entry": False, "agentsmd": False, "skills": False, "clone": False}
    assert _commit_count(remote) == 1  # AgentHub never deletes what it pushed

    monkeypatch.setattr(projects_module, "project_add", real_project_add)
    project, _ = app.hub.projects.register("retry", str(remote))
    assert project["default_base"] == "main"
    assert _commit_count(remote) == 1


def test_register_without_a_url_creates_a_private_github_repo(app, env):
    project, warning = app.hub.projects.register("demo2")
    log = env.gh_log()
    creates = [c for c in log if c["argv"][:2] == ["repo", "create"]]
    assert len(creates) == 1
    argv = creates[0]["argv"]
    assert argv[2] == "demo2" and "--private" in argv and "--add-readme" in argv
    assert "--public" not in argv and "--internal" not in argv
    assert all(c["GH_HOST"] == "github.com" for c in log)
    entry = _manifest(env)["demo2"]
    assert entry["repo"] == str(env.gh_dir / "repos" / "demo2.git") and entry["default_base"] == "main"
    assert project["repo"] == entry["repo"]
    assert _state(app, env, "demo2") == {"entry": True, "agentsmd": True, "skills": True, "clone": True}
    assert "agentmds/demo2/AGENTS.md" in _remote_files(env)


@pytest.mark.parametrize("name", ["bad name", "-x", "", "a" * 65, "DEMO"])
def test_bad_or_taken_names_are_refused_before_anything(app, env, name):
    with pytest.raises(ProjectError) as e:
        app.hub.projects.register(name)
    assert e.value.status in (409, 422)
    assert env.gh_log() == []
    assert set(_manifest(env)) == {"demo", "draft"}


def test_refused_or_unreachable_urls_leave_nothing(app, env, tmp_path):
    with pytest.raises(ProjectError):
        app.hub.projects.register("p1", str(tmp_path))  # a local path
    with pytest.raises(ProjectError) as e:
        app.hub.projects.register("p2", "ssh://git@127.0.0.1:1/none.git")
    assert "cannot be reached" in e.value.message
    assert set(_manifest(env)) == {"demo", "draft"}
    assert not (env.private / "agentmds" / "p2").exists()


@pytest.mark.parametrize("switch, text", [("name_taken", "already exists"), ("not_logged_in", "gh auth login")])
def test_gh_refusals_are_502_with_its_message(app, env, switch, text):
    env.gh_scenario(**{switch: True})
    with pytest.raises(ProjectError) as e:
        app.hub.projects.register("demo4")
    assert e.value.status == 502 and text in e.value.message and e.value.created_repo is None
    assert _state(app, env, "demo4") == {"entry": False, "agentsmd": False, "skills": False, "clone": False}


@pytest.mark.parametrize("setup, text", [
    ("missing", "not installed"), ("not_logged_in", "gh auth login"), ("auth_broken", "did not say"),
])
def test_a_create_without_url_is_refused_before_gh_repo_create(app, env, tmp_path, setup, text):
    if setup == "missing":
        _without_gh(app, tmp_path)
    else:
        env.gh_scenario(**{setup: True})
    with pytest.raises(ProjectError) as e:
        app.hub.projects.register("demo7")
    assert e.value.status == 502 and text in e.value.message and "enter a repo URL" in e.value.message
    assert not [c for c in env.gh_log() if c["argv"][:2] == ["repo", "create"]]
    assert not (env.gh_dir / "repos").exists()
    assert _state(app, env, "demo7") == {"entry": False, "agentsmd": False, "skills": False, "clone": False}


def test_a_created_repo_that_cannot_be_cloned_is_kept_and_named(app, env):
    env.gh_scenario(unclonable=True)
    with pytest.raises(ProjectError) as e:
        app.hub.projects.register("demo5")
    assert e.value.created_repo == "https://github.com/fake-owner/demo5"
    assert "https://github.com/fake-owner/demo5" in e.value.message
    assert (env.gh_dir / "repos" / "demo5.git").exists()
    assert _state(app, env, "demo5") == {"entry": False, "agentsmd": False, "skills": False, "clone": False}


def test_a_failed_clone_after_creation_removes_the_traces(app, env, monkeypatch):
    def fail_clone(*args, **kwargs):
        raise subprocess.CalledProcessError(128, ["git", "clone"])

    monkeypatch.setattr(projects_module, "project_add", lambda layout, name, repo, base, no_chat=True: (
        _write_entry(env, name, repo), fail_clone()))
    with pytest.raises(ProjectError) as e:
        app.hub.projects.register("demo6")
    assert e.value.created_repo == "https://github.com/fake-owner/demo6"
    assert "demo6" not in _manifest(env)


def _write_entry(env, name, repo):
    path = env.private / "harness.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["projects"][name] = {"repo": repo, "default_base": "main"}
    path.write_text(yaml.safe_dump(raw))
    (env.private / "agentmds" / name).mkdir(parents=True)


# ---------------------------------------------------------------- what `gh` can do
def _gh_script(tmp_path, body):
    script = tmp_path / "gh-script"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    return str(script)


@pytest.mark.parametrize("setup, expected", [
    ("ok", {"can_create": True, "reason": None}),
    ("missing", {"can_create": False, "reason": "not_installed"}),
    ("not_logged_in", {"can_create": False, "reason": "not_logged_in"}),
    ("exit_4", {"can_create": False, "reason": "not_logged_in"}),
    ("auth_broken", {"can_create": False, "reason": "unknown"}),
    ("auth_hangs", {"can_create": False, "reason": "unknown"}),
    ("not_executable", {"can_create": False, "reason": "unknown"}),
])
def test_github_status_maps_what_gh_auth_status_does(app, env, monkeypatch, tmp_path, setup, expected):
    if setup == "auth_hangs":
        monkeypatch.setattr(Projects, "github_timeout_s", 0.3)  # the fake sleeps 5 s
    if setup == "missing":
        _without_gh(app, tmp_path)
    elif setup == "exit_4":
        app.config.gh_bin = _gh_script(tmp_path, "exit 4")
    elif setup == "not_executable":
        app.config.gh_bin = _gh_script(tmp_path, "exit 0")
        (tmp_path / "gh-script").chmod(0o644)
    elif setup != "ok":
        env.gh_scenario(**{setup: True})
    assert app.hub.projects.github_status() == expected


def test_github_status_is_kept_for_a_while_and_then_read_again(app, env, monkeypatch):
    def auth_calls():
        return [c for c in env.gh_log() if c["argv"][:2] == ["auth", "status"]]

    assert app.hub.projects.github_status()["can_create"] is True
    assert app.hub.projects.github_status()["can_create"] is True
    assert len(auth_calls()) == 1
    assert all(c["GH_HOST"] == "github.com" for c in auth_calls())

    monkeypatch.setattr(Projects, "github_cache_s", 0.0)
    env.gh_scenario(not_logged_in=True)
    assert app.hub.projects.github_status() == {"can_create": False, "reason": "not_logged_in"}
    assert len(auth_calls()) == 2

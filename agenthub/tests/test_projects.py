"""Registered projects and new ones, with a given repo URL (AC39) or a created private repo (AC43)."""

import subprocess

import pytest
import yaml

from agenthub import projects as projects_module
from agenthub.projects import ProjectError, check_repo_url
from agenthub.tests.serve_fake import make_bare_repo


def _manifest(env):
    return yaml.safe_load((env.private / "harness.yaml").read_text())["projects"]


def _remote_files(env):
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"], cwd=env.private_remote,
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


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


def test_register_with_a_url(app, env, monkeypatch, tmp_path):
    remote = make_bare_repo(tmp_path / "given.git", {"README.md": "x"}, branch="trunk")
    monkeypatch.setattr(projects_module, "check_repo_url", lambda url: url)
    project, warning = app.hub.projects.register("demo3", str(remote))
    assert warning is None
    assert project == {"name": "demo3", "default_base": "trunk", "repo": str(remote), "ready": False}
    assert _state(app, env, "demo3") == {"entry": True, "agentsmd": True, "skills": True, "clone": True}
    assert "TODO(onboard)" in (env.private / "agentmds" / "demo3" / "AGENTS.md").read_text()
    assert "agentmds/demo3/AGENTS.md" in _remote_files(env)
    assert env.gh_log() == []


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

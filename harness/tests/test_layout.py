"""The three roots (code, private, data), worktree linking, the external collector and project add.

Temp folders only: no network, no Docker, nothing under the real home folder.
"""

import os
import socket
import subprocess
from pathlib import Path

import pytest

import harness
from harness import cli
from harness.config import load_manifest
from harness.link import link_worktree
from harness.observability import Observability
from harness.paths import Layout, layout_from_env
from harness.project import project_add


def _git(args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True, capture_output=True)


def _three_roots(tmp_path: Path) -> Layout:
    code = tmp_path / "agenthub"
    return Layout(code, private_root=code / "private", data_root=code / "data" / "orchestrator")


def _skill(folder: Path, text: str = "---\nname: x\n---\n") -> Path:
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(text)
    return folder


def test_three_root_layout_places_each_path_under_its_root(tmp_path):
    # Constraint: the manifest, project AGENTS.md files and project skills live in the private root; tickets, runs,
    #             logs, worktrees and the archive in the data root; the rest in the code root. The write boundary
    #             protects what it protected before, the project skills now under the private root.
    # Input: Layout(code, private_root=code/private, data_root=code/data/orchestrator); a single-root Layout
    # Expected output: each path under its root; protected_paths lists code skills, private project skills,
    #                  workflows, GENERAL.md, the private manifest and the source; one root keeps the old five
    layout = _three_roots(tmp_path)
    code, private, data = layout.root, layout.private_root, layout.data_root
    assert (layout.manifest, layout.agentmds, layout.project_skills) == (private / "harness.yaml", private / "agentmds", private / "skills" / "projects")
    assert [layout.tickets, layout.runs, layout.workflow_logs, layout.worktrees, layout.archived] == [
        data / "tickets", data / "runs", data / "workflow_logs", data / "worktrees", data / "archived",
    ]
    assert (layout.general_md, layout.general_skills, layout.workflows) == (code / "agentmds" / "GENERAL.md", code / "skills" / "general", code / "workflows")
    assert layout.base_clone("demo") == data / "worktrees" / "demo" / ".base"
    assert layout.project_agentsmd("demo") == private / "agentmds" / "demo" / "AGENTS.md"
    assert layout.private_path("skills/projects/demo") == private / "skills" / "projects" / "demo"
    assert layout.protected_paths() == [
        code / "skills", private / "skills" / "projects", code / "workflows", code / "agentmds" / "GENERAL.md",
        private / "harness.yaml", code / "harness",
    ]
    single = Layout(tmp_path)
    assert (single.private_root, single.data_root) == (tmp_path, tmp_path)
    assert single.protected_paths() == [
        tmp_path / "skills", tmp_path / "workflows", tmp_path / "agentmds" / "GENERAL.md", tmp_path / "harness.yaml", tmp_path / "harness",
    ]


def test_layout_from_env_reads_the_three_variables(tmp_path, monkeypatch):
    # Constraint: the command line builds its layout from HARNESS_ROOT, HARNESS_PRIVATE_ROOT and HARNESS_DATA_ROOT;
    #             without HARNESS_ROOT the code root is this package's parent when a private root is named, and
    #             the folder holding harness.yaml otherwise.
    # Input: all three set; only the private root set; none set, starting below a folder with harness.yaml
    # Expected output: the named roots; the package parent; that folder for all three roots
    code, private, data = tmp_path / "code", tmp_path / "private", tmp_path / "data"
    monkeypatch.setenv("HARNESS_ROOT", str(code))
    monkeypatch.setenv("HARNESS_PRIVATE_ROOT", str(private))
    monkeypatch.setenv("HARNESS_DATA_ROOT", str(data))
    layout = layout_from_env()
    assert (layout.root, layout.private_root, layout.data_root) == (code.resolve(), private.resolve(), data.resolve())
    monkeypatch.delenv("HARNESS_ROOT")
    monkeypatch.delenv("HARNESS_DATA_ROOT")
    layout = layout_from_env()
    assert layout.root == Path(harness.__file__).resolve().parent.parent
    assert (layout.private_root, layout.data_root) == (private.resolve(), layout.root)
    monkeypatch.delenv("HARNESS_PRIVATE_ROOT")
    (tmp_path / "harness.yaml").write_text("projects: {}\n")
    (tmp_path / "sub").mkdir()
    layout = layout_from_env(tmp_path / "sub")
    assert (layout.root, layout.private_root, layout.data_root) == (tmp_path.resolve(),) * 3


def test_link_worktree_links_general_and_project_skills_and_writes_the_three_imports(tmp_path):
    # Constraint: steps read no user settings, so a worktree gets every skill itself: the general ones and then the
    #             project's (which win on a shared name), kept out of git status; its CLAUDE.md imports GENERAL.md,
    #             the project AGENTS.md and the private agents.md. Nothing is written outside the worktree.
    # Input: general skills plan and spec, project skills plan and deploy, private agents.md; a linked git worktree;
    #        link_worktree run twice
    # Expected output: plan and deploy point at the project skills, spec at the general one; CLAUDE.md holds the three
    #                  imports in that order; the repository's exclude file names .claude/skills/ once; git status
    #                  shows no .claude path; the second call reports nothing
    layout = _three_roots(tmp_path)
    general_plan = _skill(layout.general_skills / "plan")
    general_spec = _skill(layout.general_skills / "spec")
    project_plan = _skill(layout.project_skills / "demo" / "plan")
    project_deploy = _skill(layout.project_skills / "demo" / "deploy")
    layout.general_md.parent.mkdir(parents=True)
    layout.general_md.write_text("# general\n")
    (layout.agentmds / "demo").mkdir(parents=True)
    (layout.agentmds / "demo" / "AGENTS.md").write_text("# demo\n")
    (layout.private_root / "agents.md").write_text("# private rules\n")
    layout.manifest.write_text("projects:\n  demo:\n    repo: none\n")
    base = tmp_path / "base"
    base.mkdir()
    _git(["init", "-q", "-b", "main"], base)
    (base / "README.md").write_text("demo\n")
    _git(["add", "."], base)
    _git(["commit", "-q", "-m", "init"], base)
    worktree = tmp_path / "wt"
    _git(["worktree", "add", "-q", "-b", "feat", str(worktree)], base)

    report = link_worktree(layout, load_manifest(layout), "demo", worktree)
    links = worktree / ".claude" / "skills"
    assert {p.name: p.resolve() for p in links.iterdir()} == {
        "plan": project_plan.resolve(), "spec": general_spec.resolve(), "deploy": project_deploy.resolve(),
    }
    assert general_plan.resolve() not in [p.resolve() for p in links.iterdir()]
    assert (worktree / "CLAUDE.md").read_text() == (
        f"@{layout.general_md}\n@{layout.agentmds / 'demo' / 'AGENTS.md'}\n@{layout.private_root / 'agents.md'}\n"
    )
    exclude = base / ".git" / "info" / "exclude"
    assert exclude.read_text().splitlines().count(".claude/skills/") == 1
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=worktree, capture_output=True, text=True, check=True).stdout
    assert ".claude" not in status and "CLAUDE.md" in status
    assert report
    assert link_worktree(layout, load_manifest(layout), "demo", worktree) == []
    assert exclude.read_text().splitlines().count(".claude/skills/") == 1


def _fake_docker(tmp_path: Path, monkeypatch) -> Path:
    """A `docker` first on PATH that leaves a marker when anything calls it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "docker_called"
    docker = bin_dir / "docker"
    docker.write_text(f"#!/bin/sh\necho \"$@\" >> {marker}\nexit 1\n")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return marker


def test_external_observability_probes_the_collector_and_never_calls_docker(tmp_path, monkeypatch, capsys):
    # Constraint: the copy only probes a collector someone else runs: it never starts, stops or asks Docker; the
    #             collector's port comes from the private root's .env; `obs` offers only status and mcp-config.
    # Input: a failing fake `docker` first on PATH; a listening local socket as the collector, its port in
    #        <private root>/.env; every Observability call and `agenthub-harness obs status|mcp-config|up`
    # Expected output: collector up while the socket listens, down once it is closed; step_env carries otel.env and
    #                  the resource attributes; `obs up` is not a command; docker was never invoked
    marker = _fake_docker(tmp_path, monkeypatch)
    layout = _three_roots(tmp_path)
    layout.observability.mkdir(parents=True)
    (layout.observability / "otel.env").write_text("CLAUDE_CODE_ENABLE_TELEMETRY=1\n")
    layout.private_root.mkdir(parents=True)
    layout.manifest.write_text("observability: external\nprojects: {}\n")
    collector = socket.socket()
    collector.bind(("127.0.0.1", 0))
    collector.listen()
    port = collector.getsockname()[1]
    (layout.private_root / ".env").write_text(f"OTLP_GRPC_PORT={port}\nSIGNOZ_UI_PORT={port}\n")
    try:
        obs = Observability(layout, load_manifest(layout).observability)
        assert obs.mode == "external" and obs.collector_port == port
        assert obs.collector_up()
        assert f"collector :{port} up" in obs.status_text()
        env = obs.step_env({"app": "agenthub", "run_id": "demo-feat_1"})
        assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
        assert env["OTEL_RESOURCE_ATTRIBUTES"] == "app=agenthub,run_id=demo-feat_1"
        assert obs.mcp_config()["mcpServers"]["signoz"]["env"]["SIGNOZ_URL"] == f"http://localhost:{port}"
        for var, value in (("HARNESS_ROOT", layout.root), ("HARNESS_PRIVATE_ROOT", layout.private_root), ("HARNESS_DATA_ROOT", layout.data_root)):
            monkeypatch.setenv(var, str(value))
        assert cli.main(["obs", "status"]) == 0
        assert cli.main(["obs", "mcp-config"]) == 0
        with pytest.raises(SystemExit):
            cli.main(["obs", "up"])
    finally:
        collector.close()
    assert not obs.collector_up()
    assert "mode external" in capsys.readouterr().out
    assert not marker.exists()


@pytest.mark.parametrize("value, mode", [("external", "external"), ("required", "external"), ("optional", "external"), ("off", "off")])
def test_manifest_accepts_external_and_reads_the_old_modes_as_external(tmp_path, value, mode):
    # Constraint: the copy has two observability modes; manifests written for the original harness still load.
    # Input: harness.yaml with observability external, required, optional, off
    # Expected output: external, external, external, off
    (tmp_path / "harness.yaml").write_text(f"observability: {value}\nprojects: {{}}\n")
    assert load_manifest(Layout(tmp_path)).observability == mode


def test_project_add_writes_under_the_private_root_and_clones_under_the_data_root(tmp_path):
    # Constraint: adding a project changes only private files (manifest entry, AGENTS.md template, skills folder)
    #             and data (the base clone); the code root gets nothing else.
    # Input: project_add of `webapp` from a local bare repository, no onboarding chat
    # Expected output: the manifest entry with paths relative to the private root, the template with placeholders,
    #                  the skills folder, the base clone under data/orchestrator/worktrees/webapp/.base, and only
    #                  the private and data folders in the code root
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "README.md").write_text("webapp\n")
    _git(["init", "-q", "-b", "main"], seed)
    _git(["add", "."], seed)
    _git(["commit", "-q", "-m", "init"], seed)
    remote = tmp_path / "webapp.git"
    _git(["clone", "-q", "--bare", str(seed), str(remote)], tmp_path)
    layout = _three_roots(tmp_path)
    layout.private_root.mkdir(parents=True)
    layout.manifest.write_text("observability: external\nprojects: {}\n")

    project_add(layout, "webapp", str(remote), "main", no_chat=True)
    project = load_manifest(layout).project("webapp")
    assert (project.agentsmd, project.skills, project.default_base) == ("agentmds/webapp/AGENTS.md", "skills/projects/webapp", "main")
    assert "TODO(onboard)" in (layout.private_root / "agentmds" / "webapp" / "AGENTS.md").read_text()
    assert (layout.private_root / "skills" / "projects" / "webapp" / ".gitkeep").is_file()
    assert (layout.data_root / "worktrees" / "webapp" / ".base" / ".git").is_dir()
    assert sorted(p.name for p in layout.root.iterdir()) == ["data", "private"]

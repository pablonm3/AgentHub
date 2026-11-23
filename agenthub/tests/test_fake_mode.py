"""Fake mode points the private folder and its origin into the temp folder and names both fakes."""

import subprocess
from pathlib import Path

from agenthub.tests.serve_fake import FAKE_CLAUDE, FAKE_GH, build_fake_environment, make_bare_repo


def test_fake_environment_with_a_private_source(tmp_path):
    source_remote = make_bare_repo(tmp_path / "src.git", {"harness.yaml": "projects: {}\n", "agents.md": "x\n"})
    source = tmp_path / "source"
    subprocess.run(["git", "clone", "-q", str(source_remote), str(source)], check=True)
    base = tmp_path / "fake"
    env = build_fake_environment(base, source)
    private = Path(env["AGENTHUB_PRIVATE_DIR"])
    assert base in private.parents and (private / "harness.yaml").is_file()
    origin = subprocess.run(["git", "remote", "get-url", "origin"], cwd=private, capture_output=True, text=True).stdout.strip()
    assert Path(origin).resolve().is_relative_to(base.resolve())
    assert env["AGENTHUB_CLAUDE_BIN"] == str(FAKE_CLAUDE) and env["AGENTHUB_GH_BIN"] == str(FAKE_GH)
    assert Path(env["AGENTHUB_DATA_DIR"]).resolve().is_relative_to(base.resolve())


def test_fake_environment_without_a_source_is_synthetic(tmp_path):
    env = build_fake_environment(tmp_path / "fake")
    manifest = (Path(env["AGENTHUB_PRIVATE_DIR"]) / "harness.yaml").read_text()
    assert "demo:" in manifest and "draft:" in manifest

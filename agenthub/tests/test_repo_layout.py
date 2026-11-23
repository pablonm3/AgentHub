"""The public tree holds nothing private, and the private folder has its required content (AC35, AC36)."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "check_public_tree.py"
PRIVATE = ROOT / "private"
ENV_KEYS = ["SIGNOZ_UI_PORT", "OTLP_GRPC_PORT", "OTLP_HTTP_PORT", "SIGNOZ_TAG", "OTELCOL_TAG", "CLICKHOUSE_TAG",
            "ZOOKEEPER_TAG", "SIGNOZ_JWT_SECRET", "RETENTION_TRACES", "SIGNOZ_API_KEY", "SIGNOZ_MCP_BIN"]

needs_private = pytest.mark.skipif(not (PRIVATE / ".git").exists(), reason="the private submodule is not initialised")


def _guard(root: Path, private: Path | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(GUARD), "--root", str(root)]
    if private:
        args += ["--private", str(private)]
    return subprocess.run(args, capture_output=True, text=True)


@needs_private
def test_the_guard_passes_on_this_tree():
    r = _guard(ROOT)
    assert r.returncode == 0, r.stdout


def _planted_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "private").mkdir()
    (repo / "private" / "public_guard.txt").write_text("# test patterns\nForbiddenCorpName\n")
    (repo / "private" / ".env").write_text("SOME_API_KEY=s3cr3t-value-123456\nPLAIN=not-a-secret-value\n")
    (repo / ".gitignore").write_text("private/\n")
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    return repo


@pytest.mark.parametrize("rel, text, rule", [
    ("notes.md", "made by ForbiddenCorpName\n", "public_guard.txt"),
    ("config/.env", "A=b\n", ".env file"),
    ("paths.md", "see " + "/" + "Users" + "/someone/project\n", "home-folder path"),
    ("obs.md", "SIGNOZ_" + "API_KEY=abc\n", "SIGNOZ_"),
    ("leak.py", "token = 's3cr3t-" + "value-123456'\n", "the value of SOME_API_KEY"),
])
def test_the_guard_fails_on_planted_content_without_printing_a_secret(tmp_path, rel, text, rule):
    repo = _planted_repo(tmp_path, {"clean.md": "nothing here\n", rel: text})
    r = _guard(repo)
    assert r.returncode == 1
    assert rule in r.stdout
    assert "s3cr3t" not in r.stdout
    assert "clean.md" not in r.stdout


def test_the_guard_passes_a_clean_planted_repo(tmp_path):
    repo = _planted_repo(tmp_path, {"clean.md": "SIGNOZ_API_KEY=<from private/.env>\nPLAIN is fine\n"})
    assert _guard(repo).returncode == 0


@needs_private
def test_private_env_has_the_eleven_keys_and_the_two_secrets():
    # the values are the coding harness's own; it leaves RETENTION_TRACES empty, so only the secrets must be set
    values = {}
    for line in (PRIVATE / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    assert sorted(values) == sorted(ENV_KEYS)
    assert values["SIGNOZ_JWT_SECRET"] and values["SIGNOZ_API_KEY"]
    assert sum(1 for k in ENV_KEYS if values[k]) >= 10


@needs_private
def test_private_folder_content():
    agents = (PRIVATE / "agents.md").read_text()
    assert re.search(r"committed and pushed", agents)
    assert (PRIVATE / "README.md").is_file() and "## Structure" in (PRIVATE / "README.md").read_text()
    projects = sorted(p.name for p in (PRIVATE / "agentmds").iterdir() if (p / "AGENTS.md").is_file())
    assert len(projects) == 5 and "AgentHub" in projects
    assert all((PRIVATE / "skills" / "projects" / p).is_dir() for p in projects)
    assert (PRIVATE / "harness.yaml").is_file() and (PRIVATE / "public_guard.txt").is_file()


def test_the_submodule_url_names_no_account():
    text = (ROOT / ".gitmodules").read_text()
    assert "url = ../AgentHub-private.git" in text

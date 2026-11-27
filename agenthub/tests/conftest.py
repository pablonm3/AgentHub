"""Fixtures: every test runs on temp data and private folders with a fake `claude` and a fake `gh`."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from agenthub.api import create_app
from agenthub.config import Config
from agenthub.projects import Projects
from agenthub.tests.serve_fake import FAKE_GH, _executable, build_fake_environment


@pytest.fixture(autouse=True)
def no_real_gh(tmp_path_factory, monkeypatch):
    """No test can reach the real `gh`; HARNESS_CLAUDE_BIN is restored after a hub set it."""
    monkeypatch.setenv("AGENTHUB_GH_BIN", _executable(FAKE_GH))
    monkeypatch.setenv("AGENTHUB_FAKE_GH_DIR", str(tmp_path_factory.mktemp("fake-gh")))
    monkeypatch.setenv("HARNESS_CLAUDE_BIN", os.environ.get("HARNESS_CLAUDE_BIN", "claude"))
    monkeypatch.setattr(Projects, "branch_retry_wait_s", 0.0)


def wait_for(predicate: Callable[[], object], timeout: float = 20, what: str = "condition") -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Env:
    base: Path
    vars: dict[str, str]

    @property
    def fake_dir(self) -> Path:
        return Path(self.vars["AGENTHUB_FAKE_DIR"])

    @property
    def gh_dir(self) -> Path:
        return Path(self.vars["AGENTHUB_FAKE_GH_DIR"])

    @property
    def private(self) -> Path:
        return Path(self.vars["AGENTHUB_PRIVATE_DIR"])

    @property
    def private_remote(self) -> Path:
        return self.base / "private-remote.git"

    def scenario(self, **values) -> None:
        (self.fake_dir / "scenario.json").write_text(json.dumps(values))
        for counter in self.fake_dir.glob("scenario.counter*"):
            counter.unlink()

    def gh_scenario(self, **values) -> None:
        (self.gh_dir / "scenario.json").write_text(json.dumps(values))

    def calls(self) -> list[dict]:
        path = self.fake_dir / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def gh_log(self) -> list[dict]:
        path = self.gh_dir / "gh.log"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.fixture
def env(tmp_path, monkeypatch) -> Env:
    values = build_fake_environment(tmp_path / "agenthub")
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return Env(tmp_path / "agenthub", values)


class App:
    """The app under test, with helpers to drive it through HTTP."""

    def __init__(self, env: Env, port: int):
        self.env = env
        self.port = port
        self.config = Config.from_env(port=port)
        self.app = create_app(self.config)
        self.hub = self.app.state.hub
        self.client = TestClient(self.app, base_url=f"http://127.0.0.1:{port}")

    def rebuild(self) -> "App":
        """A new app object on the same data: what a restart sees (AC18)."""
        self.wait_idle()
        self.hub.shutdown()
        return App(self.env, self.port)

    def post(self, path: str, body: dict | None = None, status: int = 200) -> dict:
        r = self.client.post(path, json=body or {})
        assert r.status_code == status, r.text
        return r.json()

    def patch(self, path: str, body: dict, status: int = 200) -> dict:
        r = self.client.patch(path, json=body)
        assert r.status_code == status, r.text
        return r.json()

    def get(self, path: str, status: int = 200) -> dict:
        r = self.client.get(path)
        assert r.status_code == status, r.text
        return r.json()

    def ticket(self, title: str = "A ticket", description: str = "Do the thing.", assignee: str = "pablo",
               project: str | None = None, **extra) -> dict:
        body = {"title": title, "description": description, "stage": "backlog", "assignee_id": assignee,
                "model": extra.pop("model", "opus"), **extra}
        if "new_project" not in body:
            body["project"] = project
        return self.post("/api/tickets", body)

    def comment(self, ticket_id: int, body: str, reply_to: int | None = None) -> dict:
        payload = {"body": body} if reply_to is None else {"body": body, "reply_to": reply_to}
        return self.post(f"/api/tickets/{ticket_id}/comments", payload)

    def task(self, task_id: int) -> dict:
        return self.get(f"/api/tasks/{task_id}")

    def wait_task(self, task_id: int, timeout: float = 20) -> dict:
        """Until the task's turn has ended and nothing is queued."""
        def settled():
            t = self.task(task_id)
            return t if t["status"] != "running" and not self.hub.tasks.is_working(task_id) else None
        return wait_for(settled, timeout, f"task {task_id} to settle")

    def wait_idle(self, timeout: float = 20) -> None:
        wait_for(lambda: not self.hub.tasks._active, timeout, "all turns to end")


@pytest.fixture
def app(env) -> App:
    a = App(env, free_port())
    yield a
    try:
        a.wait_idle()
    finally:
        a.hub.shutdown()


class LiveServer:
    """The app served over real HTTP, so a session's `agenthub` commands can reach it."""

    def __init__(self, app: App):
        import uvicorn

        self.app = app
        self.server = uvicorn.Server(uvicorn.Config(app.app, host="127.0.0.1", port=app.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        wait_for(lambda: self.server.started, 10, "the server to start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def live(app) -> App:
    server = LiveServer(app)
    yield app
    app.wait_idle()
    server.stop()

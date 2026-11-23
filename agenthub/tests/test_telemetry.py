"""Telemetry: AgentHub's attributes when the collector answers, none and no failure when it does not (AC33, AC34)."""

import socket

from agenthub.tests.conftest import free_port


def _env_of_last_launch(env):
    return [c for c in env.calls() if "--json-schema" in c["argv"]][-1]["env"]


def test_with_a_listening_collector_the_turn_has_agenthub_attributes(app, env, monkeypatch):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    (env.private / ".env").write_text(f"OTLP_GRPC_PORT={port}\n")
    try:
        t = app.ticket("Telemetry", "x", assignee="devops")
        app.wait_task(t["tasks"][0]["id"])
    finally:
        listener.close()
    attrs = dict(kv.split("=", 1) for kv in _env_of_last_launch(env)["OTEL_RESOURCE_ATTRIBUTES"].split(","))
    assert attrs["app"] == "agenthub" and attrs["task_id"] == str(t["tasks"][0]["id"]) and attrs["ai_user"] == "DevOps"
    assert attrs["ticket"] == f"AH-{t['id']}"


def test_with_the_collector_down_the_turn_runs_without_telemetry(app, env, monkeypatch):
    (env.private / ".env").write_text(f"OTLP_GRPC_PORT={free_port()}\n")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "run_id=inherited")  # from a parent session: dropped
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "x", "model": "opus"})
    t = app.wait_task(task["id"])
    assert t["status"] == "waiting_on_user" and [e for e in t["events"] if e["kind"] == "reply"]
    assert "OTEL_RESOURCE_ATTRIBUTES" not in _env_of_last_launch(env)

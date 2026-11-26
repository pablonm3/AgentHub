"""Runs of the harness copy started by tasks: project rules, gates as comments, guarded resume,
questions, harness tokens (fake `claude` for turns, the harness's fake for the run's steps)."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from agenthub.harness_bridge import BridgeRefused
from harness.orchestrator import pending_question
from agenthub.tests.conftest import wait_for

ANSWER = Path(__file__).with_name("answer_decision.py")


def _start_command(feature="demo-feat", extra=""):
    return (f"printf '# Add a greeting\\nPrint hello on start.\\n' > harness_ticket.md && "
            f"agenthub harness start --feature {feature} --ticket-file harness_ticket.md {extra}").strip()


def _answer_command(app, run_id, text):
    run_dir = app.config.layout().run_dir(run_id)
    return (f"{shlex.quote(sys.executable)} {shlex.quote(str(ANSWER))} {shlex.quote(str(run_dir))} {shlex.quote(text)} "
            f"&& agenthub harness resume {run_id}")


def _run_row(app, run_id):
    return app.hub.db.one("SELECT * FROM harness_runs WHERE run_id = ?", (run_id,))


def _wait_gate(app, run_id, step_label, timeout=120):
    def at_gate():
        row = _run_row(app, run_id)
        return row and row["pending_kind"] == "gate" and step_label in (app.hub.bridge.status(
            app.hub.tasks.get(row["task_id"]))[0]["current_step"] or "") and row
    return wait_for(at_gate, timeout, f"{run_id} at gate {step_label}")


def _replies(task):
    return [e["text"] for e in task["events"] if e["kind"] == "reply"]


def test_a_task_runs_the_harness_through_gate_1_and_gate_2(live, env):
    env.scenario(turns=[{"commands": [_start_command()], "message": "Started the run."}])
    ticket = live.ticket("Greeting", "Print hello on start.", assignee="engineer", project="demo", model="haiku")
    task_id = ticket["tasks"][0]["id"]
    row = wait_for(lambda: _run_row(live, "demo-feat_1"), 60, "the run row")
    assert row["project"] == "demo" and row["task_id"] == task_id

    gate = _wait_gate(live, "demo-feat_1", "7")
    layout = live.config.layout()
    run_dir = layout.run_dir("demo-feat_1")
    assert run_dir.is_dir() and Path(live.config.orchestrator_dir) in run_dir.parents
    assert "project: demo" in (layout.tickets / "demo-feat.md").read_text()
    state = json.loads(layout.state_file("demo-feat_1").read_text())
    assert state["base_branch"] == "main" and state["project"] == "demo"

    task = live.wait_task(task_id)
    assert task["status"] == "waiting_on_user"
    comments = live.get(f"/api/tickets/{ticket['id']}")["comments"]
    gate_comment = comments[-1]
    assert gate_comment["author_id"] == "engineer" and "demo-feat_1" in gate_comment["body"]
    assert "stays paused until Pablo replies" in gate_comment["body"]
    question = pending_question(layout, "demo-feat_1")["question"].strip().splitlines()[0]
    assert question and f"> {question}" in gate_comment["body"]

    # AC41: three AI steps of 1,000 tokens each before GATE 1, apart from the session count
    assert task["harness_tokens"] == 3000
    assert task["session_tokens"] == 100  # one turn of the fake
    detail = live.get(f"/api/tickets/{ticket['id']}")
    assert detail["harness_tokens"] == 3000

    # the run's steps use the workflow's models, not the task's haiku
    launch = json.loads((layout.run_log_dir("demo-feat_1") / "04.jsonl").read_text().splitlines()[0])
    assert launch["argv"][launch["argv"].index("--model") + 1] == "fable"

    # only Pablo's reply releases the gate
    with pytest.raises(BridgeRefused):
        live.hub.bridge.resume(live.hub.tasks.get(task_id), "demo-feat_1")
    env.scenario(turns=[{"commands": [_answer_command(live, "demo-feat_1", "Approved by Pablo.")]}])
    live.comment(ticket["id"], "Spec and plan look good, go ahead (kumquat).")
    _wait_gate(live, "demo-feat_1", "19", timeout=180)
    decision = Path(gate["pending_decision_file"]).read_text()
    assert "answered: true" in decision and "## Human reply (verbatim)" in decision
    assert "go ahead (kumquat)" in decision
    final = live.wait_task(task_id)
    assert final["status"] == "waiting_on_user" and final["harness_tokens"] > 3000

    # survives a rebuilt app object (AC18)
    again = live.rebuild()
    t = again.task(task_id)
    assert (t["harness_tokens"], t["session_tokens"]) == (final["harness_tokens"], final["session_tokens"])
    again.hub.shutdown()


def test_no_project_ticket_refuses_a_run(live, env):
    env.scenario(turns=[{"commands": [_start_command("free-run")]}])
    ticket = live.ticket("Research", "Look into caching.", assignee="data_scientist")
    task = live.wait_task(ticket["tasks"][0]["id"])
    assert "has no project" in _replies(task)[-1]
    assert live.hub.db.all("SELECT * FROM harness_runs") == []
    assert not live.config.layout().run_dir("free-run_1").exists()


def test_a_task_runs_a_research_run_and_is_told_its_final_report(live, env):
    env.scenario(turns=[{"commands": [_start_command("topic-x", "--workflow research-v1")], "message": "Started the run."}])
    ticket = live.ticket("Queue waits", "How long is the wait at load 0.8?", assignee="data_scientist", project="demo")
    task_id = ticket["tasks"][0]["id"]
    row = wait_for(lambda: _run_row(live, "topic-x_1"), 60, "the run row")
    assert row["workflow"] == "research-v1" and row["project"] == "demo"

    def told_the_report():
        notices = [e["text"] for e in live.task(task_id)["events"] if e["kind"] == "notice"]
        return next((n for n in notices if "Harness run topic-x_1 finished" in n), None)
    notice = wait_for(told_the_report, 120, "the notice that the research run finished")
    assert "final_report_topic-x_1.md" in notice
    row = _run_row(live, "topic-x_1")
    assert row["status"] == "done" and not row["pending_kind"]
    layout = live.config.layout()
    state = json.loads(layout.state_file("topic-x_1").read_text())
    assert state["workflow"] == "research-v1" and not state.get("gates")
    launch = json.loads((layout.run_log_dir("topic-x_1") / "21.jsonl").read_text().splitlines()[0])
    assert launch["argv"][launch["argv"].index("--model") + 1] == "opus"
    assert live.wait_task(task_id)["status"] != "running"


def test_an_unknown_workflow_is_refused(app):
    t = app.ticket("On demo", assignee="pablo", project="demo")
    task = app.hub.tasks.create("engineer", "opus", "x", ticket_id=t["id"], origin="assignment")
    with pytest.raises(BridgeRefused, match="unknown workflow 'nope-v1'"):
        app.hub.bridge.start(app.hub.tasks.get(task["id"]), "feat-a", "text", workflow="nope-v1")
    assert app.hub.db.all("SELECT * FROM harness_runs") == []


def test_project_rules_of_start(app):
    t = app.ticket("On demo", assignee="pablo", project="demo")
    on_demo = app.hub.tasks.create("engineer", "opus", "x", ticket_id=t["id"], origin="assignment")
    with pytest.raises(BridgeRefused, match="ticket's project demo"):
        app.hub.bridge.start(app.hub.tasks.get(on_demo["id"]), "feat-a", "text", project="draft")
    d = app.ticket("On draft", assignee="pablo", project="draft")
    on_draft = app.hub.tasks.create("engineer", "opus", "x", ticket_id=d["id"], origin="assignment")
    with pytest.raises(BridgeRefused, match="not ready"):
        app.hub.bridge.start(app.hub.tasks.get(on_draft["id"]), "feat-b", "text")
    free = app.post("/api/tasks", {"ai_user_id": "devops", "message": "x", "model": "opus"})
    with pytest.raises(BridgeRefused, match="must name the project"):
        app.hub.bridge.start(app.hub.tasks.get(free["id"]), "feat-c", "text")
    with pytest.raises(BridgeRefused, match="no project named"):
        app.hub.bridge.start(app.hub.tasks.get(free["id"]), "feat-c", "text", project="nope")
    assert app.hub.db.all("SELECT * FROM harness_runs") == []


def test_a_task_without_ticket_starts_a_run_on_its_project(live, env):
    env.scenario(turns=[{"commands": [_start_command("solo-feat", "--project demo")]}])
    task = live.post("/api/tasks", {"ai_user_id": "engineer", "message": "build it", "model": "opus"})
    _wait_gate(live, "solo-feat_1", "7")
    t = live.wait_task(task["id"])
    assert t["status"] == "waiting_on_user"
    assert "solo-feat_1" in _replies(t)[-1]  # the gate, in the task's chat when it has no ticket


def test_a_question_answered_by_the_ai_user_stays_in_the_chat(live, env):
    (Path(env.vars["FAKE_CLAUDE_SCENARIO"])).write_text(json.dumps({"context_status": ["not_reproduced"]}))
    env.scenario(turns=[
        {"commands": [_start_command("question-feat")]},
        {"commands": [_answer_command(live, "question-feat_1", "Use the filter value 42.")]},
    ])
    ticket = live.ticket("Question", "body", assignee="engineer", project="demo")
    task_id = ticket["tasks"][0]["id"]
    _wait_gate(live, "question-feat_1", "7", timeout=180)
    events = live.task(task_id)["events"]
    texts = "\n".join(e["text"] for e in events)
    assert "Which filter value reproduces the issue?" in texts
    assert "Answer recorded for run question-feat_1" in texts and "Use the filter value 42." in texts


def test_a_turn_without_a_run_leaves_no_run(app):
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "what is 2+2?", "model": "opus"})
    t = app.wait_task(task["id"])
    assert t["harness_runs"] == [] and t["harness_tokens"] == 0


def test_tokens_follow_the_state_and_the_exit_syncs_the_private_folder(app, env):
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "x", "model": "opus"})
    app.wait_task(task["id"])
    layout = app.config.layout()
    state_file = layout.state_file("stub_1")
    state_file.parent.mkdir(parents=True)
    tokens = {"input": 10, "output": 90, "cache_creation": 400, "cache_read": 500}
    state_file.write_text(json.dumps({"status": "running", "feature": "stub", "executions": [{"tokens": tokens}]}))
    proc = subprocess.Popen(["sleep", "0.5"])
    app.hub.db.run(
        "INSERT INTO harness_runs (run_id, task_id, workflow, feature, project, status, pid, started_at)"
        " VALUES ('stub_1', ?, 'feature-v1', 'stub', 'demo', 'running', ?, '2026-01-01T00:00:00Z')",
        (task["id"], proc.pid),
    )
    app.hub.bridge._procs["stub_1"] = proc
    assert app.hub.bridge.refresh_tokens("stub_1")
    assert app.task(task["id"])["harness_tokens"] == 1000
    assert not app.hub.bridge.refresh_tokens("stub_1")  # idempotent
    state_file.write_text(json.dumps({"status": "done", "feature": "stub",
                                      "executions": [{"tokens": tokens}, {"tokens": {**tokens, "input": 1010}}]}))
    (env.private / "from_a_step.md").write_text("added by a step\n")
    app.hub.bridge._watch("stub_1")
    assert app.task(task["id"])["harness_tokens"] == 3000
    log = subprocess.run(["git", "log", "--format=%s", "main"], cwd=env.private_remote, capture_output=True, text=True).stdout
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"], cwd=env.private_remote,
                           capture_output=True, text=True).stdout
    assert "run stub_1" in log.splitlines() and "from_a_step.md" in files
    t = app.wait_task(task["id"])
    assert "Harness run stub_1 finished" in [e["text"] for e in t["events"] if e["kind"] == "notice"][-1]

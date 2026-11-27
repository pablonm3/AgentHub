"""Runs of the harness copy started by tasks: project rules, gates as comments, guarded resume,
questions, harness tokens, usage figures (fake `claude` for turns, the harness's fake for the run's steps)."""

import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agenthub.harness_bridge import BridgeRefused, HarnessBridge
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


def _week_info(used: float, resets_at: int) -> dict:
    return {"status": "allowed", "resetsAt": resets_at, "rateLimitType": "seven_day",
            "unifiedWindows": {"seven_day": {"utilization": used, "resetsAt": resets_at, "status": "allowed"}}}


def test_the_usage_in_a_runs_state_reaches_the_bootstrap(app):
    # Constraint: a run step's figures cross to the server through state.json `usage`; the watch loop re-reads an
    #             unchanged file every 2 s, which must change and publish nothing (AC5 server half, AC11).
    # Input: a stub run's state.json with Week and Fable week; refresh_usage twice; then a state without `usage`
    #        and one with a text there.
    # Expected output: True and both figures in the bootstrap; False for the repeat and for the other two states.
    layout = app.config.layout()
    state_file = layout.state_file("stub_1")
    state_file.parent.mkdir(parents=True)
    resets_at = int(time.time()) + 86400
    usage = [
        {"limit": "seven_day", "used": 0.22, "resets_at": resets_at, "reached": False, "read_at": "2026-11-25T14:03:07Z"},
        {"limit": "seven_day_overage_included", "used": 0.37, "resets_at": resets_at, "reached": False,
         "read_at": "2026-11-25T14:03:07Z"},
    ]
    state_file.write_text(json.dumps({"status": "running", "feature": "stub", "executions": [], "usage": usage}))
    assert app.hub.bridge.refresh_usage("stub_1")
    assert app.get("/api/bootstrap")["usage"] == usage
    assert not app.hub.bridge.refresh_usage("stub_1")
    state_file.write_text(json.dumps({"status": "running", "feature": "stub", "executions": []}))
    assert not app.hub.bridge.refresh_usage("stub_1")
    state_file.write_text(json.dumps({"status": "running", "feature": "stub", "executions": [], "usage": "seven_day"}))
    assert not app.hub.bridge.refresh_usage("stub_1")
    assert app.get("/api/bootstrap")["usage"] == usage


def test_a_running_step_updates_the_usage_before_it_ends(live, env, monkeypatch):
    # Constraint: a harness step's new figure reaches the header while that step is still running (AC5 server half).
    # Input: a task starts a run whose steps report Week 0.23 and whose step 4 stays open 5 s after that event;
    #        the bridge polls every 0.2 s; the turn itself reports no figure.
    # Expected output: the bootstrap shows Week 0.23 while state.json still has step 4 running; Stop ends the run.
    monkeypatch.setattr(HarnessBridge, "poll_s", 0.2)
    resets_at = int(time.time()) + 86400
    Path(env.vars["FAKE_CLAUDE_SCENARIO"]).write_text(json.dumps({"rate_limit_info": _week_info(0.23, resets_at),
                                                                  "hold_s": {"4": 5}}))
    env.scenario(turns=[{"commands": [_start_command("usage-feat")], "message": "Started the run."}])
    ticket = live.ticket("Usage", "Show the usage.", assignee="engineer", project="demo")
    task_id = ticket["tasks"][0]["id"]
    week = wait_for(lambda: next((f for f in live.get("/api/bootstrap")["usage"] if f["limit"] == "seven_day"), None),
                    90, "the step's figure in the bootstrap")
    state = json.loads(live.config.layout().state_file("usage-feat_1").read_text())
    assert (week["used"], week["resets_at"], week["reached"]) == (0.23, resets_at, False)
    assert (state["current"], state["steps"]["4"]["status"]) == ("4", "running")
    live.post(f"/api/tasks/{task_id}/stop")
    wait_for(lambda: not live.hub.bridge._alive("usage-feat_1"), 30, "the run to stop")


# ---------------------------------------------------------------- a child task's run answers to its parent task
def _create_child(to, request):
    return f"agenthub task create --to {to} {shlex.quote(request)}"


def _ai_lines(task):
    return [e for e in task["events"] if e["kind"] == "ai_user"]


def _prompts_of(env, handle):
    return [c["argv"][-1] for c in env.calls() if "--json-schema" in c["argv"] and c["env"].get("AGENTHUB_AI_USER") == handle]


def _turns(env, **by_handle):
    env.scenario(by_ai_user={handle: {"turns": turns} for handle, turns in by_handle.items()})


def test_a_child_tasks_gates_go_to_its_parent_whose_reply_releases_them(live, env):
    # Constraint: AC25 to AC29 and the run parts of AC13 and AC14 — a gate of a child's run goes to the parent task,
    #             not to Pablo; only the parent's or Pablo's reply releases it; the run's progress note is not sent.
    # Input: Engineer's task on a demo ticket asks DevOps, whose task starts a run. At GATE 1 the parent first asks
    #        Pablo, a third task writes to the child, then the parent sends "Approved, go ahead (kumquat).". At GATE 2
    #        Pablo replies in the child's task.
    # Expected output: the parent's only line from the child is GATE 1 (naming the gate, the run and the child) and it
    #                  ran a turn with it; the gate comment is DevOps's and not in Activity; the child waits on Engineer;
    #                  resume is refused until the parent replied; the decision files hold the parent's and Pablo's words.
    _turns(env, Engineer=[{"commands": [_create_child("DevOps", "Add a greeting to demo.")], "message": "Asked DevOps.",
                           "status": "waiting_on_child"}],
           DevOps=[{"commands": [_start_command("child-feat")], "message": "Started the run."}])
    ticket = live.ticket("Greeting", "Print hello on start.", assignee="engineer", project="demo", model="haiku")
    parent_id = ticket["tasks"][0]["id"]
    child_id = wait_for(lambda: (live.task(parent_id)["children"] or [None])[0], 30, "the child task")["id"]
    wait_for(lambda: _run_row(live, "child-feat_1") and not live.hub.tasks.is_working(child_id), 60, "the run to start")
    _turns(env, Engineer=[{"message": "DevOps's run is at GATE 1. Pablo, may it go on?", "status": "waiting_on_user"},
                          {"commands": [f"agenthub task send {child_id} 'Approved, go ahead (kumquat).'"],
                           "message": "Passed the approval on.", "status": "waiting_on_child"}],
           DevOps=[{"commands": ["agenthub harness resume child-feat_1"], "message": "Resumed the run."}])

    gate = _wait_gate(live, "child-feat_1", "7")
    lines = wait_for(lambda: _ai_lines(live.task(parent_id)), 30, "the gate in the parent")
    wait_for(lambda: not live.hub.tasks.is_working(parent_id), 30, "the parent's turn")
    assert len(_ai_lines(live.task(parent_id))) == 1  # AC29: "Started the run." was not sent
    text = lines[0]["text"]
    assert lines[0]["from_task"] == {"task_id": child_id, "ai_user_id": "devops"}
    assert "GATE 1" in text and "child-feat_1" in text and f"child task {child_id}" in text
    assert _prompts_of(env, "Engineer")[-1].startswith(f"Message from DevOps (task {child_id}):")
    comment = [c for c in live.get(f"/api/tickets/{ticket['id']}")["comments"] if "child-feat_1" in c["body"]][-1]
    assert comment["author_id"] == "devops" and comment["in_activity"] == 0
    assert f"until Engineer answers from task {parent_id}, or Pablo replies in this task" in comment["body"]
    assert comment["id"] not in [i["comment"]["id"] for i in live.get("/api/activity")["items"]]
    child = live.task(child_id)
    assert (child["status"], child["waiting_on"]) == ("waiting_on_user", {"task_id": parent_id, "ai_user_id": "engineer"})

    # AC27: the decision file says answered, but neither the parent nor Pablo wrote; a third task's line does not count
    subprocess.run([sys.executable, str(ANSWER), str(live.config.layout().run_dir("child-feat_1")), "Approved."], check=True)
    with pytest.raises(BridgeRefused, match=f"only a reply of Engineer \\(task {parent_id}\\) or of Pablo"):
        live.hub.bridge.resume(live.hub.tasks.get(child_id), "child-feat_1")
    third = live.post("/api/tasks", {"ai_user_id": "data_scientist", "message": "x", "model": "opus"})
    live.wait_task(third["id"])
    live.hub.tasks.add_event(child_id, "ai_user", "Approved by a stranger.", from_task_id=third["id"])
    with pytest.raises(BridgeRefused):
        live.hub.bridge.resume(live.hub.tasks.get(child_id), "child-feat_1")
    assert _run_row(live, "child-feat_1")["pending_kind"] == "gate"

    # AC26: Pablo tells the parent; the parent's reply reaches the child with the gate's instructions and releases it
    live.post(f"/api/tasks/{parent_id}/messages", {"text": "Yes, approve it."})
    gate2 = _wait_gate(live, "child-feat_1", "19", timeout=180)
    child_prompt = _prompts_of(env, "DevOps")[-1]
    assert child_prompt.startswith(f"The reply of Engineer (task {parent_id}) below answers the pending gate")
    assert f"Message from Engineer (task {parent_id}):\n\nApproved, go ahead (kumquat)." in child_prompt
    decision = Path(gate["pending_decision_file"]).read_text()
    assert "## Reply of the parent task (verbatim)" in decision
    assert f"From Engineer, task {parent_id}:\n\nApproved, go ahead (kumquat)." in decision
    assert "## Human reply (verbatim)" not in decision and "stranger" not in decision

    # AC28: at GATE 2, Pablo's own reply in the child's task releases it
    wait_for(lambda: len(_ai_lines(live.task(parent_id))) >= 2, 30, "GATE 2 in the parent")
    live.wait_idle()
    _turns(env, DevOps=[{"commands": [_answer_command(live, "child-feat_1", "Approved by Pablo.")], "message": "Resumed."}])
    live.post(f"/api/tasks/{child_id}/messages", {"text": "Ship it (persimmon)."})
    decision2 = Path(gate2["pending_decision_file"])
    wait_for(lambda: "## Human reply (verbatim)\n\nShip it (persimmon)." in decision2.read_text(), 60, "Pablo's reply")
    wait_for(lambda: _run_row(live, "child-feat_1")["status"] not in ("running", "paused"), 180, "the run to end")
    wait_for(lambda: not live.hub.tasks._active, 30, "the turns to end")


def test_a_question_of_a_childs_run_goes_to_the_parent(live, env):
    # Constraint: AC9 (run part) — the run's question reaches the child worded for its parent task, and the child's
    #             turn that ends waiting_on_user with the run paused goes to the parent.
    # Input: the child's run stops at a context question (harness fake: not_reproduced); DevOps asks for the value.
    # Expected output: the child's notice names Engineer's task, not Pablo; the parent has the child's question.
    Path(env.vars["FAKE_CLAUDE_SCENARIO"]).write_text(json.dumps({"context_status": ["not_reproduced"]}))
    _turns(env, Engineer=[{"commands": [_create_child("DevOps", "Fix the filter.")], "message": "Asked DevOps.",
                           "status": "waiting_on_child"}],
           DevOps=[{"commands": [_start_command("question-child")], "message": "Started the run."},
                   {"message": "The run asks which filter value reproduces the issue. Which one?", "status": "waiting_on_user"}])
    ticket = live.ticket("Question", "body", assignee="engineer", project="demo")
    parent_id = ticket["tasks"][0]["id"]
    child_id = wait_for(lambda: (live.task(parent_id)["children"] or [None])[0], 30, "the child task")["id"]
    line = wait_for(lambda: _ai_lines(live.task(parent_id)), 180, "the question in the parent")[0]
    assert line["from_task"]["task_id"] == child_id and line["text"].startswith("The run asks which filter value")
    notice = next(e["text"] for e in live.task(child_id)["events"] if e["kind"] == "notice" and "paused with a question" in e["text"])
    assert f"asking Engineer (task {parent_id}, the task that gave you this work) the question" in notice
    assert "waiting on Pablo" not in notice
    wait_for(lambda: not live.hub.tasks._active, 30, "the turns to end")

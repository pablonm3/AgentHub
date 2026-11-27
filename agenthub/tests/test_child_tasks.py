"""Child tasks: an AI user's session gives work to another AI user, and the child answers to its parent task
(fake `claude` per AI user; session commands over real HTTP)."""

import shlex
import subprocess
import time

from agenthub.tests.conftest import wait_for


def _create(to: str, request: str) -> str:
    return f"agenthub task create --to {shlex.quote(to)} {shlex.quote(request)}"


def _send(task_id, text: str) -> str:
    return f"agenthub task send {task_id} {shlex.quote(text)}"


def _script(env, **turns_by_handle) -> None:
    """The fake turns of each AI user, by handle: `Engineer=[{...}, ...]`."""
    env.scenario(by_ai_user={handle: {"turns": turns} for handle, turns in turns_by_handle.items()})


def _lines(task: dict, kind: str = "ai_user") -> list[dict]:
    return [e for e in task["events"] if e["kind"] == kind]


def _replies(task: dict) -> list[str]:
    return [e["text"] for e in _lines(task, "reply")]


def _prompts(env, handle: str) -> list[str]:
    return [c["argv"][-1] for c in env.calls() if "--json-schema" in c["argv"] and c["env"].get("AGENTHUB_AI_USER") == handle]


def _child(app, parent_id: int) -> dict:
    ref = wait_for(lambda: (app.task(parent_id)["children"] or [None])[0], 20, "the child task")
    return ref


def _quiet(app, timeout: float = 40) -> None:
    """Until no turn runs and no task is running, twice in a row (a child's report starts its parent's turn)."""
    def calm():
        return not app.hub.tasks._active and all(t["status"] != "running" for t in app.get("/api/tasks")["tasks"])
    for _ in range(2):
        wait_for(calm, timeout, "every task to settle")
        time.sleep(0.3)


def _parent_on_ticket(live, env, model="haiku", **turns) -> tuple[dict, int]:
    _script(env, **turns)
    ticket = live.ticket("Parent work", "needs DevOps help", assignee="engineer", model=model)
    return ticket, ticket["tasks"][0]["id"]


def _comments(app, ticket_id: int) -> list[dict]:
    return app.get(f"/api/tickets/{ticket_id}")["comments"]


# ---------------------------------------------------------------- parent and children in the API (AC16, AC2)
def test_a_child_names_its_parent_and_the_parent_its_children(app, env):
    # Constraint: the task view carries parent and children; a child's first line is the parent's, not Pablo's.
    # Input: a task without a ticket and two children created for it through Tasks.create.
    # Expected output: parent refs and children refs (oldest first) with id, AI user, title, status; null and []
    #                  where there are none; the child's first line is `ai_user` from the parent, headed so in its prompt.
    parent = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "parent work", "model": "opus"})
    app.wait_task(parent["id"])
    first = app.hub.tasks.create("devops", "opus", "check the deploy script", origin="ai_user", first_kind="ai_user",
                                 parent_task_id=parent["id"])
    second = app.hub.tasks.create("data_scientist", "opus", "profile the query", origin="ai_user", first_kind="ai_user",
                                  parent_task_id=parent["id"])
    _quiet(app)
    child = app.task(first["id"])
    assert child["origin"] == "ai_user"
    assert {k: child["parent"][k] for k in ("id", "ai_user_id", "title", "status")} == {
        "id": parent["id"], "ai_user_id": "engineer", "title": "Fake task title", "status": "waiting_on_user"}
    p = app.task(parent["id"])
    assert [(c["id"], c["ai_user_id"]) for c in p["children"]] == [(first["id"], "devops"), (second["id"], "data_scientist")]
    assert set(p["children"][0]) >= {"id", "ai_user_id", "title", "display_title", "status", "waiting_on"}
    assert p["parent"] is None and child["children"] == []
    line = child["events"][0]
    assert line["kind"] == "ai_user" and line["text"] == "check the deploy script"
    assert line["from_task"] == {"task_id": parent["id"], "ai_user_id": "engineer"}
    prompt = _prompts(env, "DevOps")[0]
    assert prompt.startswith(f"Message from Engineer (task {parent['id']}):") and "Message from Pablo" not in prompt


# ---------------------------------------------------------------- creating a child task (AC1 to AC8)
def test_a_session_creates_a_child_task_on_its_ticket(live, env):
    # Constraint: AC1 to AC4 — the child is the receiver's, running, on the ticket with the ticket's model, its first
    #             line names the asker; one comment by the asker announces it; assignee and stage stay.
    # Input: Engineer's task on AH-1 (ticket model haiku, the task's own model changed to sonnet) runs
    #        `agenthub task create --to devops "check the deploy script"`; DevOps's turn sleeps 3 s.
    # Expected output: as above; the command prints the child's id.
    ticket, parent_id = _parent_on_ticket(live, env, Engineer=[{}, {"commands": [_create("devops", "check the deploy script")]}],
                                          DevOps=[{"sleep": 3}])
    live.wait_task(parent_id)
    live.patch(f"/api/tasks/{parent_id}", {"model": "sonnet"})
    before = live.get(f"/api/tickets/{ticket['id']}")
    live.post(f"/api/tasks/{parent_id}/messages", {"text": "ask DevOps"})
    ref = _child(live, parent_id)
    child = live.task(ref["id"])
    assert (child["ai_user_id"], child["status"], child["model"], child["origin"]) == ("devops", "running", "haiku", "ai_user")
    assert child["ticket_id"] == ticket["id"] and child["parent"]["id"] == parent_id
    first = child["events"][0]
    assert first["kind"] == "ai_user" and first["from_task"] == {"task_id": parent_id, "ai_user_id": "engineer"}
    assert first["text"].startswith("check the deploy script") and f"from task {parent_id}" in first["text"]
    parent = live.wait_task(parent_id)
    assert f"task {child['id']} created for DevOps on AH-{ticket['id']}" in _replies(parent)[-1]
    announcing = [c for c in _comments(live, ticket["id"]) if c["child_task"]]
    assert len(announcing) == 1
    c = announcing[0]
    assert (c["author_id"], c["task_id"], c["child_task"]["id"]) == ("engineer", parent_id, child["id"])
    assert c["body"].startswith("Created a task for DevOps:") and "> check the deploy script" in c["body"]
    assert c["child_task"]["status"] == live.task(child["id"])["status"]
    assert live.task(child["id"])["origin_comment_id"] == c["id"]
    after = live.get(f"/api/tickets/{ticket['id']}")
    assert (after["assignee_id"], after["stage"]) == (before["assignee_id"], before["stage"])
    _quiet(live)


def test_a_task_without_a_ticket_gets_a_child_without_one(live, env):
    # Constraint: AC5 — no ticket: the child has none, the parent's model, the parent link, and no comment is posted.
    # Input: a task on no ticket, model sonnet, runs `agenthub task create --to "Data Scientist" …`.
    # Expected output: a data_scientist task with ticket null, model sonnet, parent the task; zero comments.
    _script(env, Engineer=[{"commands": [_create("Data Scientist", "profile the query")]}])
    parent = live.post("/api/tasks", {"ai_user_id": "engineer", "message": "work", "model": "sonnet"})
    ref = _child(live, parent["id"])
    child = live.task(ref["id"])
    assert (child["ai_user_id"], child["ticket_id"], child["model"]) == ("data_scientist", None, "sonnet")
    assert child["parent"]["id"] == parent["id"] and child["events"][0]["text"].startswith("profile the query")
    _quiet(live)
    assert f"task {child['id']} created for Data Scientist with no ticket" in _replies(live.task(parent["id"]))[0]
    assert live.hub.db.value("SELECT COUNT(*) FROM comments") == 0


def test_only_another_ai_user_can_be_asked(live, env):
    # Constraint: AC6 — the asker itself, Pablo or an unknown name is refused, listing who can be asked.
    # Input: Engineer's task runs create with --to Engineer, --to Pablo and --to Nobody.
    # Expected output: three refusals (422) naming DataScientist and DevOps; no new task, no comment.
    commands = [_create(to, "help me") for to in ("Engineer", "@pablo", "Nobody")]
    _script(env, Engineer=[{"commands": commands}])
    parent = live.post("/api/tasks", {"ai_user_id": "engineer", "message": "work", "model": "opus"})
    reply = _replies(live.wait_task(parent["id"]))[-1]
    assert reply.count("refused (422)") == 3
    assert "Engineer cannot be asked. AI users you can ask: DataScientist, DevOps" in reply
    assert "@pablo cannot be asked" in reply and "Nobody cannot be asked" in reply
    assert len(live.get("/api/tasks")["tasks"]) == 1 and live.hub.db.value("SELECT COUNT(*) FROM comments") == 0


def test_a_second_request_goes_to_the_existing_child(live, env):
    # Constraint: AC7 — the receiver's open task on the ticket is already this task's child: no second task.
    # Input: Engineer asks DevOps twice (the second time in the turn started by DevOps's answer).
    # Expected output: one DevOps task holding both requests as lines from the parent; the command names its id.
    ticket, parent_id = _parent_on_ticket(
        live, env,
        Engineer=[{"commands": [_create("DevOps", "first request")]}, {"commands": [_create("DevOps", "second request")]}],
        DevOps=[{"message": "What exactly?"}, {"message": "Got it.", "status": "done"}],
    )
    child_id = _child(live, parent_id)["id"]
    wait_for(lambda: len(_lines(live.task(child_id))) == 2, 30, "the second request in the child")
    _quiet(live)
    devops = [t for t in live.get("/api/tasks")["tasks"] if t["ai_user_id"] == "devops"]
    assert [t["id"] for t in devops] == [child_id]
    lines = _lines(live.task(child_id))
    assert lines[1]["text"] == "second request" and lines[1]["from_task"]["task_id"] == parent_id
    assert any(f"in task {child_id}, a child task of this task: the request was sent to it" in r
               for r in _replies(live.task(parent_id)))
    assert len([c for c in _comments(live, ticket["id"]) if c["child_task"]]) == 1


def test_an_open_task_this_task_did_not_create_refuses_the_request(live, env):
    # Constraint: AC8 — DevOps already has an open task on the ticket that Pablo's mention started.
    # Input: Pablo mentions DevOps; then Engineer's task runs create --to DevOps.
    # Expected output: refused (409) naming that task; task count unchanged; no announcing comment.
    ticket, parent_id = _parent_on_ticket(live, env, Engineer=[{}, {"commands": [_create("DevOps", "check it")]}])
    live.wait_task(parent_id)
    mention = live.comment(ticket["id"], "@DevOps look at the logs")["started"][0]
    live.wait_task(mention)
    tasks_before = len(live.get("/api/tasks")["tasks"])
    live.post(f"/api/tasks/{parent_id}/messages", {"text": "ask DevOps"})
    reply = _replies(live.wait_task(parent_id))[-1]
    assert "refused (409)" in reply and f"DevOps already has an open task on AH-{ticket['id']}" in reply
    assert f"task {mention} \"Fake task title\" (waiting_on_user)" in reply
    assert len(live.get("/api/tasks")["tasks"]) == tasks_before
    assert not [c for c in _comments(live, ticket["id"]) if c["child_task"] or c["body"].startswith("Created a task")]


# ---------------------------------------------------------------- the child answers to its parent (AC9 to AC13, AC14)
def test_a_childs_question_reaches_the_parent_and_not_activity(live, env):
    # Constraint: AC9, AC13, AC14 — the child's question is the receiver's line in the parent's chat and starts its turn;
    #             on the ticket it is the receiver's comment, not in Activity; the child waits on the asker.
    # Input: Engineer asks DevOps, whose turn ends waiting_on_user with "Which server?".
    # Expected output: an ai_user line from the child in the parent, its prompt headed "Message from DevOps (task c)";
    #                  the comment by devops not listed nor counted in Activity, the parent's comments still listed;
    #                  the child's and the ticket's waiting_on name the asker.
    ticket, parent_id = _parent_on_ticket(live, env, Engineer=[{"commands": [_create("DevOps", "check the deploy")]}],
                                          DevOps=[{"message": "Which server?", "status": "waiting_on_user"}])
    child_id = _child(live, parent_id)["id"]
    wait_for(lambda: _lines(live.task(parent_id)), 30, "the question in the parent")
    _quiet(live)
    parent = live.task(parent_id)
    line = _lines(parent)[0]
    assert line["from_task"] == {"task_id": child_id, "ai_user_id": "devops"} and not line["queued"]
    assert line["text"].startswith("Which server?") and f"agenthub task send {child_id}" in line["text"]
    prompt = _prompts(env, "Engineer")[-1]
    assert prompt.startswith(f"Message from DevOps (task {child_id}):") and "Which server?" in prompt
    comments = _comments(live, ticket["id"])
    question = [c for c in comments if c["author_id"] == "devops"]
    assert [c["body"] for c in question] == ["Which server?"] and question[0]["in_activity"] == 0
    activity = live.get("/api/activity")
    listed = [i["comment"]["id"] for i in activity["items"]]
    assert question[0]["id"] not in listed and activity["unseen"] == len(listed)
    assert all(c["id"] in listed for c in comments if c["author_id"] == "engineer" and not c["child_task"])
    child = live.task(child_id)
    assert child["status"] == "waiting_on_user"
    assert child["waiting_on"] == {"task_id": parent_id, "ai_user_id": "engineer"}
    newest = live.get("/api/tickets")["tickets"][0]
    assert (newest["task_status"], newest["task_waiting_on"]) == ("waiting_on_user", "engineer")


def test_a_childs_result_reaches_a_done_parent(live, env):
    # Constraint: AC10 — the result goes to the parent even when the parent is done, and runs a turn.
    # Input: Engineer's turn creates the child and ends done; DevOps ends done 2 s later with "Script is fine.".
    # Expected output: the parent's line from the child holding the result; the parent ran a second turn.
    ticket, parent_id = _parent_on_ticket(
        live, env, Engineer=[{"commands": [_create("DevOps", "check the deploy")], "status": "done"}],
        DevOps=[{"sleep": 2, "message": "Script is fine.", "status": "done"}],
    )
    child_id = _child(live, parent_id)["id"]
    assert live.wait_task(parent_id)["status"] == "done"
    wait_for(lambda: _lines(live.task(parent_id)), 30, "the result in the parent")
    _quiet(live)
    text = _lines(live.task(parent_id))[0]["text"]
    assert text.startswith("Script is fine.") and f"result of child task {child_id}" in text
    assert len(_prompts(env, "Engineer")) == 2


def test_a_childs_result_reaches_a_stopped_parent(live, env):
    # Constraint: AC10 — a parent Pablo stopped also gets the result and runs again.
    # Input: Engineer's turn creates the child and sleeps; Pablo stops it; DevOps ends done after 2 s.
    # Expected output: the parent was stopped, then got the result and ran a second turn.
    ticket, parent_id = _parent_on_ticket(
        live, env, Engineer=[{"commands": [_create("DevOps", "check the deploy")], "sleep": 30}],
        DevOps=[{"sleep": 2, "message": "Script is fine.", "status": "done"}],
    )
    _child(live, parent_id)
    live.post(f"/api/tasks/{parent_id}/stop")
    wait_for(lambda: _lines(live.task(parent_id)), 30, "the result in the parent")
    _quiet(live)
    events = live.task(parent_id)["events"]
    assert any(e["text"] == "Stopped by Pablo" for e in events)
    assert len(_prompts(env, "Engineer")) == 2


def test_the_parent_writes_to_its_child_only(live, env):
    # Constraint: AC11 — `agenthub task send` reaches the parent's own child as the asker's line and runs its turn;
    #             it is refused for a task that is not its child and for an archived child.
    # Input: after the child's question, Pablo has the parent answer with send to the child and to itself;
    #        the child ends done; Pablo archives it; the parent sends again.
    # Expected output: the child's line from the parent, unchanged, in its next prompt under "Message from Engineer";
    #                  refusals 404 and 409.
    ticket, parent_id = _parent_on_ticket(live, env, Engineer=[{"commands": [_create("DevOps", "check the deploy")]}],
                                          DevOps=[{"message": "Which server?"}])
    child_id = _child(live, parent_id)["id"]
    wait_for(lambda: _lines(live.task(parent_id)), 30, "the question in the parent")
    _quiet(live)
    _script(env, Engineer=[{"commands": [_send(child_id, "Use staging."), _send("$AGENTHUB_TASK_ID", "to myself")]}],
            DevOps=[{"message": "Done on staging.", "status": "done"}])
    live.post(f"/api/tasks/{parent_id}/messages", {"text": "answer DevOps"})
    wait_for(lambda: live.task(child_id)["status"] == "done", 30, "the child to finish")
    _quiet(live)
    line = _lines(live.task(child_id))[-1]
    assert line["text"] == "Use staging." and line["from_task"] == {"task_id": parent_id, "ai_user_id": "engineer"}
    assert _prompts(env, "DevOps")[-1].startswith(f"Message from Engineer (task {parent_id}):\n\nUse staging.")
    reply = next(r for r in _replies(live.task(parent_id)) if "to myself" in r or "refused (404)" in r)
    assert f"sent to task {child_id}" in reply and f"refused (404): task {parent_id} is not a child task" in reply
    live.post(f"/api/tasks/{child_id}/archive")
    _script(env, Engineer=[{"commands": [_send(child_id, "one more thing")]}])
    live.post(f"/api/tasks/{parent_id}/messages", {"text": "write again"})
    assert "refused (409)" in _replies(live.wait_task(parent_id))[-1]


def test_a_child_of_an_archived_parent_ends_as_today(live, env):
    # Constraint: AC12, P3 default — the parent is archived: nothing is delivered; the child's message is for Pablo.
    # Input: Engineer's turn creates the child and ends done; Pablo archives it; DevOps asks "Which server?" after 3 s.
    # Expected output: the parent's chat has no line from the child; the child waits on Pablo (waiting_on null) and
    #                  its comment is listed in Activity.
    ticket, parent_id = _parent_on_ticket(
        live, env, Engineer=[{"commands": [_create("DevOps", "check the deploy")], "status": "done"}],
        DevOps=[{"sleep": 3, "message": "Which server?"}],
    )
    child_id = _child(live, parent_id)["id"]
    live.wait_task(parent_id)
    live.post(f"/api/tasks/{parent_id}/archive")
    child = live.wait_task(child_id)
    _quiet(live)
    assert _lines(live.task(parent_id)) == []
    assert (child["status"], child["waiting_on"]) == ("waiting_on_user", None)
    question = next(c for c in _comments(live, ticket["id"]) if c["author_id"] == "devops")
    assert question["in_activity"] == 1 and question["id"] in [i["comment"]["id"] for i in live.get("/api/activity")["items"]]


def test_a_stopped_or_failed_child_tells_nobody(live, env):
    # Constraint: out of scope by the spec — a stopped child and a failed child notify nobody; both still read as
    #             waiting on the asker while the parent is live (P4 default), and on Pablo once it is archived.
    # Input: Engineer creates a DevOps child (sleeps 30 s) and a Data Scientist child (its turn fails), ends done;
    #        Pablo stops the DevOps child; later archives the parent.
    # Expected output: no line in the parent; both children waiting_on the parent, then null.
    ticket, parent_id = _parent_on_ticket(
        live, env,
        Engineer=[{"commands": [_create("DevOps", "long work"), _create("DataScientist", "a query")], "status": "done"}],
        DevOps=[{"sleep": 30}], DataScientist=[{"not_logged_in": True}],
    )
    wait_for(lambda: len(live.task(parent_id)["children"]) == 2, 20, "two children")
    devops, scientist = [c["id"] for c in live.task(parent_id)["children"]]
    wait_for(lambda: live.hub.tasks._active.get(devops) and live.hub.tasks._active[devops].proc, 10, "the child's process")
    live.post(f"/api/tasks/{devops}/stop")
    _quiet(live)
    assert _lines(live.task(parent_id)) == []
    assert live.task(scientist)["status_reason"]
    for child_id in (devops, scientist):
        assert live.task(child_id)["waiting_on"] == {"task_id": parent_id, "ai_user_id": "engineer"}
    live.post(f"/api/tasks/{parent_id}/archive")
    assert [live.task(c)["waiting_on"] for c in (devops, scientist)] == [None, None]


def test_a_turn_during_the_childs_live_run_is_a_progress_note(app, env):
    # Constraint: AC29 — a child's message while its own harness run works is not delivered to the parent.
    # Input: a child task whose harness run is a living stub process; its turn ends with a message.
    # Expected output: the child's reply exists; the parent has no line from it.
    parent = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "x", "model": "opus"})
    app.wait_task(parent["id"])
    _script(env, DevOps=[{"sleep": 1, "message": "Run started; it reports later."}])
    child = app.hub.tasks.create("devops", "opus", "do it", origin="ai_user", first_kind="ai_user", parent_task_id=parent["id"])
    proc = subprocess.Popen(["sleep", "30"])
    try:
        app.hub.db.run(
            "INSERT INTO harness_runs (run_id, task_id, workflow, feature, project, status, pid, started_at)"
            " VALUES ('stub_1', ?, 'feature-v1', 'stub', 'demo', 'running', ?, '2026-01-01T00:00:00Z')",
            (child["id"], proc.pid),
        )
        app.hub.bridge._procs["stub_1"] = proc
        wait_for(lambda: not app.hub.tasks.is_working(child["id"]) and _replies(app.task(child["id"])), 20, "the child's turn")
        assert _lines(app.task(parent["id"])) == []
        assert app.task(child["id"])["status"] == "running"
    finally:
        proc.kill()


# ---------------------------------------------------------------- whom a task waits on (AC14, AC15)
def test_a_parent_that_waits_for_its_child_waits_on_the_receiver(live, env):
    # Constraint: AC15 — a parent's turn that ends waiting_on_child shows it waiting on the receiver, also after a
    #             restart; a message to the parent clears it; with no child at work nothing is stored.
    # Input: Engineer creates a DevOps child (sleeps 30 s) and ends waiting_on_child; Pablo stops the child; the app is
    #        rebuilt; Pablo writes to the parent. Then a task without children ends waiting_on_child.
    # Expected output: waiting_on {child, devops} before and after the rebuild, null after the message; null for the other.
    ticket, parent_id = _parent_on_ticket(
        live, env, Engineer=[{"commands": [_create("DevOps", "long work")], "status": "waiting_on_child"}],
        DevOps=[{"sleep": 30}],
    )
    child_id = _child(live, parent_id)["id"]
    parent = live.wait_task(parent_id)
    assert (parent["status"], parent["waiting_on"]) == ("waiting_on_user", {"task_id": child_id, "ai_user_id": "devops"})
    live.post(f"/api/tasks/{child_id}/stop")
    again = live.rebuild()
    try:
        assert again.task(parent_id)["waiting_on"] == {"task_id": child_id, "ai_user_id": "devops"}
        assert again.task(child_id)["waiting_on"] == {"task_id": parent_id, "ai_user_id": "engineer"}
        env.scenario()
        again.post(f"/api/tasks/{parent_id}/messages", {"text": "status?"})
        assert again.wait_task(parent_id)["waiting_on"] is None
        env.scenario(status="waiting_on_child")
        alone = again.post("/api/tasks", {"ai_user_id": "devops", "message": "x", "model": "opus"})
        t = again.wait_task(alone["id"])
        assert (t["status"], t["waiting_on"]) == ("waiting_on_user", None)
    finally:
        again.wait_idle()
        again.hub.shutdown()


# ---------------------------------------------------------------- instructions (AC24)
def test_new_and_open_tasks_learn_how_to_ask_another_ai_user(app, env):
    # Constraint: AC24 — new tasks get the commands in their rules; tasks opened before the change get the skill.
    # Input: a new task; its stored system prompt then replaced by a text without the commands; one more turn.
    # Expected output: the first system prompt names both commands; the workspace links the ask-ai-user skill, which
    #                  names both commands, the incoming message head, the gates and the answer-or-ask-Pablo rule.
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "x", "model": "opus"})
    app.wait_task(task["id"])
    system = next(c for c in env.calls() if "--json-schema" in c["argv"])["argv"]
    system = system[system.index("--append-system-prompt") + 1]
    assert "agenthub task create" in system and "agenthub task send" in system and "waiting_on_child" in system
    app.hub.db.run("UPDATE tasks SET system_prompt = 'You are an AI user of AgentHub.' WHERE id = ?", (task["id"],))
    app.post(f"/api/tasks/{task['id']}/messages", {"text": "again"})
    app.wait_task(task["id"])
    skill = app.config.tasks_dir / str(task["id"]) / "workspace" / ".claude" / "skills" / "ask-ai-user" / "SKILL.md"
    text = skill.read_text()
    for phrase in ("agenthub task create", "agenthub task send", "Message from <AI user> (task <id>)", "gate",
                   "Pablo's ticket, comments or messages already settle", "ask Pablo", "waiting_on_child"):
        assert phrase in text, phrase

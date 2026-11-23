"""The task runner: turns, status, timer, session tokens, stop, continue, recovery (fake `claude`)."""

import json
import time

from agenthub.tests.conftest import wait_for


def _launches(env):
    return [c for c in env.calls() if "--json-schema" in c["argv"]]


def _arg(call, name):
    argv = call["argv"]
    return argv[argv.index(name) + 1] if name in argv else None


def test_first_turn_gets_the_ticket_and_the_role_prompt(app, env):
    detail = app.ticket("Fix the login page", "The button does nothing.", assignee="engineer")
    task = detail["tasks"][0]
    assert task["status"] == "running" and task["ai_user_id"] == "engineer" and task["origin"] == "assignment"
    app.wait_task(task["id"])
    call = _launches(env)[0]
    prompt = call["argv"][-1]
    assert "Fix the login page" in prompt and "The button does nothing." in prompt
    system = _arg(call, "--append-system-prompt")
    assert "Design and implement a solution to the defined problem." in system
    assert "private folder" in system.lower()
    assert _arg(call, "--model") == "opus"
    assert _arg(call, "--setting-sources") == "project,local"
    assert json.loads(_arg(call, "--json-schema"))["required"] == ["message", "status", "title"]


def test_turn_end_posts_the_message_as_comment_and_applies_status(app, env):
    env.scenario(status="done", message="All finished.", title="Login fix")
    detail = app.ticket("T", "D", assignee="engineer")
    task = app.wait_task(detail["tasks"][0]["id"])
    assert task["status"] == "done"
    assert task["title"] == "Login fix"
    assert [e["text"] for e in task["events"] if e["kind"] == "reply"] == ["All finished."]
    comments = app.get(f"/api/tickets/{detail['id']}")["comments"]
    assert [(c["author_id"], c["body"], c["task_id"]) for c in comments] == [("engineer", "All finished.", task["id"])]


def test_waiting_status_and_a_reply_without_structured_output(app, env):
    env.scenario(no_structured_output=True)
    detail = app.ticket("T", "D", assignee="devops")
    task = app.wait_task(detail["tasks"][0]["id"])
    assert task["status"] == "waiting_on_user"
    reply = [e["text"] for e in task["events"] if e["kind"] == "reply"]
    assert len(reply) == 1 and reply[0].startswith("Fake reply 1")


def test_session_tokens_are_the_session_totals(app, env):
    env.scenario(turns=[{"report": 1000}, {"report": 2500}, {"report": 400, "session_gone": True}, {"report": 400}])
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "hello", "model": "haiku"})
    app.wait_task(task["id"])
    assert app.task(task["id"])["session_tokens"] == 1000
    app.post(f"/api/tasks/{task['id']}/messages", {"text": "again"})
    assert app.wait_task(task["id"])["session_tokens"] == 2500
    # the session is gone: the turn is replayed in a replacement session that reports 400
    app.post(f"/api/tasks/{task['id']}/messages", {"text": "third"})
    t = app.wait_task(task["id"])
    assert t["session_tokens"] == 2900
    assert t["harness_tokens"] == 0


def test_session_gone_falls_back_to_the_history_replay(app, env):
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "Remember the word orchid.", "model": "opus"})
    first = app.wait_task(task["id"])
    env.scenario(turns=[{"session_gone": True}])
    app.post(f"/api/tasks/{task['id']}/messages", {"text": "What was the word?"})
    t = app.wait_task(task["id"])
    launches = _launches(env)
    assert _arg(launches[1], "--resume") == first["session_id"]
    replay = launches[2]
    assert "--resume" not in replay["argv"]
    assert "Remember the word orchid." in replay["argv"][-1] and "What was the word?" in replay["argv"][-1]
    assert t["session_id"] != first["session_id"]


def test_timer_advances_only_while_running(app, env):
    env.scenario(sleep=0.6)
    task = app.post("/api/tasks", {"ai_user_id": "devops", "message": "hi", "model": "opus"})
    assert task["running_since"] is not None
    t = app.wait_task(task["id"])
    assert t["running_since"] is None and t["running_ms"] >= 500
    time.sleep(0.3)
    assert app.task(task["id"])["running_ms"] == t["running_ms"]


def test_stop_ends_a_sleeping_turn_and_keeps_the_history(app, env):
    env.scenario(sleep=60)
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "long work", "model": "opus"})
    wait_for(lambda: app.hub.tasks._active.get(task["id"]) and app.hub.tasks._active[task["id"]].proc, 10, "the process")
    started = time.monotonic()
    stopped = app.post(f"/api/tasks/{task['id']}/stop")
    assert stopped["status"] == "waiting_on_user"
    app.wait_idle(timeout=10)
    assert time.monotonic() - started < 10
    t = app.task(task["id"])
    assert t["status"] == "waiting_on_user"
    kinds = [e["kind"] for e in t["events"]]
    assert kinds[0] == "user" and "system" in kinds
    assert any(e["text"] == "Stopped by Pablo" for e in t["events"])
    assert not [e for e in t["events"] if e["kind"] == "reply"]


def test_a_message_sent_while_running_is_queued_and_runs_next(app, env):
    env.scenario(turns=[{"sleep": 1.0}, {}])
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "first", "model": "opus"})
    queued = app.post(f"/api/tasks/{task['id']}/messages", {"text": "second"})
    assert [e["queued"] for e in queued["events"] if e["kind"] == "user"] == [False, True]
    t = app.wait_task(task["id"])
    launches = _launches(env)
    assert len(launches) == 2
    assert "second" in launches[1]["argv"][-1]
    assert _arg(launches[1], "--resume") == t["session_id"]
    assert len([e for e in t["events"] if e["kind"] == "reply"]) == 2


def test_a_message_to_a_done_task_continues_its_session(app, env):
    env.scenario(status="done")
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "first", "model": "opus"})
    done = app.wait_task(task["id"])
    assert done["status"] == "done"
    running = app.post(f"/api/tasks/{task['id']}/messages", {"text": "one more"})
    assert running["status"] == "running"
    t = app.wait_task(task["id"])
    assert _arg(_launches(env)[1], "--resume") == done["session_id"]
    assert "2 messages seen" in [e["text"] for e in t["events"] if e["kind"] == "reply"][-1]


def test_a_model_change_reaches_the_next_launch(app, env):
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "first", "model": "opus"})
    app.wait_task(task["id"])
    assert app.patch(f"/api/tasks/{task['id']}", {"model": "haiku"})["model"] == "haiku"
    app.post(f"/api/tasks/{task['id']}/messages", {"text": "next"})
    app.wait_task(task["id"])
    assert [_arg(c, "--model") for c in _launches(env)] == ["opus", "haiku"]


def test_not_logged_in_leaves_the_task_waiting_with_the_reason(app, env):
    env.scenario(not_logged_in=True)
    app.hub.sessions._login = None
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "hi", "model": "opus"})
    t = app.wait_task(task["id"])
    assert t["status"] == "waiting_on_user"
    assert "claude auth login" in t["status_reason"]
    assert not _launches(env)
    assert app.get("/api/login")["logged_in"] is False


def test_restart_recovery_and_continue_with_the_stored_session(app, env):
    env.scenario(sleep=30)
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "work", "model": "opus"})
    wait_for(lambda: app.task(task["id"])["session_id"], 10, "the session id")
    session_id = app.task(task["id"])["session_id"]
    # the server dies with the turn running: simulate by killing the process and dropping the hub
    proc = app.hub.tasks._active[task["id"]].proc
    app.hub.tasks._finish = lambda *args, **kwargs: None  # the dead server records nothing more
    app.hub.tasks._active.clear()
    proc.kill()
    env.scenario()
    restarted = app.__class__(env, app.port)
    t = restarted.task(task["id"])
    assert t["status"] == "waiting_on_user" and t["status_reason"] == "interrupted by a restart"
    assert t["running_since"] is None
    assert t["session_id"] == session_id
    restarted.post(f"/api/tasks/{task['id']}/messages", {"text": "continue please"})
    restarted.wait_task(task["id"])
    assert _arg(_launches(env)[-1], "--resume") == session_id
    restarted.hub.shutdown()


def test_restart_keeps_tickets_comments_and_tasks(app, env):
    env.scenario(status="done", title="Kept title")
    detail = app.ticket("Persisted", "Body", assignee="devops")
    task = app.wait_task(detail["tasks"][0]["id"])
    again = app.rebuild()
    t = again.task(task["id"])
    for key in ("status", "title", "model", "running_ms", "session_tokens", "harness_tokens", "session_id"):
        assert t[key] == task[key], key
    assert [e["text"] for e in t["events"]] == [e["text"] for e in task["events"]]
    assert again.get(f"/api/tickets/{detail['id']}")["comments"][0]["body"] == task["events"][-1]["text"]
    again.hub.shutdown()


def test_session_settings_deny_the_app_code_not_the_private_folder(app, env):
    task = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "hi", "model": "opus"})
    app.wait_task(task["id"])
    settings = json.loads((app.config.tasks_dir / str(task["id"]) / "settings.json").read_text())
    deny = settings["permissions"]["deny"]
    assert any(f"{app.config.root}/agenthub/" in rule for rule in deny)
    assert not any(str(env.private) in rule for rule in deny)
    protected = _launches(env)[0]["env"]["HARNESS_PROTECTED_PATHS"]
    assert str(app.config.root / "agenthub") in protected and str(env.private) not in protected


def test_an_edited_role_prompt_reaches_tasks_started_afterwards(app, env):
    before = app.post("/api/tasks", {"ai_user_id": "devops", "message": "one", "model": "opus"})
    app.wait_task(before["id"])
    app.patch("/api/users/devops", {"prompt": "You are DevOps. Always answer in haiku form."})
    assert app.get("/api/bootstrap")["users"][3]["prompt"].endswith("haiku form.")
    after = app.post("/api/tasks", {"ai_user_id": "devops", "message": "two", "model": "opus"})
    app.wait_task(after["id"])
    systems = [_arg(c, "--append-system-prompt") for c in _launches(env)]
    assert "haiku form" not in systems[0] and "haiku form" in systems[1]

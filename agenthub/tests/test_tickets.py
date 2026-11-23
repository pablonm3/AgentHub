"""Tickets, assignment hand-over, comment routing, a ticket's tasks and totals, Activity (HTTP, fakes)."""

import threading

from agenthub.tests.conftest import wait_for


def _events(app, task_id):
    return app.task(task_id)["events"]


def _tasks_of(app, ticket_id):
    return app.get(f"/api/tickets/{ticket_id}")["tasks"]


def _mention_task(app, ticket_id, handle, text="please look"):
    out = app.comment(ticket_id, f"@{handle} {text}")
    assert len(out["started"]) == 1
    return app.wait_task(out["started"][0])


# ---------------------------------------------------------------- creation and projects
def test_bootstrap_lists_users_projects_and_choices(app):
    b = app.get("/api/bootstrap")
    assert [u["name"] for u in b["users"]] == ["Pablo", "Data Scientist", "Engineer", "DevOps"]
    assert [s["name"] for s in b["stages"]] == ["Backlog", "To do", "In progress", "In review", "Done"]
    assert b["models"] == ["fable", "opus", "sonnet", "haiku"] and b["default_model"] == "opus"
    assert {p["name"]: p["ready"] for p in b["projects"]} == {"demo": True, "draft": False}
    assert app.get("/api/tickets")["tickets"] == []


def test_create_keeps_the_project_and_refuses_bad_choices(app):
    t = app.ticket("With project", project="demo")
    assert t["project"] == "demo" and t["project_info"]["repo"]
    assert app.ticket("No project")["project"] is None
    body = {"title": "x", "description": "", "stage": "backlog", "assignee_id": "pablo", "model": "opus"}
    assert "exactly one" in app.post("/api/tickets", body, status=422)["message"]
    app.post("/api/tickets", {**body, "project": "nope"}, status=422)
    app.patch(f"/api/tickets/{t['id']}", {"project": None}, status=422)
    assert app.get(f"/api/tickets/{t['id']}")["project"] == "demo"


def test_new_project_without_url_exists_before_the_task_starts(app, env, monkeypatch):
    seen = {}
    original = app.hub.tasks.create

    def spy(*args, **kwargs):
        seen["projects"] = [p["name"] for p in app.hub.projects.list_projects()]
        seen["gh"] = [c["argv"][:3] for c in env.gh_log()]
        return original(*args, **kwargs)

    monkeypatch.setattr(app.hub.tasks, "create", spy)
    t = app.ticket("New one", assignee="engineer", new_project={"name": "fresh"})
    assert t["project"] == "fresh" and len(t["tasks"]) == 1
    assert "fresh" in seen["projects"] and ["repo", "create", "fresh"] in seen["gh"]
    first = app.wait_task(t["tasks"][0]["id"])
    assert "TODO" not in first["events"][0]["text"] and "template" in first["events"][0]["text"]


def test_new_project_with_url_exists_before_the_task_starts(app, env, monkeypatch, tmp_path):
    from agenthub import projects as projects_module
    from agenthub.tests.serve_fake import make_bare_repo

    remote = make_bare_repo(tmp_path / "given.git", {"README.md": "x"}, branch="trunk")
    monkeypatch.setattr(projects_module, "check_repo_url", lambda url: url)
    seen = {}
    original = app.hub.tasks.create

    def spy(*args, **kwargs):
        seen["projects"] = {p["name"]: p["default_base"] for p in app.hub.projects.list_projects()}
        return original(*args, **kwargs)

    monkeypatch.setattr(app.hub.tasks, "create", spy)
    t = app.ticket("Given", assignee="engineer", new_project={"name": "given", "repo_url": str(remote)})
    assert seen["projects"]["given"] == "trunk"
    assert env.gh_log() == []
    app.wait_task(t["tasks"][0]["id"])


def test_failed_registration_creates_no_ticket_and_no_task(app, env):
    env.gh_scenario(name_taken=True)
    out = app.post("/api/tickets", {"title": "x", "description": "", "stage": "backlog", "assignee_id": "engineer",
                                    "model": "opus", "new_project": {"name": "taken"}}, status=502)
    assert "already exists" in out["message"]
    assert app.get("/api/tickets")["tickets"] == [] and app.get("/api/tasks")["tasks"] == []
    assert "taken" not in [p["name"] for p in app.hub.projects.list_projects()]


def test_first_prompt_states_the_project_or_its_absence(app, env):
    none = app.ticket("Free", assignee="engineer")
    with_project = app.ticket("On demo", assignee="devops", project="demo")
    free_input = app.wait_task(none["tasks"][0]["id"])["events"][0]["text"]
    demo_input = app.wait_task(with_project["tasks"][0]["id"])["events"][0]["text"]
    assert "no project" in free_input.lower() and "no harness run can be started" in free_input
    assert "project is demo" in demo_input


# ---------------------------------------------------------------- assignment (AC4, AC5, AC45)
def test_assignee_pablo_starts_nothing_and_a_later_ai_assignee_starts_a_task(app):
    t = app.ticket("Later", "Ticket body text")
    assert t["tasks"] == []
    after = app.patch(f"/api/tickets/{t['id']}", {"assignee_id": "engineer"})
    assert len(after["tasks"]) == 1
    task = app.wait_task(after["tasks"][0]["id"])
    assert task["origin"] == "assignment" and "Ticket body text" in task["events"][0]["text"]


def test_assigning_an_ai_user_with_an_open_task_hands_the_ticket_over(app, env):
    for final in ("waiting_on_user", "done"):
        env.scenario(status=final)
        t = app.ticket(f"Hand-over {final}", "Describe the zebra-lantern plan.")
        mention = _mention_task(app, t["id"], "Engineer")
        assert mention["status"] == final
        replies_before = len([e for e in mention["events"] if e["kind"] == "reply"])
        after = app.patch(f"/api/tickets/{t['id']}", {"assignee_id": "engineer"})
        assert [x["id"] for x in after["tasks"]] == [mention["id"]]
        assert after["tasks"][0]["status"] == "running"
        task = app.wait_task(mention["id"])
        notices = [e for e in task["events"] if e["kind"] == "notice"]
        assert "Describe the zebra-lantern plan." in notices[-1]["text"] and "whole ticket" in notices[-1]["text"]
        assert len([e for e in task["events"] if e["kind"] == "reply"]) == replies_before + 1
        resumed = [c for c in env.calls() if "--json-schema" in c["argv"]][-1]
        assert resumed["argv"][resumed["argv"].index("--resume") + 1] == mention["session_id"]
        assert "Hand-over" in resumed["argv"][-1]


def test_hand_over_to_a_running_task_is_queued(app, env):
    env.scenario(turns=[{"sleep": 1.0}, {}])
    t = app.ticket("Busy", "body")
    out = app.comment(t["id"], "@Engineer start")
    task_id = out["started"][0]
    app.patch(f"/api/tickets/{t['id']}", {"assignee_id": "engineer"})
    queued = [e for e in _events(app, task_id) if e["kind"] == "notice"]
    assert queued[-1]["queued"] is True
    task = app.wait_task(task_id)
    assert len([e for e in task["events"] if e["kind"] == "reply"]) == 2
    assert len(_tasks_of(app, t["id"])) == 1


def test_assignment_after_archiving_starts_a_new_task(app, env):
    env.scenario(status="done")
    t = app.ticket("Archive then assign", "body")
    first = _mention_task(app, t["id"], "Engineer")
    app.post(f"/api/tasks/{first['id']}/archive")
    after = app.patch(f"/api/tickets/{t['id']}", {"assignee_id": "engineer"})
    assert len(after["tasks"]) == 2 and after["tasks"][1]["origin"] == "assignment"
    app.wait_task(after["tasks"][1]["id"])


def test_reassigning_back_and_forth_keeps_one_task(app, env):
    t = app.ticket("Ping pong", "body", assignee="engineer")
    task_id = t["tasks"][0]["id"]
    app.wait_task(task_id)
    app.patch(f"/api/tickets/{t['id']}", {"assignee_id": "pablo"})
    app.patch(f"/api/tickets/{t['id']}", {"assignee_id": "engineer"})
    app.wait_task(task_id)
    before = len(_events(app, task_id))
    app.patch(f"/api/tickets/{t['id']}", {"assignee_id": "engineer"})  # the current assignee again: nothing
    assert len(_events(app, task_id)) == before
    tasks = _tasks_of(app, t["id"])
    assert len(tasks) == 1
    assert len([e for e in _events(app, task_id) if e["kind"] == "notice"]) == 2


def test_a_mention_and_an_assignment_at_the_same_moment_leave_one_task(app):
    t = app.ticket("Race", "body")
    barrier = threading.Barrier(2)
    errors = []

    def mention():
        barrier.wait()
        try:
            app.comment(t["id"], "@Engineer now")
        except AssertionError as e:
            errors.append(e)

    def assign():
        barrier.wait()
        try:
            app.patch(f"/api/tickets/{t['id']}", {"assignee_id": "engineer"})
        except AssertionError as e:
            errors.append(e)

    threads = [threading.Thread(target=mention), threading.Thread(target=assign)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert not errors
    assert len([x for x in _tasks_of(app, t["id"]) if x["ai_user_id"] == "engineer"]) == 1
    app.wait_idle()


# ---------------------------------------------------------------- comment routing
def test_plain_comment_goes_to_the_assignee_task_only(app):
    t = app.ticket("Routing", "body", assignee="engineer")
    engineer = app.wait_task(t["tasks"][0]["id"])
    devops = _mention_task(app, t["id"], "DevOps")
    devops_events = len(devops["events"])
    out = app.comment(t["id"], "plain words for the assignee")
    assert out["delivered_to"] == [engineer["id"]] and out["started"] == []
    assert app.task(engineer["id"])["status"] == "running" or app.hub.tasks.is_working(engineer["id"])
    task = app.wait_task(engineer["id"])
    assert "plain words for the assignee" in [e["text"] for e in task["events"] if e["kind"] == "user"]
    after = app.task(devops["id"])
    assert len(after["events"]) == devops_events and after["status"] == devops["status"]
    comment = [c for c in app.get(f"/api/tickets/{t['id']}")["comments"] if c["body"] == "plain words for the assignee"][0]
    assert comment["delivered_to"] == [{"task_id": engineer["id"], "ai_user_id": "engineer"}]


def test_plain_comment_reaches_no_task_when_the_assignee_has_none(app, env):
    t = app.ticket("Pablo's ticket", "body")
    engineer = _mention_task(app, t["id"], "Engineer")
    before = len(engineer["events"])
    out = app.comment(t["id"], "just a note")
    assert out == {**out, "delivered_to": [], "started": []}
    assert len(app.task(engineer["id"])["events"]) == before
    env.scenario(status="done")
    t2 = app.ticket("Archived assignee", "body", assignee="devops")
    done = app.wait_task(t2["tasks"][0]["id"])
    app.post(f"/api/tasks/{done['id']}/archive")
    out2 = app.comment(t2["id"], "a note on an archived task's ticket")
    assert out2["delivered_to"] == [] and out2["started"] == []
    assert len(_tasks_of(app, t2["id"])) == 1
    assert [c["body"] for c in app.get(f"/api/tickets/{t2['id']}")["comments"]][-1] == "a note on an archived task's ticket"


def test_mention_starts_a_comment_scoped_task_then_reuses_it(app, env):
    t = app.ticket("Mentions", "The ticket body.", assignee="engineer")
    engineer = app.wait_task(t["tasks"][0]["id"])
    engineer_events = len(engineer["events"])
    out = app.comment(t["id"], "@DevOps check the deploy script")
    assert out["delivered_to"] == []
    devops = app.wait_task(out["started"][0])
    first = devops["events"][0]["text"]
    assert "@DevOps check the deploy script" in first and "Only this comment was assigned to you" in first
    assert devops["origin"] == "mention"
    env.scenario(status="done")
    out2 = app.comment(t["id"], "@DevOps and the cron job too")
    assert out2["delivered_to"] == [devops["id"]] and out2["started"] == []
    done = app.wait_task(devops["id"])
    out3 = app.comment(t["id"], "@DevOps one more on a done task")
    assert out3["delivered_to"] == [devops["id"]]
    app.wait_task(devops["id"])
    assert len(_tasks_of(app, t["id"])) == 2
    assert len(app.task(engineer["id"])["events"]) == engineer_events
    assert done["status"] == "done"


def test_a_comment_mentioning_two_ai_users(app):
    t = app.ticket("Two", "body")
    engineer = _mention_task(app, t["id"], "Engineer")
    out = app.comment(t["id"], "@Engineer and @DataScientist please both look")
    assert out["delivered_to"] == [engineer["id"]] and len(out["started"]) == 1
    assert app.task(out["started"][0])["ai_user_id"] == "data_scientist"
    app.wait_idle()


def test_activity_reply_without_mention_goes_to_the_posting_task(app, env):
    t = app.ticket("Activity", "body", assignee="engineer")
    engineer = app.wait_task(t["tasks"][0]["id"])
    devops = _mention_task(app, t["id"], "DevOps")
    entry = [i for i in app.get("/api/activity")["items"] if i["task_id"] == devops["id"]][0]
    engineer_events = len(app.task(engineer["id"])["events"])
    out = app.comment(t["id"], "thanks, go on", reply_to=entry["comment"]["id"])
    assert out["delivered_to"] == [devops["id"]] and out["started"] == []
    app.wait_idle()
    assert len(app.task(engineer["id"])["events"]) == engineer_events
    # an entry of an archived task: the reply reaches no task
    env.scenario(status="done")
    app.comment(t["id"], "@DevOps finish up")
    app.wait_task(devops["id"])
    app.post(f"/api/tasks/{devops['id']}/archive")
    out2 = app.comment(t["id"], "after archive", reply_to=entry["comment"]["id"])
    assert out2["delivered_to"] == [] and out2["started"] == []


def test_activity_reply_with_mention_goes_only_to_the_mentioned(app):
    t = app.ticket("Activity mention", "body", assignee="devops")
    devops = app.wait_task(t["tasks"][0]["id"])
    entry = app.get("/api/activity")["items"][0]
    assert entry["task_id"] == devops["id"]
    before = app.task(devops["id"])
    out = app.comment(t["id"], "@Engineer take this one: kiwi-3 reply", reply_to=entry["comment"]["id"])
    assert out["delivered_to"] == [] and len(out["started"]) == 1
    engineer = app.wait_task(out["started"][0])
    out2 = app.comment(t["id"], "@Engineer second note kiwi-4", reply_to=entry["comment"]["id"])
    assert out2["delivered_to"] == [engineer["id"]] and out2["started"] == []
    app.wait_idle()
    after = app.task(devops["id"])
    assert len(after["events"]) == len(before["events"]) and after["status"] == before["status"]
    out3 = app.comment(t["id"], "@DevOps only you", reply_to=entry["comment"]["id"])
    assert out3["delivered_to"] == [devops["id"]]
    app.wait_idle()
    bodies = [c["body"] for c in app.get(f"/api/tickets/{t['id']}")["comments"]]
    assert "@Engineer take this one: kiwi-3 reply" in bodies and "@DevOps only you" in bodies


def test_a_mention_inside_an_ai_comment_starts_nothing(app):
    t = app.ticket("AI mention", "body")
    app.hub.tickets.add_comment(t["id"], "engineer", "@DevOps could you help?")
    assert _tasks_of(app, t["id"]) == []


# ---------------------------------------------------------------- a ticket's tasks and totals (AC46, AC47)
def test_a_ticket_lists_its_tasks_and_sums_their_tokens(app, env):
    t = app.ticket("Totals", "body", assignee="engineer")
    engineer = app.wait_task(t["tasks"][0]["id"])
    app.comment(t["id"], "second turn")
    engineer = app.wait_task(engineer["id"])
    env.scenario(status="done")
    devops = _mention_task(app, t["id"], "DevOps")
    app.post(f"/api/tasks/{devops['id']}/archive")
    app.hub.db.run(
        "INSERT INTO harness_runs (run_id, task_id, workflow, feature, project, status, input_tokens, output_tokens,"
        " started_at) VALUES ('x_1', ?, 'feature-v1', 'x', 'demo', 'paused', 1000, 2000, '2026-01-01T00:00:00Z')",
        (engineer["id"],),
    )
    other = app.ticket("Other", "body", assignee="data_scientist")
    app.wait_task(other["tasks"][0]["id"])
    free = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "no ticket", "model": "opus"})
    app.wait_task(free["id"])
    detail = app.get(f"/api/tickets/{t['id']}")
    tasks = {x["id"]: x for x in detail["tasks"]}
    assert set(tasks) == {engineer["id"], devops["id"]}
    assert tasks[devops["id"]]["status"] == "archived"
    assert detail["session_tokens"] == app.task(engineer["id"])["session_tokens"] + app.task(devops["id"])["session_tokens"]
    assert detail["session_tokens"] > 0
    assert detail["harness_tokens"] == 3000
    for x in detail["tasks"]:
        for key in ("id", "status", "title", "display_title", "ai_user_id", "model", "running_ms", "running_since",
                    "session_tokens", "harness_tokens"):
            assert key in x
        assert app.task(x["id"])["events"]
    empty = app.ticket("Empty")
    assert (app.get(f"/api/tickets/{empty['id']}")["session_tokens"], app.get(f"/api/tickets/{empty['id']}")["harness_tokens"]) == (0, 0)


# ---------------------------------------------------------------- tasks, Activity, settings, guard
def test_new_task_needs_an_ai_user(app):
    assert "AI user" in app.post("/api/tasks", {"message": "x", "model": "opus"}, status=422)["message"]
    app.post("/api/tasks", {"ai_user_id": "pablo", "message": "x", "model": "opus"}, status=422)
    t = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "x", "model": "opus"})
    assert t["ticket_id"] is None and t["origin"] == "manual"
    app.wait_task(t["id"])


def test_edited_title_survives_a_turn(app, env):
    env.scenario(title="AI title")
    t = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "x", "model": "opus"})
    assert app.wait_task(t["id"])["title"] == "AI title"
    app.patch(f"/api/tasks/{t['id']}", {"title": "Pablo's title"})
    env.scenario(title="Another AI title")
    app.post(f"/api/tasks/{t['id']}/messages", {"text": "more"})
    assert app.wait_task(t["id"])["title"] == "Pablo's title"
    assert app.rebuild().task(t["id"])["title"] == "Pablo's title"


def test_archive_only_from_done_and_then_read_only(app, env):
    t = app.post("/api/tasks", {"ai_user_id": "engineer", "message": "x", "model": "opus"})
    app.wait_task(t["id"])
    app.post(f"/api/tasks/{t['id']}/archive", status=409)
    env.scenario(status="done")
    app.post(f"/api/tasks/{t['id']}/messages", {"text": "finish"})
    app.wait_task(t["id"])
    archived = app.post(f"/api/tasks/{t['id']}/archive")
    assert archived["status"] == "archived" and archived["events"]
    app.post(f"/api/tasks/{t['id']}/messages", {"text": "again"}, status=409)
    app.patch(f"/api/tasks/{t['id']}", {"title": "x"}, status=409)
    assert t["id"] not in [x["id"] for x in app.get("/api/tasks")["tasks"]]
    assert t["id"] in [x["id"] for x in app.get("/api/tasks?status=archived")["tasks"]]
    assert app.task(t["id"])["status"] == "archived"


def test_activity_counts_unseen_until_seen(app):
    t = app.ticket("Act", "body", assignee="engineer")
    app.wait_task(t["tasks"][0]["id"])
    a = app.get("/api/activity")
    assert a["unseen"] == 1 and a["items"][0]["ai_user_id"] == "engineer" and a["items"][0]["ticket"]["key"] == f"AH-{t['id']}"
    assert app.post("/api/activity/seen")["unseen"] == 0
    assert app.get("/api/activity")["unseen"] == 0
    app.comment(t["id"], "more")
    app.wait_idle()
    items = app.get("/api/activity")
    assert items["unseen"] == 1 and items["items"][0]["comment"]["id"] > items["items"][1]["comment"]["id"]


def test_default_model_preselects_new_work_and_keeps_existing(app):
    t = app.ticket("Before", model="opus")
    assert app.patch("/api/settings", {"default_model": "sonnet"})["default_model"] == "sonnet"
    assert app.get("/api/bootstrap")["default_model"] == "sonnet"
    assert app.get(f"/api/tickets/{t['id']}")["model"] == "opus"
    later = app.post("/api/tickets", {"title": "After", "description": "", "stage": "backlog",
                                      "assignee_id": "engineer", "project": None})
    assert later["model"] == "sonnet" and later["tasks"][0]["model"] == "sonnet"
    app.wait_idle()


def test_a_ticket_model_change_reaches_tasks_started_afterwards(app, env):
    t = app.ticket("Models", "body", model="haiku")
    app.patch(f"/api/tickets/{t['id']}", {"model": "sonnet"})
    out = app.comment(t["id"], "@Engineer go")
    task = app.wait_task(out["started"][0])
    assert task["model"] == "sonnet"
    call = [c for c in env.calls() if "--json-schema" in c["argv"]][-1]
    assert call["argv"][call["argv"].index("--model") + 1] == "sonnet"


def test_foreign_origin_and_non_json_mutations_are_refused(app):
    r = app.client.post("/api/tasks", json={"ai_user_id": "engineer", "message": "x"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    r = app.client.post("/api/tasks", content="ai_user_id=engineer", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415
    r = app.client.get("/api/bootstrap", headers={"Host": "evil.example"})
    assert r.status_code == 403
    assert app.get("/api/tasks")["tasks"] == []

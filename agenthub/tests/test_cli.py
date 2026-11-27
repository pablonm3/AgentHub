"""The session CLI over real HTTP, and the AI-written title (AC10, AC11)."""


def test_title_set_by_the_command(live, env):
    env.scenario(commands=['agenthub title "Deploy the cache"'], title="Structured title")
    task = live.post("/api/tasks", {"ai_user_id": "devops", "message": "x", "model": "opus"})
    t = live.wait_task(task["id"])
    assert t["title"] == "Deploy the cache" and t["title_source"] == "ai"
    tool = [e["text"] for e in t["events"] if e["kind"] == "tool"]
    assert tool and "agenthub title" in tool[0]


def test_title_command_is_ignored_after_a_human_edit(live, env):
    task = live.post("/api/tasks", {"ai_user_id": "devops", "message": "x", "model": "opus"})
    live.wait_task(task["id"])
    live.patch(f"/api/tasks/{task['id']}", {"title": "Mine"})
    env.scenario(commands=['agenthub title "AI again"'])
    live.post(f"/api/tasks/{task['id']}/messages", {"text": "go"})
    t = live.wait_task(task["id"])
    assert t["title"] == "Mine"
    assert "kept: Pablo edited the title" in [e["text"] for e in t["events"] if e["kind"] == "reply"][-1]


def test_structured_title_is_the_fallback(app, env):
    env.scenario(title="From the output")
    task = app.post("/api/tasks", {"ai_user_id": "devops", "message": "first words of a message", "model": "opus"})
    assert task["title"] is None and task["display_title"].startswith("first words")
    assert app.wait_task(task["id"])["title"] == "From the output"


def test_cli_refuses_without_a_task_token(live, env):
    env.scenario(commands=["AGENTHUB_TASK_TOKEN=wrong agenthub title nope"])
    task = live.post("/api/tasks", {"ai_user_id": "devops", "message": "x", "model": "opus"})
    t = live.wait_task(task["id"])
    assert "refused (401)" in [e["text"] for e in t["events"] if e["kind"] == "reply"][-1]


def test_task_create_refuses_without_a_task_token(live, env):
    env.scenario(commands=["AGENTHUB_TASK_TOKEN=wrong agenthub task create --to DevOps check the deploy"])
    task = live.post("/api/tasks", {"ai_user_id": "engineer", "message": "x", "model": "opus"})
    t = live.wait_task(task["id"])
    assert "refused (401): unknown task token" in [e["text"] for e in t["events"] if e["kind"] == "reply"][-1]
    assert t["children"] == [] and len(live.get("/api/tasks")["tasks"]) == 1

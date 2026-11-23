"""The search-history skill's command: tickets, comments and task chats, archived tasks included (AC31)."""


def test_search_finds_a_phrase_with_its_ticket_and_task(live, env):
    a = live.ticket("Quarterly cache notes", "The rollout codename is heliotrope-walrus-58.")
    live.comment(a["id"], "For the record: the vendor passphrase is cobalt-pelican-93.")
    env.scenario(status="done", title="Dock task")
    b = live.ticket("Archive lookup", "Reply noted.", assignee="devops")
    task_id = b["tasks"][0]["id"]
    live.wait_task(task_id)
    live.post(f"/api/tasks/{task_id}/messages", {"text": "the dock number is amber-ostrich-17"})
    live.wait_task(task_id)
    live.post(f"/api/tasks/{task_id}/archive")

    hits = live.hub.tickets.search("HELIOTROPE-walrus-58")["hits"]
    assert [(h["where"], h["ticket"]["key"]) for h in hits] == [("ticket description", f"AH-{a['id']}")]
    hits = live.hub.tickets.search("cobalt-pelican-93")["hits"]
    assert [(h["where"], h["ticket"]["title"]) for h in hits] == [("comment by Pablo", "Quarterly cache notes")]
    hits = live.hub.tickets.search("amber-ostrich-17")["hits"]  # the fake's reply echoes it into a comment too
    chat = [h for h in hits if h["where"] == "task chat"]
    assert len(chat) == 1 and chat[0]["ticket"]["title"] == "Archive lookup"
    assert chat[0]["task"] == {"id": task_id, "title": "Dock task", "status": "archived", "ai_user": "DevOps"}
    assert live.hub.tickets.search("no-such-phrase-anywhere")["hits"] == []

    env.scenario(commands=['agenthub search "amber-ostrich-17"'])
    asking = live.post("/api/tasks", {"ai_user_id": "data_scientist", "message": "where is it?", "model": "opus"})
    reply = [e["text"] for e in live.wait_task(asking["id"])["events"] if e["kind"] == "reply"][-1]
    assert f"AH-{b['id']}" in reply and f"task {task_id}" in reply and "archived" in reply

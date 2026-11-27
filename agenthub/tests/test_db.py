import sqlite3

import pytest

from agenthub.db import ROLES, VERSION, Database, now_iso


def test_fresh_database_has_the_four_users_and_nothing_else(tmp_path):
    db = Database(tmp_path / "a.db")
    users = db.users()
    assert [(u["name"], u["kind"]) for u in users] == [
        ("Pablo", "human"), ("Data Scientist", "ai"), ("Engineer", "ai"), ("DevOps", "ai"),
    ]
    prompts = {u["id"]: u["prompt"] for u in users}
    assert prompts["pablo"] is None
    assert "research a given topic and build a report" in prompts["data_scientist"].lower()
    assert "link" in prompts["data_scientist"]
    assert prompts["engineer"] == (ROLES / "engineer.md").read_text().strip()
    assert "devops tasks" in prompts["devops"]
    assert db.value("SELECT COUNT(*) FROM tickets") == 0
    assert db.value("SELECT COUNT(*) FROM tasks") == 0
    assert db.value("SELECT COUNT(*) FROM comments") == 0
    assert db.setting("default_model") == "opus"


def test_reopening_the_file_keeps_the_rows(tmp_path):
    Database(tmp_path / "a.db").run("UPDATE users SET prompt = 'edited' WHERE id = 'engineer'")
    again = Database(tmp_path / "a.db")
    assert again.user("engineer")["prompt"] == "edited"
    assert len(again.users()) == 4


def _insert_task(db: Database, ticket_id, ai="engineer", status="running", token="t"):
    now = now_iso()
    return db.run(
        "INSERT INTO tasks (ticket_id, ai_user_id, origin, model, status, system_prompt, token, created_at, updated_at)"
        " VALUES (?, ?, 'mention', 'opus', ?, 'p', ?, ?, ?)",
        (ticket_id, ai, status, token, now, now),
    )


def test_one_open_task_per_ai_user_and_ticket(tmp_path):
    db = Database(tmp_path / "a.db")
    now = now_iso()
    ticket = db.run(
        "INSERT INTO tickets (title, stage, position, assignee_id, model, created_at, updated_at)"
        " VALUES ('t', 'backlog', 1, 'pablo', 'opus', ?, ?)", (now, now),
    )
    first = _insert_task(db, ticket, token="a")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_task(db, ticket, status="done", token="b")
    _insert_task(db, ticket, ai="devops", token="c")  # another AI user on the same ticket
    db.run("UPDATE tasks SET status = 'archived' WHERE id = ?", (first,))
    _insert_task(db, ticket, token="d")  # accepted once the first is archived
    _insert_task(db, None, token="e")
    _insert_task(db, None, token="f")  # tasks without a ticket are not covered
    assert db.value("SELECT COUNT(*) FROM tasks") == 5


def test_a_database_from_before_project_chosen_counts_every_ticket_as_chosen(tmp_path):
    path = tmp_path / "a.db"
    db = Database(path)
    now = now_iso()
    for title, project in (("free", None), ("on demo", "demo")):
        db.run(
            "INSERT INTO tickets (title, stage, position, assignee_id, model, project, created_at, updated_at)"
            " VALUES (?, 'backlog', 1, 'pablo', 'opus', ?, ?, ?)", (title, project, now, now),
        )
    # put the file back to version 1: the tickets table as it was before the column
    db.conn().execute("ALTER TABLE tickets DROP COLUMN project_chosen")
    db.conn().execute("PRAGMA user_version = 1")
    db.conn().close()

    def tickets(d: Database) -> list[tuple]:
        return [(r["title"], r["project"], r["project_chosen"]) for r in d.all("SELECT * FROM tickets ORDER BY id")]

    migrated = Database(path)
    assert migrated.value("PRAGMA user_version") == VERSION == 2
    assert tickets(migrated) == [("free", None, 1), ("on demo", "demo", 1)]
    migrated.conn().close()
    again = Database(path)
    assert again.value("PRAGMA user_version") == 2
    assert tickets(again) == [("free", None, 1), ("on demo", "demo", 1)]

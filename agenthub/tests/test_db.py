import sqlite3
from pathlib import Path

import pytest

from agenthub.db import ROLES, SEED_USERS, Database, now_iso


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


# ---------------------------------------------------------------- version 1 → 2 (AC23)
SCHEMA_V1 = Path(__file__).with_name("schema_v1.sql")


def _version_1_file(path: Path) -> Path:
    """A database as the app wrote it before child tasks: a ticket, two tasks, comments, chat lines, turns."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V1.read_text())
    for uid, name, kind, handle, initials, color, _ in SEED_USERS:
        conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, NULL)", (uid, name, kind, handle, initials, color))
    conn.executescript("""
        INSERT INTO tickets (id, title, stage, position, assignee_id, model, created_at, updated_at)
            VALUES (1, 'Old ticket', 'in_progress', 1, 'engineer', 'opus', 'c', 'u');
        INSERT INTO tasks (id, ticket_id, ai_user_id, origin, origin_comment_id, title, title_source, model, status,
                           status_reason, session_id, system_prompt, token, running_ms, running_since, created_at, updated_at)
            VALUES (1, 1, 'engineer', 'assignment', NULL, 'Kept title', 'ai', 'opus', 'done', NULL, 's1', 'rules', 'tok1',
                    4200, NULL, 'c', 'u'),
                   (2, 1, 'devops', 'mention', 2, NULL, NULL, 'haiku', 'waiting_on_user', 'why', NULL, 'rules', 'tok2',
                    0, NULL, 'c', 'u');
        INSERT INTO comments (id, ticket_id, author_id, body, task_id, reply_to_id, created_at)
            VALUES (1, 1, 'engineer', 'AI comment', 1, NULL, 'c'), (2, 1, 'pablo', '@DevOps look', NULL, 1, 'c');
        INSERT INTO turns (id, task_id, started_at, ended_at, outcome, input_tokens) VALUES (1, 1, 1, 2, 'completed', 50);
        INSERT INTO task_events (task_id, turn_id, kind, text, created_at)
            VALUES (1, 1, 'notice', 'assigned', 'c'), (1, 1, 'reply', 'done', 'c'), (2, NULL, 'user', 'queued', 'c');
        INSERT INTO settings VALUES ('default_model', 'opus'), ('activity_seen_comment_id', '0');
        PRAGMA user_version = 1;
    """)
    conn.close()
    return path


def _rows(db_or_conn, table: str) -> list[tuple]:
    conn = db_or_conn.conn() if isinstance(db_or_conn, Database) else db_or_conn
    return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]


def _shape(db: Database) -> dict:
    conn = db.conn()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    return {
        "columns": {t: [tuple(c)[1:] for c in conn.execute(f"PRAGMA table_info({t})")] for t in tables},
        "indexes": sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL")),
    }


def test_a_version_1_file_is_migrated_with_every_row_kept(tmp_path):
    # Constraint: the installed database (version 1) moves to version 2 at the first start and keeps every row (AC23).
    # Input: a version 1 file with a ticket, two tasks, two comments, three chat lines and a turn; opened by Database.
    # Expected output: version 2, the same rows and old columns, no parent on any task, comments listed in Activity,
    #                  a .v1.bak copy at version 1; a child row is accepted, a second open task and an orphan turn are not.
    path = _version_1_file(tmp_path / "agenthub.db")
    before = {t: _rows(sqlite3.connect(path), t) for t in ("tickets", "tasks", "comments", "turns", "task_events", "users")}
    db = Database(path)
    assert db.value("PRAGMA user_version") == 2
    assert {t: _rows(db, t) for t in ("tickets", "turns", "users")} == {t: before[t] for t in ("tickets", "turns", "users")}
    old_columns = [c[1] for c in sqlite3.connect(":memory:").executescript(SCHEMA_V1.read_text()).execute("PRAGMA table_info(tasks)")]
    assert [tuple(r) for r in db.conn().execute(f"SELECT {', '.join(old_columns)} FROM tasks ORDER BY id")] == before["tasks"]
    assert db.all("SELECT parent_task_id, waiting_on_task_id FROM tasks") == [{"parent_task_id": None, "waiting_on_task_id": None}] * 2
    assert [r[:-1] for r in _rows(db, "comments")] == before["comments"] and {r[-1] for r in _rows(db, "comments")} == {1}
    assert [r[:-1] for r in _rows(db, "task_events")] == before["task_events"]
    backup = sqlite3.connect(tmp_path / "agenthub.db.v1.bak")
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 1 and _rows(backup, "tasks") == before["tasks"]
    now = now_iso()
    child = db.run(
        "INSERT INTO tasks (ticket_id, ai_user_id, origin, parent_task_id, model, status, system_prompt, token, created_at, updated_at)"
        " VALUES (1, 'data_scientist', 'ai_user', 1, 'opus', 'running', 'p', 'tok3', ?, ?)", (now, now),
    )
    assert db.value("SELECT parent_task_id FROM tasks WHERE id = ?", (child,)) == 1
    with pytest.raises(sqlite3.IntegrityError):
        _insert_task(db, 1, ai="devops", token="tok4")  # devops still has task 2 open on the ticket
    with pytest.raises(sqlite3.IntegrityError):
        db.run("INSERT INTO turns (task_id, started_at) VALUES (99, 1)")
    with pytest.raises(sqlite3.IntegrityError):
        db.run("UPDATE tasks SET origin = 'other' WHERE id = 1")


def test_a_migrated_file_has_the_shape_of_a_fresh_one(tmp_path):
    # Constraint: schema.sql and the migration describe the same version 2 database.
    # Input: a migrated version 1 file and a new empty file.
    # Expected output: the same tables, columns (name, type, default, key) in the same order, and the same indexes.
    migrated = Database(_version_1_file(tmp_path / "old.db"))
    fresh = Database(tmp_path / "new.db")
    assert _shape(migrated) == _shape(fresh)
    assert fresh.value("PRAGMA user_version") == 2


def test_a_failed_migration_leaves_the_file_at_version_1(tmp_path, monkeypatch):
    # Constraint: the app never starts on a half-migrated file.
    # Input: a migration that rebuilds tasks and then fails on a bad statement.
    # Expected output: Database raises; the file is still at version 1 with its 17 task columns and every row.
    from agenthub import db as db_module

    path = _version_1_file(tmp_path / "agenthub.db")
    before = {t: _rows(sqlite3.connect(path), t) for t in ("tasks", "comments", "task_events")}
    broken = tmp_path / "migrations"
    broken.mkdir()
    script = (db_module.MIGRATIONS / "002_child_tasks.sql").read_text()
    (broken / "002_child_tasks.sql").write_text(script.replace("ALTER TABLE comments", "ALTER TABLE no_such_table"))
    monkeypatch.setattr(db_module, "MIGRATIONS", broken)
    with pytest.raises(sqlite3.OperationalError):
        Database(path)
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert len(conn.execute("PRAGMA table_info(tasks)").fetchall()) == 17
    assert {t: _rows(conn, t) for t in before} == before

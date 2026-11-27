"""SQLite connection, schema and seed. One connection per thread, WAL mode."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DEFAULT_MODEL

SCHEMA = Path(__file__).with_name("schema.sql")
ROLES = Path(__file__).parent / "prompts" / "roles"
VERSION = 1  # the version schema.sql creates
ADD_PROJECT_CHOSEN = (
    "ALTER TABLE tickets ADD COLUMN project_chosen INTEGER NOT NULL DEFAULT 1 CHECK (project_chosen IN (0, 1))"
)

SEED_USERS = [
    # id, name, kind, handle, initials, color, role prompt file
    ("pablo", "Pablo", "human", "Pablo", "PA", "#2F5BEA", None),
    ("data_scientist", "Data Scientist", "ai", "DataScientist", "DS", "#8E44AD", "data_scientist.md"),
    ("engineer", "Engineer", "ai", "Engineer", "EN", "#0F7B6C", "engineer.md"),
    ("devops", "DevOps", "ai", "DevOps", "DO", "#C2410C", "devops.md"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        conn = self.conn()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            conn.executescript(SCHEMA.read_text())
            self._seed(conn)
            conn.execute(f"PRAGMA user_version = {VERSION}")
        else:
            self._ensure_project_chosen_column()  # runs on every open; a no-op once the column exists

    def _ensure_project_chosen_column(self) -> None:
        """Add tickets.project_chosen to an existing file that lacks it (its tickets count as chosen, default 1).

        Checked by column presence on every open, because user_version is not a reliable marker: files exist
        past version 1 without the column.
        """
        with self.transaction() as conn:
            if "project_chosen" not in {row["name"] for row in conn.execute("PRAGMA table_info(tickets)")}:
                conn.execute(ADD_PROJECT_CHOSEN)

    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, isolation_level=None, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def _seed(self, conn: sqlite3.Connection) -> None:
        for uid, name, kind, handle, initials, color, role in SEED_USERS:
            prompt = (ROLES / role).read_text().strip() if role else None
            conn.execute(
                "INSERT INTO users (id, name, kind, handle, initials, color, prompt) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, name, kind, handle, initials, color, prompt),
            )
        conn.execute("INSERT INTO settings (key, value) VALUES ('default_model', ?)", (DEFAULT_MODEL,))
        conn.execute("INSERT INTO settings (key, value) VALUES ('activity_seen_comment_id', '0')")

    def all(self, sql: str, args: tuple | list = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn().execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple | list = ()) -> dict[str, Any] | None:
        row = self.conn().execute(sql, args).fetchone()
        return dict(row) if row else None

    def value(self, sql: str, args: tuple | list = ()) -> Any:
        row = self.conn().execute(sql, args).fetchone()
        return row[0] if row else None

    def run(self, sql: str, args: tuple | list = ()) -> int:
        """Execute one statement; returns the new row id (inserts) or the changed row count."""
        cur = self.conn().execute(sql, args)
        return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    def setting(self, key: str) -> str | None:
        return self.value("SELECT value FROM settings WHERE key = ?", (key,))

    def set_setting(self, key: str, value: str) -> None:
        self.run("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def user(self, user_id: str) -> dict[str, Any] | None:
        return self.one("SELECT * FROM users WHERE id = ?", (user_id,))

    def users(self) -> list[dict[str, Any]]:
        order = {u[0]: i for i, u in enumerate(SEED_USERS)}
        return sorted(self.all("SELECT * FROM users"), key=lambda u: order.get(u["id"], 99))

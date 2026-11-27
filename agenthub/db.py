"""SQLite connection, schema, migrations and seed. One connection per thread, WAL mode."""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DEFAULT_MODEL

SCHEMA = Path(__file__).with_name("schema.sql")
MIGRATIONS = Path(__file__).with_name("migrations")  # <version>_<name>.sql brings version - 1 to version
VERSION = 2  # the version schema.sql creates
ROLES = Path(__file__).parent / "prompts" / "roles"

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
        elif version < VERSION:
            self._backup(version)
            for target, script in _migrations(version):
                self._migrate(conn, target, script)

    def _backup(self, version: int) -> None:
        """A copy of the file as it was, beside it, before the first migration touches it."""
        target = sqlite3.connect(self.path.with_name(f"{self.path.name}.v{version}.bak"))
        try:
            self.conn().backup(target)
        finally:
            target.close()

    @staticmethod
    def _migrate(conn: sqlite3.Connection, target: int, script: Path) -> None:
        """One migration, all or nothing; foreign keys are off while it rebuilds tables and checked before it commits."""
        conn.execute("PRAGMA foreign_keys = OFF")  # a no-op inside a transaction, so set before BEGIN
        try:
            # BEGIN inside the script: Python 3.11's executescript commits an open transaction first
            conn.executescript("BEGIN IMMEDIATE;\n" + script.read_text())
            broken = conn.execute("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise sqlite3.IntegrityError(f"{script.name} leaves {len(broken)} rows with a broken reference")
            conn.execute(f"PRAGMA user_version = {target}")
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

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


def _migrations(version: int) -> list[tuple[int, Path]]:
    """The migration scripts that bring a file at `version` to VERSION, in order; a missing step is an error."""
    found = {int(m.group(1)): p for p in MIGRATIONS.glob("*.sql") if (m := re.match(r"(\d+)_", p.name))}
    missing = [v for v in range(version + 1, VERSION + 1) if v not in found]
    if missing:
        raise RuntimeError(f"no migration to database version {missing[0]} in {MIGRATIONS}")
    return [(v, found[v]) for v in range(version + 1, VERSION + 1)]

"""Task state machine: start, queue, turn end, stop, archive, timer, session tokens, restart recovery.

A task is `running`, `waiting_on_user`, `done` or `archived`; it is open in the first three.
Messages are stored as chat events; a `user` or `notice` event without a turn is queued and becomes
part of the next turn. One turn runs at a time per task.
"""

from __future__ import annotations

import logging
import os
import secrets
import signal
import sqlite3
import subprocess
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .db import now_iso, now_ms
from .sessions import TurnOutcome, tool_hint

if TYPE_CHECKING:
    from .hub import Hub

log = logging.getLogger("agenthub.tasks")

OPEN = ("running", "waiting_on_user", "done")
STATUSES = ("running", "waiting_on_user", "done", "archived")
TOKEN_COLS = ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens")
TOKEN_KEYS = ("input", "output", "cache_creation", "cache_read")
TOKEN_SUM = " + ".join(TOKEN_COLS)
STOP_GRACE_S = 5
KEEP = object()  # "leave status_reason as it is"

TASK_SELECT = f"""
SELECT t.*, k.title AS ticket_title,
  (SELECT COALESCE(SUM({TOKEN_SUM}), 0) FROM turns WHERE task_id = t.id) AS session_tokens,
  (SELECT COALESCE(SUM({TOKEN_SUM}), 0) FROM harness_runs WHERE task_id = t.id) AS harness_tokens,
  (SELECT text FROM task_events WHERE task_id = t.id AND kind IN ('user', 'notice') ORDER BY id LIMIT 1) AS first_message
FROM tasks t LEFT JOIN tickets k ON k.id = t.ticket_id
"""


class TaskError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ActiveTurn:
    turn_id: int
    n: int
    started_ms: int
    proc: subprocess.Popen | None = None
    stopped: bool = False
    thread: threading.Thread | None = None
    texts: list[str] = field(default_factory=list)  # assistant text of this turn, for a reply without structured output


def ticket_key(ticket_id: int | None) -> str | None:
    return f"AH-{ticket_id}" if ticket_id else None


def _first_words(text: str | None, n: int = 8) -> str:
    words = " ".join((text or "").split()).split(" ")
    short = " ".join(words[:n])
    return short + ("…" if len(words) > n else "")


class Tasks:
    def __init__(self, hub: "Hub"):
        self.hub = hub
        self.db = hub.db
        self.lock = threading.RLock()
        self._active: dict[int, ActiveTurn] = {}

    # ================================================================ reading
    def get(self, task_id: int) -> dict | None:
        return self.db.one("SELECT * FROM tasks WHERE id = ?", (task_id,))

    def by_token(self, token: str) -> dict | None:
        return self.db.one("SELECT * FROM tasks WHERE token = ?", (token,))

    def open_task(self, ticket_id: int, ai_user_id: str) -> dict | None:
        """The one open task of that AI user on that ticket (AC4, AC45)."""
        return self.db.one(
            "SELECT * FROM tasks WHERE ticket_id = ? AND ai_user_id = ? AND status <> 'archived'",
            (ticket_id, ai_user_id),
        )

    def is_working(self, task_id: int) -> bool:
        return task_id in self._active

    def _view(self, row: dict) -> dict:
        title = row["title"]
        runs = self.db.all(
            f"SELECT run_id, status, pending_kind, {TOKEN_SUM} AS tokens FROM harness_runs WHERE task_id = ? ORDER BY started_at",
            (row["id"],),
        )
        return {
            "id": row["id"],
            "ticket_id": row["ticket_id"],
            "ticket_key": ticket_key(row["ticket_id"]),
            "ticket_title": row["ticket_title"],
            "ai_user_id": row["ai_user_id"],
            "origin": row["origin"],
            "origin_comment_id": row["origin_comment_id"],
            "title": title,
            "title_source": row["title_source"],
            "display_title": title or row["ticket_title"] or _first_words(row["first_message"]) or f"Task {row['id']}",
            "model": row["model"],
            "status": row["status"],
            "status_reason": row["status_reason"],
            "open": row["status"] in OPEN,
            "session_id": row["session_id"],
            "running_ms": row["running_ms"],
            "running_since": row["running_since"],
            "session_tokens": row["session_tokens"],
            "harness_tokens": row["harness_tokens"],
            "harness_runs": runs,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def view(self, task_id: int, with_events: bool = False) -> dict:
        row = self.db.one(TASK_SELECT + " WHERE t.id = ?", (task_id,))
        if row is None:
            raise TaskError(f"task {task_id} not found", 404)
        out = self._view(row)
        if with_events:
            out["events"] = self.events_of(task_id)
        return out

    def list(self, status: str | None = None) -> list[dict]:
        if status in (None, "", "open"):
            rows = self.db.all(TASK_SELECT + " WHERE t.status <> 'archived' ORDER BY t.id DESC")
        elif status == "all":
            rows = self.db.all(TASK_SELECT + " ORDER BY t.id DESC")
        elif status in STATUSES:
            rows = self.db.all(TASK_SELECT + " WHERE t.status = ? ORDER BY t.id DESC", (status,))
        else:
            raise TaskError(f"unknown status filter {status!r}", 422)
        return [self._view(r) for r in rows]

    def for_ticket(self, ticket_id: int) -> list[dict]:
        """Every task attached to the ticket, archived ones too, oldest first (AC47)."""
        return [self._view(r) for r in self.db.all(TASK_SELECT + " WHERE t.ticket_id = ? ORDER BY t.id", (ticket_id,))]

    def events_of(self, task_id: int) -> list[dict]:
        rows = self.db.all("SELECT * FROM task_events WHERE task_id = ? ORDER BY id", (task_id,))
        return [
            {
                "id": e["id"],
                "kind": e["kind"],
                "text": e["text"],
                "created_at": e["created_at"],
                "comment_id": e["comment_id"],
                "queued": e["turn_id"] is None and e["kind"] in ("user", "notice"),
            }
            for e in rows
        ]

    # ================================================================ writing
    def create(
        self,
        ai_user_id: str,
        model: str,
        first_message: str,
        ticket_id: int | None = None,
        origin: str = "manual",
        origin_comment_id: int | None = None,
        first_kind: str = "user",
    ) -> dict:
        ai = self.db.user(ai_user_id)
        if not ai or ai["kind"] != "ai":
            raise TaskError("a task needs an AI user", 422)
        self._check_model(model)
        if not first_message.strip():
            raise TaskError("a task needs a first message", 422)
        system_prompt = self.hub.sessions.compose_system_prompt(ai)
        now = now_iso()
        with self.lock:
            try:
                with self.db.transaction() as conn:
                    task_id = conn.execute(
                        "INSERT INTO tasks (ticket_id, ai_user_id, origin, origin_comment_id, model, status, system_prompt, token,"
                        " running_ms, running_since, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'running', ?, ?, 0, ?, ?, ?)",
                        (ticket_id, ai_user_id, origin, origin_comment_id, model, system_prompt, secrets.token_urlsafe(24), now_ms(), now, now),
                    ).lastrowid
                    conn.execute(
                        "INSERT INTO task_events (task_id, kind, text, created_at) VALUES (?, ?, ?, ?)",
                        (task_id, first_kind, first_message, now),
                    )
            except sqlite3.IntegrityError:
                raise TaskError(f"{ai['name']} already has an open task on this ticket", 409)
            self._kick(task_id)
        self._publish(task_id)
        return self.view(task_id)

    def send(self, task_id: int, text: str, kind: str = "user", comment_id: int | None = None) -> dict:
        """Deliver a message: queued while a turn runs, else it starts the next turn (AC15)."""
        if not text.strip():
            raise TaskError("the message is empty", 422)
        with self.lock:
            task = self._require(task_id)
            if task["status"] == "archived":
                raise TaskError("this task is archived and takes no further messages", 409)
            self.add_event(task_id, kind, text, comment_id=comment_id, queued=True)
            if task["status"] != "running":  # also while a stopped turn is still finishing
                self._set_status(task_id, "running", reason=None)
            if task_id not in self._active:
                self._kick(task_id)
        self._publish(task_id)
        return self.view(task_id)

    def stop(self, task_id: int) -> dict:
        """End the work: the turn's process group and the task's live harness run (AC14)."""
        with self.lock:
            task = self._require(task_id)
            if task["status"] == "archived":
                raise TaskError("this task is archived", 409)
            if task["status"] != "running":
                return self.view(task_id)
            active = self._active.get(task_id)
            if active:
                active.stopped = True
                if active.proc:
                    _terminate(active.proc)
            self.hub.bridge.stop_runs(task_id)
            self._set_status(task_id, "waiting_on_user", reason=None)
            self.add_event(task_id, "system", "Stopped by Pablo")
        self._publish(task_id)
        return self.view(task_id)

    def archive(self, task_id: int) -> dict:
        with self.lock:
            task = self._require(task_id)
            if task["status"] != "done":
                raise TaskError("only a done task can be archived", 409)
            self._set_status(task_id, "archived", reason=None)
        self._publish(task_id)
        return self.view(task_id)

    def update(self, task_id: int, title: str | None = None, model: str | None = None) -> dict:
        with self.lock:
            task = self._require(task_id)
            if task["status"] == "archived":
                raise TaskError("this task is archived", 409)
            if title is not None:
                if not title.strip():
                    raise TaskError("the title is empty", 422)
                self.db.run(
                    "UPDATE tasks SET title = ?, title_source = 'human', updated_at = ? WHERE id = ?",
                    (title.strip(), now_iso(), task_id),
                )
            if model is not None:
                self._check_model(model)
                self.db.run("UPDATE tasks SET model = ?, updated_at = ? WHERE id = ?", (model, now_iso(), task_id))
        self._publish(task_id)
        return self.view(task_id)

    def set_ai_title(self, task_id: int, title: str) -> bool:
        """A title written by the AI user; ignored once Pablo has edited the title (AC10, AC11)."""
        title = " ".join(title.split())[:200]
        if not title:
            return False
        changed = self.db.run(
            "UPDATE tasks SET title = ?, title_source = 'ai', updated_at = ? WHERE id = ? AND COALESCE(title_source, '') <> 'human'",
            (title, now_iso(), task_id),
        )
        if changed:
            self._publish(task_id)
        return bool(changed)

    def set_waiting(self, task_id: int, reason: str | None = None) -> None:
        """Used by the harness bridge when a gate is posted (AC28)."""
        with self.lock:
            task = self.get(task_id)
            if task and task["status"] in ("running", "done") and task_id not in self._active:
                self._set_status(task_id, "waiting_on_user", reason=reason)
        self._publish(task_id)

    def settle(self, task_id: int) -> None:
        """A harness run of the task ended: a task with no turn running and nothing queued waits on Pablo."""
        with self.lock:
            task = self.get(task_id)
            if not task or task["status"] != "running" or task_id in self._active:
                return
            if self._queued(task_id):
                self._kick(task_id)
            elif not self.hub.bridge.has_live_run(task_id):
                self._set_status(task_id, "waiting_on_user", reason=None)
        self._publish(task_id)

    def add_event(self, task_id: int, kind: str, text: str, comment_id: int | None = None, queued: bool = False, turn_id: int | None = None) -> int:
        """`queued` user/notice events have no turn yet; every other event is stored as delivered (turn_id -1 when none)."""
        if not queued and turn_id is None:
            turn_id = -1
        event_id = self.db.run(
            "INSERT INTO task_events (task_id, turn_id, comment_id, kind, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, None if queued else turn_id, comment_id, kind, text, now_iso()),
        )
        self.hub.events.publish("tasks", task_id)
        return event_id

    # ================================================================ turns
    def _queued(self, task_id: int) -> list[dict]:
        return self.db.all(
            "SELECT * FROM task_events WHERE task_id = ? AND turn_id IS NULL AND kind IN ('user', 'notice') ORDER BY id",
            (task_id,),
        )

    def _kick(self, task_id: int) -> None:
        """Start a turn with every queued message, unless one is running. Called with the lock held."""
        if task_id in self._active:
            return
        queued = self._queued(task_id)
        if not queued:
            return
        task = self.get(task_id)
        login = self.hub.sessions.login_status()
        if not login["logged_in"]:
            reason = f"cannot start: {login['detail'] or 'Claude is not logged in on this machine'}"
            self._set_status(task_id, "waiting_on_user", reason=reason)
            self.add_event(task_id, "error", reason)
            return
        n = (self.db.value("SELECT COUNT(*) FROM turns WHERE task_id = ?", (task_id,)) or 0) + 1
        started = now_ms()
        turn_id = self.db.run(
            "INSERT INTO turns (task_id, started_at, last_event_at, model, session_id) VALUES (?, ?, ?, ?, ?)",
            (task_id, started, started, task["model"], task["session_id"]),
        )
        ids = [e["id"] for e in queued]
        self.db.run(f"UPDATE task_events SET turn_id = ? WHERE id IN ({','.join('?' * len(ids))})", (turn_id, *ids))
        if task["status"] != "running":
            self._set_status(task_id, "running", reason=None)
        else:
            self.db.run("UPDATE tasks SET status_reason = NULL WHERE id = ?", (task_id,))
        prompt = self._prompt(task, queued)
        active = ActiveTurn(turn_id=turn_id, n=n, started_ms=started)
        self._active[task_id] = active
        active.thread = threading.Thread(
            target=self._run, args=(task_id, active, prompt, task["session_id"]), name=f"task-{task_id}-turn-{n}", daemon=True
        )
        active.thread.start()

    def _prompt(self, task: dict, events: list[dict]) -> str:
        key = ticket_key(task["ticket_id"])
        parts = []
        for e in events:
            if e["kind"] == "user":
                head = f"Pablo commented on ticket {key}:" if e["comment_id"] and key else "Message from Pablo:"
            else:
                head = "From AgentHub:"
            parts.append(f"{head}\n\n{e['text'].strip()}")
        prefix = self.hub.bridge.reply_prefix(task["id"]) if any(e["kind"] == "user" for e in events) else ""
        return prefix + "\n\n---\n\n".join(parts)

    def _history_prompt(self, task_id: int, turn_id: int, prompt: str) -> str:
        """First message of a replacement session: the task's earlier conversation from the database."""
        rows = self.db.all(
            "SELECT kind, text FROM task_events WHERE task_id = ? AND kind IN ('user', 'notice', 'reply') AND turn_id IS NOT NULL"
            " AND turn_id <> ? ORDER BY id",
            (task_id, turn_id),
        )
        who = {"user": "Pablo", "notice": "AgentHub", "reply": "You"}
        history = "\n\n".join(f"[{who[r['kind']]}]\n{r['text'].strip()}" for r in rows)
        return (
            "Your earlier session of this task could not be continued, so this is a new session. "
            "The conversation of the task so far:\n\n" + history + "\n\n--- New input ---\n\n" + prompt
        )

    def _run(self, task_id: int, active: ActiveTurn, prompt: str, resume: str | None) -> None:
        try:
            outcome = self._launch(task_id, active, prompt, resume)
            if outcome.session_lost and not active.stopped:
                self.db.run("UPDATE tasks SET session_id = NULL WHERE id = ?", (task_id,))
                self.add_event(task_id, "system", "The earlier session could not be continued; continuing in a new session with the task's history.")
                outcome = self._launch(task_id, active, self._history_prompt(task_id, active.turn_id, prompt), None)
        except Exception as e:  # a bug here must not leave the task running forever
            log.exception("turn of task %s failed", task_id)
            outcome = TurnOutcome(ok=False, error=f"internal error: {e}")
        try:
            self._finish(task_id, active, outcome)
        except Exception as e:
            log.exception("finishing the turn of task %s failed", task_id)
            with self.lock:
                self._active.pop(task_id, None)
                self._set_status(task_id, "waiting_on_user", reason=f"internal error: {e}")
            self._publish(task_id)

    def _launch(self, task_id: int, active: ActiveTurn, prompt: str, resume: str | None) -> TurnOutcome:
        task = self.get(task_id)
        ai = self.db.user(task["ai_user_id"])

        def on_process(proc: subprocess.Popen) -> None:
            active.proc = proc
            if active.stopped:
                _terminate(proc)

        def on_session(session_id: str) -> None:
            self.db.run("UPDATE tasks SET session_id = ? WHERE id = ?", (session_id, task_id))
            self.db.run("UPDATE turns SET session_id = ? WHERE id = ?", (session_id, active.turn_id))

        return self.hub.sessions.run_turn(
            task, ai, ticket_key(task["ticket_id"]), prompt, active.n, resume,
            on_event=lambda ev: self._on_stream_event(task_id, active, ev),
            on_process=on_process,
            on_session=on_session,
        )

    def _on_stream_event(self, task_id: int, active: ActiveTurn, ev: dict) -> None:
        self.db.run("UPDATE turns SET last_event_at = ? WHERE id = ?", (now_ms(), active.turn_id))
        if ev.get("type") != "assistant":
            return
        for block in (ev.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                active.texts.append(block["text"])
                self.add_event(task_id, "assistant", block["text"].strip(), turn_id=active.turn_id)
            elif block.get("type") == "tool_use" and block.get("name") != "StructuredOutput":
                self.add_event(task_id, "tool", f"{block.get('name', 'tool')} {tool_hint(block)}".strip(), turn_id=active.turn_id)

    def _own_tokens(self, task_id: int, turn_id: int, session_id: str | None, reported: dict | None) -> dict:
        """This turn's own use from the session total the process reported (AC13)."""
        if not reported:
            return {k: 0 for k in TOKEN_KEYS}
        earlier_row = self.db.one(
            "SELECT " + ", ".join(f"COALESCE(SUM({c}), 0) AS {k}" for c, k in zip(TOKEN_COLS, TOKEN_KEYS))
            + " FROM turns WHERE task_id = ? AND session_id IS ? AND id <> ?",
            (task_id, session_id, turn_id),
        ) or {}
        earlier = {k: int(earlier_row.get(k) or 0) for k in TOKEN_KEYS}
        rep = {k: int(reported.get(k) or 0) for k in TOKEN_KEYS}
        if sum(rep.values()) >= sum(earlier.values()):
            return {k: max(0, rep[k] - earlier[k]) for k in TOKEN_KEYS}
        return rep  # a lower figure: a new session's own total

    def _finish(self, task_id: int, active: ActiveTurn, outcome: TurnOutcome) -> None:
        with self.lock:
            task = self.get(task_id)
            session_id = outcome.session_id or task["session_id"]
            own = self._own_tokens(task_id, active.turn_id, session_id, outcome.tokens)
            kind = "stopped" if active.stopped else ("completed" if outcome.ok else "failed")
            self.db.run(
                "UPDATE turns SET ended_at = ?, session_id = ?, outcome = ?, "
                + ", ".join(f"{c} = ?" for c in TOKEN_COLS) + " WHERE id = ?",
                (now_ms(), session_id, kind, *[own[k] for k in TOKEN_KEYS], active.turn_id),
            )
            if session_id:
                self.db.run("UPDATE tasks SET session_id = ? WHERE id = ?", (session_id, task_id))
            structured = outcome.structured
            reason = None
            if not active.stopped:
                if outcome.ok:
                    message = structured["message"] if structured else (active.texts[-1] if active.texts else outcome.result_text)
                    message = self.hub.reports.with_report_links(task_id, active.started_ms, message or "")
                    if message.strip():
                        self.add_event(task_id, "reply", message.strip(), turn_id=active.turn_id)
                        if task["ticket_id"]:
                            self.hub.tickets.post_ai_comment(task["ticket_id"], task["ai_user_id"], message.strip(), task_id)
                    if structured and structured["title"] and not task["title"]:
                        self.set_ai_title(task_id, structured["title"])
                else:
                    reason = outcome.error or "the turn failed"
                    self.add_event(task_id, "error", reason, turn_id=active.turn_id)
        task = self.get(task_id)
        sync = self.hub.private.sync(f"task {task_id} ({self.db.user(task['ai_user_id'])['name']}): {task['title'] or ''}".strip())
        if sync.error:
            reason = f"private folder not pushed: {sync.error}"
            self.add_event(task_id, "error", reason)
        with self.lock:
            self._active.pop(task_id, None)
            task = self.get(task_id)
            if self._queued(task_id) and task["status"] != "archived":
                self._kick(task_id)  # also a message sent after Stop, while this turn was finishing
            elif active.stopped or task["status"] != "running":
                pass  # stop already set the status
            elif self.hub.bridge.pending_gate(task_id):
                self._set_status(task_id, "waiting_on_user", reason=reason)
            elif self.hub.bridge.has_live_run(task_id) and outcome.ok:
                self.db.run("UPDATE tasks SET status_reason = ? WHERE id = ?", (reason, task_id))
            else:
                status = structured["status"] if (outcome.ok and structured) else "waiting_on_user"
                self._set_status(task_id, status, reason=reason)
        self._publish(task_id)
        self.hub.events.publish("tickets")
        self.hub.events.publish("activity")

    # ================================================================ status and timer
    def _set_status(self, task_id: int, status: str, reason: Any = KEEP) -> None:
        """Change the status; the timer runs only while the status is running (AC12)."""
        task = self.get(task_id)
        now = now_ms()
        running_ms, since = task["running_ms"], task["running_since"]
        if task["status"] == "running" and status != "running" and since:
            running_ms += max(0, now - since)
            since = None
        if status == "running" and (task["status"] != "running" or since is None):
            since = now
        if status != "running":
            since = None
        new_reason = task["status_reason"] if reason is KEEP else reason
        self.db.run(
            "UPDATE tasks SET status = ?, status_reason = ?, running_ms = ?, running_since = ?, updated_at = ? WHERE id = ?",
            (status, new_reason, running_ms, since, now_iso(), task_id),
        )

    def recover(self, live_task_ids: set[int] | None = None) -> None:
        """At app start: no task stays running that is not working (AC18)."""
        live = live_task_ids or set()
        for turn in self.db.all("SELECT * FROM turns WHERE ended_at IS NULL"):
            self.db.run(
                "UPDATE turns SET ended_at = ?, outcome = 'interrupted' WHERE id = ?",
                (turn["last_event_at"] or turn["started_at"], turn["id"]),
            )
        for task in self.db.all("SELECT * FROM tasks WHERE status = 'running'"):
            if task["id"] in live:
                continue
            last = self.db.value("SELECT MAX(last_event_at) FROM turns WHERE task_id = ?", (task["id"],)) or task["running_since"]
            since = task["running_since"] or last
            running_ms = task["running_ms"] + max(0, (last or since or 0) - (since or 0))
            self.db.run(
                "UPDATE tasks SET status = 'waiting_on_user', status_reason = 'interrupted by a restart', running_ms = ?,"
                " running_since = NULL, updated_at = ? WHERE id = ?",
                (running_ms, now_iso(), task["id"]),
            )
            self.add_event(task["id"], "system", "Interrupted by a restart of AgentHub; a new message continues the task.")

    def shutdown(self) -> None:
        with self.lock:
            for active in self._active.values():
                if active.proc:
                    _terminate(active.proc)

    # ================================================================ helpers
    def _require(self, task_id: int) -> dict:
        task = self.get(task_id)
        if task is None:
            raise TaskError(f"task {task_id} not found", 404)
        return task

    def _check_model(self, model: str) -> None:
        if model not in self.hub.config.models:
            raise TaskError(f"unknown model {model!r}; choices: {', '.join(self.hub.config.models)}", 422)

    def _publish(self, task_id: int) -> None:
        self.hub.events.publish("tasks", task_id)


def _terminate(proc: subprocess.Popen) -> None:
    """SIGTERM to the turn's process group, SIGKILL after a grace period."""
    def signal_group(sig: int) -> None:
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    signal_group(signal.SIGTERM)

    def later() -> None:
        if proc.poll() is None:
            signal_group(signal.SIGKILL)

    threading.Timer(STOP_GRACE_S, later).start()

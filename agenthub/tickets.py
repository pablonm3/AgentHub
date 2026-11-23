"""Tickets, comments, mentions, handing a ticket or a comment to an AI user's task, Activity.

An AI user has at most one open task on a ticket: assignment and mention both find that task and
hand it the input, or start a task when there is none (AC4, AC8, AC38, AC45).
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING

from .db import now_iso
from .tasks import TaskError, ticket_key

if TYPE_CHECKING:
    from .hub import Hub

INPUTS = Path(__file__).parent / "prompts" / "inputs"
STAGES = [
    {"id": "backlog", "name": "Backlog"},
    {"id": "todo", "name": "To do"},
    {"id": "in_progress", "name": "In progress"},
    {"id": "in_review", "name": "In review"},
    {"id": "done", "name": "Done"},
]
STAGE_IDS = [s["id"] for s in STAGES]
MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]*)")


def render(name: str, **values: str) -> str:
    return Template((INPUTS / name).read_text()).safe_substitute(**values).strip() + "\n"


class Tickets:
    def __init__(self, hub: "Hub"):
        self.hub = hub
        self.db = hub.db
        # "find the AI user's open task on the ticket, else start one" must not interleave
        self._handing = threading.Lock()

    # ================================================================ reading
    def get(self, ticket_id: int) -> dict:
        row = self.db.one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        if row is None:
            raise TaskError(f"ticket {ticket_id} not found", 404)
        return row

    def _view(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "key": ticket_key(row["id"]),
            "title": row["title"],
            "description": row["description"],
            "stage": row["stage"],
            "position": row["position"],
            "assignee_id": row["assignee_id"],
            "model": row["model"],
            "project": row["project"],
            "labels": json.loads(row["labels"] or "[]"),
            "comment_count": self.db.value("SELECT COUNT(*) FROM comments WHERE ticket_id = ?", (row["id"],)),
            "task_status": self.db.value("SELECT status FROM tasks WHERE ticket_id = ? ORDER BY id DESC LIMIT 1", (row["id"],)),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self) -> list[dict]:
        return [self._view(r) for r in self.db.all("SELECT * FROM tickets ORDER BY stage, position, id")]

    def comment_view(self, c: dict) -> dict:
        delivered = self.db.all(
            "SELECT DISTINCT e.task_id, t.ai_user_id FROM task_events e JOIN tasks t ON t.id = e.task_id"
            " WHERE e.comment_id = ? AND e.kind = 'user' ORDER BY e.task_id",
            (c["id"],),
        )
        started = self.db.all("SELECT id AS task_id, ai_user_id FROM tasks WHERE origin_comment_id = ? ORDER BY id", (c["id"],))
        return {**c, "delivered_to": delivered, "started": started}

    def detail(self, ticket_id: int) -> dict:
        """The ticket with its comments, its tasks and their two token totals (AC46, AC47)."""
        row = self.get(ticket_id)
        comments = self.db.all("SELECT * FROM comments WHERE ticket_id = ? ORDER BY id", (ticket_id,))
        tasks_of_ticket = self.hub.tasks.for_ticket(ticket_id)
        return {
            **self._view(row),
            "comments": [self.comment_view(c) for c in comments],
            "tasks": tasks_of_ticket,
            "session_tokens": sum(t["session_tokens"] for t in tasks_of_ticket),
            "harness_tokens": sum(t["harness_tokens"] for t in tasks_of_ticket),
            "project_info": self.hub.projects.get(row["project"]),
        }

    # ================================================================ tickets
    def create(self, data: dict) -> tuple[dict, str | None]:
        """Create a ticket; a new project is registered before the ticket and its task exist (AC39, AC43)."""
        title = str(data.get("title") or "").strip()
        if not title:
            raise TaskError("a ticket needs a title", 422)
        stage = data.get("stage") or STAGE_IDS[0]
        if stage not in STAGE_IDS:
            raise TaskError(f"unknown stage {stage!r}", 422)
        assignee = self.db.user(str(data.get("assignee_id") or "pablo"))
        if assignee is None:
            raise TaskError("unknown assignee", 422)
        model = data.get("model") or self.db.setting("default_model")
        if model not in self.hub.config.models:
            raise TaskError(f"unknown model {model!r}", 422)
        has_project, has_new = "project" in data, data.get("new_project") is not None
        if has_project == has_new:
            raise TaskError("choose exactly one of a registered project, \"No project\" (project: null) or a new project", 422)
        warning = None
        if has_new:
            new = data["new_project"] or {}
            project, warning = self.hub.projects.register(str(new.get("name") or ""), new.get("repo_url"))
            project_name = project["name"]
        else:
            project_name = data["project"]
            if project_name is not None and self.hub.projects.get(project_name) is None:
                raise TaskError(f"no project named {project_name!r} is registered", 422)
        now = now_iso()
        position = (self.db.value("SELECT MAX(position) FROM tickets WHERE stage = ?", (stage,)) or 0) + 1
        ticket_id = self.db.run(
            "INSERT INTO tickets (title, description, stage, position, assignee_id, model, project, labels, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, str(data.get("description") or ""), stage, position, assignee["id"], model, project_name,
             json.dumps(data.get("labels") or []), now, now),
        )
        self.hub.events.publish("tickets", ticket_id)
        if assignee["kind"] == "ai":
            self.hand_over(self.get(ticket_id), assignee)
        return self.detail(ticket_id), warning

    def update(self, ticket_id: int, data: dict) -> dict:
        ticket = self.get(ticket_id)
        if "project" in data or "new_project" in data:
            raise TaskError("a ticket's project is fixed once the ticket exists", 422)
        fields: dict = {}
        if "title" in data:
            if not str(data["title"] or "").strip():
                raise TaskError("a ticket needs a title", 422)
            fields["title"] = str(data["title"]).strip()
        if "description" in data:
            fields["description"] = str(data["description"] or "")
        if "stage" in data:
            if data["stage"] not in STAGE_IDS:
                raise TaskError(f"unknown stage {data['stage']!r}", 422)
            fields["stage"] = data["stage"]
        if "position" in data:
            fields["position"] = float(data["position"])
        if "model" in data:
            if data["model"] not in self.hub.config.models:
                raise TaskError(f"unknown model {data['model']!r}", 422)
            fields["model"] = data["model"]
        new_assignee = None
        if "assignee_id" in data and data["assignee_id"] != ticket["assignee_id"]:
            new_assignee = self.db.user(str(data["assignee_id"]))
            if new_assignee is None:
                raise TaskError("unknown assignee", 422)
            fields["assignee_id"] = new_assignee["id"]
        if fields:
            fields["updated_at"] = now_iso()
            self.db.run(
                f"UPDATE tickets SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                (*fields.values(), ticket_id),
            )
            self.hub.events.publish("tickets", ticket_id)
        if new_assignee is not None and new_assignee["kind"] == "ai":
            self.hand_over(self.get(ticket_id), new_assignee)
        return self.detail(ticket_id)

    def hand_over(self, ticket: dict, ai: dict) -> tuple[dict, bool]:
        """Give the whole ticket to the AI user: its open task on the ticket, else a new task (AC4, AC45)."""
        with self._handing:
            task = self.hub.tasks.open_task(ticket["id"], ai["id"])
            if task is None:
                started = self.hub.tasks.create(
                    ai["id"], ticket["model"], self._ticket_input("ticket_assigned.md", ticket),
                    ticket_id=ticket["id"], origin="assignment", first_kind="notice",
                )
                return started, True
            sent = self.hub.tasks.send(task["id"], self._ticket_input("ticket_handed_over.md", ticket), kind="notice")
            return sent, False

    # ================================================================ comments
    def ai_users_mentioned(self, body: str) -> list[dict]:
        """The AI users a text @mentions, each once, in order of appearance. `@Pablo` is no mention."""
        by_handle = {u["handle"].lower(): u for u in self.db.users() if u["kind"] == "ai"}
        out: list[dict] = []
        for m in MENTION_RE.finditer(body):
            user = by_handle.get(m.group(1).lower())
            if user and user not in out:
                out.append(user)
        return out

    def add_comment(self, ticket_id: int, author_id: str, body: str, reply_to: int | None = None) -> tuple[dict, list[int], list[int]]:
        ticket = self.get(ticket_id)
        author = self.db.user(author_id)
        if not body.strip():
            raise TaskError("the comment is empty", 422)
        reply_row = None
        if reply_to is not None:
            reply_row = self.db.one("SELECT * FROM comments WHERE id = ? AND ticket_id = ?", (reply_to, ticket_id))
            if reply_row is None:
                raise TaskError(f"comment {reply_to} is not on ticket {ticket_key(ticket_id)}", 422)
        comment_id = self.db.run(
            "INSERT INTO comments (ticket_id, author_id, body, reply_to_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, author["id"], body, reply_to, now_iso()),
        )
        comment = self.db.one("SELECT * FROM comments WHERE id = ?", (comment_id,))
        delivered, started = ([], [])
        if author["kind"] == "human":  # a mention inside an AI user's comment starts nothing
            delivered, started = self.route_comment(ticket, comment, reply_row)
        self.hub.events.publish("tickets", ticket_id)
        return self.comment_view(comment), delivered, started

    def route_comment(self, ticket: dict, comment: dict, reply_to: dict | None = None) -> tuple[list[int], list[int]]:
        """Three exclusive cases: mentioned AI users only; the entry's task for an Activity reply; the assignee's open task."""
        delivered: list[int] = []
        started: list[int] = []

        def deliver(task: dict) -> None:
            self.hub.tasks.send(task["id"], comment["body"], comment_id=comment["id"])
            delivered.append(task["id"])

        mentioned = self.ai_users_mentioned(comment["body"])
        with self._handing:
            if mentioned:  # AC8, AC38, AC44: the mentioned AI users and nobody else
                for ai in mentioned:
                    task = self.hub.tasks.open_task(ticket["id"], ai["id"])
                    if task:
                        deliver(task)
                    else:
                        new = self.hub.tasks.create(
                            ai["id"], ticket["model"], self._mention_input(ticket, comment),
                            ticket_id=ticket["id"], origin="mention", origin_comment_id=comment["id"], first_kind="notice",
                        )
                        started.append(new["id"])
            elif reply_to is not None:  # AC25: an Activity reply without a mention goes to the task that posted the entry
                posting = self.hub.tasks.get(reply_to["task_id"]) if reply_to["task_id"] else None
                if posting and posting["status"] != "archived":
                    deliver(posting)
            else:  # AC7, AC42: the assignee's open task, or no task
                assignee = self.db.user(ticket["assignee_id"])
                task = self.hub.tasks.open_task(ticket["id"], assignee["id"]) if assignee["kind"] == "ai" else None
                if task:
                    deliver(task)
        return delivered, started

    def post_ai_comment(self, ticket_id: int, ai_user_id: str, body: str, task_id: int) -> int:
        """An AI user's message on the ticket (AC6); listed in Activity (AC23)."""
        comment_id = self.db.run(
            "INSERT INTO comments (ticket_id, author_id, body, task_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, ai_user_id, body, task_id, now_iso()),
        )
        self.hub.events.publish("tickets", ticket_id)
        self.hub.events.publish("activity", comment_id)
        return comment_id

    # ================================================================ inputs
    def _project_block(self, ticket: dict) -> str:
        name = ticket["project"]
        if not name:
            return (
                "This ticket has no project. Do the work in this session: no harness run can be started for it."
            )
        project = self.hub.projects.get(name) or {"name": name, "default_base": "?", "ready": False, "repo": ""}
        agentsmd = self.hub.config.private_dir / "agentmds" / name / "AGENTS.md"
        text = (
            f"The ticket's project is {name} (repository {project['repo'] or 'unknown'}, base branch "
            f"{project['default_base']}). Its instructions are in {agentsmd}. A harness run of this task "
            f"runs on this project."
        )
        if not project["ready"]:
            text += (
                f" Its AGENTS.md is still a template: fill it from the repository before the first run, "
                "and ask Pablo in your reply for what the repository cannot tell (see the coding-harness skill)."
            )
        return text

    def _comments_text(self, ticket_id: int) -> str:
        rows = self.db.all(
            "SELECT c.body, u.name FROM comments c JOIN users u ON u.id = c.author_id WHERE c.ticket_id = ? ORDER BY c.id",
            (ticket_id,),
        )
        return "\n\n".join(f"- {r['name']}: {r['body']}" for r in rows) or "none"

    def _ticket_input(self, template: str, ticket: dict) -> str:
        return render(
            template,
            key=ticket_key(ticket["id"]), title=ticket["title"], description=ticket["description"] or "(no description)",
            comments=self._comments_text(ticket["id"]), project_block=self._project_block(ticket),
        )

    def _mention_input(self, ticket: dict, comment: dict) -> str:
        return render(
            "comment_mention.md",
            key=ticket_key(ticket["id"]), title=ticket["title"], description=ticket["description"] or "(no description)",
            comment=comment["body"], project_block=self._project_block(ticket),
        )

    # ================================================================ search (the search-history skill, AC31)
    def search(self, phrase: str) -> dict:
        """Case-insensitive substring search over tickets, comments and task chats, archived tasks included."""
        phrase = phrase.strip()
        if not phrase:
            raise TaskError("give a phrase to search for", 422)
        users = {u["id"]: u["name"] for u in self.db.users()}

        def task_ref(t: dict) -> dict:
            return {"id": t["id"], "title": t["title"] or None, "status": t["status"], "ai_user": users.get(t["ai_user_id"])}

        def ticket_ref(ticket_id: int | None) -> dict | None:
            if not ticket_id:
                return None
            row = self.db.one("SELECT id, title FROM tickets WHERE id = ?", (ticket_id,))
            return {"key": ticket_key(row["id"]), "title": row["title"]} if row else None

        def tasks_of(ticket_id: int) -> list[dict]:
            return [task_ref(t) for t in self.db.all("SELECT * FROM tasks WHERE ticket_id = ? ORDER BY id", (ticket_id,))]

        hits: list[dict] = []
        for t in self.db.all(
            "SELECT * FROM tickets WHERE instr(lower(title), lower(?)) > 0 OR instr(lower(description), lower(?)) > 0",
            (phrase, phrase),
        ):
            where = "ticket title" if phrase.lower() in t["title"].lower() else "ticket description"
            text = t["title"] if where == "ticket title" else t["description"]
            hits.append({"where": where, "ticket": ticket_ref(t["id"]), "task": None,
                         "tasks_of_ticket": tasks_of(t["id"]), "snippet": _snippet(text, phrase)})
        for c in self.db.all("SELECT * FROM comments WHERE instr(lower(body), lower(?)) > 0 ORDER BY id", (phrase,)):
            posting = self.hub.tasks.get(c["task_id"]) if c["task_id"] else None
            hits.append({"where": f"comment by {users.get(c['author_id'])}", "ticket": ticket_ref(c["ticket_id"]),
                         "task": task_ref(posting) if posting else None, "tasks_of_ticket": tasks_of(c["ticket_id"]),
                         "snippet": _snippet(c["body"], phrase)})
        seen_tasks: set[int] = set()
        for e in self.db.all(
            "SELECT e.task_id, e.text FROM task_events e WHERE e.kind IN ('user', 'reply', 'assistant')"
            " AND instr(lower(e.text), lower(?)) > 0 ORDER BY e.id",
            (phrase,),
        ):
            if e["task_id"] in seen_tasks:
                continue
            seen_tasks.add(e["task_id"])
            t = self.hub.tasks.get(e["task_id"])
            hits.append({"where": "task chat", "ticket": ticket_ref(t["ticket_id"]), "task": task_ref(t),
                         "tasks_of_ticket": [], "snippet": _snippet(e["text"], phrase)})
        return {"query": phrase, "hits": hits}

    # ================================================================ Activity
    def activity(self) -> tuple[list[dict], int]:
        """AI comments, newest first, and how many arrived since Pablo last opened the tab (AC23, AC24)."""
        rows = self.db.all(
            "SELECT c.*, k.title AS ticket_title FROM comments c JOIN users u ON u.id = c.author_id"
            " JOIN tickets k ON k.id = c.ticket_id WHERE u.kind = 'ai' ORDER BY c.id DESC"
        )
        seen = int(self.db.setting("activity_seen_comment_id") or 0)
        items = []
        for r in rows:
            ticket_title = r.pop("ticket_title")
            items.append({
                "comment": self.comment_view(r),
                "ticket": {"id": r["ticket_id"], "key": ticket_key(r["ticket_id"]), "title": ticket_title},
                "ai_user_id": r["author_id"],
                "task_id": r["task_id"],
            })
        return items, sum(1 for r in rows if r["id"] > seen)

    def mark_activity_seen(self) -> int:
        newest = self.db.value(
            "SELECT MAX(c.id) FROM comments c JOIN users u ON u.id = c.author_id WHERE u.kind = 'ai'"
        ) or 0
        self.db.set_setting("activity_seen_comment_id", str(newest))
        self.hub.events.publish("activity")
        return 0


def _snippet(text: str, phrase: str, width: int = 80) -> str:
    flat = " ".join(text.split())
    i = flat.lower().find(phrase.lower())
    if i < 0:
        return flat[: 2 * width]
    start, end = max(0, i - width), min(len(flat), i + len(phrase) + width)
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")

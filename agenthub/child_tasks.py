"""Work one AI user gives another: a session creates a child task, writes to it, and hears back from it.

The asking task is the child's parent. A child answers to its parent while the parent is not archived
(`Tasks.answers_to`): its questions, its result and the gates of its harness run are sent to the
parent as messages from the child's AI user, and the parent answers with `agenthub task send`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import HubError
from .tasks import ticket_key

if TYPE_CHECKING:
    from .hub import Hub


class ChildTasks:
    def __init__(self, hub: "Hub"):
        self.hub = hub
        self.db = hub.db

    # ================================================================ from the parent's session
    def create(self, parent: dict, to: str, request: str) -> tuple[dict, bool]:
        """The receiver's child task with the request; False when the request went to its existing child (AC1–AC8)."""
        receiver = self._receiver(parent, to)
        if not request.strip():
            raise HubError("the request is empty: say what you need from the other AI user", 422)
        asker = self.db.user(parent["ai_user_id"])
        tasks, tickets = self.hub.tasks, self.hub.tickets
        if not parent["ticket_id"]:
            child = tasks.create(
                receiver["id"], parent["model"], tickets.child_task_input(None, asker, parent, request),
                origin="ai_user", first_kind="ai_user", parent_task_id=parent["id"],
            )
            return child, True
        ticket = tickets.get(parent["ticket_id"])
        with tickets.handing:
            existing = tasks.open_task(ticket["id"], receiver["id"])
            if existing is None:
                child = tasks.create(
                    receiver["id"], ticket["model"], tickets.child_task_input(ticket, asker, parent, request),
                    ticket_id=ticket["id"], origin="ai_user", first_kind="ai_user", parent_task_id=parent["id"],
                )
                body = f"Created a task for {receiver['name']}:\n\n" + _quote(request)
                tickets.post_ai_comment(ticket["id"], asker["id"], body, parent["id"], announces=child["id"])
                return tasks.view(child["id"]), True
            if existing["parent_task_id"] == parent["id"]:
                return tasks.send(existing["id"], request, kind="ai_user", from_task_id=parent["id"]), False
            title = tasks.view(existing["id"])["display_title"]
            raise HubError(
                f"{receiver['name']} already has an open task on {ticket_key(ticket['id'])} that this task did not create: "
                f"task {existing['id']} \"{title}\" ({existing['status']}). No second task can be created for it on this "
                "ticket: tell Pablo in your message.",
                409,
            )

    def send(self, parent: dict, child_id: int, text: str) -> dict:
        """A message of the parent's session to one of its child tasks, stored as sent (AC11)."""
        child = self.hub.tasks.get(child_id)
        if child is None or child["parent_task_id"] != parent["id"]:
            raise HubError(f"task {child_id} is not a child task of this task", 404)
        if child["status"] == "archived":
            raise HubError(f"task {child_id} is archived and takes no further messages", 409)
        if not text.strip():
            raise HubError("the message is empty", 422)
        return self.hub.tasks.send(child_id, text, kind="ai_user", from_task_id=parent["id"])

    def _receiver(self, parent: dict, to: str) -> dict:
        """The AI user named by handle, name or id in any case; never the asker itself or Pablo (AC6)."""
        others = [u for u in self.db.users() if u["kind"] == "ai" and u["id"] != parent["ai_user_id"]]
        wanted = _key(to)
        for user in others:
            if wanted and wanted in (_key(user["handle"]), _key(user["name"]), _key(user["id"])):
                return user
        raise HubError(f"{to.strip() or 'nobody'} cannot be asked. AI users you can ask: " + ", ".join(u["handle"] for u in others), 422)

    # ================================================================ from the child, to its parent
    def report(self, child: dict, message: str, what: str) -> bool:
        """Send a child's question, result or gate to the task it answers to; False when it answers to nobody."""
        parent = self.hub.tasks.answers_to(child)
        if parent is None:
            return False
        name = self.db.user(child["ai_user_id"])["name"]
        answer = f'answer with `agenthub task send {child["id"]} "<answer>"`'
        rule = "yourself when Pablo's ticket, comments or messages already settle it; otherwise ask Pablo first and pass his answer on"
        note = {
            "question": f"{name} asks this from child task {child['id']} and waits for your answer: {answer}, {rule}.",
            "result": f"This is the result of child task {child['id']} ({name}), which ended done. "
                      f"It still takes messages: `agenthub task send {child['id']} \"<text>\"`.",
            "gate": f"The harness run of child task {child['id']} ({name}) waits at this gate, and your reply releases it: "
                    f"{answer}, {rule}. Pablo's reply in task {child['id']} releases it too.",
        }[what]
        try:
            self.hub.tasks.send(parent["id"], f"{message.strip()}\n\n> From AgentHub: {note}", kind="ai_user", from_task_id=child["id"])
        except HubError:
            return False  # the parent was archived in the same instant
        return True


def _key(text: str) -> str:
    return text.strip().lstrip("@").lower().replace(" ", "").replace("_", "")


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.strip().splitlines())

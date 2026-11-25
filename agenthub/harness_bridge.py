"""Runs of the harness copy started by tasks: project rules, watching, gates as comments, questions,
guarded resume, the runs' token counts (AC26–AC29, AC40, AC41) and the usage figures their steps report.

A run lasts hours and a turn is a process that ends, so the server owns the run: it spawns
`agenthub-harness run` in its own process group, reads the run's `state.json` while it lives and
acts when it exits. A gate is posted as a comment by code; the run resumes only after Pablo replied.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from harness.naming import next_run_number, run_id as make_run_id, validate_feature
from harness.orchestrator import pending_question

from .db import now_iso
from .sessions import clean_env
from .errors import HubError
from .tasks import TOKENS, ticket_key, token_assignments

if TYPE_CHECKING:
    from .hub import Hub

log = logging.getLogger("agenthub.harness")

STATE_WAIT_S = 60
# a run file named in a text: a versioned `_v<k>.md`, a `<name>_<feature>_<n>.md`, or any .md/.csv/.html
FILE_REF_RE = re.compile(r"[\w./-]*?([\w.-]+_v\d+\.md|[\w.-]+_[\w-]+_\d+\.md|[\w.-]+\.(?:md|csv|html))")


class BridgeRefused(HubError):
    pass


class HarnessBridge:
    poll_s = 2.0

    def __init__(self, hub: "Hub"):
        self.hub = hub
        self.db = hub.db
        self.config = hub.config
        self.layout = hub.config.layout()
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen | None] = {}  # run id → process (None: adopted after a restart)

    # ================================================================ start
    def start(self, task: dict, feature: str, ticket_text: str, project: str | None = None, workflow: str = "feature-v1") -> str:
        project = self._project_for(task, project)
        try:
            feature = validate_feature(feature)
        except (SystemExit, ValueError) as e:
            raise BridgeRefused(str(e), 422)
        if not (self.layout.workflows / workflow / "workflow.yaml").is_file():
            raise BridgeRefused(f"unknown workflow {workflow!r}", 422)
        if not ticket_text.strip():
            raise BridgeRefused("the harness ticket is empty", 422)
        self.layout.tickets.mkdir(parents=True, exist_ok=True)
        (self.layout.tickets / f"{feature}.md").write_text(f"---\nproject: {project}\n---\n{ticket_text.strip()}\n")
        console_dir = self.config.orchestrator_dir / "console"
        console_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            run_id = make_run_id(feature, next_run_number(self.layout, feature))
            console = console_dir / f"{run_id}.log"
            proc = self._spawn(["run", workflow, feature, "--quiet"], task, console)
            self._wait_for_state_file(proc, run_id, console)
            self.db.run(
                "INSERT INTO harness_runs (run_id, task_id, workflow, feature, project, status, pid, started_at)"
                " VALUES (?, ?, ?, ?, ?, 'running', ?, ?)",
                (run_id, task["id"], workflow, feature, project, proc.pid, now_iso()),
            )
            self._procs[run_id] = proc
        self.hub.tasks.add_event(task["id"], "system", f"Harness run {run_id} started on project {project} ({workflow}).")
        self._watch_in_background(run_id)
        self.hub.events.publish("tasks", task["id"])
        return run_id

    def _wait_for_state_file(self, proc: subprocess.Popen, run_id: str, console: Path) -> None:
        """Wait until the new run has written its state.json; refuse when it exits or takes too long."""
        state = self.layout.state_file(run_id)
        deadline = time.monotonic() + STATE_WAIT_S
        while not state.exists():
            exited = proc.poll() is not None
            if exited or time.monotonic() > deadline:
                if not exited:
                    _signal_group(proc.pid, signal.SIGTERM)
                raise BridgeRefused(f"the run did not start: {_tail(console)}", 500)
            time.sleep(0.1)

    def _project_for(self, task: dict, project: str | None) -> str:
        """A ticket's task runs on the ticket's project; a task without a ticket names a registered one (AC27, AC40)."""
        if task["ticket_id"]:
            ticket = self.db.one("SELECT * FROM tickets WHERE id = ?", (task["ticket_id"],))
            if not ticket["project"]:
                raise BridgeRefused(
                    f"ticket {ticket_key(ticket['id'])} has no project (\"No project\"): no harness run can be started "
                    "for its tasks; do the work in this session"
                )
            if project and project != ticket["project"]:
                raise BridgeRefused(f"a run of this task runs on the ticket's project {ticket['project']}, not on {project}")
            project = ticket["project"]
        elif not project:
            raise BridgeRefused("a task without a ticket must name the project of the run (--project <name>)")
        info = self.hub.projects.get(project)
        if info is None:
            raise BridgeRefused(f"no project named {project!r} is registered")
        if not info["ready"]:
            agentsmd = self.config.private_dir / "agentmds" / project / "AGENTS.md"
            raise BridgeRefused(
                f"project {project} is not ready: fill {agentsmd} (it still holds TODO(onboard) placeholders) before the first run"
            )
        return project

    def _env(self, task: dict) -> dict[str, str]:
        env = clean_env(dict(os.environ))
        env.pop("AGENTHUB_TASK_TOKEN", None)
        env.update(
            {
                "HARNESS_ROOT": str(self.config.root),
                "HARNESS_PRIVATE_ROOT": str(self.config.private_dir),
                "HARNESS_DATA_ROOT": str(self.config.orchestrator_dir),
                "HARNESS_NO_NOTIFY": "1",
                "HARNESS_CLAUDE_BIN": self.config.claude_bin,
                "AGENTHUB_TASK_ID": str(task["id"]),
                "AGENTHUB_AI_USER": self.db.user(task["ai_user_id"])["handle"],
            }
        )
        return env

    def _spawn(self, args: list[str], task: dict, console: Path, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
        env = self._env(task)
        env.update(extra_env or {})
        with open(console, "a") as out:
            return subprocess.Popen(
                [sys.executable, "-m", "harness.cli", *args],
                cwd=self.config.root, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

    # ================================================================ watching
    def _watch_in_background(self, run_id: str) -> None:
        threading.Thread(target=self._watch, args=(run_id,), name=f"run-{run_id}", daemon=True).start()

    def _alive(self, run_id: str) -> bool:
        proc = self._procs.get(run_id)
        if proc is not None:
            return proc.poll() is None
        pid = self.db.value("SELECT pid FROM harness_runs WHERE run_id = ?", (run_id,))
        return bool(pid) and _pid_alive(pid)

    def _watch(self, run_id: str) -> None:
        try:
            while self._alive(run_id):
                self.refresh_tokens(run_id)
                self.refresh_usage(run_id)
                time.sleep(self.poll_s)
            self.refresh_tokens(run_id)
            self.refresh_usage(run_id)
            self.hub.private.sync(f"run {run_id}")  # a step may have added to a project's AGENTS.md (AC37)
            self._on_exit(run_id)
        except Exception:
            log.exception("watching run %s failed", run_id)
        finally:
            self._procs.pop(run_id, None)

    def _read_state(self, run_id: str) -> dict | None:
        try:
            return json.loads(self.layout.state_file(run_id).read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def refresh_tokens(self, run_id: str) -> bool:
        """The run's four token columns := the sum over its step executions (AC41). Idempotent."""
        state = self._read_state(run_id)
        if state is None:
            return False
        totals = {k: 0 for k in TOKENS}
        for exe in state.get("executions") or []:
            for k in TOKENS:
                totals[k] += int((exe.get("tokens") or {}).get(k) or 0)
        values = [totals[k] for k in TOKENS]
        any_differs = " OR ".join(f"{c} <> ?" for c in TOKENS.values())
        changed = self.db.run(
            f"UPDATE harness_runs SET {token_assignments()} WHERE run_id = ? AND ({any_differs})",
            (*values, run_id, *values),
        )
        if changed:
            task_id = self.db.value("SELECT task_id FROM harness_runs WHERE run_id = ?", (run_id,))
            self.hub.events.publish("tasks", task_id)
        return bool(changed)

    def refresh_usage(self, run_id: str) -> bool:
        """Record the figures the run's steps wrote to state.json `usage`; True when one changed. Idempotent."""
        state = self._read_state(run_id)
        return bool(state) and self.hub.usage.record(state.get("usage"))

    def _on_exit(self, run_id: str) -> None:
        row = self.db.one("SELECT * FROM harness_runs WHERE run_id = ?", (run_id,))
        state = self._read_state(run_id) or {}
        state_status = state.get("status") or "failed"
        status = "stopped" if row["status"] == "stopped" else state_status  # a run Pablo stopped stays stopped
        task_id = row["task_id"]
        task = self.hub.tasks.get(task_id)
        pending = pending_question(self.layout, run_id) if status == "paused" else None
        self.db.run(
            "UPDATE harness_runs SET status = ?, pid = NULL, ended_at = ? WHERE run_id = ?",
            (status, now_iso() if state_status in ("done", "failed", "blocked") else None, run_id),
        )
        if task is None or task["status"] == "archived":
            return
        if pending and pending.get("kind") == "gate":
            self._post_gate(task, run_id, pending)
        elif pending:
            self.db.run(
                "UPDATE harness_runs SET pending_kind = ?, pending_decision_file = ?, pending_posted_at = ? WHERE run_id = ?",
                (pending["kind"], pending["decision_file"], now_iso(), run_id),
            )
            self.hub.tasks.send(task_id, self._question_notice(run_id, pending), kind="notice")
        elif status == "done":
            report = self._newest(run_id, "final_report")
            self.hub.tasks.send(
                task_id,
                f"Harness run {run_id} finished. Final report: {report or 'none written'}. "
                "Summarise the result for Pablo, with links to the run files, and end the turn done.",
                kind="notice",
            )
        elif status in ("failed", "blocked"):
            error = state.get("error") or "no error recorded"
            transcript = self.layout.run_log_dir(run_id)
            self.hub.tasks.send(
                task_id,
                f"Harness run {run_id} ended {status}: {error}. Step transcripts: {transcript}. "
                "Tell Pablo what happened and what you propose.",
                kind="notice",
            )
        self.hub.tasks.settle(task_id)
        self.hub.events.publish("tasks", task_id)

    def _question_notice(self, run_id: str, pending: dict) -> str:
        return (
            f"Harness run {run_id} paused with a question ({pending['kind']}, step {pending['step']}): "
            f"{pending.get('reason') or ''}\n\n{pending['question']}\n\n"
            f"Decision file: {pending['decision_file']}\n\n"
            "Answer it yourself only if Pablo's ticket or comments already answer it: record the answer in the "
            "decision file (`## Answer`, frontmatter `answered: true`) and run `agenthub harness resume "
            f"{run_id}`. Otherwise end the turn waiting on Pablo, asking him the question in your message.\n\n"
            f"The harness's own instructions for this question:\n\n{pending.get('chat_prompt') or ''}"
        )

    def _post_gate(self, task: dict, run_id: str, pending: dict) -> None:
        """The gate's message as a comment by the AI user, quoted verbatim, with links (AC28). No model turn."""
        decision = Path(pending["decision_file"])
        links = self._file_links(run_id, pending["question"])
        ai = self.db.user(task["ai_user_id"])
        quoted = "\n".join(f"> {line}" if line else ">" for line in pending["question"].strip().splitlines())
        body = (
            f"**{pending.get('reason') or 'Gate'}** of harness run `{run_id}` ({ai['name']}'s task):\n\n{quoted}\n\n"
            + (("Files: " + " · ".join(links) + "\n\n") if links else "")
            + "The run stays paused until Pablo replies here; the reply is the answer the run receives."
        )
        self.db.run(
            "UPDATE harness_runs SET pending_kind = 'gate', pending_decision_file = ?, pending_posted_at = ? WHERE run_id = ?",
            (str(decision), now_iso(), run_id),
        )
        self.hub.tasks.add_event(task["id"], "reply", body)
        if task["ticket_id"]:
            self.hub.tickets.post_ai_comment(task["ticket_id"], task["ai_user_id"], body, task["id"])
        self.hub.tasks.set_waiting(task["id"])

    def _file_links(self, run_id: str, text: str) -> list[str]:
        run_dir = self.layout.run_dir(run_id)
        links = []
        for name in sorted(set(m.group(1) for m in FILE_REF_RE.finditer(text))):
            base = re.sub(r"_v\d+(\.\w+)$", r"\1", name)
            newest = self._newest_file(run_dir, base) or (run_dir / name if (run_dir / name).is_file() else None)
            if newest:
                links.append(f"[{newest.name}]({self.config.base_url}/runs/{run_id}/files/{newest.name})")
        if not links:
            for stem in ("plan_short", "spec", "final_report"):
                newest = self._newest(run_id, stem)
                if newest:
                    links.append(f"[{newest.name}]({self.config.base_url}/runs/{run_id}/files/{newest.name})")
        return links

    def _newest(self, run_id: str, stem: str) -> Path | None:
        run_dir = self.layout.run_dir(run_id)
        feature = (self._read_state(run_id) or {}).get("feature") or run_id.rsplit("_", 1)[0]
        n = run_id.rsplit("_", 1)[-1]
        return self._newest_file(run_dir, f"{stem}_{feature}_{n}.md")

    @staticmethod
    def _newest_file(run_dir: Path, base_name: str) -> Path | None:
        stem, ext = os.path.splitext(base_name)
        found = [p for p in run_dir.glob(f"{stem}*{ext}") if re.fullmatch(re.escape(stem) + r"(_v\d+)?" + re.escape(ext), p.name)]
        return max(found, key=_version) if found else None

    # ================================================================ while a gate is pending
    def pending_gate(self, task_id: int) -> dict | None:
        return self.db.one(
            "SELECT * FROM harness_runs WHERE task_id = ? AND pending_kind = 'gate' ORDER BY started_at DESC LIMIT 1",
            (task_id,),
        )

    def reply_prefix(self, task_id: int) -> str:
        """Pablo's reply while a gate is pending reaches the AI user with what to do with it."""
        gate = self.pending_gate(task_id)
        if not gate:
            return ""
        pending = pending_question(self.layout, gate["run_id"]) or {}
        return (
            f"Pablo's reply below answers the pending gate of harness run {gate['run_id']} "
            f"({pending.get('reason') or 'gate'}). Decision file: {gate['pending_decision_file']}. Record his answer "
            "in that file as the gate's instructions say, then run `agenthub harness resume "
            f"{gate['run_id']}`.\n\nThe gate's instructions:\n\n{pending.get('chat_prompt') or ''}\n\n---\n\n"
        )

    def has_live_run(self, task_id: int) -> bool:
        return any(
            self._alive(r["run_id"])
            for r in self.db.all("SELECT run_id FROM harness_runs WHERE task_id = ? AND status = 'running'", (task_id,))
        )

    # ================================================================ resume
    def resume(self, task: dict, run_id: str) -> str:
        row = self.db.one("SELECT * FROM harness_runs WHERE run_id = ? AND task_id = ?", (run_id, task["id"]))
        if row is None:
            raise BridgeRefused(f"run {run_id} was not started by this task", 404)
        if self._alive(run_id):
            raise BridgeRefused(f"run {run_id} is still running")
        pending = pending_question(self.layout, run_id)
        extra: dict[str, str] = {}
        if pending:
            decision = Path(pending["decision_file"])
            if not _answered(decision):
                raise BridgeRefused(
                    f"the decision file {decision} does not say `answered: true` yet: record the answer first"
                )
            if pending["kind"] == "gate":
                extra = self._release_gate(task, row, decision)
            else:
                answer = decision.read_text().split("## Answer", 1)[-1].strip()
                self.hub.tasks.add_event(task["id"], "notice", f"Answer recorded for run {run_id}:\n\n{answer}")
        console = self.config.orchestrator_dir / "console" / f"{run_id}.log"
        with self._lock:
            proc = self._spawn(["resume", run_id, "--quiet"], task, console, extra)
            self.db.run(
                "UPDATE harness_runs SET status = 'running', pid = ?, pending_kind = NULL, pending_decision_file = NULL,"
                " pending_posted_at = NULL, ended_at = NULL WHERE run_id = ?",
                (proc.pid, run_id),
            )
            self._procs[run_id] = proc
        self.hub.tasks.add_event(task["id"], "system", f"Harness run {run_id} resumed.")
        self._watch_in_background(run_id)
        return run_id

    def _release_gate(self, task: dict, row: dict, decision: Path) -> dict[str, str]:
        """Append Pablo's replies since the gate was posted to its decision file; the extra env that releases it."""
        run_id = row["run_id"]
        replies = self.db.all(
            "SELECT text FROM task_events WHERE task_id = ? AND kind = 'user' AND turn_id IS NOT NULL"
            " AND created_at >= ? ORDER BY id",
            (task["id"], row["pending_posted_at"] or ""),
        )
        if not replies:
            raise BridgeRefused(
                f"run {run_id} waits at a gate: only Pablo's reply releases it, and he has not replied since it was posted"
            )
        with open(decision, "a") as f:
            f.write("\n## Human reply (verbatim)\n\n" + "\n\n".join(r["text"].strip() for r in replies) + "\n")
        return {"HARNESS_GATE_RELEASE": decision.name}

    # ================================================================ status, stop, recovery
    def status(self, task: dict) -> list[dict]:
        out = []
        for r in self.db.all("SELECT * FROM harness_runs WHERE task_id = ? ORDER BY started_at", (task["id"],)):
            state = self._read_state(r["run_id"]) or {}
            out.append({
                "run_id": r["run_id"], "project": r["project"], "workflow": r["workflow"], "status": r["status"],
                "current_step": state.get("current"), "pending_kind": r["pending_kind"],
                "decision_file": r["pending_decision_file"], "run_dir": str(self.layout.run_dir(r["run_id"])),
                "tokens": sum(int(r[c] or 0) for c in TOKENS.values()),
            })
        return out

    def stop_runs(self, task_id: int) -> None:
        for r in self.db.all("SELECT run_id, pid FROM harness_runs WHERE task_id = ? AND status = 'running'", (task_id,)):
            if r["pid"] and self._alive(r["run_id"]):
                self.db.run("UPDATE harness_runs SET status = 'stopped' WHERE run_id = ?", (r["run_id"],))
                _signal_group(r["pid"], signal.SIGTERM)
                threading.Timer(5, _signal_group, args=(r["pid"], signal.SIGKILL)).start()

    def recover(self) -> set[int]:
        """At app start: runs whose process is gone are marked interrupted; live ones are watched again.
        Returns the ids of tasks that still have a working run."""
        live: set[int] = set()
        for r in self.db.all("SELECT * FROM harness_runs"):
            self.refresh_tokens(r["run_id"])
            if r["status"] != "running":
                continue
            if r["pid"] and _pid_alive(r["pid"]):
                self._procs[r["run_id"]] = None
                live.add(r["task_id"])
                self._watch_in_background(r["run_id"])
            else:
                self.db.run("UPDATE harness_runs SET status = 'interrupted', pid = NULL WHERE run_id = ?", (r["run_id"],))
                self.hub.tasks.add_event(
                    r["task_id"], "system",
                    f"Harness run {r['run_id']} was interrupted by a restart; `agenthub harness resume {r['run_id']}` continues it.",
                )
        return live

    def shutdown(self) -> None:
        """The server stops: runs keep going in their own process groups and are adopted at the next start."""


def _answered(decision: Path) -> bool:
    try:
        head = decision.read_text().split("---", 2)
    except OSError:
        return False
    return len(head) >= 3 and re.search(r"^answered:\s*true\s*$", head[1], re.M) is not None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _tail(path: Path, n: int = 8) -> str:
    try:
        return " | ".join(path.read_text().strip().splitlines()[-n:]) or "no output"
    except OSError:
        return "no output"


def _version(path: Path) -> int:
    """The `_v<k>` suffix of a run file; an unversioned file counts as v1."""
    m = re.search(r"_v(\d+)\.\w+$", path.name)
    return int(m.group(1)) if m else 1

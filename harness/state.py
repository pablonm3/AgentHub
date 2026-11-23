"""Run state (spec 5.2): runs/<run-id>/state.json, written by the orchestrator only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_STATUSES = ("running", "waiting_on_human", "paused", "done", "failed", "blocked")
STEP_STATUSES = ("pending", "running", "done", "failed", "skipped", "waiting")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "–"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def seconds_between(a: str | None, b: str | None) -> float | None:
    da, db = parse_iso(a), parse_iso(b)
    if da is None or db is None:
        return None
    return (db - da).total_seconds()


class State:
    """Thin wrapper over the state dict with save()."""

    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data

    # ------------------------------------------------------------ construction
    @classmethod
    def new(
        cls,
        path: Path,
        *,
        run_id: str,
        workflow: str,
        feature: str,
        n: int,
        project: str,
        base_branch: str,
        harness_commit: str,
        defaults: dict[str, Any],
        step_ids: list[str],
    ) -> "State":
        data: dict[str, Any] = {
            "run_id": run_id,
            "workflow": workflow,
            "feature": feature,
            "n": n,
            "project": project,
            "base_branch": base_branch,
            "branch": run_id,
            "harness_commit": harness_commit,
            "status": "running",
            "iteration": 1,
            "max_iterations": int(defaults.get("max_iterations", 3)),
            "spec_revisions": 0,
            "waiting_on_human": None,
            "current": None,
            "started": now_iso(),
            "ended": None,
            "defaults": defaults,
            "telemetry": {"active": False, "since_step": None, "reason": None},
            "pending_chat": None,
            "injected_answer": None,
            "question_history": [],
            "steps": {sid: {"status": "pending"} for sid in step_ids},
            "executions": [],
            "gates": {},
            "error": None,
        }
        return cls(path, data)

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.is_file():
            raise SystemExit(f"harness: no state file at {path}")
        with open(path) as f:
            return cls(path, json.load(f))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        tmp.replace(self.path)

    # ------------------------------------------------------------ accessors
    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def run_id(self) -> str:
        return self.data["run_id"]

    @property
    def feature(self) -> str:
        return self.data["feature"]

    @property
    def n(self) -> int:
        return int(self.data["n"])

    @property
    def status(self) -> str:
        return self.data["status"]

    @property
    def current(self) -> str | None:
        return self.data.get("current")

    def step(self, sid: str) -> dict[str, Any]:
        return self.data["steps"].setdefault(str(sid), {"status": "pending"})

    def executions_of(self, sid: str) -> list[dict[str, Any]]:
        return [e for e in self.data["executions"] if e["step"] == str(sid)]

    def execution_count(self, sid: str) -> int:
        return len(self.executions_of(sid))

    # ------------------------------------------------------------ transitions
    def begin_step(self, sid: str, skill: str | None, inputs: list[str], outputs: list[str]) -> dict:
        exe = {
            "step": str(sid),
            "skill": skill,
            "iteration": self.data["iteration"],
            "k": self.execution_count(sid) + 1,
            "started": now_iso(),
            "ended": None,
            "status": "running",
            "in": inputs,
            "out": outputs,
            "outcome": None,
            "transcript": None,
            "project_cost": None,
            "cost_usd": None,
            "commits": None,
        }
        self.data["executions"].append(exe)
        st = self.step(sid)
        st.update({"status": "running", "started": exe["started"], "runs": exe["k"]})
        self.data["current"] = str(sid)
        return exe

    def end_step(self, exe: dict, status: str, outcome: str | None = None, **extra: Any) -> None:
        exe["ended"] = now_iso()
        exe["status"] = status
        if outcome is not None:
            exe["outcome"] = outcome
        exe.update(extra)
        st = self.step(exe["step"])
        st.update({"status": status, "ended": exe["ended"]})
        if outcome is not None:
            st["outcome"] = outcome
        if exe.get("out"):
            st["out"] = exe["out"]
        if exe.get("in"):
            st["in"] = exe["in"]
        if exe.get("project_cost"):
            st["project_cost"] = exe["project_cost"]

    def reopen_step(self, exe: dict) -> None:
        """Put a failed or interrupted execution back to running: it continues in its own session,
        as one more attempt of the same execution. The time it sat stopped is kept in `waited_s`."""
        exe["waited_s"] = (exe.get("waited_s") or 0) + (seconds_between(exe.get("ended"), now_iso()) or 0)
        exe["attempts"] = (exe.get("attempts") or 1) + 1
        exe["status"] = "running"
        exe["ended"] = None
        self.step(exe["step"]).update({"status": "running", "started": now_iso()})
        self.data["current"] = exe["step"]

    def mark_skipped(self, sid: str, reason: str) -> None:
        self.step(sid).update({"status": "skipped", "reason": reason})

    def gate_reached(self, sid: str) -> None:
        self.step(sid).update({"status": "waiting", "gate": True, "reached": now_iso()})
        self.data["gates"].setdefault(str(sid), []).append(
            {"reached": now_iso(), "released": None, "after_execution": len(self.data["executions"])}
        )
        self.data["waiting_on_human"] = str(sid)
        self.data["status"] = "waiting_on_human"
        self.data["current"] = str(sid)

    def gate_released(self, sid: str) -> None:
        self.step(sid).update({"status": "done", "released": now_iso()})
        entries = self.data["gates"].get(str(sid), [])
        if entries and entries[-1]["released"] is None:
            entries[-1]["released"] = now_iso()
        self.data["waiting_on_human"] = None
        if self.data["status"] == "waiting_on_human":
            self.data["status"] = "running"

    def finish(self, status: str, error: str | None = None) -> None:
        self.data["status"] = status
        self.data["ended"] = now_iso()
        if error:
            self.data["error"] = error

    # ------------------------------------------------------------ derived timings
    def human_wait_seconds(self) -> float:
        total = 0.0
        for entries in self.data.get("gates", {}).values():
            for e in entries:
                s = seconds_between(e.get("reached"), e.get("released") or (self.data.get("ended") or now_iso()))
                if s:
                    total += s
        return total

    def total_seconds(self) -> float | None:
        return seconds_between(self.data.get("started"), self.data.get("ended") or now_iso())

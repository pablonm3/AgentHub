"""The Claude account's usage left: the last figure of each limit that an AI user's turn or a harness run
step reported in a `rate_limit_event`, kept in the `settings` row `account_usage` so a restart keeps it.

A figure is `{"limit", "used", "resets_at", "reached", "read_at"}`. A newer figure replaces the one of its
own limit and leaves the others alone; a figure whose reset time has passed is no longer answered.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import TYPE_CHECKING

from harness.claude_runner import limit_usage

from .db import now_iso

if TYPE_CHECKING:
    from .hub import Hub

log = logging.getLogger("agenthub.usage")

SETTING = "account_usage"
FIELDS = ("limit", "used", "resets_at", "reached", "read_at")


class Usage:
    def __init__(self, hub: "Hub"):
        self.db = hub.db
        self.events = hub.events
        self._lock = threading.Lock()

    def record(self, figures: object) -> bool:
        """Keep each well-formed figure whose limit has none stored, or has a different one not read later.
        True when one was kept: the row is written and topic `usage` published once."""
        incoming = [_clean(f) for f in figures if _valid(f)] if isinstance(figures, list) else []
        with self._lock:
            stored = self._stored()
            kept = dict(stored)
            for figure in incoming:
                old = kept.get(figure["limit"])
                if old is None or (figure != old and figure["read_at"] >= old["read_at"]):
                    kept[figure["limit"]] = figure
            if kept == stored:
                return False
            self.db.set_setting(SETTING, json.dumps(list(kept.values())))
        self.events.publish("usage")
        return True

    def record_event(self, event: dict) -> None:
        """The figures of one stream event of a turn, read now. A failure here never reaches the turn."""
        try:
            figures = limit_usage(event)
            if figures:
                read_at = now_iso()
                self.record([{**f, "read_at": read_at} for f in figures])
        except Exception:
            log.exception("reading a rate_limit_event failed")

    def current(self) -> list[dict]:
        """The stored figures whose period has not ended yet, by limit name; [] when none is known."""
        now = time.time()
        return sorted((f for f in self._stored().values() if f["resets_at"] > now), key=lambda f: f["limit"])

    def _stored(self) -> dict[str, dict]:
        try:
            rows = json.loads(self.db.setting(SETTING) or "[]")
        except Exception:
            log.exception("the %s setting cannot be read", SETTING)
            return {}
        if not isinstance(rows, list):
            return {}
        return {f["limit"]: _clean(f) for f in rows if _valid(f)}


def _valid(figure: object) -> bool:
    """A figure with the five fields well formed; it may come from another process's state.json."""
    if not isinstance(figure, dict):
        return False
    limit, used, resets_at = figure.get("limit"), figure.get("used"), figure.get("resets_at")
    reached = figure.get("reached")
    if not (isinstance(limit, str) and limit and isinstance(reached, bool) and isinstance(figure.get("read_at"), str)):
        return False
    if isinstance(resets_at, bool) or not isinstance(resets_at, int) or resets_at <= 0:
        return False
    if used is None:
        return reached
    return not isinstance(used, bool) and isinstance(used, (int, float)) and 0 <= used <= 1


def _clean(figure: dict) -> dict:
    return {k: figure[k] for k in FIELDS}

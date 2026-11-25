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

from harness.claude_runner import limit_usage, readable_epoch, readable_share

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
        """Keep each well-formed figure that replaces the stored one of its limit (see `_replaces`).
        True when one was kept: the row is written and topic `usage` published once."""
        incoming = [_clean(f) for f in figures if _valid(f)] if isinstance(figures, list) else []
        with self._lock:
            stored = self._stored()
            kept = dict(stored)
            for figure in incoming:
                if _replaces(figure, kept.get(figure["limit"])):
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


def _replaces(new: dict, old: dict | None) -> bool:
    """True for a first figure of its limit, or a changed one read no earlier than the stored one
    (an unchanged re-read of state.json every 2 s does not count, so nothing is written or published)."""
    return old is None or (new != old and new["read_at"] >= old["read_at"])


def _valid(figure: object) -> bool:
    """A figure with the five fields well formed; it may come from another process's state.json."""
    if not isinstance(figure, dict):
        return False
    limit, used, resets_at = figure.get("limit"), figure.get("used"), figure.get("resets_at")
    reached = figure.get("reached")
    if not (isinstance(limit, str) and limit and isinstance(reached, bool) and isinstance(figure.get("read_at"), str)):
        return False
    # The parser's rules for a readable share and reset time; a stored reset time is the int it gives.
    if not (isinstance(resets_at, int) and readable_epoch(resets_at)):
        return False
    if used is None:
        return reached
    return readable_share(used) is not None


def _clean(figure: dict) -> dict:
    return {k: figure[k] for k in FIELDS}

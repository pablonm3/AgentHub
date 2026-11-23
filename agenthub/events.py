"""In-process publish/subscribe for live updates: the UI listens on /api/events and refetches a topic."""

from __future__ import annotations

import queue
import threading


class Events:
    def __init__(self) -> None:
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, topic: str, id: int | str | None = None) -> None:
        message = {"topic": topic} if id is None else {"topic": topic, "id": id}
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(message)
            except queue.Full:
                pass  # a stalled listener misses updates; the UI also polls

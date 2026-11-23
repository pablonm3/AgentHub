"""The server's parts, wired together once per app."""

from __future__ import annotations

import os

from .config import Config
from .db import Database
from .events import Events
from .harness_bridge import HarnessBridge
from .private_sync import PrivateSync
from .projects import Projects
from .reports import Reports
from .sessions import Sessions
from .tasks import Tasks
from .tickets import Tickets


class Hub:
    def __init__(self, config: Config):
        self.config = config
        config.data_dir.mkdir(parents=True, exist_ok=True)
        # read by the harness copy's launcher in this process
        os.environ["HARNESS_CLAUDE_BIN"] = config.claude_bin
        self.db = Database(config.db_path)
        self.events = Events()
        self.sessions = Sessions(config)
        self.private = PrivateSync(config.private_dir)
        self.projects = Projects(self)
        self.reports = Reports(self)
        self.tasks = Tasks(self)
        self.tickets = Tickets(self)
        self.bridge = HarnessBridge(self)

    def start(self) -> None:
        """Restart recovery (AC18): runs first, so a task whose run still works stays running."""
        self.private.prepare()
        live = self.bridge.recover()
        self.tasks.recover(live)

    def shutdown(self) -> None:
        self.tasks.shutdown()
        self.bridge.shutdown()

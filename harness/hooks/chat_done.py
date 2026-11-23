#!/usr/bin/env python3
"""Stop hook of a harness chat: report that the chat is finished (spec 5.7).

Claude Code runs it each time Claude finishes a reply. When the decision file of the
question (HARNESS_DECISION_FILE) carries `answered: true`, it creates the marker file
(HARNESS_CHAT_DONE_MARKER). The orchestrator, which waits on the chat process, sees the
marker and closes the chat. The marker is created here, not when the decision file is
written, so the reply that wrote it is complete before the chat closes.

Always exits 0 and prints nothing: it never blocks or alters the chat.
"""

import os
import re
import sys

FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---", re.S)
ANSWERED = re.compile(r"^answered:[ \t]*true[ \t]*$", re.M)


def is_answered(path: str) -> bool:
    try:
        with open(path, errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    m = FRONTMATTER.match(text)
    return bool(m and ANSWERED.search(m.group(1)))


def main() -> int:
    decision = os.environ.get("HARNESS_DECISION_FILE")
    marker = os.environ.get("HARNESS_CHAT_DONE_MARKER")
    if decision and marker and is_answered(decision):
        try:
            open(marker, "w").close()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

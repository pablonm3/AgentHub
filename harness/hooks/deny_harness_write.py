#!/usr/bin/env python3
"""PreToolUse hook: enforce the run write boundary (spec 5.1).

Blocks Edit/Write/MultiEdit/NotebookEdit whose target lies under a protected path, and
Bash commands with a write-like operation and a path under a protected path. The Bash check
goes by where a path points, not by its text: the path-like words of the command (words
holding `/`, redirect targets, `cd` targets) are resolved against the session's folder and
against the folder of every `cd` in the command. A word that cannot be resolved (it holds a
variable or a command substitution) counts when it names a protected path or folder as text.
Protected paths come from HARNESS_PROTECTED_PATHS (os.pathsep separated, absolute).

Exit 2 with a message on stderr denies the tool call; exit 0 lets it through.
"""

import json
import os
import re
import shlex
import sys

WRITE_LIKE = re.compile(
    r"(^|[\s;&|])(sed\s+-i|tee|mv|cp|rm|rmdir|truncate|chmod|chown|ln|mkdir|touch|git\s+(checkout|restore|reset|clean|rm|mv|commit|apply|stash))\b|>>?\s*\S"
)
OPERATORS = ";&|<>"


def _words(cmd: str) -> list[str] | None:
    """Shell words of the command, operators (`&&`, `>`, `;`) as words of their own; None when it does not parse.

    Parentheses stay inside words, so `$(pwd)/x` stays one word.
    """
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=OPERATORS)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return None


def _path_words(words: list[str], cwd: str) -> tuple[list[tuple[str, bool]], list[str]]:
    """The path-like words of a command, each with whether it cannot be resolved, and the folders
    they may be relative to: the session's folder and that of every `cd`."""
    folders = [cwd]
    paths = []
    substitution = 0  # depth of `$(` opened by earlier words: `$(git rev-parse --show-toplevel)/x` spans three
    for i, word in enumerate(words):
        prev = words[i - 1] if i else ""
        unresolvable = substitution > 0 or "$" in word or "`" in word
        substitution = max(substitution + word.count("$(") - word.count(")"), 0)
        if prev.lstrip("(") == "cd":
            folders.append(os.path.join(folders[-1], os.path.expanduser(word)))
            paths.append((word, unresolvable))
        elif "/" in word or (prev and set(prev) <= set(OPERATORS) and ">" in prev):
            paths.append((word, unresolvable))
            if "=" in word:  # `of=/x`, `--output=/x`
                paths.append((word.split("=", 1)[1], unresolvable))
    return paths, folders


def _names_protected(text: str, protected: list[str]) -> bool:
    """The text rule: a protected path, or a protected folder name followed by `/`, appears in the text."""
    return any(p in text or os.path.basename(p) + "/" in text for p in protected)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    protected = [p for p in os.environ.get("HARNESS_PROTECTED_PATHS", "").split(os.pathsep) if p]
    if not protected:
        return 0
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}
    cwd = payload.get("cwd") or os.getcwd()

    def is_protected(path: str, base: str = cwd) -> bool:
        if not path:
            return False
        ap = os.path.realpath(os.path.join(base, os.path.expanduser(path)))
        for p in protected:
            rp = os.path.realpath(p)
            if ap == rp or ap.startswith(rp + os.sep):
                return True
        return False

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        target = inp.get("file_path") or inp.get("notebook_path") or ""
        if is_protected(target):
            sys.stderr.write(
                f"harness write boundary: {target} is part of the harness (skills, workflows, "
                "GENERAL.md, harness.yaml or the orchestrator) and cannot be edited from inside a run. "
                "Record the proposed change in your output file instead.\n"
            )
            return 2
        return 0

    if tool == "Bash":
        cmd = inp.get("command", "") or ""
        if not WRITE_LIKE.search(cmd):
            return 0
        words = _words(cmd)
        if words is None:
            touches = _names_protected(cmd, protected)
        else:
            paths, folders = _path_words(words, cwd)
            touches = any(
                _names_protected(word, protected) if unresolvable else any(is_protected(word, f) for f in folders)
                for word, unresolvable in paths
            )
        if touches:
            sys.stderr.write(
                "harness write boundary: this command would modify a protected harness path. "
                "Runs may write only to their worktree, their run folder and agentmds/<project>/AGENTS.md.\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

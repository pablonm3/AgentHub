#!/usr/bin/env python3
"""A stand-in for the `gh` command (AGENTHUB_GH_BIN) — no test reaches GitHub.

Every call is appended to `$AGENTHUB_FAKE_GH_DIR/gh.log` (argv and GH_HOST).
- `repo create <name> …` makes a bare repository with one README commit on `main` under
  `$AGENTHUB_FAKE_GH_DIR/repos/<name>.git` and prints a web URL for it;
- `repo view <url> --json sshUrl,url` prints that repository's path as both URLs;
- `config get git_protocol …` prints `ssh`;
- `auth status …` exits 0 with a "Logged in to github.com" line.
Switches in `$AGENTHUB_FAKE_GH_DIR/scenario.json`: `name_taken`, `not_logged_in` (the creation fails
with gh's message and `auth status` exits 1), `unclonable` (the URLs point at nothing),
`auth_broken` (`auth status` exits 3), `auth_hangs` (`auth status` sleeps 5 s before answering).
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OWNER = "fake-owner"


def main() -> int:
    d = Path(os.environ.get("AGENTHUB_FAKE_GH_DIR") or tempfile.gettempdir()) / "."
    d.mkdir(parents=True, exist_ok=True)
    argv = sys.argv[1:]
    with open(d / "gh.log", "a") as log:
        log.write(json.dumps({"argv": argv, "GH_HOST": os.environ.get("GH_HOST")}) + "\n")
    sc_path = d / "scenario.json"
    sc = json.loads(sc_path.read_text()) if sc_path.exists() else {}
    repos = d / "repos"
    if argv[:2] == ["repo", "create"]:
        name = argv[2]
        if sc.get("not_logged_in"):
            print("To get started with GitHub CLI, please run:  gh auth login", file=sys.stderr)
            return 4
        if sc.get("name_taken") or (repos / f"{name}.git").exists():
            print("GraphQL: Name already exists on this account (createRepository)", file=sys.stderr)
            return 1
        bare = repos / f"{name}.git"
        bare.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        with tempfile.TemporaryDirectory() as work:
            git = ["git", "-C", work, "-c", "user.name=fake", "-c", "user.email=fake@example.invalid"]
            subprocess.run(["git", "init", "-q", "-b", "main", work], check=True)
            Path(work, "README.md").write_text(f"# {name}\n")
            subprocess.run([*git, "add", "README.md"], check=True)
            subprocess.run([*git, "commit", "-q", "-m", "Initial commit"], check=True)
            subprocess.run([*git, "push", "-q", str(bare), "main"], check=True)
        print(f"https://github.com/{OWNER}/{name}")
        return 0
    if argv[:2] == ["repo", "view"]:
        name = argv[2].rstrip("/").rsplit("/", 1)[-1]
        path = str(repos / ("missing-" + name if sc.get("unclonable") else name)) + ".git"
        print(json.dumps({"sshUrl": path, "url": path}))
        return 0
    if argv[:3] == ["config", "get", "git_protocol"]:
        print("ssh")
        return 0
    if argv[:2] == ["auth", "status"]:
        if sc.get("auth_hangs"):
            time.sleep(5)
        if sc.get("auth_broken"):
            print("fake gh: unexpected error", file=sys.stderr)
            return 3
        if sc.get("not_logged_in"):
            print("You are not logged into any GitHub hosts. To log in, run: gh auth login", file=sys.stderr)
            return 1
        print(f"github.com\n  ✓ Logged in to github.com account {OWNER} (keyring)")
        return 0
    print(f"fake gh: unsupported command {' '.join(argv)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fail when a file the public repo tracks, or would track on the next commit, holds what must stay private.

Checked: a `.env` file; any file under `private/` (only the submodule link may be tracked); a
`SIGNOZ_…=value` line; a home-folder path of a machine; every fixed string of
`private/public_guard.txt`; and, when `private/.env` exists, the value of each of its keys whose name
holds SECRET, KEY, TOKEN or PASSWORD (eight characters or more). Prints the file and the rule, never
a secret value.

    uv run python scripts/check_public_tree.py [--root <repo>] [--private <folder>]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SIGNOZ_RE = re.compile(r"SIGNOZ_[A-Z_]+=[^\s<${\"'`]")  # a placeholder (<…>, $VAR, {name}) is no value
HOME_RE = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
SECRET_NAME_RE = re.compile(r"SECRET|KEY|TOKEN|PASSWORD")


def candidate_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout
    return sorted(set(out.splitlines()))


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def read_guard(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]


def check(root: Path, private: Path, files: list[str] | None = None) -> list[str]:
    files = candidate_files(root) if files is None else files
    patterns = read_guard(private / "public_guard.txt")
    secrets = {k: v for k, v in read_env(private / ".env").items() if SECRET_NAME_RE.search(k) and len(v) >= 8}
    findings: list[str] = []
    private_rel = private.resolve().relative_to(root.resolve()).as_posix() if root.resolve() in private.resolve().parents else None
    for rel in files:
        if Path(rel).name == ".env":
            findings.append(f"{rel}: a .env file is tracked")
        if private_rel and rel.startswith(private_rel + "/"):
            findings.append(f"{rel}: a file of the private folder is tracked")
        path = root / rel
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if SIGNOZ_RE.search(line):
                findings.append(f"{rel}:{n}: a SIGNOZ_ setting with a value")
            if HOME_RE.search(line):
                findings.append(f"{rel}:{n}: a home-folder path of a machine")
            for p in patterns:
                if p in line:
                    findings.append(f"{rel}:{n}: a pattern of public_guard.txt (line {patterns.index(p) + 1})")
            for key, value in secrets.items():
                if value in line:
                    findings.append(f"{rel}:{n}: the value of {key} from the private .env")
    return findings


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", default=str(here))
    p.add_argument("--private", default=None, help="default: <root>/private")
    args = p.parse_args()
    root = Path(args.root).resolve()
    private = Path(args.private).resolve() if args.private else root / "private"
    if not (private / "public_guard.txt").is_file():
        print(f"warning: {private}/public_guard.txt not found (is the submodule initialised?); its patterns are not checked")
    findings = check(root, private)
    for f in findings:
        print(f)
    if findings:
        print(f"{len(findings)} finding(s): the public tree holds private content")
        return 1
    print("public tree clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Naming and tracking rules (spec section 1) plus artifact frontmatter.

- run id          <feature>_<n>
- artifact        <stem>_<feature>_<n>[_v<k>].md   (no suffix = version 1)
- reads pattern   ending in *.md resolves to the highest version per stem
"""

from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Any

import yaml

from .paths import Layout

FEATURE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^(?P<stem>.+?)_v(?P<k>\d+)(?P<ext>\.[A-Za-z0-9]+)$")
RUN_ID_RE = re.compile(r"^(?P<feature>[a-z0-9]+(?:-[a-z0-9]+)*)_(?P<n>\d+)$")


def validate_feature(feature: str) -> str:
    if not FEATURE_RE.match(feature):
        raise SystemExit(
            f"harness: feature name {feature!r} must be kebab-case (lowercase letters, digits, dashes)"
        )
    return feature


def run_id(feature: str, n: int) -> str:
    return f"{feature}_{n}"


def split_run_id(rid: str) -> tuple[str, int]:
    m = RUN_ID_RE.match(rid)
    if not m:
        raise SystemExit(f"harness: {rid!r} is not a run id (<feature>_<n>)")
    return m.group("feature"), int(m.group("n"))


def next_run_number(layout: Layout, feature: str) -> int:
    """One more than the highest run number found in workflow_logs/, runs/ and archived/."""
    highest = 0
    pat = re.compile(rf"^(?:\d{{4}}-\d{{2}}-\d{{2}}_)?{re.escape(feature)}_(\d+)(?:\.log)?$")
    for d in (layout.workflow_logs, layout.runs, layout.archived):
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            m = pat.match(entry.name)
            if m:
                highest = max(highest, int(m.group(1)))
    return highest + 1


def split_version(path: Path | str) -> tuple[str, int]:
    """'runs/x/plan_f_1_v3.md' → ('runs/x/plan_f_1.md', 3); no suffix → version 1."""
    p = Path(path)
    m = VERSION_RE.match(p.name)
    if m:
        return str(p.with_name(m.group("stem") + m.group("ext"))), int(m.group("k"))
    return str(p), 1


def version_suffix(k: int) -> str:
    return "" if k <= 1 else f"_v{k}"


def versioned(base: Path | str, k: int) -> Path:
    """Version k of a base (unversioned) path."""
    b = Path(base)
    return b.with_name(b.stem + version_suffix(k) + b.suffix)


def highest_version(base: Path | str) -> int:
    """Highest version present on disk for a base path; 0 when none exists."""
    b = Path(base)
    best = 0
    if b.exists():
        best = 1
    for cand in b.parent.glob(f"{glob.escape(b.stem)}_v*{b.suffix}"):
        _, k = split_version(cand)
        best = max(best, k)
    return best


def latest(base: Path | str) -> Path | None:
    k = highest_version(base)
    return versioned(base, k) if k else None


def next_version(base: Path | str, execution_count: int = 1) -> int:
    """Version for a new execution: unique on disk and at least the execution count."""
    return max(execution_count, highest_version(base) + 1)


def resolve_reads(root: Path, pattern: str) -> list[Path]:
    """Expand a reads pattern. `*.md` patterns keep only the latest version per stem."""
    matches = [Path(p) for p in glob.glob(str(root / pattern), recursive=True)]
    matches = [m for m in matches if m.is_file()]
    if not pattern.endswith("*.md"):
        return sorted(matches)
    best: dict[str, tuple[int, Path]] = {}
    for m in matches:
        base, k = split_version(m)
        if base not in best or k > best[base][0]:
            best[base] = (k, m)
    return [best[b][1] for b in sorted(best)]


# ---------------------------------------------------------------- frontmatter

FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def read_frontmatter(path: Path | str) -> dict[str, Any]:
    """YAML frontmatter of a markdown artifact, {} when absent or malformed."""
    p = Path(path)
    if not p.is_file():
        return {}
    text = p.read_text(errors="replace")
    m = FM_RE.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return _frontmatter_by_key(m.group(1))
    return data if isinstance(data, dict) else {}


TOP_KEY_RE = re.compile(r"[A-Za-z_][\w-]*:")


def _frontmatter_by_key(block: str) -> dict[str, Any]:
    """Frontmatter that is not valid YAML as a whole, read one top-level key at a time.

    Skills write `summary:` as one unquoted line, and a ": " inside it makes the whole block
    invalid YAML; without this the routing keys next to it (decision, status, answered) read
    as missing. A key whose own lines still do not parse keeps its raw text as a string.
    """
    chunks: list[list[str]] = []
    for line in block.splitlines():
        if TOP_KEY_RE.match(line):
            chunks.append([line])
        elif chunks:
            chunks[-1].append(line)
    data: dict[str, Any] = {}
    for chunk in chunks:
        try:
            parsed = yaml.safe_load("\n".join(chunk))
        except yaml.YAMLError:
            key, _, rest = chunk[0].partition(":")
            parsed = {key: " ".join([rest.strip(), *(c.strip() for c in chunk[1:])]).strip()}
        if isinstance(parsed, dict):
            data.update(parsed)
    return data


def body_without_frontmatter(path: Path | str) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    text = p.read_text(errors="replace")
    return FM_RE.sub("", text, count=1)


SEVERITY_HEADING_RE = re.compile(r"^#{2,4}\s*\[?(CRITICAL|HIGH|MEDIUM|LOW)\]?\b", re.I | re.M)


def count_severities(path: Path | str) -> dict[str, int]:
    """Counts from frontmatter `counts:` when present, else from `### [HIGH] ...` headings."""
    fm = read_frontmatter(path)
    counts = fm.get("counts")
    if isinstance(counts, dict):
        return {str(k).lower(): int(v or 0) for k, v in counts.items()}
    out: dict[str, int] = {}
    for m in SEVERITY_HEADING_RE.finditer(body_without_frontmatter(path)):
        key = m.group(1).lower()
        out[key] = out.get(key, 0) + 1
    return out


def severities_line(counts: dict[str, int]) -> str:
    order = ["critical", "high", "medium", "low"]
    parts = [f"{counts[k]} {k}" for k in order if counts.get(k)]
    return ", ".join(parts) if parts else "no findings"


# ---------------------------------------------------------------- run cost (spec 4.6)

COST_KEYS = {
    "project runs": "runs",
    "wall time": "wall_time",
    "llm usage": "llm_usage",
    "source": "source",
}


def parse_run_cost(path: Path | str) -> dict[str, str] | None:
    """Parse the `## Run cost` section of an artifact. None when absent."""
    text = body_without_frontmatter(path)
    m = re.search(r"^##\s+Run cost\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not m:
        return None
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip().lstrip("-").strip()
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower().rstrip(":")
        if key in COST_KEYS:
            out[COST_KEYS[key]] = val.strip()
    return out or None


def cost_line(cost: dict[str, str] | None) -> str:
    if not cost:
        return "project none"
    runs = (cost.get("runs") or "").strip().lower()
    if runs in ("", "none"):
        return "project none"
    parts = []
    if cost.get("wall_time"):
        parts.append(f"wall {cost['wall_time']}")
    if cost.get("llm_usage"):
        parts.append(f"LLM {cost['llm_usage']}")
    s = "project " + " · ".join(parts) if parts else f"project {cost['runs']}"
    if cost.get("source"):
        s += f" ({cost['source']})"
    return s

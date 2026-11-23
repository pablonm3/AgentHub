"""Loading of harness.yaml, workflow.yaml and defaults.yaml (spec sections 5.4, 6.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import Layout


class ConfigError(SystemExit):
    pass


def load_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"harness: missing {path}")
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"harness: {path} must hold a mapping")
    return data


def dump_yaml(data: dict, path: Path) -> None:
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


@dataclass
class Project:
    name: str
    repo: str
    default_base: str
    agentsmd: str
    skills: str
    setup: list[str] = field(default_factory=list)
    defaults: dict[str, Any] = field(default_factory=dict)  # tunables every run of this project starts with


@dataclass
class Manifest:
    observability: str = "external"  # external | off
    projects: dict[str, Project] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    def project(self, name: str) -> Project:
        if name not in self.projects:
            known = ", ".join(sorted(self.projects)) or "(none)"
            raise ConfigError(f"harness: unknown project '{name}'. Known: {known}")
        return self.projects[name]


def load_manifest(layout: Layout) -> Manifest:
    raw = load_yaml(layout.manifest)
    obs = raw.get("observability", "external")
    if obs is False:  # YAML reads a bare `off` as boolean false
        obs = "off"
    if obs in ("required", "optional"):  # the original harness's modes; the copy never starts a stack
        obs = "external"
    if obs not in ("external", "off"):
        raise ConfigError(f"harness: observability must be external|off, got {obs}")
    projects = {}
    for name, p in (raw.get("projects") or {}).items():
        p = p or {}
        project_defaults = p.get("defaults") or {}
        if not isinstance(project_defaults, dict):
            raise ConfigError(f"harness: projects.{name}.defaults must hold a mapping")
        projects[name] = Project(
            name=name,
            repo=p.get("repo", ""),
            default_base=p.get("default_base", "main"),
            agentsmd=p.get("agentsmd", f"agentmds/{name}/AGENTS.md"),
            skills=p.get("skills", f"skills/projects/{name}"),
            setup=list(p.get("setup") or []),
            defaults=dict(project_defaults),
        )
    return Manifest(observability=obs, projects=projects, raw=raw)


@dataclass
class Step:
    id: str
    label: str
    actor: str = "ai"  # ai | human | orchestrator
    skill: str | None = None
    prompt: str | None = None
    incremental_prompt: str | None = None  # used instead of `prompt` when a repeat covers only the new commits
    reads: dict[str, str] = field(default_factory=dict)
    writes: dict[str, str] = field(default_factory=dict)
    writes_commit: bool = False
    gate: bool = False
    action: str | None = None  # orchestrator steps: start_run | run_log | push_branch
    message: str | None = None
    chat_skill: str | None = None
    chat_prompt: str | None = None
    skip_when: str | None = None
    on_decision: dict[str, str] = field(default_factory=dict)
    on_status: dict[str, str] = field(default_factory=dict)
    max_loops: str | None = None
    display: str | None = None
    # MCP servers the step's session gets (`--mcp-config`), Claude Code's mcpServers shape;
    # ${...} in command, args and env take the prompt variables (run_dir, feature, n, iteration…)
    mcp_servers: dict[str, dict] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def primary_output(self) -> str | None:
        """Pattern of the first declared output; its frontmatter carries the outcome."""
        for v in self.writes.values():
            return v
        return None


@dataclass
class Group:
    name: str
    steps: list[str]
    loop: bool = False


@dataclass
class Workflow:
    name: str
    dir: Path
    steps: list[Step]
    groups: list[Group]
    raw: dict

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == str(step_id):
                return s
        raise ConfigError(f"harness: workflow {self.name} has no step {step_id}")

    def has_step(self, step_id: str) -> bool:
        return any(s.id == str(step_id) for s in self.steps)

    def next_after(self, step_id: str) -> str | None:
        ids = [s.id for s in self.steps]
        i = ids.index(str(step_id))
        return ids[i + 1] if i + 1 < len(ids) else None

    def first_ai_or_gate(self) -> str:
        for s in self.steps:
            if s.actor == "ai" or s.gate:
                return s.id
        raise ConfigError("harness: workflow has no AI step")

    def prompt_text(self, rel: str | None) -> str:
        if not rel:
            return ""
        p = self.dir / rel
        if not p.is_file():
            raise ConfigError(f"harness: prompt file missing: {p}")
        return p.read_text()


def _as_map(value: Any, kind: str) -> dict[str, str]:
    """reads/writes may be a list of patterns or a name→pattern mapping."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, list):
        return {f"{kind}{i + 1}": str(v) for i, v in enumerate(value)}
    raise ConfigError(f"harness: {kind} must be a list or mapping")


def load_workflow(layout: Layout, name: str) -> Workflow:
    wdir = layout.workflow_dir(name)
    raw = load_yaml(wdir / "workflow.yaml")
    steps = []
    for s in raw.get("steps") or []:
        sid = str(s["id"])
        actor = s.get("actor") or ("human" if s.get("gate") else "ai")
        steps.append(
            Step(
                id=sid,
                label=s.get("label") or s.get("skill") or s.get("action") or f"step {sid}",
                actor=actor,
                skill=s.get("skill"),
                prompt=s.get("prompt"),
                incremental_prompt=s.get("incremental_prompt"),
                reads=_as_map(s.get("reads"), "in"),
                writes=_as_map(s.get("writes"), "out"),
                writes_commit=bool(s.get("writes_commit", False)),
                gate=bool(s.get("gate")),
                action=s.get("action"),
                message=s.get("message"),
                chat_skill=s.get("chat_skill"),
                chat_prompt=s.get("chat_prompt"),
                skip_when=s.get("skip_when"),
                on_decision={str(k): str(v) for k, v in (s.get("on_decision") or {}).items()},
                on_status={str(k): str(v) for k, v in (s.get("on_status") or {}).items()},
                max_loops=s.get("max_loops"),
                display=s.get("display"),
                mcp_servers=dict(s.get("mcp_servers") or {}),
                raw=s,
            )
        )
    groups = [
        Group(name=g["name"], steps=[str(x) for x in g.get("steps", [])], loop=bool(g.get("loop")))
        for g in (raw.get("groups") or [])
    ]
    return Workflow(name=raw.get("name", name), dir=wdir, steps=steps, groups=groups, raw=raw)


EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

DEFAULTS_FALLBACK: dict[str, Any] = {
    "max_iterations": 3,
    "spec": "always",
    "review_severity_threshold": "high",
    "readability_severity_threshold": "medium",
    "review_scope": "incremental",
    "review_incremental_max_lines": 400,
    "review_incremental_max_share": 0.25,
    "test_subset_on_retry": "full",
    "on_rate_limit": "wait",
    "step_continuations": 3,
    "regression": "always",
    "regression_repetitions": 3,
    "langsmith_cleanup": "always",
    "auth": "account",
    "on_question": "pause",
    "permission_mode": "bypassPermissions",
    "chat_permission_mode": "auto",
    "model": {},
    "effort": {},
    "timeouts": {},
    "max_budget_usd": None,
}


def load_defaults(
    layout: Layout,
    workflow: str,
    project_defaults: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict:
    """Later wins: fallbacks, defaults.yaml, the project's `defaults` in harness.yaml, per-run overrides (spec 5.4)."""
    path = layout.workflow_dir(workflow) / "defaults.yaml"
    data = dict(DEFAULTS_FALLBACK)
    if path.is_file():
        data.update(load_yaml(path))
    data.update(project_defaults or {})
    data.update(overrides or {})
    if data["spec"] not in ("always", "auto", "never"):
        raise ConfigError("harness: defaults.spec must be always|auto|never")
    if data["regression"] not in ("always", "never"):
        raise ConfigError("harness: defaults.regression must be always|never")
    if data["langsmith_cleanup"] not in ("always", "never"):
        raise ConfigError("harness: defaults.langsmith_cleanup must be always|never")
    effort = data["effort"] or {}
    levels = [effort] if isinstance(effort, str) else [effort.get("default"), *(effort.get("steps") or {}).values()]
    unknown = sorted({str(level) for level in levels if level is not None and level not in EFFORT_LEVELS})
    if unknown:
        raise ConfigError(f"harness: defaults.effort must be one of {'|'.join(EFFORT_LEVELS)}, got {', '.join(unknown)}")
    if data["on_rate_limit"] not in ("wait", "pause"):
        raise ConfigError("harness: defaults.on_rate_limit must be wait|pause")
    data["step_continuations"] = int(data["step_continuations"])
    if data["review_scope"] not in ("incremental", "full"):
        raise ConfigError("harness: defaults.review_scope must be incremental|full")
    data["review_incremental_max_lines"] = int(data["review_incremental_max_lines"])
    data["review_incremental_max_share"] = float(data["review_incremental_max_share"])
    # only workflows with a push_branch step define `push`; absent means the step runs
    if data.get("push", "always") not in ("always", "never"):
        raise ConfigError("harness: defaults.push must be always|never")
    if data["auth"] not in ("account", "api_key"):
        raise ConfigError("harness: defaults.auth must be account|api_key")
    if data["on_question"] not in ("chat", "pause"):
        raise ConfigError("harness: defaults.on_question must be chat|pause")
    data["max_iterations"] = int(data["max_iterations"])
    return data


def parse_override(text: str) -> tuple[str, Any]:
    """`--set key=value` with YAML-typed values (3 → int, true → bool)."""
    if "=" not in text:
        raise ConfigError(f"harness: --set expects key=value, got {text!r}")
    k, v = text.split("=", 1)
    return k.strip(), yaml.safe_load(v)

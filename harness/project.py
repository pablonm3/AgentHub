"""`agenthub-harness project add | list` (spec 6.3): base clone, manifest entry, AGENTS.md template,
then an interactive session with the `onboard-project` skill.

The manifest, the AGENTS.md and the skills folder are written under the private root, the base
clone under the data root."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .claude_runner import base_env, run_chat
from .config import dump_yaml, load_manifest, load_yaml
from .paths import Layout

PLACEHOLDER = "TODO(onboard)"

AGENTS_TEMPLATE = """# {name} — instructions for agents

Project know-how lives here, never in the harness skills. Every section below is read by
`build-context`, `plan`, `run-tests` and the other skills. Keep it concise and factual.

## How to run the app and check a change

{ph}: command(s) to start the app locally, URL/port, how to log in, how to see a change in the UI.

## How to run tests

{ph}: unit and integration test commands, where tests live, conventions.

## How to run evals or regression suites

{ph}: eval runner commands, how to read the output, what counts as a regression. Write `none` if the project has no evals.

## Companion repos and tools

{ph}: other repositories or services a change may depend on, where they live, how to run them, when a change needs them re-run. Write `none` if there are none.

## Secrets and config

{ph}: which files or variables are required, where they come from, what must never be written.

## Data access rules

{ph}: databases and environments, which are read-only, how to connect.

## Branching rules

{ph}: base branch, feature branch naming, what is never merged by an agent.
"""


def agents_template(name: str) -> str:
    return AGENTS_TEMPLATE.format(name=name, ph=PLACEHOLDER)


def has_placeholders(path: Path) -> bool:
    return path.is_file() and PLACEHOLDER in path.read_text()


def project_add(layout: Layout, name: str, repo: str | None, base: str | None, no_chat: bool = False) -> None:
    manifest_raw = load_yaml(layout.manifest)
    projects = manifest_raw.setdefault("projects", {}) or {}
    manifest_raw["projects"] = projects
    existing = projects.get(name)
    if existing is None:
        if not repo:
            raise SystemExit("harness: --repo <git url> is required for a new project")
        projects[name] = {
            "repo": repo,
            "default_base": base or "main",
            "agentsmd": f"agentmds/{name}/AGENTS.md",
            "skills": f"skills/projects/{name}",
            "setup": [],
        }
        dump_yaml(manifest_raw, layout.manifest)
        print(f"added projects.{name} to harness.yaml")
    else:
        if repo and existing.get("repo") != repo:
            existing["repo"] = repo
        if base:
            existing["default_base"] = base
        dump_yaml(manifest_raw, layout.manifest)
        print(f"project {name} already in harness.yaml; reopening onboarding")

    manifest = load_manifest(layout)
    project = manifest.project(name)

    base_clone = layout.base_clone(name)
    if not (base_clone / ".git").exists():
        base_clone.parent.mkdir(parents=True, exist_ok=True)
        print(f"cloning {project.repo} → {layout.rel(base_clone)}")
        subprocess.run(["git", "clone", project.repo, str(base_clone)], check=True)
    else:
        print(f"base clone present: {layout.rel(base_clone)}")

    skills_dir = layout.private_path(project.skills)
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / ".gitkeep").touch()

    agentsmd = layout.private_path(project.agentsmd)
    if not agentsmd.exists():
        agentsmd.parent.mkdir(parents=True, exist_ok=True)
        agentsmd.write_text(agents_template(name))
        print(f"created {project.agentsmd} from the template")

    if no_chat:
        return
    prompt = (
        f"Invoke the `onboard-project` skill for project `{name}`.\n\n"
        f"- harness code root: {layout.root}\n"
        f"- harness private root: {layout.private_root}\n"
        f"- base clone (this directory): {base_clone}\n"
        f"- AGENTS.md to fill: {agentsmd}\n"
        f"- project skills directory: {skills_dir}\n"
        f"- manifest with the `setup` list: {layout.manifest} (key projects.{name}.setup)\n"
        f"- default base branch: {project.default_base}\n\n"
        "Start at phase 0 (check what the harness already has for this project). "
        "Write files only on approval. Tell the human to exit when done."
    )
    env = base_env(layout, "account")
    print("\nopening the onboarding session in the base clone; exit it when the AGENTS.md is complete.\n")
    run_chat(layout=layout, prompt=prompt, cwd=base_clone, settings_file=None, env=env, permission_mode="auto", name=f"onboard {name}")
    if has_placeholders(agentsmd):
        print(f"\n{project.agentsmd} still has {PLACEHOLDER} placeholders; `agenthub-harness run` will refuse this project until they are filled.")
    else:
        print(f"\n{project.agentsmd} is complete.")


def project_list(layout: Layout) -> None:
    manifest = load_manifest(layout)
    if not manifest.projects:
        print("no projects in harness.yaml")
        return
    for name, p in sorted(manifest.projects.items()):
        agentsmd = layout.private_path(p.agentsmd)
        if not agentsmd.exists():
            status = "AGENTS.md missing"
        elif has_placeholders(agentsmd):
            status = "AGENTS.md has placeholders"
        else:
            status = "ready"
        clone = "cloned" if (layout.base_clone(name) / ".git").exists() else "not cloned"
        print(f"{name:<16} base {p.default_base:<8} {clone:<11} {status:<28} setup: {len(p.setup)} command(s)")

# Coding harness — rules for every project

This file is the copy of the coding harness that AgentHub runs. `link_worktree` imports it into every run worktree's `CLAUDE.md`, next to the project's `AGENTS.md` and `<private root>/agents.md`, so every step and AI user session knows the harness exists. Nothing is written under the user's home Claude folder. The design is in `docs/WORKFLOW_SPEC.md`.

The copy works from three roots, each set by a variable (both others default to the code root):

| root | variable | holds |
|---|---|---|
| code root (the AgentHub repo) | `HARNESS_ROOT` | `harness/`, `workflows/`, `skills/general/`, `agentmds/GENERAL.md`, `docs/`, `observability/otel.env` |
| private root (`private/`) | `HARNESS_PRIVATE_ROOT` | `harness.yaml`, `agentmds/<project>/AGENTS.md`, `skills/projects/<project>/`, `agents.md`, `.env` |
| data root (`data/orchestrator/`) | `HARNESS_DATA_ROOT` | `tickets/`, `runs/`, `workflow_logs/`, `worktrees/`, `archived/` |

## The harness CLI

`agenthub-harness` is the console script of the AgentHub package (`uv sync` in the repo). `--root <path>` or `HARNESS_ROOT` point it at a code root. Inside an AgentHub session (`AGENTHUB_TASK_TOKEN` is set) use `agenthub harness start | status | resume` instead: `run` and `resume` refuse there, because the AgentHub server is their only caller.

| command | what it does |
|---|---|
| `agenthub-harness run <workflow> <feature>` | start a run of `tickets/<feature>.md` with `workflows/<workflow>/`; allocates the run number, creates `runs/<feature>_<n>/` and the worktree, runs the project setup list, then the AI steps. `--set key=value` overrides a `defaults.yaml` value for this run |
| `agenthub-harness resume <run-id>` | continue a run that paused (question or gate), failed or was interrupted; a step that stopped unfinished continues in its own session, and starts over as a new `_v<k>` only when that session cannot be continued. A paused question continues only once its decision file says `answered: true`; a paused gate also needs `HARNESS_GATE_RELEASE` set to the decision file's name, which AgentHub sets after the human's reply |
| `agenthub-harness status [<run-id>] [--watch] [--log <step>]` | render the run graph (no id: list runs); `--watch` redraws; `--log` tails a step transcript |
| `agenthub-harness obs status \| mcp-config` | whether the external telemetry collector answers; the SigNoz MCP server registration |
| `agenthub-harness link <project> <worktree> [--codex]` | link the general and the project skills into `<worktree>/.claude/skills/` and write the worktree's `CLAUDE.md` imports |
| `agenthub-harness project add <name> --repo <url> --base <branch>` / `agenthub-harness project list` | add a project (base clone, manifest entry, AGENTS.md template, onboarding session) / list projects and whether their AGENTS.md is complete |
| `agenthub-harness verify-auth` | check that the logged-in Claude credential works from a launched process |
| `agenthub-harness --help` | everything above |

## Rules inside a run

- A run writes only to its worktree, its run folder `runs/<feature>_<n>/`, and `agentmds/<project>/AGENTS.md` (to add run or test instructions that were missing). `skills/`, `workflows/`, `agentmds/GENERAL.md`, `harness.yaml` and the orchestrator source are read-only; a settings file and a hook enforce it. Propose harness changes in your output file instead; the human applies them with `improve-harness`.
- Every generated file carries `_<feature>_<n>` and, for repeated executions, `_v<k>`. Never overwrite an artifact: write the next version.
- Autonomous steps never edit the spec. Spec, plan and ticket-copy edits happen only on the human's approval, as approved diffs written as new versions.
- A gate or question pauses the run with a decision file. AgentHub shows it to the human; the human's reply reaches an AI user as a ticket comment, and that AI user records the answer in the decision file (`## Answer`, `answered: true`, approved edits as new versions) and runs `agenthub harness resume <run-id>`.
- Skills and chats never push and never merge into the base branch. The orchestrator pushes the feature branch to `origin` before GATE 2 (step 18b; `--set push=never` skips it); the human opens the PR.
- Skills are non-interactive when the invocation gives every input, and ask only for missing inputs when called by hand.
- Every skill that runs the project (app, UIs, evals) ends its output with a `## Run cost` section using numbers the project already exposes.

## Working on the harness itself

- Changes to the code root (`skills/general/`, `workflows/`, `agentmds/GENERAL.md`, the orchestrator source, docs) are committed in the AgentHub repo, one commit per logical change, message stating what changed and why. Changes in the private root (`harness.yaml`, project `AGENTS.md` files, project skills) are committed and pushed as `<private root>/agents.md` says. A project branch is pushed only by its run's push step (rule above).

## Manual skills

`archive-old-work`, `obs-query`, `improve-harness` and `onboard-project` are conversations with judgement in them; invoke them by name in an ordinary session (`/obs-query what did filter-recovery_2 cost per step`).

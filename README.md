# AgentHub

A board where one human user, Pablo, works with three AI users — Data Scientist, Engineer and
DevOps — through tickets and tasks instead of a terminal. Assigning a ticket to an AI user,
@mentioning one in a comment, or starting a task from the Tasks page starts a Claude session with
that AI user's role prompt. What the AI user needs from Pablo comes back as a ticket comment, listed
in the Activity tab. Tasks are saved in a database, so they stop and continue later; the Tasks page
shows each task's status, title, model, working time and token use.

At its core AgentHub has its own copy of a coding harness (`agenthub-harness`): an AI user starts a
harness run (context, spec, plan, build, tests, reviews, report) when a ticket's work needs it, and
the run's gates reach Pablo as comments.

## Layout

| path | what it is |
|---|---|
| `agenthub/` | the web server (FastAPI + SQLite): tickets, comments, tasks, AI turns, Activity, harness runs, reports |
| `agenthub/prompts/` | the AI users' rules, their starting role prompts, and the first-message templates |
| `agenthub/tests/` | pytest suite with a fake `claude` and a fake `gh`; `serve_fake.py` starts the app in fake mode |
| `web/` | the UI (React, Vite, TypeScript), built to `web/dist` and served by the server |
| `harness/`, `workflows/`, `skills/general/`, `agentmds/GENERAL.md`, `docs/WORKFLOW_SPEC.md`, `observability/otel.env` | the harness copy: orchestrator, workflows `feature-v1` and `regression-v1`, the harness skills and rules |
| `skills/agents/` | the AI users' shared skills: `search-history` (search tickets, comments and task chats, archived ones included) and `coding-harness` |
| `scripts/check_public_tree.py` | fails when a tracked file holds private content; run it before every commit |
| `private/` | git submodule `AgentHub-private` (private): `agents.md`, `.env`, the harness manifest `harness.yaml`, every project's `AGENTS.md` and skills. Its `README.md` describes it. Nothing of it is tracked here |
| `prototype/Main.dc.html` | the interface prototype the UI follows (a claude.ai Design artboard; it does not render on its own) |
| `data/` | created at run time, never committed: `agenthub.db`, `tasks/<id>/` (workspace, turn transcripts), `reports/<task id>/`, `orchestrator/` (the harness copy's tickets, runs, logs, worktrees) |

## Install

Needs Python 3.11+, `uv`, Node 22 with npm, `git`, and the `claude` CLI logged in on this machine
(`claude auth login`). "New project" without a repo URL also needs `gh` logged in on `github.com`.

```bash
git clone --recurse-submodules <this repo's URL>   # or, in a clone: git submodule update --init
uv sync
npm --prefix web ci
npm --prefix web run build
```

## Start and stop

```bash
uv run agenthub serve            # http://127.0.0.1:8787 (another port: --port <n> or AGENTHUB_PORT)
```

Open `http://127.0.0.1:8787`. Ctrl+C stops the server; a task that was running is shown as waiting
on the user after the next start, and a message continues it. The server listens on 127.0.0.1 only.

Tasks use the Claude login stored on this machine; the Settings page shows whether it is valid. A
task session ignores the settings and skills in `~/.claude`, and AgentHub never writes there.

## Tests

```bash
uv run pytest                    # the server and the harness copy, with fake claude and fake gh
npm --prefix web test            # the UI's unit tests
uv run python scripts/check_public_tree.py
```

Fake mode runs the whole app without Claude, GitHub or the private repo — fake `claude`, fake `gh`,
a temp data folder and a temp clone of `private/`, all deleted on Ctrl+C:

```bash
uv run python -m agenthub.tests.serve_fake --port 8799
```

## Data

Everything the app writes is under `data/` (`AGENTHUB_DATA_DIR` moves it). To start over, stop the
server and delete `data/agenthub.db`, `data/tasks/`, `data/reports/` and `data/orchestrator/`.

Not undone by a reset: a project registered with "New project" stays in `private/harness.yaml`, and
a "New project" without a repo URL creates a **private GitHub repository** of that name on the
account `gh` is logged in with. AgentHub never deletes a repository; delete it on GitHub by hand.

## Observability

When the shared SigNoz collector answers (ports from `private/.env`), every AI turn and every harness
step sends telemetry with `app=agenthub`, `task_id` and `ai_user`; filter on `app = agenthub` to see
AgentHub alone. AgentHub never starts, stops or configures the instance, and tasks run the same when
it is down.

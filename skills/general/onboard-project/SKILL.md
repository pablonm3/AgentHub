---
name: onboard-project
description: Fill a project's agentmds/<project>/AGENTS.md and its setup list in harness.yaml with the human — checks what the harness already has, drafts from the repo (README, manifests, CI, launchers), asks only what the repo cannot tell, verifies the commands in a scratch worktree, writes on approval. Launched by `agenthub-harness project add`; also use when the user asks to onboard a project or revise a project's AGENTS.md.
---

# Onboard project

Interactive by nature: it runs in the base clone (`worktrees/<project>/.base/` under the data root) in a session opened by `agenthub-harness project add` (or by an AgentHub AI user following this skill), outside any run, so it is the one place a skill may write `harness.yaml`. `harness.yaml`, `agentmds/<project>/` and `skills/projects/<project>/` live in the private root (`HARNESS_PRIVATE_ROOT`, `private/` in AgentHub). It fills the AGENTS.md template whose headings are the step-3 list: how to run the app and check a change, run tests, run evals, companion tools, secrets and config, data access rules, branching rules. Placeholders look like `TODO(onboard): …`; `agenthub-harness run` refuses a project whose AGENTS.md still has one.

## Phase 0 — what the harness already has

Look only inside the private root: `agentmds/<project>/AGENTS.md` and `skills/projects/<project>/`. If either has real content (not just the template), list it (AGENTS.md sections present, skill names) and ask: **edit these, or start new?**

- *Edit*: the existing AGENTS.md is the draft and the skills stay; the phases below only ask for what is missing or fails verification.
- *Start new*: move the existing files to `agentmds/<project>/previous_<yyyy-mm-dd>/` and `skills/projects/<project>/previous_<yyyy-mm-dd>/` (never delete), then run from the template.

Nothing there: continue silently.

## Phase 1 — draft from the repo

Read README, Makefile or task-runner files, package manifests and lockfiles, Docker and compose files, CI workflows, launch configs, test directories, any `AGENTS.md`/`CLAUDE.md` in the repo. Draft each AGENTS.md section and the `setup` list (dependency install, secrets fetch — whatever a fresh worktree needs, safe to repeat, writing only inside the worktree). Mark everything inferred rather than read with `(inferred)`.

## Phase 2 — ask only what the repo cannot tell

Secrets and where they come from, dev servers and databases and the access rule for each (read-only or not), companion repos or tools and when a change needs them re-run, branching rules, anything marked inferred. One question at a time, proposing the draft answer when there is one. Nothing the repo already answers is asked.

## Phase 3 — verify

Create a scratch worktree from the base clone (`git worktree add <tmp> origin/<default_base>`), run the `setup` list in it, then the documented commands for running tests and starting the app (stop it afterwards). Fix the draft until they work or the human says to stop. Remove the scratch worktree.

## Phase 4 — write

Show both as diffs and write on approval:

- the AGENTS.md in the file's concise style, every placeholder gone, with a short onboarding note at the end (date, what was verified, what the human chose not to set up);
- the `setup` list into `harness.yaml` under `projects.<project>.setup`.

The `setup` list is the machine-readable version of what the AGENTS.md says under secrets/config and how to run; they must agree.

End by telling the human to exit the session. `agenthub-harness project list` then shows the project as ready.

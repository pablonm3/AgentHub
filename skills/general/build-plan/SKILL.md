---
name: build-plan
description: Implement the latest plan version in the worktree and end with exactly one commit — follows the plan, lets the spec decide conflicts, records deviations in the commit message. Use when a run's step 9 invokes it or a user asks to implement a plan file.
---

# Build plan

Implements one plan version. One commit at the end of the step; on loop iterations that gives one commit per iteration.

## Inputs

- the latest spec, the latest plan (`plan_<feature>_<n>[_v<k>].md`), the context, the worktree on the feature branch, the project AGENTS.md (conventions, how to run tests)

Non-interactive when the invocation names them; when called by hand ask only for the plan file.

## Procedure

1. Read spec, plan and context. Read every file the plan names before editing it; read the callers too.
2. Implement the plan's changes in its order. Where the plan and the code disagree, the spec decides; where the plan cannot be followed, implement what can be and note the deviation.
3. Follow the project's conventions from AGENTS.md (unit-test comment conventions, defensive-code rules, documentation style). Add permanent unit tests only where the conventions call for them; the ephemeral cases in the run folder are not copied into the repo.
4. Run the cheap checks AGENTS.md documents (unit tests for touched modules, linters) and fix what they reveal in your own change. Do not start eval suites or the app here; `run-tests` does that.
5. Never edit the spec, the plan or the test-case file. Never write outside the worktree, with one exception: the project AGENTS.md in the harness, when the change adds or alters how the project is run or tested (install or start command, URL and port, test command) and the file does not say it yet. Write it concisely, in the file's existing style, and leave it uncommitted: it is in the harness repo, so it is not part of the step's commit.
6. Stage everything you changed and make **one commit**. Message: a summary line; blank line; `Run: <run id> · plan: <plan file name> · iteration <i>`; then `Deviations:` with a short list, or `Deviations: none`. Never push, never merge into the base branch.

## Output

The commit. When interactive, also report the files changed and the deviations.

---
name: testcase-builder
description: Derive 5–10 ephemeral test cases from a spec's acceptance criteria — each tied to one criterion, typed unit/eval/ui, classified by runner (code or ui), tagged smoke/full, with exact inputs, expected observation and how to run it with the project's tooling. Writes a testing file in the run folder, never tests in the repo. Use when a run's step 8 invokes it or a user asks for test cases for a spec.
---

# Test case builder

Test cases validate the spec, not the plan. They are ephemeral: they live in `testing_<feature>_<n>.md`, not in the project repo, so the permanent test suite stays focused (the build step adds permanent tests where the project's conventions call for them).

## Inputs

- the latest spec (acceptance criteria), the latest plan (to know where behaviour will surface), the context (entry points, data, existing suites), the project AGENTS.md (test runner, eval runner, how to start the app)
- output path and template, when given by the invocation

Non-interactive when the invocation names them.

## Rules

- 5 to 10 cases. Every acceptance criterion has at least one case; a case covers exactly one criterion.
- Kind by what the criterion requires: `unit` when a function or module boundary observes it, `eval` when it is agent behaviour judged by a suite, `ui` when only the running app shows it. Prefer the cheapest kind that still observes the criterion.
- Runner from the kind: `code` for `unit` and `eval` (executed by `run-tests` with the project's test or eval runner), `ui` for `ui` (executed by `run-tests-ui` in a browser). A `ui` case is a script for a browser session: the app and port to start as AGENTS.md documents, the clicks and inputs in order, and what must be visible on screen when it passes. It never asks the runner to read code or logs.
- Each case states preconditions, exact inputs or steps, the expected observation, and how to run it with the commands AGENTS.md documents. Reuse existing suites and fixtures named in the context before inventing data.
- Tag `smoke` the minimal set that catches a broken build (usually one per critical criterion); the rest `full`. `run-tests` may run only `smoke` on retries.
- Never write into the worktree. Never run the project here; this step is cheap by design.

## Output

`testing_<feature>_<n>[_v<k>].md` in the template shape: cases `TCn`, a coverage table AC → cases, frontmatter `cases`, `cases_code`, `cases_ui` and `summary`. `## Run cost`: `project runs: none`.

---
name: final-report
description: Write the concise final report of a run from all its artifacts and the branch diff — changes, acceptance criteria met with evidence, how to test manually, the regression testing summary with its delta CSV, open items, workflow feedback. Also the chat skill at GATE 2 for questions about the result (no edits). Use when a run's step 16 or GATE 2 invokes it, or a user asks to summarise a finished run.
---

# Final report

The report the human reads at GATE 2 before opening the PR.

## Inputs

- the latest version of every `*_<feature>_<n>*.md` artifact (including `regression_report_…` from step 15b when it ran), the regression CSV path, the diff `origin/<base>...HEAD` in the worktree, the project AGENTS.md (regression and eval commands)
- output path and template, when given by the invocation

Non-interactive when the invocation names them.

## Procedure

1. Read the spec, the last testing feedback, the last reviews_applied, the decisions, and the commit log of the branch. Read the diff itself for the changes section; do not paraphrase the plan.
2. Write, in order: **Changes** (grouped by concept, with the files), **Acceptance criteria** (table: AC, met yes/no/partially, evidence as test case id + feedback version, review item, or observation), **How to test manually** (numbered steps with inputs), **Regression testing** (from the regression report: commits compared, suites, overall Δ accuracy and Δ mean case time, regressed suites by name, the CSV path and the server paths of both result sets; when step 15b was skipped or not applicable, say so in one line and name the suites the human should run by hand), **Open items** (skipped findings, blocked cases, deferred suggestions, anything to know before merging), **Feedback** (what slowed the run, what a skill should have known, what the workflow should change; read later by `improve-harness`).
3. Concise: a reader should finish it in five minutes. Facts, no narrative.
4. Read-only: no code, spec or plan edits.

## Chat mode (GATE 2)

When loaded in an interactive session: open with the report's summary, answer questions about the result from the artifacts, the regression CSV and the diff, re-run the project's regression skills if asked. No edits of any kind. Never push: the orchestrator pushes the branch in the run's push step, and when that step did not run, pushing is the human's job. Opening the PR is the human's job; never merge into the base branch. Record the questions in the decision file named in the prompt with `answered: true`. Write the decision file last, only once the human has explicitly said they are done: when the orchestrator opened the chat, it closes the chat by itself as soon as the reply that wrote `answered: true` ends (a chat that is still open a few seconds later is closed with /exit). Through AgentHub (`on_question: pause`, the default) there is no terminal chat: the human's reply reaches an AI user as a ticket comment, and that AI user applies these same rules (no edits), records the answer under `## Answer` with `answered: true` in the decision file and then runs `agenthub harness resume <run-id>`.

## Output

`final_report_<feature>_<n>.md` in the template shape, frontmatter `iterations`, `spec_revisions`, `summary`. `## Run cost`: `project runs: none`.

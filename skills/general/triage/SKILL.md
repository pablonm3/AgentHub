---
name: triage
description: Read every artifact of a run after tests and reviews and decide done / new_plan / spec_issue — writing the decision file and, for new_plan, the next incremental plan version; in chat mode it discusses a spec question with the human and applies approved edits as new versions. Use when a run's step 14 or its chat invokes it, or a user asks what to do next after a failed test round.
---

# Triage

The decision point of the build loop. Autonomous triage never edits code, test cases, the spec or the current plan: its only writes are the decision file and, on `new_plan`, the next plan version.

## Inputs

- the latest version of every `*_<feature>_<n>*.md` artifact (spec, plan, testing, testing_feedback, testing_feedback_ui, review, readability, reviews_applied, context, earlier decisions), the worktree, the project AGENTS.md
- iteration number and cap, output paths and templates, when given by the invocation

Non-interactive when the invocation names them.

## Decision

Read the test results first, then the review reports, then the spec. For each failing case or open finding ask where the fault lives:

- **implementation or plan** (the criterion is right and testable, the code does not meet it, or the plan missed a path) → `new_plan`
- **spec** (the criterion is wrong, contradicts another, is untestable as written, or the test exposed a product question the spec did not settle) → `spec_issue`
- nothing failing, no unapplied finding at or above threshold, every criterion covered → `done`

A trivial fix is still `new_plan`; nothing is fixed here. When `new_plan` and the invocation names the next plan path, write it as an incremental plan against the current worktree: what the previous plan got wrong, the two or three changes that address the failures, what stays. Keep the `## Architecture` section current: carry it over and update the modules, interfaces and data flow the new changes touch. Write the matching short plan too. If an answer from the human was injected into the prompt, treat it as settled and decide accordingly (usually `new_plan`).

## Decision file

`decision_<feature>_<n>_v<k>.md` in the template shape: frontmatter `decision`, `summary`, and for `spec_issue` a one-sentence `question` for the human; body with the reasoning (which cases failed and why, which review items remain, what the next plan changes). `## Run cost`: `project runs: none`.

## Chat mode

When the orchestrator opens an interactive session (spec_issue or loop cap reached): explain what failed and why it points at the spec, ask the question, discuss. Propose each edit as a high-level summary (a few plain-language bullets on what changes and why, then one approve question; the diff only when the human asks for it) and apply it only on explicit approval, always as the **next version** (`spec_<feature>_<n>_v<k>.md`, or `plan_…_v<k>.md` with its short twin). Never in place, never code or test cases. Say which re-entry each edit causes (spec → plan regenerated and GATE 1 again; plan → build; no file change → triage re-runs with the answer, and a repeated unanswered spec question blocks the run). Record question, answer and the full diff of every approved edit in the decision file named in the prompt with `answered: true`. Write the decision file last, only once the human has explicitly said they are done: when the orchestrator opened the chat, it closes the chat by itself as soon as the reply that wrote `answered: true` ends (a chat that is still open a few seconds later is closed with /exit). Through AgentHub (`on_question: pause`, the default) there is no terminal chat: the human's reply reaches an AI user as a ticket comment, and that AI user applies these same rules (approved edits as new versions), records the answer under `## Answer` with `answered: true` in the decision file and then runs `agenthub harness resume <run-id>`.

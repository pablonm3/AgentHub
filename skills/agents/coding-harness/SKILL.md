---
name: coding-harness
description: Start and follow a run of AgentHub's coding harness (spec, plan, build, tests, reviews, report) for work that changes a project's code; relay its gates to Pablo, answer or surface its questions, resume it. Use when a task needs a project's code changed through the full workflow, never for a small question.
---

# Running AgentHub's coding harness from a task

AgentHub has its own copy of the coding harness (`agenthub-harness`). A run takes a ticket file,
works in its own git worktree of the project and goes through context, spec, plan, GATE 1, build,
tests, reviews, triage, final report and GATE 2. AgentHub's server starts and watches the run for
you; you never call `agenthub-harness run` or `resume` yourself (they refuse inside a task).

## When to use it, and when not

- Use it for work that changes a project's code and deserves a spec, a plan, tests and reviews.
- Do not use it for a question, an explanation, a quick look at code, a research report or a small
  script: do those in your own session.
- A run of a ticket's task always runs on the **ticket's project**, from that project's base branch
  (`default_base` in `private/harness.yaml`). A ticket with "No project" has no run: AgentHub refuses it.
- A task without a ticket names the project with `--project <name>`; it must be registered.

## A project that is not ready

A project is ready when `private/agentmds/<project>/AGENTS.md` holds no `TODO(onboard)`. A project
just registered from the "New project" form is not ready; AgentHub refuses a run until it is.

1. Read the project's base clone (`data/orchestrator/worktrees/<project>/.base/` under the AgentHub
   repo; `agenthub harness status` and the refusal message give the paths) and fill
   `private/agentmds/<project>/AGENTS.md` and the project's `setup` list in `private/harness.yaml`,
   following the `onboard-project` skill (`skills/general/onboard-project/SKILL.md`) but without a chat.
2. Ask Pablo in your reply, as a numbered list, for what the repository cannot tell (how to run and
   test it, secrets, data rules). A repository AgentHub created holds only a README, so for such a
   project nearly everything is asked. End the turn `waiting_on_user`.
3. Commit and push the private folder (see `private/agents.md`), then start the run once no
   placeholder is left.

## Starting a run

1. Write the harness ticket from what Pablo wrote — his words, his examples, nothing added — to a
   file in your workspace, for example `harness_ticket.md`:

   ```markdown
   # <title>
   <the requested behaviour or the symptom, in Pablo's words>
   <the entry point, concrete examples, expected behaviour, out of scope, pasted references>
   ```

   Do not add frontmatter: AgentHub writes `project` itself, and the base branch is the project's.
2. Start it:

   ```bash
   agenthub harness start --feature <kebab-case-name> --ticket-file harness_ticket.md
   ```

   (`--project <name>` only for a task without a ticket.) The command prints the run id and its folder.
3. End your turn: tell Pablo in your message that run `<run id>` started and what it will do. The
   task stays running while the run works. `agenthub harness status` shows the runs of this task,
   their current step, the pending question and their token use.

## Gates: only Pablo releases them

At GATE 1 (spec and plan review) and GATE 2 (result review) AgentHub itself posts the gate's message
as your comment on the ticket and sets the task waiting on Pablo. You do nothing until he replies.

His reply reaches you with the gate's decision file and the gate's own instructions (the copy's
`plan` chat rules at GATE 1, `final-report` rules at GATE 2). Then:

1. Record his answer in the decision file: his words under `## Answer`, every edit he approved under
   `## Approved edits` (or `none`), and `answered: true` in the frontmatter. AgentHub also appends his
   reply verbatim when you resume.
2. If he asked for a change of the spec, the plan or the ticket copy, write it as the next version in
   the run folder (`spec_<feature>_<n>_v<k+1>.md`, a plan change also its `plan_short_…_v<k+1>.md`),
   never in place, and only what he approved.
3. `agenthub harness resume <run id>`. AgentHub refuses it until Pablo has replied after the gate.

## Other questions of the run

When the run pauses with a question that is not a gate (setup failed, the context could not be
reproduced, triage found a spec problem), AgentHub hands it to you as a notice with the decision file.

- Answer it yourself only when Pablo's ticket, comments or messages already answer it: record the
  answer as above and resume. The question and your answer stay in this task's chat.
- Otherwise ask Pablo in your reply, quoting the question verbatim, and end the turn `waiting_on_user`.
  When he answers, record and resume.

## When the run ends

AgentHub tells you with a notice: done (with the final report's path), failed or blocked (with the
error and the transcripts). Summarise for Pablo with links to the run files
(`$AGENTHUB_URL/runs/<run id>/files/<file name>`) and end the turn. Never merge, never open a pull
request: the run pushes its branch before GATE 2, and the pull request is Pablo's step.

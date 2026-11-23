---
name: build-context
description: Build the context file for a ticket before any spec or plan is written — locate the code path, read the data, reproduce the current behaviour read-only, and record run costs. Use when a run's step 4 invokes it, or when a user asks to "build context", "investigate this ticket" or "reproduce this issue" without changing code.
---

# Build context

Read-only investigation of a ticket that ends in `context_<feature>_<n>.md`. No code edits, no DB writes, no writes to the dev server. The only file this skill may write besides its output is the project's AGENTS.md in the harness (phase 3).

## Inputs

- the ticket (or its frozen copy in the run folder)
- the project repo (worktree) and its AGENTS.md
- output path and template, when given by the invocation

If the invocation names the inputs and the output path, run non-interactively and never ask a question. When called by hand, ask only for what is missing: the ticket, the output path.

## Phases, in order

1. **Parse the ticket.** Symptom or requested behaviour, user-visible entry point, concrete examples (a query, a filter, a record id). Quote them.
2. **Locate the code.** From the entry point inward: UI component, API route, agent graph node, prompt, DB query. Record file paths and the call chain. Read the code, do not guess from names.
3. **Read supporting material.** Project docs, recent git history on the touched files (`git log -p --follow` on the key files), existing evals and tests for the area, and the project AGENTS.md.
   The AGENTS.md **must** say how to run the project and how to test it (start the app, open the UIs, run evals, run checks). If something is missing or does not work:
   - gather it from the repo (README, launcher scripts, Makefiles, launch configs, CI files) and verify it by running it;
   - if it still cannot be established, set `status: not_reproduced` with a `question:` for the human (the orchestrator opens a chat), or ask directly when interactive;
   - then document what was learned in the project AGENTS.md, concisely and in the file's existing style. This is the only write outside the run folder, to the harness copy, never to a remote machine.
4. **Read the DB.** Through the read-only access AGENTS.md documents: confirm the records in the ticket's examples exist and what their fields hold. Never write. Record the queries.
5. **Reproduce.** Start the app as AGENTS.md documents and walk the scenario, or run the relevant eval suite when the ticket is about agent behaviour. Record exact inputs and what happened. Outcomes:
   - `reproduced`: observed vs expected, with inputs.
   - `not_reproduced`: what was tried; set `question:` to the one thing the human must clarify.
   - `not_applicable`: new feature with nothing to reproduce; describe the current behaviour of the area that will change.
   Budget about 15 minutes, then record what was found and move on. If the app will not start, say so and continue with static context; do not fix the environment.
6. **Write the context file** in the template shape (ticket summary, code, data, current behaviour, related evals/tests, risks and unknowns, commands run) with frontmatter `status`, `question`, `summary`, and end with the `## Run cost` section: project runs, wall time, LLM usage, source. Use what the project already exposes (LangSmith summaries, eval tables, app logs); add no instrumentation. A rough number is enough; `LLM usage: not available` with the reason is acceptable.

## Output

The context file at the given path. When interactive, also summarise the status and the open question in the chat.

---
name: plan
description: Turn a spec into an implementation plan — long plan with per-change detail plus a short plan for human review, including a self plan-review and a communicator pass. Also the chat skill at GATE 1, where it applies human-approved edits to the spec or plan as new versions. Use when a run's step 6 or GATE 1 invokes it, or a user asks to plan the implementation of a spec.
---

# Plan

The spec is authoritative; the plan says how. In a run the plan is regenerated on every loop iteration as a new version, so it is incremental: it plans against the code already in the worktree.

## Inputs

- the latest spec, the context (with the observed current behaviour), the ticket copy, the repo (worktree), read-only DB access per AGENTS.md
- the previous plan version when one exists
- output paths and templates (long and short), when given by the invocation

Non-interactive when the invocation names them; otherwise ask only for the spec and the output paths.

## Procedure

1. **Read the spec and the context.** Never re-derive requirements. Map every acceptance criterion to the code paths the context located. Do not redo the reproduction; targeted read-only checks for design questions are fine (grep, reading a table, running an existing unit test).
2. **Design.** Prefer the smallest incremental, modular change that satisfies every criterion. Reuse existing abstractions before adding any. Keep behaviour changes, refactors and cleanups separable.
3. **Write the long plan**: approach; architecture (modules created or modified, new or changed interfaces with inputs, outputs and callers, data flow from input to output); then one subsection per change in build order with files and functions, exact before/after behaviour, data or schema impact, and how it is verified; risks and rollback; open questions; suggestions outside the plan (bigger changes, kept out of the build).
4. **Plan review (self).** Check the plan is incremental and modular, that each change is verifiable against a criterion, that nothing in it is unrequested scope. Simplify where the review finds bloat; record what changed under `## Plan review`.
5. **Communicator pass.** Write the short plan: what we build, the architecture (modules, interfaces, data flow, each in a few lines), how it is verified, decisions to confirm, open questions. Under one page, plain language, for a human deciding at GATE 1.
6. If the spec is ambiguous or contradicts the code, write the question into `## Open questions` of both files instead of resolving it silently. Never edit the spec.

## Chat mode (GATE 1 and plan edits)

When loaded in an interactive session by the orchestrator: summarise spec and plan, the plan's architecture included (modules new and modified, changed interfaces, data flow), take the human's requests, propose each edit as a high-level summary (a few plain-language bullets on what changes and why, then one approve question; the diff only when the human asks for it), and apply it only on explicit approval, always as the **next version** of the file (`spec_<feature>_<n>_v<k>.md`, `plan_<feature>_<n>_v<k>.md` with its `plan_short_` twin). Never in place, never code or test cases. Record questions, answers and the full diff of every approved edit in the decision file named in the prompt with frontmatter `answered: true`. Write the decision file last, only once the human has explicitly said they are done: when the orchestrator opened the chat, it closes the chat by itself as soon as the reply that wrote `answered: true` ends (a chat that is still open a few seconds later is closed with /exit). Through AgentHub (`on_question: pause`, the default) there is no terminal chat: the human's reply reaches an AI user as a ticket comment, and that AI user applies these same rules (approved edits as new versions), records the answer under `## Answer` with `answered: true` in the decision file and then runs `agenthub harness resume <run-id>`.

## Output

`plan_<feature>_<n>[_v<k>].md` and `plan_short_<feature>_<n>[_v<k>].md` in the template shapes, frontmatter `version`, `previous_version`, `summary`. `## Run cost`: `project runs: none` unless something was run.

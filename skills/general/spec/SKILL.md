---
name: spec
description: Write a short, testable spec for a ticket from the ticket and its context file — goal, in/out of scope, acceptance criteria in a fixed WHEN/THEN shape, open questions. States what must be true when done, never how. Use when a run's step 5 invokes it or a user asks for a spec, acceptance criteria or a requirements write-up for a ticket.
---

# Spec

Product judgement only, no design. The spec is the contract with the human: it is frozen after GATE 1 and only changes through a human-approved new version.

## Inputs

- the ticket (frozen copy) and `context_<feature>_<n>.md`
- output path and template, when given by the invocation

Non-interactive when the invocation names them; otherwise ask only for the missing paths.

## Rules

- State **what** must be true when done, never **how**. No file names, no design choices, no implementation hints.
- Resolve an ambiguity in the ticket when the context makes the answer clear, and say so in one line. Otherwise list it under open questions; the human answers at GATE 1.
- Every acceptance criterion is observable through the UI, an API response, a DB state or an eval, so `testcase-builder` can turn it into one test case. Shape: `ACn. WHEN <event/condition> THEN the system SHALL <observable behaviour>`. One behaviour per criterion.
- Out of scope is explicit: name the adjacent things this ticket does not change.
- Target under two pages. If it cannot fit, write at the top that the ticket should be split and say along which line.
- Write in the context's vocabulary (entry points, record ids, suite names) so the criteria are concrete.

## Output

`spec_<feature>_<n>.md` in the template shape with frontmatter `acceptance_criteria` (count), `open_questions` (count) and `summary`. `## Run cost` says `project runs: none`; this skill never runs the project.

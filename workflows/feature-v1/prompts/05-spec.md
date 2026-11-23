Run ${run_id} · step 5 · spec. Non-interactive: every input is given here, do not ask questions.

Invoke the `spec` skill with these inputs.

Inputs:
${inputs}
- output template: ${templates}/spec.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Product judgement only, no design: state what must be true when done, never how.
- Resolve ambiguity in the ticket where the context makes the answer clear; otherwise list it under open questions (the human answers at GATE 1).
- Every acceptance criterion is observable through the UI, an API response, a DB state or an eval, in the shape `ACn. WHEN <event/condition> THEN the system SHALL <observable behaviour>`.
- Target under two pages. If it cannot fit, say in the spec that the ticket should be split.
- Fill the frontmatter: `acceptance_criteria` (count), `open_questions` (count), `summary` (one line).
- Do not run the project; `## Run cost` says `project runs: none`.

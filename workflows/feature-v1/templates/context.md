---
run_id: <feature>_<n>
step: "4"
skill: build-context
status: reproduced            # reproduced | not_reproduced | not_applicable
question:                     # only when not_reproduced: the one question for the human
summary: <one line: what the context established>
---
# <feature> — context

## Ticket summary
Symptom or requested behaviour, entry point, concrete example from the ticket.

## Code
Entry points and call chain: UI → API → agent graph / prompt → DB query, with file paths.

## Data
What the DB holds for the example (read-only), relevant tables and fields.

## Current behaviour
Observed, not inferred: exact inputs used, what happened, expected vs actual.
status: reproduced | not reproduced | not applicable (new feature; current behaviour of the area described instead)

## Related evals/tests
Suites and test files that cover the area.

## Risks and unknowns

## Commands run
Every command used, so plan and the human can rerun them.

## Run cost
- project runs:    <app session, eval suites, checks — or none>
- wall time:       <e.g. 11m 40s>
- LLM usage:       <approximate: calls, tokens or $, whichever the project exposes; or "not available" and why>
- source:          <LangSmith run summary, eval output, app log>

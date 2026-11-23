---
run_id: <feature>_<n>
step: "13"
skill: run-tests
version: <k>
passed: 0
failed: 0
blocked: 0
total: 0
subset: full                  # full | smoke
scope: code                   # this report covers runner: code cases only; ui cases are in testing_feedback_ui_…
summary: <one line, e.g. "8/10 pass; TC4 and TC7 fail on the empty-filter path">
---
# <feature> — test results (v<k>)

Report only: nothing was edited.

## Results
| case | AC | kind | result | notes |
|---|---|---|---|---|
| TC1 | AC1 | unit | pass | |
| TC4 | AC3 | unit | fail | expected X, observed Y |
| TC7 | AC5 | eval | blocked | suite needs the dev DB tunnel |

## Details per failing or blocked case
### TC4
- command / steps: …
- observed: …
- expected: …

## Deferred to run-tests-ui
| case | AC |
|---|---|
| TC5 | AC4 |

## Observations
Anything seen while testing that no case covers.

## Commands run

## Run cost
- project runs:    <unit test runner, eval suites, app session>
- wall time:       …
- LLM usage:       …
- source:          …

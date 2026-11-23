---
run_id: <feature>_<n>
step: "13b"
skill: run-tests-ui
version: <k>
passed: 0
failed: 0
blocked: 0
total: 0
subset: full                  # full | smoke
scope: ui                     # runner: ui cases only; code cases are in testing_feedback_…
browser: <playwright-mcp | claude-in-chrome | playwright | none>
summary: <one line, e.g. "2/3 UI cases pass; TC5 shows the old filter after reset">
---
# <feature> — UI test results (v<k>)

Report only: nothing was edited. App started as AGENTS.md documents; stopped at the end.

## Results
| case | AC | tag | result | evidence | notes |
|---|---|---|---|---|---|
| TC5 | AC4 | smoke | pass | ui_<feature>_<n>_iter<i>/TC5.png | |
| TC6 | AC4 | full | fail | ui_<feature>_<n>_iter<i>/TC6.png | expected X on screen, saw Y |
| TC8 | AC6 | full | blocked | | no browser tool available in this session |

## Details per failing or blocked case
### TC6
- app / URL: …
- steps performed: …
- observed: …
- expected: …

## UI writes made
None, or every record saved, added or reset through the UI (table, id, what changed).

## Observations
Anything seen on screen that no case covers (errors, slow paths, layout breakage).

## Run cost
- project runs:    <app sessions, messages sent to the app>
- wall time:       …
- LLM usage:       …
- source:          …

---
run_id: <feature>_<n>
step: "8"
skill: testcase-builder
version: 1
cases: <count>
cases_code: <count of runner: code>
cases_ui: <count of runner: ui>
summary: <one line>
---
# <feature> — test cases

Ephemeral: these cases live here, not in the project repo. 5–10 cases, each tied to one acceptance criterion. Every case names its runner: `code` (kind unit or eval) runs in step 13 `run-tests`; `ui` (kind ui) runs in step 13b `run-tests-ui`, in a browser.

## TC1 — <title>
- criterion: AC1
- runner: code | ui
- kind: unit | eval | ui
- tag: smoke | full
- preconditions: …
- steps / inputs: exact inputs, commands or UI steps (from AGENTS.md tooling)
- expected: the observable result that satisfies the criterion
- how to run: `<command>` (code) or app + port to start, then the clicks and inputs in order, and what must be on screen (ui)

## TC2 — <title>
…

## Coverage
| AC | cases | runners |
|---|---|---|
| AC1 | TC1 | code |

## Run cost
- project runs:    none

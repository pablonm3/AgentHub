---
run_id: <feature>_<n>
step: "16"
skill: final-report
version: 1
iterations: <count>
spec_revisions: <count>
summary: <one line>
---
# <feature> — final report

## Changes
What changed and where, grouped by concept, not by file. Commit range `origin/<base_branch>..<branch>`.

## Acceptance criteria
| AC | met | evidence |
|---|---|---|
| AC1 | yes | TC1 pass (testing_feedback v2) |

## How to test manually
Numbered steps the human can follow in the UI or with commands, with the inputs to use.

## Regression testing
From `regression_report_<feature>_<n>.md` (step 15b): baseline and modified commits, suites compared, repetitions, overall Δ accuracy and Δ mean case time, the regressed suites by name with one line each. Then the CSV, `runs/<feature>_<n>/regression_<feature>_<n>.csv`, and the server paths of the two result sets. When the step was skipped or found no suite to compare: one line saying so, and the suites the human should run by hand (names or exact commands from AGENTS.md).

## Open items
Review findings skipped, blocked test cases, suggestions deferred, anything the human should know before merging.

## Feedback
What slowed this run, which question a skill should have been able to answer itself, what the workflow should do differently. Read by `improve-harness`.

## Run cost
- project runs:    none

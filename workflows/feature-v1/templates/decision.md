---
run_id: <feature>_<n>
step: "14"                    # the step that raised it (14 triage, 4 build-context, 7/19 gates, 2 setup)
skill: triage
version: <k>
decision: done                # done | new_plan | spec_issue   (triage only)
question:                     # spec_issue / not_reproduced: the one question for the human
answered: false               # set to true in the chat once the human answered
summary: <one line>
---
# <feature> — decision v<k>

## Decision
`done` | `new_plan` | `spec_issue`, with the reasoning: which test cases failed and why, which review items remain, what the evidence says about where the problem lives (implementation, plan, or spec).

## Next plan
For `new_plan`: the file written (`plan_<feature>_<n>_v<k+1>.md`) and the two or three things it changes.

## Question
For `spec_issue` (or when the human must decide): the question, with the evidence that raised it.

## Answer
Filled in the chat: what the human decided.

## Approved edits
Filled in the chat: the diff of every approved edit (spec, plan or ticket copy, each written as a new version), or `none`.

## Run cost
- project runs:    none

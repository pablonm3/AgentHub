---
run_id: <feature>_<n>
step: "22"
skill: research-report
version: <k>
questions: <count>
supported: <count>              # verdict: supported
partly_supported: <count>       # verdict: partly supported
not_supported: <count>          # verdict: not supported
no_answer: <count>              # verdict: no answer
notebook: none                  # none | final_report_<feature>_<n>.ipynb, when the report needs one
summary: <one line: how many questions, how many supported, the main result>
---
# <feature> — final report

## Summary
The topic in one sentence, then the main results in three to five bullets, and what stayed open.

## Answers
One subsection per question id, in order.

### Q1. <question>
- answer: <the answer, or "No answer found: <why>">
- verdict: supported | partly supported | not supported | no answer — <reason: what the review checked and found>
- files: `<notebook or program in the run folder>`, `<its saved output>` | none: <reason>
- sources: <URL>, <URL>

## Not settled
Every question without a supported answer: what was tried, what failed (error, time limit, missing data), what would settle it.

## Review notes
What the review checked per file (exists, executed, no error behind a settled answer, quoted numbers present in the output, method fits the question, agreement with the sources) and every problem found.

## Files
Every file of the run behind this report, all in the run folder: the research context, the answers file, each notebook, program and saved output, and the report notebook when there is one.

## Feedback
What slowed this run, what a skill should have known, what the workflow should do differently. Read by `improve-harness`.

## Run cost
- project runs:    <checks re-run in a temp folder and the report notebook's execution; or none>

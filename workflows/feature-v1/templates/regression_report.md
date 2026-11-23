---
run_id: <feature>_<n>
step: "15b"
skill: regression-testing-report
version: <k>
status: ran                     # ran | not_applicable | failed
baseline: <sha7> (<base_branch>)
modified: <sha7> (<branch>)
repetitions: 3
suites: 0
regressions: 0                  # suites with acc_delta < 0
acc_delta_overall: 0.000        # modified minus baseline, fraction
time_delta_overall_s: 0.0       # modified minus baseline, mean case seconds
upload: ok                      # ok | failed | skipped
csv: runs/<feature>_<n>/regression_<feature>_<n>.csv
summary: <one line, e.g. "6 suites, no accuracy regression; power_user-entry +9 s per case">
---
# <feature> — regression testing report (v<k>)

Report only: nothing was edited.

## Runs
| side | ref | commit | run name | local results | server results |
|---|---|---|---|---|---|
| baseline | <base_branch> | <sha7> | baseline_<sha7>_<ts> | runs/<feature>_<n>/evals/details_… | /…/sava_evals/details_… |
| modified | <branch> | <sha7> | modified_<sha7>_<ts> | runs/<feature>_<n>/evals/details_… | /…/sava_evals/details_… |

Suites: <names>. Repetitions: <n> per case, both sides. Case rosters matched: yes/no (differences listed under caveats).

## Deltas per suite
Same numbers as the CSV (`regression_<feature>_<n>.csv`).

| suite | cases | acc baseline | acc modified | Δ acc | time baseline (s) | time modified (s) | Δ time (s) |
|---|---|---|---|---|---|---|---|
| … | | | | | | | |
| OVERALL | | | | | | | |

## Regressions
One block per suite with Δ acc < 0: the regressed cases (case key, user question, baseline behaviour, modified behaviour, failing evaluator and reason), classified as the project's comparison skill does. `none` when no suite regressed. Time-only regressions (Δ acc ≥ 0, Δ time clearly worse) listed in one line each.

## Caveats
Stale fixtures, unmatched cases, changed expectations between the refs, failed uploads, anything that weakens the comparison.

## Commands run
Exact commands for both sides and for the upload.

## Run cost
- project runs:    <baseline and modified eval runs: suites × cases × repetitions>
- wall time:       <…>
- LLM usage:       <from the project's summaries / LangSmith>
- source:          <files>

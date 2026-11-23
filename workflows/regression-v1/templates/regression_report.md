---
run_id: <feature>_<n>
step: "15b"
skill: regression-testing-report
version: <k>
status: ran                     # ran | not_applicable | failed
baseline: <sha7> (merge-base of <compare_branch> with <base_branch>)
modified: <sha7> (<compare_branch>, found at origin/<compare_branch> | local <compare_branch>)
repetitions: 3
workers: 4                      # concurrent eval cases per side
suites: 0                       # whole and case-restricted
regressions: 0                  # suites with acc_delta < 0
acc_delta_overall: 0.000        # modified minus baseline, fraction
time_delta_overall_s: 0.0       # modified minus baseline, mean case seconds
upload: ok                      # ok | failed | skipped
csv: <harness root>/runs/<feature>_<n>/regression_<feature>_<n>.csv   # absolute path, as given under Output
summary: <one line, e.g. "4 suites, no accuracy regression; power_user-entry +9 s per case">
---
# <feature> — regression testing report (v<k>)

Report only: nothing was edited.

## Selection
- base branch: <base_branch>; compare branch: <compare_branch>
- suites run whole: <names or none>
- suites restricted to cases: <suite: key, key; … or none>
- repetitions: <n> per case; workers: <n> per side; both sides identical
- case rosters matched: yes/no (differences listed under caveats)

## Runs
One row per eval command per side.

| side | commit | run name | suites | local table CSV | local details | server table CSV | server details | server summary |
|---|---|---|---|---|---|---|---|---|
| baseline | <sha7> | baseline_<sha7>_<ts> | … | sava/src/evals/results/table_… | runs/<feature>_<n>/evals/details_… | /…/sava_evals/table_… | /…/sava_evals/details_… | /…/sava_evals/summary_… |
| modified | <sha7> | modified_<sha7>_<ts> | … | | | | | |

Logs: <paths under runs/<feature>_<n>/evals/logs/>.

## Deltas per suite
Same numbers as the CSV (`regression_<feature>_<n>.csv`).

| suite | cases | acc baseline | acc modified | Δ acc | time baseline (s) | time modified (s) | Δ time (s) |
|---|---|---|---|---|---|---|---|
| … | | | | | | | |
| OVERALL | | | | | | | |

## Regressions
One block per suite with Δ acc < 0: the regressed cases (case key, user question, baseline behaviour, modified behaviour, failing evaluator and reason), classified as the project's comparison skill does. `none` when no suite regressed. Time-only changes are left to the final report's timing summary.

## Caveats
Stale fixtures, unmatched or changed cases between the refs, changed expectations, failed uploads, anything that weakens the comparison.

## Commands run
Exact commands for both sides, the checks before running, and the upload.

## Run cost
- project runs:    <every eval run of both sides: suites × cases × repetitions>
- wall time:       <…>
- LLM usage:       <from the project's summaries / LangSmith>
- source:          <files>

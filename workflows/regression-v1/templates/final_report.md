---
run_id: <feature>_<n>
step: "16"
skill: regression-final-report
version: <k>
status: ran                     # the regression report's status: ran | not_applicable | failed
baseline: <sha7> (<base_branch>)
modified: <sha7> (<compare_branch>)
acc_delta_overall: 0.000        # fraction, modified minus baseline
time_delta_overall_s: 0.0       # mean case seconds, modified minus baseline
time_delta_overall_pct: 0.0     # time_delta_overall_s / baseline overall time × 100
regressions: 0                  # suites with Δ acc < 0
csv: <harness root>/runs/<feature>_<n>/regression_<feature>_<n>.csv   # absolute path, as listed in the inputs
summary: <one line, e.g. "4 suites: accuracy +0.012, no suite regressed; mean case time +3.1 s (+8.4%)">
---
# <feature> — regression final report

## Compared
- base: `<base_branch>` at <sha7>, the commit `<compare_branch>` forked from
- new: `<compare_branch>` at <sha7>, found at <origin/… | local branch>
- suites run whole: <names>; suites restricted to cases: <suite: keys>
- repetitions: <n> per case; workers: <n> per side

## Accuracy
Overall Δ accuracy (base → new). Then one line per regressed suite: name, Δ accuracy, regressed case keys. `No suite regressed.` when none.

## Timing
- overall mean case time: <base> s → <new> s, <±Δ> s (<±%>)
- suites slower: <n>; faster: <n>; unchanged: <n>
- largest slowdowns: <suite +Δ s (+%)>, … (up to three)
- largest speed-ups: <suite −Δ s (−%)>, … (up to three)
- workers per side: <n>, both sides; times are comparable only between runs with the same value

## Deltas per suite
Copied from the CSV, except its `repetitions` column, which is stated under Compared; Δ time % is base-relative.

| suite | cases | acc base | acc new | Δ acc | time base (s) | time new (s) | Δ time (s) | Δ time % |
|---|---|---|---|---|---|---|---|---|
| … | | | | | | | | |
| OVERALL | | | | | | | | |

## Files
Local paths are absolute, as listed in the inputs.

- delta CSV (local): `<harness root>/runs/<feature>_<n>/regression_<feature>_<n>.csv`
- regression report (local): `<harness root>/runs/<feature>_<n>/regression_report_<feature>_<n>.md`
- server, base side: table CSV `<path>`, details `<path>`, summary `<path>` (one line per eval run)
- server, new side: table CSV `<path>`, details `<path>`, summary `<path>` (one line per eval run)

## Cleanup
LangSmith scratch datasets of `<run_id>`: <deleted> deleted, <remaining> remaining (status <…>).

## Caveats
From the regression report: unmatched or changed cases, stale fixtures, failed uploads; plus anything that does not agree between the CSV and the report.

## Feedback
What slowed this run, what a skill should have known, what the workflow should do differently. Read by `improve-harness`.

## Run cost
- project runs:    none

---
name: regression-testing-report
description: Run the project's eval regression between two commits of a run — by default its base commit and its branch head — with the same suites, cases, repetitions and workers on both sides, upload both result sets to the project's shared results directory, and write a CSV of accuracy and mean-time deltas per suite and overall, plus a short report with the regressed cases. Report only — never edits code, tests, config or datasets. Use when a run's step 15b invokes it or a user asks to compare a branch against its base with a delta CSV.
---

# Regression testing report

Runs once per run. In a build workflow it comes after the last build and the comment cleanup, before the final report; in a regression-only workflow the ticket names what to compare and it is the main step. It answers one question: did the branch make any eval suite worse, in accuracy or in time, and where are the raw results. Project know-how (which suites exist, how to run two refs, how case filters apply, where numbers are, where results are shared) comes from the project AGENTS.md, never from this skill.

## Inputs

- the worktree, the baseline and modified commits (or how to resolve them), the repetitions per case
- the selection, when the invocation gives one: suites to run whole and suites restricted to named case keys; and the workers (concurrent cases) per side
- otherwise the latest testing file and testing feedback (which eval suites this run touched), the latest spec
- the project AGENTS.md: eval suites, the two-ref regression procedure (a project skill when it names one), the per-suite metrics files, the shared results directory and the copy command
- the run's eval results directory; output paths and template when given

Non-interactive when the invocation names them.

## Procedure

1. **Suites.** When the invocation gives the selection, use exactly that, nothing added. Otherwise collect the eval suites of the testing file's `eval` cases, the suites the testing feedback ran, and any suite AGENTS.md marks as always part of regression. No suite → write the report with `status: not_applicable` and the CSV with its header only, and stop.
2. **Refs.** Resolve baseline and modified to commits and state both SHAs. Never check anything out in the run's worktree. With a selection from the invocation, check before running anything that every named suite and case key exists on both refs; one that does not makes the report `status: failed` naming it, with a header-only CSV and no eval run.
3. **Run both sides** with the project's two-ref procedure as AGENTS.md documents it: isolated checkouts, identical suites, case filters, repetitions and workers (the procedure's default when the invocation gives none), results into the run's eval directory, unique run names (`baseline_<sha7>_<ts>`, `modified_<sha7>_<ts>`, one shared timestamp). When the project's runner applies a case filter to every suite of one command (AGENTS.md says so), run the whole suites in one command and each case-restricted suite in its own, one after another on each side, with `_<suite>` appended to the run name. Scratch datasets only; never flags that push, sync or recreate shared data. Do not fix the environment; a side that cannot finish makes the report `status: failed` with the log paths, and both output files are still written.
4. **Metrics.** Per suite and per side, accuracy and mean case time from the project's result files (AGENTS.md says which file and which columns), merged into one row per suite when a side ran several commands. Deltas are modified minus baseline. `OVERALL` weights suites equally, the way the project's own table does. A suite with a negative accuracy delta is a regression: list its regressed cases (case key, question, baseline behaviour, modified behaviour, failing evaluator and reason), classified as the project's comparison skill does when it has one.
5. **Upload.** Copy the result files of both runs (summaries, details, per-suite tables) to the shared results directory AGENTS.md names, with a copy that never overwrites or deletes. Record the server path of every file. Retry once; then `upload: failed` and local paths in the CSV.
6. **Write** the CSV first, then the report.

## Output

- `regression_<feature>_<n>[_v<k>].csv`, columns in this order: `suite,cases,repetitions,acc_baseline,acc_modified,acc_delta,time_baseline_s,time_modified_s,time_delta_s,baseline_report,modified_report`. One row per suite, then `OVERALL`. `repetitions` is the repetitions per case the runs of that row used, the same on both sides and on `OVERALL`. Accuracies as fractions, times in seconds, report columns with the server paths of the details files (local paths when the upload failed). Header only when not applicable.
- `regression_report_<feature>_<n>[_v<k>].md` in the template shape: frontmatter `status`, `baseline`, `modified`, `repetitions`, `suites`, `regressions`, `acc_delta_overall`, `time_delta_overall_s`, `upload`, `csv`, `summary`, plus `workers` when the invocation set it; the runs table with local and server paths, the deltas table, the regressions, caveats, commands run. End with `## Run cost` for both eval runs, with the source of the numbers.

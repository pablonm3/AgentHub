---
name: regression-final-report
description: Write the final report of a regression-only harness run from its regression report, delta CSV and cleanup report — what was compared, the accuracy result, a timing summary, the per-suite delta table, the local delta CSV and the server paths of every result file, cleanup, caveats, workflow feedback. Read-only — copies numbers and paths, never re-runs or recomputes them. Use when a regression run's step 16 invokes it or a user asks to summarise a regression run.
---

# Regression final report

The report the human reads when a regression-only run ends. It has no build, spec or diff to describe: it turns the regression report and its CSV into one page that says what was compared, whether accuracy dropped, how timing moved, and where every file is.

## Inputs

- the ticket copy (branches, selection), the latest regression report and delta CSV, the latest cleanup report
- output path and template, when given by the invocation

Non-interactive when the invocation names them.

## Procedure

1. **Read** the three files. The regression report's `status` decides the shape: `ran` fills every section; `failed` or `not_applicable` opens the report with that status, its reason and the log paths, and fills only what exists.
2. **Compared:** both branches with their commits and where each ref was found, the suites run whole, the suites restricted to case keys, repetitions, workers per side. All from the regression report.
3. **Accuracy:** overall Δ from the CSV's `OVERALL` row; one line per suite with Δ accuracy < 0, with its regressed case keys from the report. Say so in one line when none regressed.
4. **Timing**, a summary from the CSV's time columns:
   - overall mean case time per side and the change, in seconds and in percent of the base time (one decimal);
   - how many suites got slower (Δ > 0), faster (Δ < 0), unchanged;
   - the three largest slowdowns and the three largest speed-ups by Δ seconds, each with its percent (fewer when there are fewer suites);
   - the workers per side, since times compare only between runs with the same value.

   Timing is reported as numbers; a time change is never called a regression.
5. **Deltas per suite:** the CSV rows as a table, plus a base-relative Δ time % column.
6. **Files:** the local delta CSV and the local regression report, each by absolute path (the paths the invocation gave, never shortened to relative ones), and for each side and each eval run the server paths of its table CSV, details JSON and summary JSON, copied from the regression report's runs table. When the upload failed, say so and give the local paths.
7. **Cleanup:** the cleanup report's status, deleted and remaining counts.
8. **Caveats:** the regression report's caveats, plus any number that does not agree between the CSV and the report (named, not corrected).
9. **Feedback:** what slowed the run, what a skill should have known, what the workflow should change; read later by `improve-harness`.

Percent changes are the only figures this skill computes. It never re-runs an eval, never re-reads result files to recompute a number, and never edits any input.

## Output

`final_report_<feature>_<n>[_v<k>].md` in the template shape, frontmatter `status`, `baseline`, `modified`, `acc_delta_overall`, `time_delta_overall_s`, `time_delta_overall_pct`, `regressions`, `csv` (absolute path of the delta CSV), `summary` (one line with Δ accuracy and Δ time). `## Run cost`: `project runs: none`.

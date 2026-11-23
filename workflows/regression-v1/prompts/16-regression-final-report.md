Run ${run_id} · step 16 · regression-final-report. Non-interactive: every input is given here, do not ask questions.

Invoke the `regression-final-report` skill with these inputs.

Inputs (latest version of each; for the CSV, the highest `_v<k>` listed):
${inputs}
- output template: ${templates}/final_report.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Read-only: copy numbers and paths from the regression report and the CSV. Never re-run an eval, re-read result files to recompute, or edit any input. The only figures you compute are the percent time changes.
- Sections in order: Compared, Accuracy, Timing, Deltas per suite, Files, Cleanup, Caveats, Feedback, Run cost.
- Timing is a summary: overall mean case time per side with the change in seconds and percent, how many suites got slower, faster or stayed equal, the three largest slowdowns and the three largest speed-ups (fewer when there are fewer suites), and the workers per side. Report timing as numbers; never call a time change a regression.
- Files: the local delta CSV and the local regression report, each by its absolute path exactly as listed under Inputs (never relative to the harness root or the worktree), and for each side and each eval run the server paths of its table CSV, details JSON and summary JSON. When the upload failed, say so and give the local paths instead. Any other local path the report names is absolute too.
- When step 15b ended `failed` or `not_applicable`, say so first with its reason and log paths, fill only what exists, and still report the cleanup.
- Frontmatter: `status` (the regression report's status), `baseline`, `modified`, `acc_delta_overall`, `time_delta_overall_s`, `time_delta_overall_pct`, `regressions`, `csv` (the absolute path of the delta CSV), `summary` (one line with Δ accuracy and Δ time).
- `## Run cost`: `project runs: none`.

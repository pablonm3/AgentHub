Run ${run_id} · step 15b · regression-testing-report. Non-interactive: every input is given here, do not ask questions.

Invoke the `regression-testing-report` skill with these inputs.

Inputs:
${inputs}
- project instructions (AGENTS.md: eval suites, the two-ref regression procedure, where the per-suite numbers are, the results directory on the server and how to copy files there): ${agentsmd}
- worktree: ${worktree} (branch ${branch}, based on ${base_branch})
- baseline: the commit `git merge-base origin/${base_branch} HEAD` resolves to (fall back to `${base_branch}` when the remote ref does not resolve); modified: `HEAD` of ${branch}
- repetitions per case, both sides: ${def_regression_repetitions}
- eval results directory of this run: ${run_dir}/evals
- output template: ${templates}/regression_report.md

Output (write exactly these paths, both of them always):
${outputs}

Rules for this run:
- Suites: every eval suite this run's test cases touched (the `eval` cases of the testing file and the suites the testing feedback ran) plus any suite AGENTS.md marks as always part of regression. Same suites, same case filters, same repetitions on both sides. With no suite to compare, write the report with `status: not_applicable` and the CSV with its header line only.
- Run the two refs with the project's regression procedure exactly as AGENTS.md documents it, results into ${run_dir}/evals, run names `baseline_<sha7>_<ts>` and `modified_<sha7>_<ts>` with one shared timestamp. Scratch datasets only; never the dataset flags AGENTS.md forbids inside a run.
- Upload the result files of both runs to the server results directory AGENTS.md names, without overwriting anything there, and record the server path of each file. One retry on failure, then `upload: failed` and local paths in the CSV.
- CSV columns, in this order: `suite,cases,repetitions,acc_baseline,acc_modified,acc_delta,time_baseline_s,time_modified_s,time_delta_s,baseline_report,modified_report`. One row per suite, then one `OVERALL` row. `repetitions` is the repetitions per case the runs of that row used, the same on both sides; `OVERALL` carries the run's value. Accuracies as fractions, times as mean case seconds, deltas are modified minus baseline, the report columns hold the server paths of the two details files.
- Report only: no code, test, config or dataset edits. Do not fix the environment; a comparison that cannot complete is `status: failed` with the log paths, and both files are still written.
- Frontmatter: `status`, `baseline`, `modified`, `repetitions`, `suites`, `regressions`, `acc_delta_overall`, `time_delta_overall_s`, `upload`, `csv`, `summary`.
- End with `## Run cost` covering both eval runs, with the source of the numbers.

Run ${run_id} · step 15b · regression-testing-report. Non-interactive: every input is given here, do not ask questions.

Invoke the `regression-testing-report` skill with these inputs. This is a regression-only run (workflow ${workflow}): there is no spec, plan, testing file or code change. The ticket names what to compare.

Inputs:
${inputs}
- selection, from the ticket's frontmatter: `compare_branch` (the new branch), `base_branch`, `suites` (suites run whole), `cases` (suite → the case keys to run), `repetitions` and `workers` (both optional)
- project instructions (AGENTS.md: eval suites, the two-ref regression procedure, how case filters apply, where the per-suite numbers are, the results directory on the server and how to copy files there): ${agentsmd}
- worktree: ${worktree}, on branch ${branch} at ${base_branch}, with `.env` and dependencies from the project setup. Run the project commands from it; never check anything out in it.
- eval results directory of this run: ${run_dir}/evals
- output template: ${templates}/regression_report.md

Output (write exactly these paths, both of them always):
${outputs}

Rules for this run:
- Refs. Modified is the tip of `compare_branch`: `origin/<compare_branch>` when it resolves in the worktree (step 2 fetched it), otherwise the local branch `<compare_branch>` (a harness run branch is on the remote only once its run reached the push step; before that it exists only locally). Baseline is the commit `compare_branch` forked from: `git merge-base origin/${base_branch} <modified commit>`, or with the local `${base_branch}` when the remote ref does not resolve. Record both SHAs and the ref each was found at.
- Selection. Exactly the suites in `suites` and the case keys in `cases`, nothing added: no suite from a testing file or from AGENTS.md.
- Check before any eval runs: both refs resolve; at least one suite or case is named; no suite appears in both `suites` and `cases`; every named suite exists on both refs; every named case key exists in its suite on both refs. The first failure ends the step: `status: failed` naming what did not resolve, the CSV with its header line only, no eval run.
- Repetitions per case: the ticket's `repetitions`, otherwise ${def_regression_repetitions}. Workers (concurrent cases per side, the eval runner's concurrency): the ticket's `workers`, otherwise ${def_regression_workers}. Same values on both sides; state both in the report.
- Run both sides with the project's regression procedure exactly as AGENTS.md documents it: scratch owner `${run_id}`, results into ${run_dir}/evals, one shared timestamp, run names `baseline_<sha7>_<ts>` and `modified_<sha7>_<ts>`. When AGENTS.md says a case filter applies to every suite of one command, run the whole suites in one command and each case-restricted suite in its own command (run name with `_<suite>` appended), one after another on each side so the workers per side hold, the two sides in parallel. Scratch datasets only; never the dataset flags AGENTS.md forbids inside a run.
- A suite whose cases or inputs differ between the refs runs as each ref defines it: list the unmatched and changed case keys under caveats. Never drop or invent cases.
- Upload the result files of every eval run on both sides (per-suite table CSV, details JSON, summary JSON) to the server results directory AGENTS.md names, without overwriting anything there, and record the server path of each file. One retry on failure, then `upload: failed` and local paths in the CSV.
- CSV columns, in this order: `suite,cases,repetitions,acc_baseline,acc_modified,acc_delta,time_baseline_s,time_modified_s,time_delta_s,baseline_report,modified_report`. One row per suite, whole and case-restricted alike, then one `OVERALL` row with suites weighted equally. `repetitions` is the repetitions per case the runs of that row used, the same on both sides; `OVERALL` carries the run's value. Accuracies as fractions, times as mean case seconds, deltas are modified minus baseline. The report columns hold the server path of the details file of the eval run that holds that suite; on `OVERALL`, every details path of that side joined with `;`.
- The runs table of the report has one row per eval command per side, with the local and server paths of its table CSV, details JSON and summary JSON. Step 16 copies the paths from there.
- Report only: no code, test, config or dataset edits. Do not fix the environment; a comparison that cannot complete is `status: failed` with the log paths, and both files are still written.
- Frontmatter: `status`, `baseline`, `modified`, `repetitions`, `workers`, `suites`, `regressions`, `acc_delta_overall`, `time_delta_overall_s`, `upload`, `csv` (the absolute path of the CSV, as listed under Output), `summary`.
- End with `## Run cost` covering every eval run of both sides, with the source of the numbers.

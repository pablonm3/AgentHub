Run ${run_id} · step 10 · code-review (iteration ${iteration}, incremental). Non-interactive: every input is given here, do not ask questions.

This branch was already reviewed at commit `${since_commit}`; that report is the `previous_report` input below. Since then ${new_commits} commit(s) changed ${new_lines} line(s), out of ${branch_lines} for the whole branch. This execution reviews those commits and brings the earlier report up to date. It does not review the rest of the branch again.

Invoke the `code-review` skill with these inputs. Both of its questions are answered here, so do not ask them:

1. Comparison ref: the commit `${since_commit}`. It is an ancestor of HEAD, so the skill's merge-base diff `${since_commit}...HEAD` holds exactly the commits made since the earlier review. The review target is HEAD of ${branch} in ${worktree}.
2. Feature context: the spec below. Its acceptance criteria are the requirements checklist.

Inputs:
${inputs}
- project instructions (AGENTS.md, including unit-test conventions): ${agentsmd}
- output template: ${templates}/review.md

Output (write exactly this path):
${outputs}

Scope, for the coordinator, every specialist and the summary agent:
- New findings come from the diff `${since_commit}...HEAD` and from the code those commits call or are called by. The rest of the branch was reviewed in the earlier report: do not search it for new findings, and do not repeat the earlier report's checks on it (test runs, mutation checks, browser scenarios, documentation lookups). A defect you notice there while reading around the new commits is still reported.
- Give each specialist the earlier findings of its section along with the diff. Spawn the frontend-compatibility specialist only when the new commits change browser-delivered code.
- For each finding of the earlier report, read the code it names at HEAD and decide whether it is fixed or still open. Re-run a test or a scenario for it only when the new commits touch that code.

The report replaces the earlier one for the steps that follow, which read only the newest review, so it must be complete on its own:
- `Comparison:` line: `${since_commit_short}...HEAD` at the HEAD commit, marked incremental, naming the earlier report file.
- Findings: the new findings, plus every earlier finding that is still open, copied with its severity, evidence and remediation (location updated when lines moved) and one more bullet, `- carried: from <earlier report file name>`. The skill's rule to drop issues the diff did not introduce does not remove these: for that rule the diff is the whole branch, `origin/${base_branch}...HEAD`. Sort new and carried findings together by severity.
- Earlier findings that are fixed: leave them out of Findings and list them in Review notes under `Fixed since <earlier report file name>`, one line each with the commit that fixed it.
- Requirements coverage: the full table. Re-check a criterion when the new commits can affect it, or when the earlier report had it as not satisfied or not verifiable; copy the other rows with their evidence.
- Test assessment and Frontend compatibility: what the new commits add or change, then what the earlier report said that still stands, shortened. Compatibility rows of features the new commits did not touch are copied as they are.
- Frontmatter `counts` count every finding in the file, new and carried. `summary`: one line that also says how many findings are new, how many are carried and how many earlier ones were fixed.

Rules for this run:
- Review only. Do not edit the implementation.
- Report every severity (critical, high, medium, low); what gets applied is decided later by thresholds, not by you.
- Save the skill's final report into the output file in the template's shape: frontmatter with `counts` per severity and a one-line `summary`, then one `### [SEVERITY] title` heading per finding, then the Requirements coverage, Test assessment, Frontend compatibility and Review notes sections.
- `## Run cost`: `project runs: none` unless you ran the app or evals to verify a finding.

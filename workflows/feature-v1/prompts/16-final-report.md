Run ${run_id} · step 16 · final-report. Non-interactive: every input is given here, do not ask questions.

Invoke the `final-report` skill with these inputs.

Inputs (latest version of every artifact of this run):
${inputs}
- diff: `origin/${base_branch}...HEAD` in ${worktree} (branch ${branch})
- regression deltas, when step 15b wrote them: ${run_dir}/regression_${feature}_${n}.csv (detail in regression_report_${feature}_${n}.md among the inputs)
- project instructions (AGENTS.md, for the regression/eval commands): ${agentsmd}
- output template: ${templates}/final_report.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Concise. Sections in order: changes (what and where), acceptance criteria met (one line per ACn with the evidence: test case id, review item or observation), how to test manually (steps the human can follow), regression testing (one short paragraph from the regression report: baseline and modified commits, suites compared, overall Δ accuracy and Δ mean case time, the regressed suites by name, then the CSV path and the server paths of the two result sets; when step 15b was skipped or not applicable, one line saying so and which suites the human should run by hand), open items, and a short `## Feedback` section on the workflow itself (what slowed the run, what a skill should have known).
- Read-only: no code, spec or plan edits.
- Frontmatter: `iterations`, `spec_revisions`, `summary`.
- `## Run cost`: `project runs: none`.

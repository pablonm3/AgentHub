Run ${run_id} · step 12 · apply-reviews (iteration ${iteration}). Non-interactive: every input is given here, do not ask questions.

Invoke the `apply-reviews` skill with these inputs.

Inputs:
${inputs}
- worktree (branch ${branch}): ${worktree}
- project instructions (AGENTS.md): ${agentsmd}
- thresholds for this run: code-review items at `${def_review_severity_threshold}` and above; readability items at `${def_readability_severity_threshold}` and above
- output template: ${templates}/reviews_applied.md

Outputs:
- commits on ${branch} (one per report is fine; none if nothing meets the threshold)
${outputs}

Rules for this run:
- Apply only findings at or above the threshold for their report; list everything else as skipped with the reason (below threshold, disagreed, not reproducible, already fixed).
- A finding you disagree with after checking the code is skipped with a one-line justification, never silently dropped.
- Keep the edits to what the finding asks; no drive-by refactors. Run the relevant unit tests when they are cheap.
- Frontmatter: `applied: {review: n, readability: n}`, `skipped: {review: n, readability: n}`, `summary`.
- Commit messages reference `Run: ${run_id}` and the report file name. Never push.
- `## Run cost`: `project runs: none` unless you ran the app or evals.

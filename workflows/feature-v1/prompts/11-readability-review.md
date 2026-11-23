Run ${run_id} · step 11 · readability-review (iteration ${iteration}). Non-interactive: every input is given here, do not ask questions.

Invoke the `readability-review` skill with these inputs.

- Diff: `origin/${base_branch}...HEAD` in ${worktree} (merge-base diff; fall back to `${base_branch}` if the remote ref does not resolve).

Inputs:
${inputs}
- project instructions (AGENTS.md): ${agentsmd}
- output template: ${templates}/readability.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Review only. Do not edit code.
- Judge cognitive load, not correctness: HIGH = very hard to understand; MEDIUM = understandable with effort; LOW = minor. Every finding carries one concrete suggestion (naming, extraction, flattening, removing indirection, a comment only where intent is not obvious).
- Report every severity; thresholds are applied later.
- Frontmatter: `counts` per severity, `summary`. One `### [SEVERITY] title` heading per finding.
- `## Run cost`: `project runs: none`.

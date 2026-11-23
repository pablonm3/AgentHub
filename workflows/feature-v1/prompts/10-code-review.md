Run ${run_id} · step 10 · code-review (iteration ${iteration}). Non-interactive: every input is given here, do not ask questions.

Invoke the `code-review` skill with these inputs. Both of its questions are answered here, so do not ask them:

1. Comparison ref: `origin/${base_branch}` (fall back to `${base_branch}` if the remote ref does not resolve). The review target is HEAD of ${branch} in ${worktree}.
2. Feature context: the spec below. Turn its acceptance criteria into the requirements checklist and report whether the diff satisfies each.

Inputs:
${inputs}
- project instructions (AGENTS.md, including unit-test conventions): ${agentsmd}
- output template: ${templates}/review.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Review only. Do not edit the implementation.
- Report every severity (critical, high, medium, low); what gets applied is decided later by thresholds, not by you.
- Save the skill's final report into the output file in the template's shape: frontmatter with `counts` per severity and a one-line `summary`, then one `### [SEVERITY] title` heading per finding, then the Requirements coverage, Test assessment, Frontend compatibility and Review notes sections.
- `## Run cost`: `project runs: none` unless you ran the app or evals to verify a finding.

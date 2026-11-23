Run ${run_id} · step 13 · run-tests (iteration ${iteration}). Non-interactive: every input is given here, do not ask questions.

Invoke the `run-tests` skill with these inputs.

Inputs:
${inputs}
- project instructions (AGENTS.md: how to run unit tests, evals and the app): ${agentsmd}
- worktree (branch ${branch}): ${worktree}
- subset rule: `test_subset_on_retry: ${def_test_subset_on_retry}`; this is iteration ${iteration} (run only `smoke`-tagged cases when the rule is `smoke` and the iteration is 2 or more)
- output template: ${templates}/testing_feedback.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Report only. Never edit code, tests or config, however trivial the fix; every fix goes through triage and build.
- Run only the cases with `runner: code` (kind `unit` or `eval`), each the way its kind requires (unit test runner, eval runner) using only what AGENTS.md documents. Cases with `runner: ui` belong to step 13b (`run-tests-ui`): do not run them; list them under `## Deferred to run-tests-ui` and leave them out of `passed`/`failed`/`blocked`/`total`. Record exact commands, observed output and pass/fail per case, plus observations that are not covered by a case.
- If a case cannot be run (environment, missing tooling), mark it `blocked` with the reason; do not fix the environment.
- Frontmatter: `passed`, `failed`, `blocked`, `total`, `scope: code`, `summary`.
- End with `## Run cost` for everything you ran (eval suites, app sessions), with the source of the numbers.

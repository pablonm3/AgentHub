Run ${run_id} · step 8 · testcase-builder. Non-interactive: every input is given here, do not ask questions.

Invoke the `testcase-builder` skill with these inputs.

Inputs:
${inputs}
- project instructions (AGENTS.md): ${agentsmd}
- worktree: ${worktree}
- output template: ${templates}/testing.md

Output (write exactly this path):
${outputs}

Rules for this run:
- 5 to 10 ephemeral test cases, each tied to one acceptance criterion by id (ACn). Ephemeral: they live in this file, not in the project repo. Never write tests into the worktree.
- Each case states its kind (`unit`, `eval` or `ui`), chosen by what the criterion requires, its exact inputs and expected observation, and how to run it with the project tooling documented in AGENTS.md.
- Classify every case with `runner`: `code` for kind `unit` or `eval` (step 13 `run-tests` executes it with the project's test or eval runner), `ui` for kind `ui` (step 13b `run-tests-ui` executes it in a browser). A `ui` case names the app and port to start (from AGENTS.md), the exact clicks and inputs in order, and what must be visible on screen when it passes; it never relies on reading code or logs.
- Tag each case `smoke` or `full`; `smoke` is the minimal set that catches a broken build (used on retries when `test_subset_on_retry: smoke`).
- Fill the frontmatter: `cases` (count), `cases_code`, `cases_ui`, `summary`.
- `## Run cost`: `project runs: none`.

Run ${run_id} · step 15c · langsmith-cleanup. Non-interactive: every input is given here, do not ask questions.

Invoke the `langsmith-cleanup` skill with these inputs.

Inputs:
${inputs}
- project instructions (AGENTS.md: how eval scratch datasets are named, the commands that list and delete them): ${agentsmd}
- worktree: ${worktree}
- scratch owner of this run: `${run_id}` (every eval run of this harness run, in run-tests and in regression-testing-report, used it)
- output template: ${templates}/langsmith_cleanup.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Delete only the temporary eval datasets whose owner is `${run_id}`, with the project's own command for that and nothing else: no other owner, no canonical or shared dataset, no result files, nothing on the server.
- List before deleting and again after; the report records both lists and the exact commands.
- If the project has no scratch dataset mechanism, or `${run_id}` owns nothing, write the report with `deleted: 0` and say so; do not improvise another way to clean up.
- A failed deletion is reported with the command output (`status: failed`); do not fix credentials or the environment.
- Frontmatter: `status` (done | failed | not_applicable), `owner`, `deleted`, `remaining`, `summary`.
- `## Run cost`: `project runs: none` (listing and deleting datasets runs no evals).

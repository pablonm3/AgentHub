Run ${run_id} · step 13b · run-tests-ui (iteration ${iteration}). Non-interactive: every input is given here, do not ask questions.

Invoke the `run-tests-ui` skill with these inputs.

Inputs:
${inputs}
- project instructions (AGENTS.md: how to start the app and its UIs, ports, what UI writes are allowed): ${agentsmd}
- worktree (branch ${branch}): ${worktree}
- subset rule: `test_subset_on_retry: ${def_test_subset_on_retry}`; this is iteration ${iteration} (run only `smoke`-tagged cases when the rule is `smoke` and the iteration is 2 or more)
- evidence folder for screenshots: ${run_dir}/ui_${feature}_${n}_iter${iteration}/
- output template: ${templates}/testing_feedback_ui.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Run only the cases with `runner: ui`. Code cases were run by step 13; do not repeat them.
- Report only. Never edit code, tests or config, however trivial the fix; every fix goes through triage and build.
- Start the app exactly as AGENTS.md documents, drive it in a browser with the browser tools this session has (the Playwright MCP tools `mcp__playwright__*`, which this step is given; load them with ToolSearch if they are deferred), follow each case's steps literally and compare what is on screen with the expected observation. Save one screenshot per case into the evidence folder, passing the absolute path `<evidence folder>/<case id>.png` as the screenshot filename, and reference it in the report. Never install tooling or change the environment: a case that cannot be driven is `blocked` with the reason.
- UI writes (saving, adding, resetting records) only when the case requires it and AGENTS.md allows it; list every write made.
- If the testing file has no `runner: ui` case, write the report with `total: 0` and summary `no UI cases` and stop.
- Stop the app and the browser session when done.
- Frontmatter: `passed`, `failed`, `blocked`, `total`, `scope: ui`, `browser` (the tool used, or `none`), `summary`.
- End with `## Run cost` for everything you ran (app sessions, LLM calls the app made), with the source of the numbers.

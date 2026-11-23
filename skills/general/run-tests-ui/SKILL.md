---
name: run-tests-ui
description: Run the `runner: ui` test cases of a run in a real browser — start the app as the project AGENTS.md documents, perform each case's clicks and inputs, compare the screen with the expected observation, save a screenshot per case — and write a pass/fail report with evidence and project run cost. Report only — never edits code, never installs tooling. Use when a run's step 13b invokes it or a user asks to execute the UI cases of a testing file against a worktree.
---

# Run UI tests

Executes the `runner: ui` cases of `testing_<feature>_<n>.md` in a browser and reports. Code cases (`runner: code`) are run by `run-tests` (step 13), not here. Every fix, however small, goes through triage and build; this skill changes nothing in the worktree.

## Inputs

- the latest testing file, the latest spec, the worktree, the project AGENTS.md (how to start the app and its UIs, ports, which UI writes are allowed)
- the subset rule (`full` or `smoke`) and the iteration number, when given
- an evidence folder for screenshots, the output path and the template, when given by the invocation

Non-interactive when the invocation names them.

## Procedure

1. Select the cases: those with `runner: ui`; all of them, or only those tagged `smoke` when the rule is `smoke` and this is iteration 2 or later. If there are none, write the report with `total: 0` and summary `no UI cases` and stop.
2. Pick the browser tool this session has, in this order, and record it in the frontmatter as `browser`:
   - Playwright MCP tools (`mcp__playwright__*`; step 13b of a run gets them, headless in a fresh profile): give screenshots an absolute filename, since a relative one is saved in the working directory, i.e. the worktree;
   - Claude in Chrome tools (`mcp__claude-in-chrome__*`), when the skill is called by hand in a session that has them: open a new tab, never reuse the human's tabs;
   - the Playwright library, only if the worktree environment already provides it (`python -c "import playwright"` or `npx playwright --version` succeeds without installing);
   - none: every case is `blocked` with the reason "no browser tool available".
   Never install tooling, never change the environment.
3. Start the app exactly as AGENTS.md documents (command, env file, port). Wait until the port answers. If it does not, every case is `blocked` with the output tail.
4. For each case: open the URL, perform the steps literally and in order, wait for the screen to settle, compare what is visible with the expected observation. `pass` only when the expected observation was seen. Save one screenshot per case into the evidence folder as `<case id>.png` and reference it in the results table. Note anything unexpected on screen (errors, slow paths, layout breakage) under observations.
5. UI writes (saving, adding or resetting records) only when a case requires them and AGENTS.md allows them; list every write made under `## UI writes made`.
6. Stop the app and close the browser tab or session you opened.

## Output

`testing_feedback_ui_<feature>_<n>[_v<k>].md` in the template shape: frontmatter `passed`, `failed`, `blocked`, `total`, `subset`, `scope: ui`, `browser`, `summary`; the results table with evidence paths; details per failing or blocked case; UI writes made; observations. End with `## Run cost` covering the app sessions (wall time, messages sent, LLM usage from what the project exposes, and the source).

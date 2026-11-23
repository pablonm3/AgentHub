---
name: run-tests
description: Run the `runner: code` test cases of a run (kinds unit and eval) with the project's own tooling and write a pass/fail report with observations and project run cost; UI cases are left to run-tests-ui. Report only — never edits code, however trivial the fix. Use when a run's step 13 invokes it or a user asks to execute the code cases of a testing file against a worktree.
---

# Run tests

Executes the `runner: code` cases of `testing_<feature>_<n>.md` and reports. Cases with `runner: ui` are listed as deferred and run by `run-tests-ui` (step 13b) in a browser. Every fix, however small, goes through triage and build; this skill changes nothing in the worktree.

## Inputs

- the latest testing file, the latest spec, the worktree, the project AGENTS.md (how to run unit tests, evals, the app and the companion tools)
- the subset rule (`full` or `smoke`) and the iteration number, when given
- output path and template, when given by the invocation

Non-interactive when the invocation names them.

## Procedure

1. Select the cases: those with `runner: code`; all of them, or only those tagged `smoke` when the rule is `smoke` and this is iteration 2 or later. Say in the report which subset ran. `runner: ui` cases go into `## Deferred to run-tests-ui` and are not counted.
2. Run each case the way its kind requires, using only what AGENTS.md documents:
   - `unit`: the project's test runner on the named tests or modules;
   - `eval`: the eval runner on the named suite or case keys, scratch mode never the shared/canonical dataset unless AGENTS.md says the run is read-only;
   Record the exact command or steps and the observed output for every case.
3. A case that cannot run (environment, missing tool, dev server down) is `blocked` with the reason. Do not fix the environment and do not edit tests or config.
4. Compare observed against expected per case; `pass` only when the expected observation was seen. Note observations outside the cases (crashes, slow paths, unexpected logs).
5. Stop the app or any process you started.

## Output

`testing_feedback_<feature>_<n>[_v<k>].md` in the template shape: frontmatter `passed`, `failed`, `blocked`, `total`, `subset`, `scope: code`, `summary`; the results table; details per failing or blocked case; deferred UI cases; observations; commands run. End with `## Run cost` covering everything run (eval suites, app sessions): wall time, LLM usage from what the project exposes (eval summaries, LangSmith, app log), and the source.

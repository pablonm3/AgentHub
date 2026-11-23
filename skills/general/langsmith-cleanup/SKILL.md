---
name: langsmith-cleanup
description: Delete the temporary (scratch) eval datasets a harness run created in LangSmith, selected by the run's owner id and nothing else, using the project's own scratch commands from AGENTS.md; lists before and after and writes a short report. Never touches canonical or shared datasets, result files or the server. Use when a run's step 15c invokes it or a user asks to remove a run's scratch datasets.
---

# LangSmith cleanup

The last step that touches the project's eval tooling. Every eval run of a harness run (run-tests, regression-testing-report) names the run id as the scratch owner, so the run's datasets can be removed as one set without looking at anything else.

## Inputs

- the scratch owner (the run id), the worktree
- the project AGENTS.md: how scratch datasets are named and the commands that list and delete them
- output path and template, when given by the invocation

Non-interactive when the invocation names them.

## Procedure

1. **List** the datasets of the owner with the project's list command and record the output. No mechanism in AGENTS.md, or nothing owned → `status: not_applicable` or `deleted: 0`, write the report, stop.
2. **Delete** with the project's command that removes exactly one owner's datasets, confirmation flag included so it runs non-interactively. Never a command that crosses owners, prunes by age, or touches canonical datasets, result files or the server.
3. **List again** and record the output; what is still listed is `remaining`.
4. A failed command is `status: failed` with its output. Do not fix credentials or the environment.

## Output

`langsmith_cleanup_<feature>_<n>[_v<k>].md` in the template shape: frontmatter `status`, `owner`, `deleted`, `remaining`, `summary`; the before list, the deleted names, the after list, the commands run. `## Run cost`: `project runs: none`.

---
run_id: <feature>_<n>
step: "15c"
skill: langsmith-cleanup
version: <k>
status: done                    # done | failed | not_applicable
owner: <run_id>
deleted: 0
remaining: 0                    # datasets of this owner still listed after the delete
summary: <one line, e.g. "7 scratch datasets of update-filters-readability_1 deleted, 0 remaining">
---
# <feature> — LangSmith scratch cleanup (v<k>)

Only datasets owned by `<run_id>` were touched. Result files, canonical datasets and the server were not.

## Before
Output of the list command (dataset names, ages, owner).

## Deleted
One line per dataset deleted.

## After
Output of the list command after the delete; `remaining` in the frontmatter is this count.

## Commands run
Exact commands, in order.

## Run cost
- project runs:    none

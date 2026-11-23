# regression-v1

Regression only: compares a branch against the commit it forked from on the eval suites and case keys a ticket names, then writes a final report with the deltas, a timing summary, the local delta CSV and the server paths of the raw results. No spec, plan, build or gates. Described in docs/WORKFLOW_SPEC.md section 10.

- `workflow.yaml`: 6 steps in 3 groups. 1 ticket, 2 start (worktree at the base branch, project setup), 15b `regression-testing-report`, 15c `langsmith-cleanup`, 16 `regression-final-report`, 18 run log. The ids match the same skills and actions in `feature-v1`.
- `defaults.yaml`: `regression_repetitions` (3) and `regression_workers` (4 per side) when the ticket gives none; opus for every AI step, overridable per step under `model.steps`; 15b timeout 300 min.
- `prompts/`: 15b takes refs and selection from the ticket; 15c is the `feature-v1` prompt with the owner note adjusted; 16 is new; `02-setup-chat.md` and `continue-step.md` (the message sent to a step's own session when it stopped unfinished, spec 5.8) are copied unchanged from `feature-v1`.
- `templates/`: `regression_report.md` (selection section, workers, one runs-table row per eval command), `final_report.md` (new), `langsmith_cleanup.md` (copied unchanged).

Ticket shape (`tickets/<feature>.md`; the feature name differs from any feature ticket, e.g. `reg-<branch>`):

```markdown
---
project: webapp
base_branch: dev
compare_branch: filter-recovery-classifier_1
suites: [power_user-entry, results-show_more]   # run whole
cases: { results-show_all: [all-1x, all-2x] }   # only these case keys of that suite
repetitions: 3                                  # optional, default from defaults.yaml
workers: 4                                      # optional, default from defaults.yaml
---
# Regression: filter-recovery-classifier_1 vs dev
```

At least one of `suites` and `cases`; a suite appears in only one of them.

Changing a default or a step: edit this directory in place, one commit per change saying what changed and why. A run records the harness commit it started on (`harness_commit` in `state.json`); a run resumed after an edit continues on the edited workflow, so keep prompts true for runs that started before the change. Copy to a new directory only when the human asks for a second workflow.

# research-v1

Research on a topic: gathers context from the web, tries to answer the ticket's questions with Jupyter notebooks or Python programs that run simulations, then reviews the answers and writes a final report. No spec, plan, build or gates; nothing in the project is edited, committed or pushed. Described in docs/WORKFLOW_SPEC.md section 11.

- `workflow.yaml`: 6 steps in 3 groups. 1 ticket, 2 start (worktree at the base branch, project setup; the worktree is only a working folder), 20 `research-context` (fable), 21 `research-answers` (opus), 22 `research-report` (fable), 18 run log. Ids 1, 2 and 18 match `feature-v1`; 20 to 22 are new skills, so they get ids no other workflow uses.
- `defaults.yaml`: `proposed_questions_max` (3, questions step 20 may add to the ticket's own) and `simulation_timeout_min` (20, minutes per notebook cell or program run in step 21); the three models; effort high, xhigh, high; timeout 240 min for step 21 and 90 for the others.
- `prompts/`: 20, 21 and 22 are new; `02-setup-chat.md` and `continue-step.md` (the message sent to a step's own session when it stopped unfinished, spec 5.8) are copied unchanged from `feature-v1`.
- `templates/`: `research_context.md` (questions with ids, findings with URLs), `answers.md` (one entry per question, the files behind them), `final_report.md` (per question: answer, verdict, files, sources).

Ticket shape (`tickets/<feature>.md`; from a task AgentHub writes the frontmatter itself):

```markdown
---
project: webapp
---
# <topic>
<what the research is about and why, what is already known, links>

## Questions
1. <question>
2. <question>
```

A ticket without `## Questions` is valid: the run works on the questions step 20 proposes.

Outputs, all directly in `runs/<feature>_<n>/` and never committed: `research_context_<feature>_<n>.md`, `answers_<feature>_<n>.md`, the notebooks and programs `sim_<short-name>_<feature>_<n>.ipynb` or `.py` with a program's output in `.out.txt`, and `final_report_<feature>_<n>.md` (plus `final_report_<feature>_<n>.ipynb` only when the report needs one). AgentHub serves them at `/runs/<run id>/files/<name>`, a notebook rendered read-only. A simulation that fails is kept with its error and reported as not settled; the run still ends `done`.

Changing a default or a step: edit this directory in place, one commit per change saying what changed and why. A run records the harness commit it started on (`harness_commit` in `state.json`); a run resumed after an edit continues on the edited workflow, so keep prompts true for runs that started before the change. Copy to a new directory only when the human asks for a second workflow.

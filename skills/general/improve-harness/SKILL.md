---
name: improve-harness
description: Review recent harness runs (run logs, decision files, final-report feedback, test and review reports, harness git log, SigNoz numbers) and write docs/harness_reviews/<date>_harness_review.md with metrics, evidence-backed findings and one concrete proposed change per problem; applies a change only on explicit approval and commits it. Manual skill, run in an ordinary session, never inside a run. Use when the user says /improve-harness or asks to review how the workflow has been performing.
---

# Improve harness

The feedback loop for the harness itself (spec 4.7). Run from the code root (the AgentHub repo; runs, logs and decision files are under the data root `HARNESS_DATA_ROOT`) in an ordinary Claude session, never from inside a run: runs may not edit skills, workflows or the orchestrator.

## Inputs

Period: given by the user, or by default every run since the previous review file in `docs/harness_reviews/` (none → all runs).

- `workflow_logs/*.log`: step durations, iterations per run, where runs looped, paused or were blocked, project run costs per step.
- `runs/*/decision_*.md`: the questions the human had to answer and the edits that resulted. Repeated questions of the same kind point at a skill or ticket template that should pre-empt them.
- `runs/*/final_report_*.md`, `## Feedback` sections: what each run said about the workflow.
- `runs/*/testing_feedback_*.md`, `review_*.md`, `readability_*.md`: recurring failure classes and readability problems.
- `runs/*/log/02-setup.txt` and context files: setup steps or run instructions a run had to discover that `harness.yaml: setup` (private root) or the AGENTS.md lacked (flag the disagreement).
- `git log` of the harness since the previous review: improvements already made, so they are not proposed again.
- SigNoz through `obs-query` when a finding needs numbers the logs do not hold.

## Output

`docs/harness_reviews/<yyyy-mm-dd>_harness_review.md`, in order:

1. **Runs covered**: run ids, workflow versions, period.
2. **Metrics** compared with the previous review: runs, mean iterations, mean duration, human wait time, blocked or failed runs, project cost totals (wall time, LLM usage).
3. **Findings**, each tied to its evidence (file paths, run ids, counts).
4. **Proposed changes**, ranked by expected effect. Each is a concrete diff to a skill, a prompt, a workflow default, an AGENTS.md or the orchestrator. One proposal per problem, the smallest change that addresses it. Never a rewrite.

## Applying changes

Propose; the human approves each change separately; then apply it and commit it on its own with the review file linked in the commit message. Changes never go into a running workflow definition: when a default, prompt or step of a workflow changes, create `workflows/<name>-v<k+1>/` as a copy with the change and a README stating what changed, so completed runs stay reproducible against the version they ran on. Skill and orchestrator changes apply in place (they are shared), with `harness_commit` in each run's state tying old runs to the version they used.

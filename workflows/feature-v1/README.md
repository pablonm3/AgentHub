# feature-v1

First version of the workflow in docs/WORKFLOW_SPEC.md section 2. Nothing to compare against yet.

- `workflow.yaml` — the graph: 22 steps in 5 groups (13b `run-tests-ui` follows 13; 15b `regression-testing-report` and 15c `langsmith-cleanup` follow 15; 18b `push`, run by the orchestrator, follows 18 and puts the feature branch on `origin` before GATE 2), loop over 9–14, gates at 7 and 19, chat re-entry table.
- `defaults.yaml` — tunables; the effective values are copied into each run's `state.json`.
- `prompts/` — the exact text passed to `claude -p` per step, plus the chat prompts (`*-chat.md`) for gates and questions, worded for an answer that reaches the run through AgentHub (`on_question: pause`, the default), and `continue-step.md`, the message sent to a step's own session when it stopped unfinished (spec 5.8). `10-code-review-incremental.md` replaces `10-code-review.md` when the build loop repeats the review and the change since the last one is inside the `review_incremental_*` limits of `defaults.yaml`.
- `templates/` — output shapes. Every artifact starts with YAML frontmatter; the orchestrator reads `status`, `decision`, `question`, `counts`, `passed/total`, `applied/skipped` and `summary` from it.

Changing a default or a step: edit this directory in place, one commit per change saying what changed and why. A run records the harness commit it started on (`harness_commit` in `state.json`); a run resumed after an edit continues on the edited workflow, so keep prompts true for runs that started before the change. Copy to a new directory only when the human asks for a second workflow.

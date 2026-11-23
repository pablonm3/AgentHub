Run ${run_id} · step ${step_id} · ${skill} (attempt ${attempt}, same session). Non-interactive: do not ask questions.

This session stopped before the step was finished: ${stop_reason}. The step's instructions, given at the start of this conversation, still apply. Continue from where it stopped; do not start the step over.

- Use what this conversation already holds: what you read, ran and concluded, and the reports of subagents that had finished.
- A command or subagent that was still running when the session stopped is gone and was not run again. Start it again only if its result is still needed.
- Before writing, look at what the step already left behind: files in the run folder, and commits or uncommitted edits in the worktree.

The step is finished when its outputs exist as those instructions describe them:
${outputs}

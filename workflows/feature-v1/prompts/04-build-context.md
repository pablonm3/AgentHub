Run ${run_id} · step 4 · build-context. Non-interactive: every input is given here, do not ask questions.

Invoke the `build-context` skill with these inputs.

Inputs:
${inputs}
- project instructions (AGENTS.md): ${agentsmd}
- worktree (branch ${branch} from ${base_branch}): ${worktree}
- output template: ${templates}/context.md

Output (write exactly this path):
${outputs}

Rules for this run:
- Read-only: no code edits, no DB writes, no writes to the dev server. The only file you may write besides the output is ${agentsmd}, and only to add run/test instructions that were missing or wrong (skill phase 3).
- Follow the template's shape and frontmatter. `status` must be one of `reproduced`, `not_reproduced`, `not_applicable`. When `not_reproduced`, also set `question:` to the one question the human must answer; the orchestrator opens a chat with them.
- Spend at most about 15 minutes on reproduction, then record what was found and move on. If the app will not start, say so and continue with static context.
- End the file with the `## Run cost` section (project runs, wall time, LLM usage, source).
${answer}

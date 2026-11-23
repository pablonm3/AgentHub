Run ${run_id} · step 9 · build-plan (iteration ${iteration} of at most ${max_iterations}). Non-interactive: every input is given here, do not ask questions.

Invoke the `build-plan` skill with these inputs.

Inputs:
${inputs}
- project instructions (AGENTS.md): ${agentsmd}
- worktree (branch ${branch} from ${base_branch}): ${worktree}
- latest plan to implement: ${plan_latest}

Output: one commit on branch ${branch} at the end of the step. No run-folder file.

Rules for this run:
- Implement the latest plan version only; the spec decides any conflict between plan and code.
- Work inside ${worktree}. Do not touch files outside it, except the project AGENTS.md above when the change adds or alters how the project is run or tested (the `build-plan` skill says when and how).
- Do not change the spec, the plan or the test-case file; if the plan cannot be followed, implement what can be and describe the deviation in the commit message so review and triage see it.
- Exactly one commit at the end of the step (stage everything you changed). Message format:
  `<summary line>` then a blank line, then `Run: ${run_id} · plan: <plan file name> · iteration ${iteration}` and a short list of deviations from the plan, if any.
- Never push. Never merge into ${base_branch}.
${answer}

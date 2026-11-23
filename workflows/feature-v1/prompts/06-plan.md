Run ${run_id} · step 6 · plan (execution ${k}, iteration ${iteration}). Non-interactive: every input is given here, do not ask questions.

Invoke the `plan` skill with these inputs.

Inputs:
${inputs}
- project instructions (AGENTS.md): ${agentsmd}
- worktree (branch ${branch} from ${base_branch}): ${worktree}
- templates: ${templates}/plan.md and ${templates}/plan_short.md

Outputs (write exactly these paths):
${outputs}

Rules for this run:
- The spec is authoritative. Never re-derive requirements. If the spec is ambiguous or contradicts the code, write the question into the plan's `## Open questions` instead of resolving it silently.
- Read the observed current behaviour from the context; do not redo the reproduction. Targeted read-only checks for design questions are fine (DB read-only, grep, running a unit test).
- If a previous plan version is listed in the inputs, this is an incremental plan against the code already in the worktree: say what changes versus the previous plan and why.
- Include the self plan-review (incremental, modular; big changes as suggestions at the end) and the communicator pass that produces the short plan.
- Write code only as illustration inside the plan; never edit the worktree.
- End both files with `## Run cost` (`project runs: none` unless you ran the app or evals).
${answer}

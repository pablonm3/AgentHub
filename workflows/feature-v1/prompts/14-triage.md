Run ${run_id} · step 14 · triage (iteration ${iteration} of at most ${max_iterations}). Non-interactive: every input is given here, do not ask questions.

Invoke the `triage` skill with these inputs.

Inputs (latest version of every artifact of this run):
${inputs}
- worktree (branch ${branch} from ${base_branch}): ${worktree}
- project instructions (AGENTS.md): ${agentsmd}
- templates: ${templates}/decision.md, ${templates}/plan.md and ${templates}/plan_short.md

Outputs:
${outputs}
- when the decision is `new_plan`, ALSO write the next plan version at: ${plan_next}
  (and a matching short plan at ${plan_short_next})

Rules for this run:
- Decide exactly one of: `done` (all acceptance criteria hold and nothing blocks), `new_plan` (failures or review items trace back to the plan or the implementation; write the incremental next plan against the code already in the worktree), `spec_issue` (a failure traces back to the spec itself: a criterion is wrong, contradictory or untestable).
- Never edit code, test cases, the spec or the current plan. The decision file and, for `new_plan`, the next plan version are your only writes.
- Frontmatter of the decision file: `decision`, `summary`, and for `spec_issue` a `question:` field with the one question the human must answer (the orchestrator opens a chat with them).
- Reasoning in the body: which cases failed and why, which review items remain, what the next plan changes.
- `## Run cost`: `project runs: none`.
${answer}

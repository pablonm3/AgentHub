The coding harness paused run ${run_id}: build-context could not reproduce the ticket (${reason}). AgentHub shows this to the human (Pablo): his replies reach you as ticket comments, and your replies reach him the same way. Load the `build-context` skill in chat mode.

Question for the human:

${question}

Context:
- context file with what was tried: ${artifact}
- frozen ticket copy (latest version): ${ticket_latest}
- project instructions: ${agentsmd}
- worktree: ${worktree}
- decision file, written by the orchestrator with the question: ${decision_file}

How to work:
1. Summarise in a few lines what was tried and what was observed, then ask the question. Discuss until the premise of the ticket is settled. When the human's ticket or comments already settle it, say so and use that answer.
2. Possible resolutions, and what each means for the run:
   - The ticket is wrong or incomplete → propose an edit to the ticket copy as a diff; on explicit approval write it as the NEXT version (`ticket_${feature}_${n}_v<k>.md` in ${run_dir}, never in place). The orchestrator then rebuilds the context from the new copy.
   - The ticket is right and the reproduction needs different inputs or steps → record them as the answer; the orchestrator re-runs build-context with the answer injected.
3. Never edit code, the spec, the plan or test cases. Never write anything outside ${run_dir} except, if the human asks, run/test instructions that were missing in ${agentsmd}.
4. When the premise is settled and every approved edit is written, fill in ${decision_file}: set `answered: true` in its frontmatter and keep the other fields, write the answer under `## Answer`, and add `## Approved edits` (the diffs, or `none`). Write it last and never earlier, then run `agenthub harness resume ${run_id}`. End your reply with one short line: the answer is recorded, the run continues, and what it does next (point 2).
5. If the human wants to leave the question open, leave the file at `answered: false` and do not resume: the run stays paused until an answer is recorded.

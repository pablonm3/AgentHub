The coding harness paused run ${run_id} at GATE 1 (human review of spec and plan). AgentHub shows the gate to the human (Pablo): his replies reach you as ticket comments, and your replies reach him the same way. Load the `plan` skill in chat mode.

${question}

Files to review (latest versions):
- spec: ${spec_latest}
- short plan: ${plan_short_latest}
- full plan: ${plan_latest}
- context: ${context_latest}
- ticket copy: ${ticket_latest}
- project instructions: ${agentsmd}
- worktree: ${worktree}
- decision file, written by the orchestrator with the gate message: ${decision_file}

How to work:
1. Open with a short summary: the spec's goal, the number of acceptance criteria, the open questions the spec lists, the plan's architecture (modules created and modified, interfaces that are new or change contract, the data flow in one line) and the plan's main steps. If the plan has no `## Architecture` section (it was written before the section existed), build the same summary from its changes and say so. Ask the human whether the spec says what they asked for and whether the architecture and plan are how they would build it.
2. For every change the human asks for: propose the edit as a high-level summary, not a diff. A few plain-language bullets saying what changes and why (which criteria or plan steps, in one line each), then one question: approve? No quoted spec text, no before/after lines, no diff unless the human asks to see it. Apply only on explicit approval, always as the NEXT version of the file (`spec_${feature}_${n}_v<k>.md`, `plan_${feature}_${n}_v<k>.md` together with `plan_short_${feature}_${n}_v<k>.md`) in ${run_dir}. Never edit in place. Keep every message short: the human is deciding, not reviewing text.
3. A spec change makes the orchestrator regenerate the plan and reach this gate again; a plan-only change continues to test cases. Say which will happen when you apply an edit.
4. Never edit code or test cases. Never write outside ${run_dir}.
5. Release the gate only on the human's word, given in a reply of his: AgentHub lets the run resume past a gate only after he replied. When he explicitly says he is done (for example "continue", "approved", "nothing else") and every approved edit is written, fill in ${decision_file}: set `answered: true` in its frontmatter and keep the other fields, write the questions discussed and his answers under `## Answer`, and add `## Approved edits` (every approved diff, or `none`). Write it last and never earlier, then run `agenthub harness resume ${run_id}`.
6. End that reply with one short line: the answer is recorded, the run continues, and what it does next (point 3).

The coding harness paused run ${run_id} at GATE 2 (the run is finished; the human reads the report and the regression deltas). AgentHub shows the gate to the human (Pablo): his replies reach you as ticket comments, and your replies reach him the same way. Load the `final-report` skill in chat mode.

${question}

Files:
- final report: ${run_dir}/final_report_${feature}_${n}.md
- explain-diff page: ${run_dir}/explain_diff_${feature}_${n}.html
- regression deltas: ${run_dir}/regression_${feature}_${n}.csv (detail: ${run_dir}/regression_report_${feature}_${n}.md; absent when step 15b was skipped)
- spec: ${spec_latest}
- run folder: ${run_dir}
- worktree: ${worktree} (branch ${branch} from ${base_branch})
- project instructions, including the regression/eval skills and commands: ${agentsmd}
- decision file, written by the orchestrator with the gate message: ${decision_file}

How to work:
1. Open with the report's summary: what changed, which acceptance criteria are met, what to test manually, what regression testing found (or that it did not run).
2. Answer questions about the result from the artifacts and the diff. You may re-run the project-specific regression skills if the human asks.
3. No edits in this gate: not to code, spec, plan or reports. Never push: the orchestrator pushes ${branch} to origin in step 18b, before this gate. `git status -sb` in the worktree shows whether the branch tracks `origin/${branch}`; when it does not (the run has `push: never`, or it passed step 18 before step 18b existed), tell the human the branch is not pushed and that pushing it is theirs to do. Opening the PR is the human's job; never merge into ${base_branch}.
4. Close the gate only on the human's word, given in a reply of his: AgentHub lets the run resume past a gate only after he replied. When he explicitly says he is done (for example "done", "nothing else"), fill in ${decision_file}: set `answered: true` in its frontmatter and keep the other fields, and write the questions discussed under `## Answer`. Write it last and never earlier, then run `agenthub harness resume ${run_id}`: the run is closed. End your reply with one short line saying so.

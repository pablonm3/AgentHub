The coding harness paused run ${run_id} because the project setup failed before the first AI step (${reason}). AgentHub shows this to the human (Pablo): his replies reach you as ticket comments, and your replies reach him the same way.

${question}

Context:
- worktree: ${worktree} (branch ${branch} from ${base_branch})
- project instructions, including how secrets, the dev server and the database are reached: ${agentsmd}
- setup output log: ${run_dir}/log/02-setup.txt
- decision file, written by the orchestrator with the question: ${decision_file}

How to work:
1. Read the log and AGENTS.md, diagnose the cause, and explain it to the human in two or three sentences.
2. Propose the fix. Typical causes: the dev server is off (the human turns it on), an SSH key is missing, a package manager is not installed. Do not edit the worktree code and do not change `harness.yaml` or the harness skills; if the setup list itself is wrong, say exactly what should change and let the human edit it after this run.
3. When the human confirms the cause is fixed, fill in ${decision_file}: set `answered: true` in its frontmatter and keep the other fields, and put a one-paragraph record of the cause and the fix under `## Answer`. Write it last and never earlier, then run `agenthub harness resume ${run_id}`: the orchestrator re-runs the setup list from the start. End your reply with one short line saying so.
4. Until then the run stays paused; leave the file at `answered: false` and do not resume.

Run ${run_id} · step 17 · explain-diff-html. Non-interactive: every input is given here, do not ask questions.

Invoke the `explain-diff-html` skill for the change `origin/${base_branch}...HEAD` in ${worktree} (branch ${branch}; fall back to `${base_branch}` if the remote ref does not resolve).

Destination override: save the single self-contained HTML file at exactly this path instead of the project's `docs/diffs_explained/`:
${outputs}

The spec of the change, for the Background and Intuition sections: ${spec_latest}

Rules for this run:
- Do not create anything inside the worktree; the deliverable lives in the run folder only.
- Keep every other rule of the skill (sections, five interactive quiz questions, `<pre>` code blocks, no network dependencies).

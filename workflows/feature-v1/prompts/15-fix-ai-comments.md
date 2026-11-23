Run ${run_id} · step 15 · fix_ai_comments. Non-interactive: every input is given here, do not ask questions.

Invoke the `fix_ai_comments` skill in **baseline branch** mode with baseline `origin/${base_branch}` (fall back to `${base_branch}` if the remote ref does not resolve), in the worktree ${worktree} on branch ${branch}.

Output: one commit on ${branch} with the comment cleanup, or no commit when nothing changed. No run-folder file.

Rules for this run:
- Only comments introduced on this branch are in scope, as the skill defines. Preserve required test annotations (`Constraint:`, `Input:`, `Expected output:`) and tooling directives.
- Commit message: `Clean up comments` then a blank line and `Run: ${run_id}`. Never push.

---
name: archive-old-work
description: Archive finished harness runs older than a given age (or one feature regardless of age) — move the run log, the run folder and a zipped worktree into archived/<date>_<feature>_<n>/, with git mv for tracked files and confirmation before anything unpushed is zipped. Manual skill, not a workflow step. Use when the user says /archive-old-work <age>, "archive old runs" or "clean up finished runs".
---

# Archive old work

Invoked by hand: `/archive-old-work 2 weeks`, or `--feature <feature>` to archive every run of one feature regardless of age. Works in the data root (`HARNESS_DATA_ROOT`, `data/orchestrator/` in AgentHub; the code root when unset), which holds `tickets/`, `runs/`, `workflow_logs/`, `worktrees/` and `archived/`.

## Procedure

1. **Age.** Ask for it if not given (`days`, `weeks`, `months`). A run is in scope when the `ended` line of its log is older than now minus the age. With `--feature`, every run of that feature whose log exists is in scope.
2. **Find runs** by reading `workflow_logs/*.log`; the header gives run id, feature and project. Also read `runs/<run-id>/state.json`.
3. **Exclude** any run whose state is `running`, `waiting_on_human` or `paused`, whatever its age. A run folder without a log (crashed before step 18) is reported and skipped.
4. **Check the worktree** `worktrees/<project>/<run-id>/`: unpushed commits (`git log @{upstream}..` or, without an upstream, `git log origin/<base>..HEAD`) and uncommitted changes. Report them and **ask the human to confirm** before continuing, since the zip becomes the only copy. Branches are never deleted.
5. **Move**, per run, into `archived/<yyyy-mm-dd>_<feature>_<n>/` where the date is the run's end date:
   - `<feature>_<n>.log` from `workflow_logs/` (`git mv`)
   - `run/` ← `runs/<feature>_<n>/` moved as is, artifacts, `state.json` and `log/` (`git mv` for tracked files, plain move for `log/`)
   - `worktree.zip` ← the worktree zipped **excluding** `.venv`, `node_modules`, `.uv-cache`, `__pycache__`, `.pytest_cache`, `dist`, `build` and other dependency or build folders. Verify the zip (`unzip -t`), then `git worktree remove` it from the base clone `worktrees/<project>/.base/`.
   - The ticket `tickets/<feature>.md` is moved into the archive folder only when no other run of that feature remains in `runs/` or `workflow_logs/`.
6. Never touch the code root or the private root.
7. **Summary**: runs archived, folders created, size moved, size of each zip, tickets moved, anything skipped and why.

When the data root is tracked in git, `archived/` keeps there what was committed before the move (log, ticket, run md files) and ignores `run/log/` and `worktree.zip`; AgentHub's data root is untracked, so there every move is a plain move. A restored archive needs the project's `setup` list run again because dependency folders were excluded.

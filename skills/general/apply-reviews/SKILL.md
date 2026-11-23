---
name: apply-reviews
description: Apply the findings of a code-review report and a readability report that meet given severity thresholds, commit the fixes, and write a report listing every finding as applied or skipped with the reason. Thresholds come from the invocation, never from the skill. Use when a run's step 12 invokes it or a user asks to apply review findings above a severity.
---

# Apply reviews

Turns review reports into commits. It receives the thresholds (`review_severity_threshold`, `readability_severity_threshold`) in the invocation; by default in `feature-v1` code-review items are applied at HIGH and above, readability items at MEDIUM and above.

## Inputs

- `review_<feature>_<n>[_v<k>].md`, `readability_<feature>_<n>[_v<k>].md` (latest versions), the worktree, the thresholds, the project AGENTS.md
- output path and template, when given by the invocation

Non-interactive when the invocation names them; when called by hand ask for the reports and the thresholds.

## Procedure

1. Parse both reports: one entry per `### [SEVERITY] title` heading with its location and remediation.
2. For each finding at or above its report's threshold: read the code at the location, confirm the finding still holds (an earlier fix may have covered it), apply the smallest change that resolves it. A finding you disagree with after checking is **skipped with a one-line justification**, never silently dropped.
3. Findings below the threshold are listed as skipped with reason `below threshold`.
4. Keep edits to what each finding asks; no drive-by refactors. Run the cheap checks AGENTS.md documents for touched modules.
5. Commit: one commit per report is fine (`Apply code review v<k>` / `Apply readability review v<k>`), body `Run: <run id>` and the list of findings applied. No commit when nothing was applied. Never push.

## Output

`reviews_applied_<feature>_<n>[_v<k>].md` in the template shape: frontmatter `thresholds`, `applied: {review, readability}`, `skipped: {review, readability}`, `summary`; a table per report with action and commit or reason; verification run. `## Run cost`: `project runs: none` unless the app or evals ran.

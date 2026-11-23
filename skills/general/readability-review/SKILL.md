---
name: readability-review
description: Review a branch diff from a cognitive-load perspective and produce a severity-sorted report where every finding carries one concrete simplification (naming, extraction, flattening, removing indirection, a comment only where intent is not obvious). Reports every severity; applies nothing. Use when a run's step 11 invokes it or a user asks how to make a change easier to read.
---

# Readability review

Code review looks for defects; this skill looks at how hard the change is to understand for a reader meeting it cold. It never edits code.

## Inputs

- comparison ref and worktree (merge-base diff `<base>...HEAD`), the spec and plan for intent
- output path and template, when given by the invocation

Non-interactive when the invocation names them; when called by hand ask only for the comparison ref.

## Procedure

1. Establish the diff: `git diff --find-renames <base>...HEAD`, plus the changed-file list. Read each changed hunk with its surrounding code, not in isolation.
2. For every changed region ask: can a reader state what this does and why after one pass? What makes them stop: a name that hides the meaning, a function doing three things, nested branches, a value that travels through indirection, a comment that narrates instead of explaining intent, a clever construct where a plain one would do?
3. Write one finding per stopping point with exactly one concrete suggestion: the rename (old → new), the extraction (what moves where and under which name), the flattening (which guard clause), the removal (which layer), or the one-line comment stating the intent. No "consider refactoring".
4. Severity: `HIGH` very hard to understand (a reader would have to reconstruct the behaviour); `MEDIUM` understandable with effort; `LOW` minor friction. Report all of them; the apply threshold is not your decision.
5. Do not report defects (that is code review), style-guide trivia a formatter handles, or pre-existing code the diff did not touch unless the change made it harder to read.

## Output

`readability_<feature>_<n>[_v<k>].md` in the template shape: frontmatter `counts` per severity and `summary`; one `### [SEVERITY] title` heading per finding with location, why it is hard to read, and the suggestion; then notes. `## Run cost`: `project runs: none`.

---
run_id: <feature>_<n>
step: "11"
skill: readability-review
version: <k>
counts: { high: 0, medium: 0, low: 0 }
summary: <one line>
---
# <feature> — readability review (v<k>)

Comparison: `origin/<base_branch>...HEAD` at `<sha>`. Perspective: cognitive load of a reader meeting this code for the first time.

## Findings
One heading per finding, exactly `### [SEVERITY] title`. HIGH = very hard to understand; MEDIUM = understandable with effort; LOW = minor.

### [HIGH] <title>
- location: `path/file.py:123`
- why it is hard to read: …
- suggestion: one concrete change (rename X to Y, extract Z, flatten the branch, remove the indirection, add a one-line comment stating the intent)

### [MEDIUM] <title>
…

## Notes
Patterns across the diff, what reads well, anything out of scope.

## Run cost
- project runs:    none

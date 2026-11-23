---
run_id: <feature>_<n>
step: "10"
skill: code-review
version: <k>
counts: { critical: 0, high: 0, medium: 0, low: 0 }
summary: <one line, e.g. "2 high, 5 medium; AC3 not satisfied">
---
# <feature> — code review (v<k>)

Comparison: `origin/<base_branch>...HEAD` at `<sha>`.

## Findings
Sorted by severity, then confidence. One heading per finding, exactly `### [SEVERITY] title`.

### [HIGH] <title>
- location: `path/file.py:123`
- category: bug risk | requirements | modularity/readability | unit tests | frontend compatibility
- evidence: concrete trigger or execution path
- impact: …
- remediation: smallest practical fix

### [MEDIUM] <title>
…

## Requirements coverage
| AC | status | evidence |
|---|---|---|
| AC1 | satisfied / not satisfied / not verifiable | … |

## Test assessment
Tests added or changed, redundant or low-value tests, gaps, commands run and results.

## Frontend compatibility
Table when applicable, otherwise `Not applicable.`

## Review notes
Non-blocking suggestions, residual risks, review limitations.

## Run cost
- project runs:    none

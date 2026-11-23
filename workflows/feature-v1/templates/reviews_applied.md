---
run_id: <feature>_<n>
step: "12"
skill: apply-reviews
version: <k>
thresholds: { review: high, readability: medium }
applied: { review: 0, readability: 0 }
skipped: { review: 0, readability: 0 }
summary: <one line, e.g. "review 2 applied / 5 skipped · readability 4 applied / 4 skipped">
---
# <feature> — reviews applied (v<k>)

Inputs: `review_<feature>_<n>[_v<k>].md`, `readability_<feature>_<n>[_v<k>].md`.

## Code review
| # | severity | finding | action | commit / reason |
|---|---|---|---|---|
| 1 | HIGH | … | applied | `abc1234` |
| 2 | MEDIUM | … | skipped | below threshold |

## Readability review
| # | severity | finding | action | commit / reason |
|---|---|---|---|---|

## Verification
Tests or checks run after the edits, with results.

## Run cost
- project runs:    none

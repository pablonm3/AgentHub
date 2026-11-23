---
run_id: <feature>_<n>
step: "6"                     # "14" when triage writes the next version
skill: plan                   # or triage
version: <k>
previous_version:             # <k-1> for incremental plans, empty for the first
summary: <one line>
---
# <feature> — plan (v<k>)

## Approach
Design in a few paragraphs: what changes, where, why this shape. Incremental and modular.

## Architecture
The shape of the change as a whole, before the per-change detail.

### Modules
Every module created or modified: path, `new` or `modified`, its responsibility after the change, and the modules it depends on or that depend on it.

### Interfaces
Every function, class, endpoint, command, event or schema that is new or whose contract changes: full signature, input and output types, errors or edge cases it raises or returns, callers. Say for each whether existing callers are affected. `none` when no contract changes.

### Data flow
How the input travels through the modules to the output, as a short text diagram plus a line per hop; mark which hops are new.

## Changes
One subsection per change, in build order. For each: files and functions, the exact behaviour before and after, data or schema impact, how it is verified.

### 1. <change>
### 2. <change>

## What changes versus the previous plan
Only for v2+: what the previous plan got wrong or did not cover, and what is already in the worktree.

## Risks and rollback

## Open questions
Spec ambiguities or contradictions with the code, written down instead of resolved silently. `none` when empty.

## Suggestions outside this plan
Bigger changes worth doing later, kept out of the build.

## Plan review
Self-review: is it incremental, modular, verifiable; what was simplified as a result.

## Run cost
- project runs:    none

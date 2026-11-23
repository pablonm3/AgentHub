---
run_id: <feature>_<n>
step: "6"
skill: plan
version: <k>
summary: <one line>
---
# <feature> — plan (short, v<k>)

For human review: under one page.

## What we build
Three to six bullets in plain language.

## Architecture
What the human approves before the build: the shape of the change, not its code.

### Modules
One line per module created or modified: path, `new` or `modified`, what it is responsible for after the change.

### Interfaces
One line per function, class, endpoint, command, event or schema that is new or whose contract changes: name, inputs, outputs, who calls it. `none` when no contract changes.

### Data flow
How the input travels through the modules above to the output, in a few lines or a small text diagram (`A → B → C`).

## How it is verified
Which acceptance criteria each change satisfies; what tests cover it.

## Decisions to confirm
Choices the human may want to override, with the alternative.

## Open questions
`none` when empty.

---
run_id: <feature>_<n>
step: "20"
skill: research-context
version: <k>
questions: <count>              # all questions of the run, ticket and proposed
proposed: <count>               # of those, proposed by this step
sources: <count>                # distinct URLs under Sources
summary: <one line: the topic, how many questions (how many proposed), what the sources already settle>
---
# <feature> — research context

## Topic
The topic in two or three sentences, from the ticket: what the research is about and why, what is already known.

## Questions
Every question of the run. Ticket questions word for word, in the ticket's order; proposed ones after them. The ids are fixed here: steps 21 and 22 answer exactly these.

| id | question | source | why (proposed only) |
|---|---|---|---|
| Q1 | <the ticket's words> | ticket | |
| Q2 | <question> | proposed | <what the topic needs that the ticket's questions do not ask> |

## Findings
One subsection per question id, in order.

### Q1. <question>
- <finding> — <URL>
- <finding> — <URL> (disagrees with the one above: <how>)
- simulation: <what a simulation could settle and what it would need: model, parameters, data> | <none needed: the sources above answer it>

## Background
Definitions, standard models, known results and data sets that more than one question relies on, each with its URL.

## Open points
Claims found without a source, contradictions the sources do not resolve, what could not be found.

## Sources
One line per URL cited above: `<URL>` — <title or publisher>, <date when shown>.

## Run cost
- project runs:    none

---
run_id: <feature>_<n>
step: "21"
skill: research-answers
version: <k>
questions: <count>              # entries below; one per question id of the research context
settled: <count>                # entries with result: settled
not_settled: <count>            # entries with result: not settled
notebooks: <count>              # .ipynb files written by this step
programs: <count>               # .py files written by this step
summary: <one line: how many questions settled of how many, the main result>
---
# <feature> — answers

## Answers
One entry per question id of the research context, in order, ticket and proposed alike.

### Q1. <question>
- result: settled | not settled
- answer: <one to three sentences, or "No answer found: <why>">
- evidence: <the numbers or output the answer rests on, with the cell or line they come from>
- simulation: `<file name in the run folder>` (notebook | program, output in `<name>.out.txt`), or `none: <reason>`
- assumptions and limits: <what the simulation assumes and does not model>

## Files
Every notebook, program and saved output this step wrote, all directly in the run folder.

| file | kind | question | executed | wall time |
|---|---|---|---|---|
| `sim_<short-name>_<feature>_<n>.ipynb` | notebook | Q1 | yes \| failed: <error in one line> \| timed out | <s> |
| `sim_<short-name>_<feature>_<n>.py` | program | Q2 | yes (exit 0) \| failed: exit <code> | <s> |
| `sim_<short-name>_<feature>_<n>.out.txt` | program output | Q2 | — | — |

## Environment
The exact commands that executed each file, and the packages each fetched (with versions when shown).

## Run cost
- project runs:    <number of executions (notebooks, programs) and their total wall time; or none>
- wall time:       <e.g. 42m>
- LLM usage:       none by the simulations
- source:          <time output, nbconvert output>

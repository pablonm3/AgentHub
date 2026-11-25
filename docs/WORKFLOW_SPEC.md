# Coding Harness — Workflow Spec (draft 4, 2026-11-09)

Source: handwritten notes on an LLM development process (5 pages, scanned 2026-11-07), plus decisions taken in conversation. All readings of the notes have been confirmed with the author.
Status: implemented 2026-11-09 (see section 9 for what the implementation does differently). This is the copy AgentHub runs: three roots (section 3), questions and gates surfaced through AgentHub (5.7), an external telemetry collector (5.6), nothing written under the user's home Claude folder (6.1).

---

## 1. Naming and tracking

- **Feature name.** Every ticket defines a feature name: the stem of its file, `tickets/<feature>.md`. Short, kebab-case, unique (for example `filter-recovery`).
- **Run number.** Each run of a feature gets a sequential number `<n>`, starting at 1. The orchestrator computes it as one more than the highest number found for that feature in `workflow_logs/`, `runs/` and `archived/`. **Run id** = `<feature>_<n>` (for example `filter-recovery_1`, `filter-recovery_2`).
- **Every file the workflow generates carries feature name and run number as a suffix**: `context_<feature>_<n>.md`, `spec_<feature>_<n>.md`, `plan_<feature>_<n>.md`, `plan_short_<feature>_<n>.md`, `testing_<feature>_<n>.md`, and so on. Any file on disk can be traced back to its ticket and to the exact run by name alone, and a new run never overwrites files from a previous one. The run number is always present, including on the first run.
- **Repeated executions** of a step inside a run add `_v<k>` after the run number, where `k` is that step's execution count in the run: `plan_<feature>_<n>_v2.md`, `testing_feedback_<feature>_<n>_v2.md`. No `_v` suffix means the first execution. This applies to every artifact, whatever the reason for the repeat: a loop iteration, a re-entry after a chat (5.7), or a resume that starts a stopped step over. A step that is continued in its own session (5.8) is still the same execution and keeps its names. A file name is therefore unique per execution and nothing is ever overwritten; readers that want "the latest" take the highest `k`.
- **All artifacts of a run live in one folder**: `runs/<feature>_<n>/`, together with the orchestrator state and the step transcripts. The suffix stays on every filename even though the folder already identifies the run, because files get linked, pasted and copied out of their folder and must remain self-identifying.
- The ticket itself is written by the human and has no run number: `tickets/<feature>.md`. All runs of the feature read the same ticket.

---

## 2. Steps

Actor is **H** (human) or **AI** (a skill run by the orchestrator). Step 3 is a one-time prerequisite per project, not a per-run step.

| # | Step | Actor | Inputs | Outputs |
|---|---|---|---|---|
| 1 | Write ticket | **H** | information from wiki, Google Docs, Notion, chat, etc. The harness never connects to those systems. | `tickets/<feature>.md` with frontmatter `project` and `base_branch` |
| 2 | Start run | **H** | `agenthub-harness run <workflow-name> <feature>` (in AgentHub the server runs it for `agenthub harness start`) | run number `<n>` allocated; `runs/<feature>_<n>/` created with `state.json` and a frozen copy `ticket_<feature>_<n>.md`; worktree `worktrees/<project>/<feature>_<n>/` on feature branch `<feature>_<n>` created from `base_branch` after a `git fetch` of the base clone; `link_worktree` run in it (6.1); then the project's `setup` commands from `harness.yaml` run inside it (dependencies, secrets, 6.3). A failing setup command stops the run before any AI step and asks the human (5.7) |
| 3 | Document project for agents (one-time) | **H** + AI `onboard-project` (6.3) | the repo (README, build and CI files), the human's knowledge of the project | `agentmds/<project>/AGENTS.md` covering, for example: how to start the app and check a change in the UI; how to run unit and integration tests; how to run evals or regression suites and read their output; how to run companion repos or tools the project depends on; how to obtain required secrets or config; data access rules; branching rules. The harness never names project-specific tools; they live only in this file (4.3) |
| 4 | Build context | AI `build-context` | `tickets/<feature>.md`, repo, DB (read-only), AGENTS.md, running app / evals (read-only) | `runs/<feature>_<n>/context_<feature>_<n>.md` including observed current behaviour (reproduction, see 4.5); may add missing run/test instructions to `agentmds/<project>/AGENTS.md`; asks the human when the ticket cannot be reproduced (5.7) |
| 5 | Spec | AI `spec` | ticket, `context_<feature>_<n>.md` | `runs/<feature>_<n>/spec_<feature>_<n>.md`: goal, in scope, out of scope, acceptance criteria in a fixed testable shape, open questions. Short (target under 2 pages). States **what** must be true when done, never **how** |
| 6 | Plan | AI `plan` | `spec_<feature>_<n>.md` (authoritative), context (including the observed behaviour recorded in step 4), ticket, repo, DB (read-only); may run targeted checks for design questions but does not redo the reproduction; includes self plan-review (incremental, modular; big changes as suggestions at the end) and the communicator pass. Never re-derives requirements; if the spec is ambiguous or contradicts the code it writes the question into the plan instead of resolving it silently | `runs/<feature>_<n>/plan_<feature>_<n>.md` (long: architecture, then low-level detail per change), `runs/<feature>_<n>/plan_short_<feature>_<n>.md` (concise, for human review; its `## Architecture` lists the modules created or modified, the new or changed interfaces with inputs, outputs and callers, and the data flow) |
| 7 | Review spec and plan — **GATE 1** | **H** | `spec_<feature>_<n>.md` ("is this what I asked for"), `plan_short_<feature>_<n>.md` and `plan_<feature>_<n>.md` ("is this how I'd build it", architecture first: modules, interfaces, data flow), the human's reply (5.7: the run pauses; through AgentHub the reply reaches an AI user, which follows the `plan` chat rules: edits applied on approval) | approved edits written as new versions (`spec_<feature>_<n>_v2.md`, `plan_<feature>_<n>_v2.md`); the gate is released and the orchestrator continues |
| 8 | Build test cases | AI `testcase-builder` | spec (acceptance criteria), plan, context | `runs/<feature>_<n>/testing_<feature>_<n>.md`: 5–10 ephemeral test cases, each tied to an acceptance criterion. Each case states its kind: unit test, eval or UI test, chosen by what the criterion requires, and its runner: `code` (unit, eval) for step 13 or `ui` for step 13b. Ephemeral means they live in the run folder, not in the project repo |
| 9 | Build | AI `build-plan` | spec, latest `plan_<feature>_<n>[_v<k>].md`, context, worktree | one commit on the feature branch at the end of the step (one per loop iteration), message referencing the run id and plan version; may add run/test instructions the change introduces to `agentmds/<project>/AGENTS.md` |
| 10 | Code review | AI `code-review` | `base_branch`, feature branch, spec, plan | `runs/<feature>_<n>/review_<feature>_<n>[_v<k>].md`, severity-sorted; includes "does the diff satisfy the spec". A repeat inside the build loop is incremental: it reviews the commits since the last finished review and carries that report's open findings forward, so each report is complete on its own (5.4) |
| 11 | Readability review | AI `readability-review` | diff vs `base_branch`, spec, plan | `runs/<feature>_<n>/readability_<feature>_<n>[_v<k>].md`: same report shape as code review, sorted by severity. Reviews the changes from a cognitive-load perspective: HIGH = changes that are very hard to understand; MEDIUM = understandable with effort; LOW = minor. Each finding carries a concrete suggestion to make the code easier to read (naming, extraction, flattening, removing indirection, comments only where intent is not obvious) |
| 12 | Apply reviews | AI `apply-reviews` | `review_<feature>_<n>[_v<k>].md`, `readability_<feature>_<n>[_v<k>].md`, worktree | commits for code-review HIGH items and readability HIGH and MEDIUM items; `runs/<feature>_<n>/reviews_applied_<feature>_<n>[_v<k>].md` listing applied and skipped per report. Thresholds are workflow defaults (`review_severity_threshold`, `readability_severity_threshold`) |
| 13 | Run tests | AI `run-tests` | `testing_<feature>_<n>.md` (`runner: code` cases only), project tooling per AGENTS.md (test runner, eval runner) | `runs/<feature>_<n>/testing_feedback_<feature>_<n>[_v<k>].md`: pass/fail per code case plus observations; UI cases listed as deferred to 13b. Report only: never edits code, however trivial the fix; every fix goes through triage and build |
| 13b | Run UI tests | AI `run-tests-ui` | `testing_<feature>_<n>.md` (`runner: ui` cases only), the app started per AGENTS.md, a browser: the step's session is given the Playwright MCP server (`mcp_servers` of step 13b in `workflow.yaml`, written to `runs/<feature>_<n>/log/mcp_13b.json` and passed as `--mcp-config`), headless in a fresh in-memory profile, so it needs neither the human's Chrome nor an extension | `runs/<feature>_<n>/testing_feedback_ui_<feature>_<n>[_v<k>].md`: pass/fail per UI case with a screenshot per case under `runs/<feature>_<n>/ui_<feature>_<n>_iter<i>/`, UI writes made, observations. Report only, same rule as 13. With no UI cases it writes `total: 0` and the run moves on |
| 14 | Triage results | AI `triage` | all `*_<feature>_<n>*.md` files | decision `done` → step 15; decision `new_plan` → `runs/<feature>_<n>/plan_<feature>_<n>_v<k+1>.md` and back to step 9; decision `spec_issue` (a failure traces back to the spec itself) → ask the human (5.7); spec or plan are edited only on the human's approval and the answer is recorded in `runs/<feature>_<n>/decision_<feature>_<n>_v<k>.md`; the orchestrator re-enters at 6, 9 or 14 depending on what changed (5.7). Loop cap from workflow defaults (3 in `feature-v1`) triggers the same question |
| 15 | Fix AI comments | AI `fix_ai_comments` | `base_branch`, worktree | commits |
| 15b | Regression testing report | AI `regression-testing-report` | base commit (merge-base with `base_branch`) vs branch head, the eval suites the run's test cases touched, the regression procedure and shared results directory from AGENTS.md | `runs/<feature>_<n>/regression_<feature>_<n>.csv` (per suite and `OVERALL`: cases, repetitions per case, accuracy and mean case time per side, deltas, server paths of both result sets) and `regression_report_<feature>_<n>.md` (runs, deltas, regressed cases, caveats); both result sets uploaded to the project's shared results directory. Report only. Skipped with `defaults.regression: never`; with no suite to compare it writes `status: not_applicable` and a header-only CSV |
| 15c | LangSmith cleanup | AI `langsmith-cleanup` | the run id as scratch owner, the project's scratch commands from AGENTS.md | `runs/<feature>_<n>/langsmith_cleanup_<feature>_<n>.md`: datasets listed before, deleted, listed after. Deletes only the scratch datasets owned by the run id (created by 13 and 15b); never canonical datasets, result files or the server. Skipped with `defaults.langsmith_cleanup: never`, set in the `defaults` of a project that creates no scratch datasets (section 6.1) |
| 16 | Final report | AI `final-report` | all `*_<feature>_<n>*.md`, diff vs `base_branch` | `runs/<feature>_<n>/final_report_<feature>_<n>.md`: concise changes, acceptance criteria met, how to test manually, regression testing summary with the CSV link |
| 17 | Explain diff | AI `explain-diff-html` | diff vs `base_branch` | `runs/<feature>_<n>/explain_diff_<feature>_<n>.html` |
| 18 | Write run log | orchestrator | `state.json`, transcripts | `workflow_logs/<run-id>.log` (section 5.5) |
| 18b | Push branch | orchestrator | feature branch `<feature>_<n>` in the worktree | `git push --set-upstream origin <feature>_<n>`: the branch is on the project's remote when the human reaches GATE 2. Plain push, never forced. A push git rejects ends the run `failed`; `agenthub-harness resume` retries the step. Skipped with `defaults.push: never` |
| 19 | Read report — **GATE 2** | **H** | `final_report_<feature>_<n>.md`, `regression_<feature>_<n>.csv`, `explain_diff_<feature>_<n>.html` | PR opened by the human (and the push, when 18b was skipped). Never merged into `base_branch` by the agent |

Graph:

```
 1 H ticket ──► 2 H start ──► 4 build-context ──► 5 spec ──► 6 plan ──► 7 H GATE 1
                                                                            │
            ┌───────────────────────────────────────────────────────────────┘
            ▼
    8 testcase-builder ──► 9 build ──► 10 code-review ──► 11 readability-review ──► 12 apply-reviews ──► 13 run-tests ──► 13b run-tests-ui ──► 14 triage
                           ▲                                                                                                │
                           └──────────────── new_plan (plan_<feature>_<n>_v<k+1>.md) ◄──────────────────────────────────────┤ done
                                                                                                spec_issue → 🔔 chat human ◄─┤
                                                                                                                            ▼
                                  15 fix-ai-comments ──► 15b regression-testing-report ──► 15c langsmith-cleanup ──► 16 final-report ──► 17 explain-diff ──► 18 log ──► 18b push ──► 19 H GATE 2
```

Decisions (where this departs from the literal notes):

- **Spec is a separate step and skill from plan.** The notes go straight from context to plan. Spec-driven practice (GitHub Spec Kit, Kiro) separates *what* (spec: scope, acceptance criteria, non-goals) from *how* (plan: design, files, sequence). The spec is written once per run and frozen unless a human edits it; the plan is regenerated on every loop iteration. Test cases and code review check against the spec, so they validate intent rather than the agent's own plan. The step is skippable per workflow for tiny tickets (`defaults.yaml: spec: always|auto|never`, where `auto` skips when the ticket is under a fixed size and has no open questions); the skill itself always produces a full spec when called. `feature-v1` uses `always`.
- **Reproduction moved from plan to build-context.** The notes put "test current behaviour in UI / evals, read in DB" under plan. With a spec step in between, the spec needs observed current behaviour to write acceptance criteria, so build-context does it (4.5). Plan reads the result instead of repeating it.
- Plan review and plan communicator are sub-steps of `plan`. They always run together and share inputs.
- Readability review is a separate step after code review, with its own skill and report. Code review looks for defects; readability review looks at cognitive load and proposes simplifications. Separate passes keep each focused, and the two reports have different apply thresholds.
- Apply-reviews is its own step so its threshold decisions are visible in the state graph: code-review items are applied at HIGH only (a bug), readability items at MEDIUM and above (reading cost compounds over the life of the code, and a readability fix carries little risk). Both thresholds are run parameters from `defaults.yaml`, overridable per run, never hard-coded in the skills: the skills report every severity, and `apply-reviews` receives the thresholds in its invocation.
- Code review repeats incrementally. The first review of a run covers the whole branch. When the build loop comes back to step 10, the review covers the commits since the last finished review (the fix from build and the commits of apply-reviews), checks which earlier findings are fixed and carries the open ones forward. Measured on the first run that looped: the branch had 5,121 changed lines, the two later reviews had 176 and 73 new ones, and each took over 30 minutes because it reviewed everything again. The review goes back to the whole branch when the new commits exceed `review_incremental_max_lines` or `review_incremental_max_share` of the branch diff, and after a new spec version, because the requirements checklist changed. Step 13 still runs the test cases on every iteration, which is what catches a fix that breaks code outside the lines it touched.
- Triage decides, writes a new plan, or asks the human when the spec is in question. Autonomous steps never edit the spec; after the human's reply, spec or plan change only through an edit the human approves, proposed as a high-level summary (5.7). It never edits code or test cases; all code edits go through build.
- The notes have no loop exit besides "no more changes". A loop cap is added.
- Explain-diff output goes to the run folder as `explain_diff_<feature>_<n>.html`, not into the project's `docs/`, so it follows the tracking rule and stays out of the PR. (Existing skill writes to `<project>/docs/diffs_explained/`; the step prompt overrides the destination.)
- Regression testing is outside the loop and runs once, after the last build and the comment cleanup, as step 15b: base commit vs branch head on the eval suites the run touched, with the project's two-ref procedure from AGENTS.md. Its CSV of deltas is summarised in the final report, so GATE 2 reads regression results instead of producing them. `defaults.regression: never` skips the step and the report says so; the human can still run the project regression skills by hand at GATE 2.
- The feature branch is pushed by the orchestrator as step 18b, before GATE 2, so the human reviews the result with the branch already on the remote and opens the PR from there. It is an orchestrator action, not a skill: skills and chats still never push, and nothing is ever merged into the base branch. GATE 2 has no reject path, so the push does not wait for it; `defaults.push: never` keeps a run's branch local.

---

## 3. Layout

```
<code root>/                   HARNESS_ROOT: the AgentHub repo
  agentmds/
    GENERAL.md                 rules for every project
  skills/
    general/                   shared skills (section 4)
  workflows/
    feature-v1/                one directory per workflow (section 5.4)
  observability/
    otel.env                   telemetry variables for every step (section 5.6)
  harness/                     the orchestrator source, hooks and tests
  docs/
    WORKFLOW_SPEC.md
    harness_reviews/           <date>_harness_review.md from improve-harness (4.7)
<private root>/                HARNESS_PRIVATE_ROOT: private/ in AgentHub
  harness.yaml                 manifest: projects, their AGENTS.md and skills (section 6)
  agents.md                    read by every AI user and every step
  .env                         collector port and SigNoz API key (5.6); never in the public repo
  agentmds/
    webapp/AGENTS.md
  skills/
    projects/webapp/           project-specific skills
<data root>/                   HARNESS_DATA_ROOT: data/orchestrator/ in AgentHub
  tickets/                     <feature>.md  hand-written (step 1), shared by all runs
  runs/                        one folder per run, everything the run produced
    <feature>_<n>/
      ticket_<feature>_<n>[_v<k>].md         frozen copy of the ticket at run start; later versions only after the human's approval (5.7)
      context_<feature>_<n>.md               step 4
      spec_<feature>_<n>[_v<k>].md           step 5; later versions only after the human's approval (5.7)
      plan_<feature>_<n>[_v<k>].md, plan_short_<feature>_<n>[_v<k>].md
      testing_<feature>_<n>[_v<k>].md, testing_feedback_<feature>_<n>[_v<k>].md
      review_<feature>_<n>[_v<k>].md, readability_<feature>_<n>[_v<k>].md, reviews_applied_<feature>_<n>[_v<k>].md
      final_report_<feature>_<n>.md, explain_diff_<feature>_<n>.html
      state.json                             orchestrator state (section 5.2)
      log/                                   step transcripts
      decision_<feature>_<n>_v<k>.md         questions to the human and approved edits (5.7)
  workflow_logs/               <feature>_<n>.log  durable index per run (step 18)
  worktrees/                   <project>/.base/ main clone; <project>/<feature>_<n>/ worktrees
  archived/                    <yyyy-mm-dd>_<feature>_<n>/ (section 4.4)
```

The private and the data root default to the code root, so one folder holding everything still works. Workflow `reads` and `writes` patterns (`runs/...`) resolve under the data root.

In AgentHub the data root is untracked. A harness whose data root is a git folder commits the run folders except `log/` (one gitignore line: `runs/*/log/`): the md files are small and are the record of what the agent decided; transcripts are large and stay on disk only.

Ticket file format:

```markdown
---
project: webapp
base_branch: dev
---
# <title>
<ticket body, written by hand>
```

Spec file shape (step 5):

```markdown
# <feature> — spec
## Goal            one paragraph: why this exists
## In scope        bullet list
## Out of scope    bullet list (explicit, because agents scope-creep)
## Acceptance criteria
AC1. WHEN <event/condition> THEN the system SHALL <observable behaviour>
AC2. ...
## Open questions  anything the ticket + context could not settle; the human answers at GATE 1
```

Context file shape (step 4):

```markdown
# <feature> — context
## Ticket summary        symptom or requested behaviour, entry point, concrete example from the ticket
## Code                  entry points and call chain: UI → API → agent graph / prompt → DB query, with file paths
## Data                  what the DB holds for the example (read-only), relevant tables and fields
## Current behaviour     observed, not inferred: exact inputs used, what happened, expected vs actual
                         status: reproduced | not reproduced | not applicable (new feature; current behaviour of the area described instead)
## Related evals/tests   suites and test files that cover the area
## Risks and unknowns
## Commands run          every command used, so plan and the human can rerun them
## Run cost              see section 4.6
```

---

## 4. Skills

### 4.1 Existing skills, classified

| Skill | Scope | Verdict |
|---|---|---|
| `code-review` | general | Keep general. Project review conventions (for example a unit-test comment rule and its exceptions) are not in the skill: it enforces the repository's unit-test conventions from AGENTS.md. Already honours inputs given in the invocation, so it runs non-interactively when the orchestrator passes the base branch. Its optional "feature context" input receives the spec. |
| `fix_ai_comments` | general | Keep as is. |
| `explain-diff-html` | general | Keep. Destination overridden by the step prompt to `runs/<feature>_<n>/explain_diff_<feature>_<n>.html`. |

Project-specific skills (a project's own eval runners, for example) live in `skills/projects/<project>/` in the private root; eval runs inside a agenthub-harness run are covered by the regression skills and by the eval instructions in the project AGENTS.md.

### 4.2 Skills to create (general)

| Skill | Step | Inputs | Output |
|---|---|---|---|
| `build-context` | 4 | ticket, repo, DB (ro), AGENTS.md, app/evals (ro) | `runs/<feature>_<n>/context_<feature>_<n>.md`; possibly additions to `agentmds/<project>/AGENTS.md` (4.5) |
| `spec` | 5 | ticket, context | `runs/<feature>_<n>/spec_<feature>_<n>.md` |
| `plan` | 6 | spec, context, ticket, repo, DB (ro) | `runs/<feature>_<n>/plan_<feature>_<n>.md`, `runs/<feature>_<n>/plan_short_<feature>_<n>.md` |
| `testcase-builder` | 8 | spec, plan, context | `runs/<feature>_<n>/testing_<feature>_<n>.md` (each case with `runner: code|ui`) |
| `build-plan` | 9 | spec, latest plan, context, worktree | one commit at the end of the step; possibly additions to `agentmds/<project>/AGENTS.md` |
| `readability-review` | 11 | diff, spec, plan | `runs/<feature>_<n>/readability_<feature>_<n>[_v<k>].md` |
| `apply-reviews` | 12 | review, readability report, worktree, thresholds | commits, `runs/<feature>_<n>/reviews_applied_<feature>_<n>[_v<k>].md` |
| `run-tests` | 13 | testing file (`runner: code` cases), project tooling per AGENTS.md | `runs/<feature>_<n>/testing_feedback_<feature>_<n>[_v<k>].md` |
| `run-tests-ui` | 13b | testing file (`runner: ui` cases), the app per AGENTS.md, the Playwright MCP tools | `runs/<feature>_<n>/testing_feedback_ui_<feature>_<n>[_v<k>].md`, screenshots under `ui_<feature>_<n>_iter<i>/` |
| `regression-testing-report` | 15b | base and modified commits, the suites: from the testing file and feedback (`feature-v1`) or the selection and workers the invocation names (`regression-v1`), AGENTS.md regression procedure and shared results directory | `runs/<feature>_<n>/regression_<feature>_<n>[_v<k>].csv`, `runs/<feature>_<n>/regression_report_<feature>_<n>[_v<k>].md`; result files copied to the project's shared results directory |
| `langsmith-cleanup` | 15c | run id (scratch owner), AGENTS.md scratch commands | `runs/<feature>_<n>/langsmith_cleanup_<feature>_<n>[_v<k>].md`; the run's scratch datasets deleted in LangSmith |
| `triage` | 14 | all feature md files; in chat mode, the human | `runs/<feature>_<n>/decision_<feature>_<n>_v<k>.md` (decision, reasoning, question for the human when `spec_issue`), `runs/<feature>_<n>/plan_<feature>_<n>_v<k+1>.md` when `new_plan` |
| `final-report` | 16 | all feature md files (regression report included), regression CSV path, diff | `runs/<feature>_<n>/final_report_<feature>_<n>.md` |
| `regression-final-report` | 16 in `regression-v1` | ticket copy, regression report, delta CSV, cleanup report | `runs/<feature>_<n>/final_report_<feature>_<n>.md` (section 10) |
| `archive-old-work` | manual | age | `archived/<date>_<feature>_<n>/` (4.4) |
| `obs-query` | manual | a question about runs, steps, cost, failures | answer built from SigNoz via its MCP server (5.6); checks the external collector and never starts anything |
| `improve-harness` | manual | period (default: since the last review) | `docs/harness_reviews/<date>_harness_review.md`: findings across recent runs and proposed harness changes; applies a change only on explicit approval (4.7) |
| `onboard-project` | manual, launched by `agenthub-harness project add` | the project's base clone, the harness's existing AGENTS.md and skills for the project if any, the human | filled `agentmds/<project>/AGENTS.md`, `setup` list in `harness.yaml`, verified in a scratch worktree (6.3) |

Project know-how never lives in these skills; they read it from the project AGENTS.md. Tunables never live in them either: `code-review` and `readability-review` report findings at every severity, and the thresholds that decide what `apply-reviews` applies are run parameters passed in the invocation (`review_severity_threshold`, `readability_severity_threshold`). Every skill is non-interactive when all inputs are given in the invocation and interactive when you call it by hand.

`spec` skill rules: product judgement only, no design. Resolve ambiguity in the ticket where the context makes the answer clear; otherwise list it under open questions. Every acceptance criterion must be observable through the UI, an API response, a DB state or an eval, so `testcase-builder` can turn it into a test one-to-one. Target under two pages; if it cannot fit, say the ticket should be split.

### 4.3 Project prerequisite (step 3)

The project AGENTS.md must document what the steps need to verify a change: how to start the app and test a feature in the UI, how to run evals, how to run companion repos or tools the project depends on (where they live, how to run them, when a change needs them re-run), DB access rules, branching rules.

Companion tools are project-specific, so they are not harness steps. Skills reach them the same way they reach evals: `build-context` and `run-tests` read the project AGENTS.md and run whatever it documents for verifying a change. If the AGENTS.md does not mention a tool, the harness never runs it.

### 4.4 `archive-old-work`

Invoked manually (`/archive-old-work 2 weeks`, or `--feature <feature>` to archive one feature regardless of age). Not a workflow step.

1. Ask for the age if not given (`days`, `weeks`, `months`). Runs whose log `ended` line is older than `now - age` are in scope.
2. Find runs by reading `workflow_logs/*.log`; the header gives feature, run id and project.
3. Move (not copy) the whole run folder, its log and its worktree into one archive folder:
   ```
   archived/<yyyy-mm-dd>_<feature>_<n>/
     <feature>_<n>.log                  from workflow_logs/
     run/                               runs/<feature>_<n>/ moved as is (artifacts, state.json, log/)
     worktree.zip                       zipped worktrees/<project>/<feature>_<n>/
   ```
   `<yyyy-mm-dd>` is the run's end date. The ticket in `tickets/` is moved into the archive folder only when the last remaining run of that feature is archived; otherwise it stays, since other runs still reference it.
4. Tracked files use `git mv`; untracked files are plain moves.
5. The worktree is zipped into `worktree.zip` (excluding `.venv`, `node_modules` and other dependency folders), the zip is verified, then the worktree is removed with `git worktree remove`. Unpushed commits or uncommitted changes are reported and confirmed with the human first, since the zip becomes the only copy. Branches are never deleted.
6. Never archive a run that is `running`, waiting on the human, or paused, whatever its age.
7. End with a summary: runs archived, folders created, size moved, size of each zip.

Edge cases: a run that crashed before writing a log is reported and skipped. When the data root is a git folder, `archived/` keeps in git what was committed before the move (the `.log`, the ticket, and the run's md files) and ignores `run/log/` and `worktree.zip`.

### 4.5 `build-context`

Phases, in order. Read-only throughout: no code edits, no DB writes, no writes to the dev server. The only file it may write besides its output is the project's AGENTS.md in the private root (phase 3).

1. **Parse the ticket.** Symptom or requested behaviour, user-visible entry point, concrete examples (a query, a filter, a record id).
2. **Locate the code.** From the entry point inward: UI component, API route, agent graph node, prompt, DB query. Record file paths and the call chain.
3. **Read supporting material.** Project docs, recent git history on the touched files, existing evals and tests for the area, and `agentmds/<project>/AGENTS.md`.
   The project AGENTS.md **must** contain how to run the project and how to test it (start the app, open its UIs, run evals, run checks). If any of that is missing or does not work:
   - gather it from the repo (README, launch scripts, launch configs, Makefiles, CI files) and verify it by running it;
   - if it still cannot be established, ask the human (5.7) to fill the gap;
   - then document what was learned in `agentmds/<project>/AGENTS.md`, concisely and in the file's existing style, so no later step or run has to rediscover it. This is the only write the skill makes outside the run folder, and it is to the AGENTS.md in the private root, never to a remote machine.
4. **Read the DB.** Through the read-only tunnel: confirm the records in the ticket's examples exist and what their fields hold. Never write.
5. **Reproduce.** Start the app as AGENTS.md documents and walk through the scenario in the UI, or run the relevant eval suite when the ticket is about agent behaviour. Record the exact inputs and what happened. Outcomes:
   - `reproduced`: observed vs expected, with inputs.
   - `not reproduced`: what was tried. The orchestrator asks the human (5.7), since the ticket's premise is in doubt.
   - `not applicable`: new feature with nothing to reproduce. Describe the current behaviour of the area that will change instead.
   Time budget: about 15 minutes on this phase, then record what was found and move on. If the app will not start, report it and continue with static context; do not fix the environment.
6. **Write `context_<feature>_<n>.md`** in the shape given in section 3, ending with the run-cost section (4.6).

### 4.6 Run cost reporting (every skill that runs the project)

A project under development may itself be an LLM application: starting it, clicking through the UI and running evals all trigger LLM calls that cost money and time. Every skill that runs the app, its UIs or evals must end its output file with:

```markdown
## Run cost
- project runs:    <what was run: app session, eval suites, checks>
- wall time:       <time spent running the project, e.g. 11m 40s>
- LLM usage:       <approximate: calls, tokens or $, whichever the project already exposes>
- source:          <where the number came from, e.g. the eval platform's run summary, the test runner's output, app log>
```

Rules:

- **Use what the project already exposes.** Eval-platform run summaries, the eval runner's result tables, the app's own logs. Do not add instrumentation, wrappers or counters to the project to obtain this. If nothing is available, write `LLM usage: not available` and say why.
- A rough number is enough. Order of magnitude matters, precision does not.
- This is the cost **of running the project**, not of running the harness or the Claude session that performs the step. Harness-side timing is recorded by the orchestrator separately (5.5).
- Applies to: `build-context`, `plan` (when it runs anything), `run-tests`, `regression-testing-report`, and any project skill that runs evals. Skills that only read or edit code report `project runs: none`.
- The orchestrator parses this section and copies it into `state.json` for the step and into the run log (5.5), so the log shows per step both the harness duration and the project-side cost.

---

### 4.7 `improve-harness`

Invoked by hand in an ordinary Claude session (`/improve-harness`, or asking Claude to review recent runs), never from inside a run. It is the feedback loop for the harness itself.

Inputs, for the given period (default: every run since the previous review file):

- `workflow_logs/*.log`: step durations, iterations per run, where runs looped, paused or were blocked, project run costs.
- `runs/*/decision_*.md`: the questions the human had to answer and the edits that resulted. Repeated questions of the same kind point at a skill or ticket template that should pre-empt them.
- `runs/*/final_report_*.md`, feedback sections: what each run said about the workflow.
- `runs/*/testing_feedback_*.md`, `review_*.md` and `readability_*.md`: recurring failure classes and recurring readability problems.
- `git log` of the harness: what changed since the previous review, so improvements already made are not proposed again.
- SigNoz, through `obs-query`, when a finding needs numbers the logs do not hold.

Output: `docs/harness_reviews/<date>_harness_review.md` with, in order: runs covered; metrics (runs, mean iterations, mean duration, human wait time, blocked runs, project cost totals) compared with the previous review; findings, each tied to the evidence; proposed changes, each as a concrete diff to a skill, prompt, workflow default, AGENTS.md or the orchestrator, ranked by expected effect. Never a rewrite: one proposal per problem, smallest change that addresses it.

Applying changes: the skill proposes; the human approves each change separately; the skill then applies it and commits it on its own, with the review file linked in the commit message. Changes never go into a running workflow definition: a new workflow version directory is created when a default or step changes (`workflows/<name>-v<k+1>/`), so completed runs remain reproducible against the version they ran on.

Not a CLI command. The CLI belongs to the orchestrator's own operations (run, resume, status, obs, link). This skill is a conversation with judgement in it, like `archive-old-work` and `obs-query`, and an `agenthub-harness improve` command would only wrap `claude` with the skill name. If a shortcut is wanted later, one generic `agenthub-harness skill <name> [args]` covers every manual skill rather than a command per skill.

---

## 5. Orchestrator

### 5.1 Shape

A thin Python orchestrator owns the graph, loaded from `workflows/<workflow-name>/workflow.yaml`. Each AI step is a fresh `claude -p` invocation with the step prompt, the skill name and explicit input/output paths. State is `runs/<run-id>/state.json`, written by the orchestrator only. Human gates and questions: the orchestrator records the question in a decision file and pauses the run (`on_question: pause`, the default); AgentHub surfaces it and resumes the run with `agenthub-harness resume <run-id>` once the answer is recorded (5.7). A step that stopped unfinished is continued in its own session (5.8). When that is not possible, steps are idempotent so resume can re-run the current step from scratch; the re-run writes the next `_v<k>` (section 1), never over the interrupted output.

(The alternative, one long Claude session following a workflow skill, was rejected: state lives only in the conversation, hard to resume, hard to visualize, context grows across steps.)

**What the orchestrator is.** A Python CLI in the AgentHub repo (`agenthub-harness run | resume | status | obs | link | project | verify-auth`), a few hundred lines, no intelligence of its own: it sequences skills, keeps state, routes, and handles housekeeping (run numbers, worktrees, telemetry probe, console graph, run log, the push of the feature branch). `run` and `resume` refuse when `AGENTHUB_TASK_TOKEN` is set, that is inside an AI user's session; there the commands are `agenthub harness start` and `agenthub harness resume`, and the AgentHub server spawns the copy. Steps run with `--setting-sources project,local`, so the human's user settings do not reach them. It spawns the same `claude` binary the human uses, so autonomous steps authenticate with the logged-in Claude Code account and count against its plan usage. Setting `ANTHROPIC_API_KEY` in a step's environment switches that step to API billing; `defaults.yaml: auth: account | api_key` per workflow, default `account`. First thing to verify at build time: the keychain credential is reachable from a process the script launches.

**Write boundary.** The orchestrator writes only to `runs/`, `workflow_logs/` and `worktrees/` under the data root, and pushes one ref, the run's feature branch, to the project's `origin` (step 18b). Steps it launches may write only to their worktree, their run folder, and `agentmds/<project>/AGENTS.md` (build-context gap-filling, 4.5; build-plan, for run/test instructions its change introduces; chat edits to spec/plan/ticket copy, 5.7). Nothing in a run may edit the skills (`skills/general/` under the code root, `skills/projects/` under the private root), `workflows/`, `agentmds/GENERAL.md`, `harness.yaml` or the orchestrator source: a run that edits a skill changes every future run without review, and one that edits its own workflow can change its routing or loop cap mid-flight. Enforced, not just instructed: each step is launched with a Claude Code settings file whose permission rules deny `Edit`/`Write` on those paths, and a hook checks its Bash commands by path (section 9). `harness_commit` in `state.json` ties every run to the harness version that produced it. Harness improvements are made in an ordinary session, by the human or with the manual `improve-harness` skill (4.7), never from inside a run.

### 5.2 State file

```json
{
  "run_id": "filter-recovery_1",
  "workflow": "feature-v1",
  "feature": "filter-recovery",
  "project": "webapp",
  "base_branch": "dev",
  "harness_commit": "0a763e8",
  "iteration": 2,
  "max_iterations": 3,
  "spec_revisions": 0,
  "waiting_on_human": null,
  "current": "13",
  "started": "2026-11-07T14:02:11Z",
  "steps": {
    "4":  {"status": "done", "started": "…", "ended": "…", "in": ["tickets/filter-recovery.md"], "out": ["runs/filter-recovery_1/context_filter-recovery_1.md"],
           "project_cost": {"runs": "app session + eval suite results-ot", "wall_time": "11m 40s", "llm_usage": "~38 calls, ~210k tokens", "source": "eval run summary"}},
    "5":  {"status": "done", "out": ["runs/filter-recovery_1/spec_filter-recovery_1.md"]},
    "6":  {"status": "done", "out": ["runs/filter-recovery_1/plan_filter-recovery_1.md", "runs/filter-recovery_1/plan_short_filter-recovery_1.md"]},
    "7":  {"status": "done", "gate": true, "reached": "…", "released": "…"},
    "8":  {"status": "done"},
    "9":  {"status": "done", "runs": 2},
    "10": {"status": "done", "runs": 2, "outcome": "2 high, 5 medium"},
    "11": {"status": "done", "runs": 2, "outcome": "1 high, 3 medium, 4 low"},
    "12": {"status": "done", "runs": 2, "outcome": "review 2 applied / 5 skipped · readability 4 applied / 4 skipped"},
    "13": {"status": "running", "started": "…"},
    "14": {"status": "pending"},
    "15": {"status": "pending"}, "16": {"status": "pending"}, "17": {"status": "pending"}, "18": {"status": "pending"}, "19": {"status": "pending"}
  }
}
```

### 5.3 Console rendering

`agenthub-harness status <run-id>`, also printed before every step:

```
run filter-recovery_1 · workflow feature-v1 · feature filter-recovery · webapp · base: dev · iteration 2/3 · telemetry: on

 intake
   ✔  1 H ticket               tickets/filter-recovery.md
   ✔  2 H start                worktrees/webapp/filter-recovery_1
 planning
   ✔  4 build-context          runs/filter-recovery_1/context_filter-recovery_1.md
   ✔  5 spec                   runs/filter-recovery_1/spec_filter-recovery_1.md (6 acceptance criteria)
   ✔  6 plan                   runs/filter-recovery_1/plan_filter-recovery_1.md, plan_short_filter-recovery_1.md
   ✔  7 H GATE 1               released 14:31
 test cases
   ✔  8 testcase-builder       runs/filter-recovery_1/testing_filter-recovery_1.md
 build loop  ↻ 2
   ✔  9 build-plan             2 commits (1 per iteration)
   ✔ 10 code-review            runs/filter-recovery_1/review_filter-recovery_1_v2.md (2 high, 5 medium)
   ✔ 11 readability-review     runs/filter-recovery_1/readability_filter-recovery_1_v2.md (1 high, 3 medium, 4 low)
   ✔ 12 apply-reviews          review 2/7 · readability 4/8 applied
   ▶ 13 run-tests              running 00:04:12
   ○ 14 triage
 finish
   ○ 15 fix-ai-comments
   ○ 15b regression-testing-report
   ○ 15c langsmith-cleanup
   ○ 16 final-report
   ○ 17 explain-diff-html
   ○ 18 run log
   ○ 18b push
   ○ 19 H GATE 2

next: 12 → 13
```

Glyphs: `✔` done, `▶` running, `○` pending, `✖` failed, `⏸` waiting on human, `↻` loop count, `H` human step, `–` skipped (for example step 5 when `spec: auto` skips it). `--watch` redraws on change; `--log <step>` tails that step's transcript.

### 5.4 Workflow directory

One directory per workflow. A workflow changes in place, one commit per change: `harness_commit` in `state.json` ties a run to the workflow text it started on, and a run resumed after an edit continues on the edited workflow. Copying the directory under a new name is a complete fork, made only when two processes are wanted side by side (`regression-v1` next to `feature-v1`).

```
workflows/feature-v1/
  workflow.yaml        the graph: ordered steps, skill per step, inputs/outputs, gates, loop edges, loop cap
  defaults.yaml        tunables: max_iterations (3), spec (always|auto|never; always), review_severity_threshold (high), readability_severity_threshold (medium),
                       review_scope (incremental|full; incremental), review_incremental_max_lines (400), review_incremental_max_share (0.25),
                       test_subset_on_retry (smoke|full), regression (always|never), regression_repetitions, langsmith_cleanup (always|never), push (always|never),
                       on_question (pause|chat; pause), on_rate_limit (wait|pause; wait), step_continuations (3),
                       model per step, effort per step, timeouts
  prompts/             one file per AI step: the exact text passed to `claude -p`
    04-build-context.md
    05-spec.md
    06-plan.md
    ...
  templates/           optional output templates (spec, plan, testing, final report) for a stable shape across runs
  README.md            what the workflow is and how its files fit together
```

Rules: `reads` and `writes` patterns resolve under the data root; a `reads` pattern ending in `*.md` resolves to the highest `_v<k>` version present (section 1). `workflow.yaml` references skills by name only; skills are shared and never copied into a workflow. Behaviour differences between workflows go in `prompts/`. `defaults.yaml` can be overridden for every run of a project (`defaults` under the project in `harness.yaml`, section 6.1) and per run on the command line (`--set`, which wins over both); the effective values are copied into `state.json`. A step with `skip_when: defaults.<key>` is skipped when that value is `never`. The run records the harness commit, so any run traces back to the exact prompt text it used.

Incremental repeats: a step may name an `incremental_prompt` next to its `prompt` (step 10 does). Each execution of such a step records in `state.json` the worktree commit it covered and the spec version (`scope` in its execution record). A later execution gets the `incremental_prompt`, with that commit, the earlier report and the size of the change, when all of these hold: `review_scope` is `incremental`; an earlier execution finished and its report exists; the spec has had no new version since; the recorded commit is still an ancestor of HEAD; the lines changed since it (added plus deleted) are at most the lower of `review_incremental_max_lines` and `review_incremental_max_share` of the whole branch diff. Otherwise it gets the ordinary `prompt` and covers the whole branch. The reason is printed, kept in `scope.reason`, and an incremental execution ends its outcome line with `incremental since <commit>`.

Effort per step: `effort` in `defaults.yaml` has the shape of `model` (a `default` and per-step levels: low, medium, high, xhigh, max; or one level for every step). The orchestrator sets the step's level as `CLAUDE_CODE_EFFORT_LEVEL` in the environment of its `claude -p` process, on every attempt. That variable outranks the levels in the human's own Claude Code settings, which name one per model, and it holds for the subagents the step starts. Without an `effort` entry no level is set and a step runs at the level of those settings, which is also what a run started before the workflow had the entry does. Gate and question chats are the human's own sessions and keep the human's setting. In `feature-v1` plan and build run at xhigh, build-context, spec, test cases, code review and triage at high, and the other steps at medium. Why: every step used to inherit xhigh, and the writing steps alone (plan, test cases, spec) took 167 of the 635 step minutes of the first four runs, nearly all of it model time; the one run made entirely at medium finished in one iteration with those steps several times faster, on a different ticket.

Sketch:

```yaml
name: feature-v1
steps:
  - id: 4
    skill: build-context
    prompt: prompts/04-build-context.md
    reads: ["tickets/{feature}.md"]
    writes: ["runs/{feature}_{n}/context_{feature}_{n}.md"]
  - id: 5
    skill: spec
    prompt: prompts/05-spec.md
    reads: ["tickets/{feature}.md", "runs/{feature}_{n}/context_{feature}_{n}.md"]
    writes: ["runs/{feature}_{n}/spec_{feature}_{n}.md"]
    skip_when: defaults.spec   # always | auto | never
  - id: 6
    skill: plan
    reads: ["runs/{feature}_{n}/spec_{feature}_{n}*.md", "runs/{feature}_{n}/context_{feature}_{n}.md", "tickets/{feature}.md"]
    writes: ["runs/{feature}_{n}/plan_{feature}_{n}.md", "runs/{feature}_{n}/plan_short_{feature}_{n}.md"]
  - id: 7
    gate: human
    message: "Review spec_{feature}_{n}.md and plan_short_{feature}_{n}.md (and plan_{feature}_{n}.md). Ask for changes, then say you are done to continue the run."
    chat_skill: plan   # 5.7
  - id: 8
    skill: testcase-builder
    reads: ["runs/{feature}_{n}/spec_{feature}_{n}*.md", "runs/{feature}_{n}/plan_{feature}_{n}*.md", "runs/{feature}_{n}/context_{feature}_{n}.md"]
    writes: ["runs/{feature}_{n}/testing_{feature}_{n}.md"]
  # ...
  - id: 14
    skill: triage
    reads: ["**/*_{feature}_{n}*.md"]
    writes: ["runs/{feature}_{n}/decision_{feature}_{n}_v{k}.md", "runs/{feature}_{n}/plan_{feature}_{n}_v{next}.md"]
    on_decision: { done: 15, new_plan: 9, spec_issue: chat }   # chat: 5.7
    max_loops: defaults.max_iterations   # cap reached → same chat as spec_issue
    # re-entry after the chat is not declared here; the orchestrator applies the rule in 5.7
```

### 5.5 Run log (`workflow_logs/<run-id>.log`)

Written by the orchestrator when a run ends (done, failed, or loop cap). An index, not a copy: links to artifacts by path relative to the code root (absolute when the data root lies outside it), never their content. Complete even when a step failed because it is built from `state.json`.

Contents, in order:

1. Header: run id, workflow, feature, project, base branch, feature branch, harness commit, whether telemetry was active (`telemetry: on | off`).
2. Timing: start and end date/time, total duration, agent time vs time waiting on human gates, final status. Totals of project-side cost across all steps: project wall time and approximate LLM usage.
3. One block per step execution in run order (looped steps appear once per iteration): id, skill, iteration, started, ended, duration, input paths, output paths or commits, one-line outcome, transcript path, and the project-side run cost (4.6): project wall time and approximate LLM usage, or `none` for steps that did not run the project.
4. Outputs of the whole run: final report, explain-diff HTML, feature branch and commit range.
5. Gates: reached and released times.

```
run        filter-recovery_1
workflow   feature-v1
feature    filter-recovery      ticket: tickets/filter-recovery.md
project    webapp    base: dev    branch: filter-recovery_1
harness    0a763e8
telemetry  on

started    2026-11-07 14:02:11
ended      2026-11-07 16:48:37
duration   2h 46m 26s   (agent 1h 58m, waiting on human 48m)
project    wall 34m 10s · LLM ~120 calls, ~700k tokens (approx, from the eval platform + eval output)
status     done

──  4  build-context                14:02:11 → 14:21:40  (19m 29s)   reproduced
    in   tickets/filter-recovery.md
    out  runs/filter-recovery_1/context_filter-recovery_1.md
    cost project wall 11m 40s · LLM ~38 calls, ~210k tokens (eval platform)
    log  runs/filter-recovery_1/log/04.txt
──  5  spec                         14:21:40 → 14:26:02  (4m 22s)   6 acceptance criteria, 1 open question
    in   tickets/filter-recovery.md, runs/filter-recovery_1/context_filter-recovery_1.md
    out  runs/filter-recovery_1/spec_filter-recovery_1.md
    cost project none
──  6  plan                         14:26:02 → 14:31:02  (5m 00s)
    in   runs/filter-recovery_1/spec_filter-recovery_1.md, runs/filter-recovery_1/context_filter-recovery_1.md
    out  runs/filter-recovery_1/plan_filter-recovery_1.md, runs/filter-recovery_1/plan_short_filter-recovery_1.md
    cost project none
──  7  H gate 1                     14:31:02 → 15:19:45  (waited 48m 43s)
──  8  testcase-builder             15:19:45 → 15:24:10  (4m 25s)
    out  runs/filter-recovery_1/testing_filter-recovery_1.md
    cost project none
…
── 13  run-tests         (iter 1)   …   8/10 pass
    out  runs/filter-recovery_1/testing_feedback_filter-recovery_1.md
    cost project wall 9m 05s · LLM ~41 calls (app log)
…
── 14  triage            (iter 1)   …   decision: new_plan → runs/filter-recovery_1/plan_filter-recovery_1_v2.md
──  9  build-plan        (iter 2)   …
…
── 17  explain-diff-html            16:44:05 → 16:48:37  (4m 32s)
    out  runs/filter-recovery_1/explain_diff_filter-recovery_1.html

outputs
   report   runs/filter-recovery_1/final_report_filter-recovery_1.md
   diff     runs/filter-recovery_1/explain_diff_filter-recovery_1.html
   branch   filter-recovery_1   (dev..filter-recovery_1, 7 commits)
   run dir  runs/filter-recovery_1/
```

### 5.6 Observability

**Backend:** SigNoz community edition, run outside the copy: the copy never starts, stops or calls Docker, it only sends to a collector that is already up. Free, OpenTelemetry-native, accepts metrics, logs and traces in one place, runs locally. LLM-tracing tools (Langfuse, Phoenix, LangSmith) were considered and rejected for the harness: they are trace-first and would drop Claude Code's cost and token metrics, and a project's own LLM tracing must stay separate from harness data.

**Source of data:** Claude Code's built-in OpenTelemetry exporter. No MCP, no instrumentation: the `claude -p` process pushes OTLP over gRPC to the collector on an interval. The orchestrator sets these variables for every AI step:

```
CLAUDE_CODE_ENABLE_TELEMETRY=1
CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1       # enables trace export (beta)
OTEL_METRICS_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_RESOURCE_ATTRIBUTES=run_id={run_id},feature={feature},run_n={n},step={step},skill={skill},iteration={k},workflow={workflow},project={project},app=agenthub[,task_id={task},ai_user={user}]

# content: everything stays on this machine, so the opt-in flags are on
OTEL_LOG_USER_PROMPTS=1                     # prompt text on the interaction span and user_prompt event
OTEL_LOG_ASSISTANT_RESPONSES=1              # model text blocks (thinking and tool-use blocks excluded)
OTEL_LOG_TOOL_DETAILS=1                     # tool inputs: command, file path, skill name, diff (512 chars per value)
OTEL_LOG_TOOL_CONTENT=1                     # tool outputs as span events: file content, command output
CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH=262144  # per-attribute cap, default 61440
# OTEL_LOG_RAW_API_BODIES stays off: each request body carries the whole conversation so far
```

The resource attributes make every metric, log and span sliceable by run, step, skill, loop iteration and workflow version. `app` is always `agenthub`; `task_id` and `ai_user` are added when `AGENTHUB_TASK_ID` and `AGENTHUB_AI_USER` are set, that is for a run an AgentHub task started.

**Traces.** Each step produces one root span per prompt with child spans for every model request (model, tokens, time to first token, stop reason, retries) and every tool call (tool, duration, permission wait, success). With the content flags above, SigNoz also holds the prompt, the model's text, tool inputs and tool outputs, within the per-attribute cap. That makes the `obs-query` skill able to answer "what did build-context conclude" and not only "how long did it take". It is still not the full record: tool inputs are cut at 512 characters per value, long outputs at the cap, thinking blocks are never exported, the exact request the model saw (system prompt, skill text, history) is only in the raw-body export which stays off, and anything emitted while the collector is down is lost. Ordering is not a gap: spans carry parent ids and timestamps, events carry a sequence number, and both carry the tool-use id, so the order of a step is reconstructable in SigNoz; the transcript just has it in one file. The transcript in `runs/<run-id>/log/` remains the complete record (section 8). Claude Code does not pass `OTEL_*` to subprocesses started from its Bash tool, so the project's own runs (app, evals) are not covered here; their cost is captured by the run-cost section (4.6). The run log therefore carries two costs per step: harness-side (from telemetry) and project-side (from 4.6).

**Layout:**

```
observability/otel.env       (code root) the Claude Code variables above, content flags included (no per-step attrs)
<private root>/.env          OTLP_GRPC_PORT (default 4317), SIGNOZ_UI_PORT, SIGNOZ_API_KEY for the MCP server; never in the public repo
```

**Lifecycle:**

- `agenthub-harness run` and `resume`: probe the collector port, from `OTLP_GRPC_PORT` in `<private root>/.env` (falling back to `observability/.env` of the code root; default 4317). When it answers, every step gets the OTEL variables; when it does not, the run continues without telemetry. Nothing is started or stopped while the run waits on the human or when it ends.
- `harness.yaml: observability: external | off`. Default `external`; the older values `required` and `optional` are read as `external`. `off` skips the probe.
- `agenthub-harness obs status | mcp-config`: whether the collector and the UI answer; the MCP server registration to add to Claude Code.
- Data emitted while the collector is down is lost (Claude Code has no disk buffer). The run log header records whether telemetry was active, so a gap in the dashboards is a known gap.
- **Warning when telemetry is off.** Visible in three places: a console line at run start saying telemetry is off and why (collector not answering, or off in `harness.yaml`); the header of `agenthub-harness status` (`telemetry: off`) so a run inspected later still shows it; and the run log header. The orchestrator probes the collector before every step, so if the collector stops answering mid-run it warns again and `state.json` records from which step onward telemetry was missing (`telemetry: {active: false, since_step: "13"}`), which the run log repeats.

**Asking questions about the data:** via the official SigNoz MCP server (`github.com/SigNoz/signoz-mcp-server`), which exposes tools to search traces, aggregate logs, query metrics and run raw Query Builder queries. Reading is request/response initiated by the model, which is what MCP is for (unlike sending telemetry, which is a background push).

- The MCP server is registered in Claude Code (`claude mcp add-json`, config from `agenthub-harness obs mcp-config`), pointed at the local instance, authenticated with an API key created in SigNoz (Settings → API Keys) and stored in `<private root>/.env`. Pin the MCP server version: tool names have changed between releases.
- One general skill, `obs-query`, knows the harness attribute names (`run_id`, `feature`, `step`, `skill`, `iteration`, `workflow`, `app`, `task_id`, `ai_user`) and translates questions such as "what did `filter-recovery_2` cost per step" or "which step fails most across `feature-v1` runs" into queries. It checks the collector first and says so when it is down; it never starts anything.

**Dashboards to build first** (in the SigNoz UI; the copy imports none): cost and tokens per run; cost per step and per skill; harness duration vs project-side duration per step; failures and loop iterations per workflow version; tool-call counts per skill.

---

### 5.7 Questions to the human: pause, answer, re-entry

Some steps hit a question only the human can answer: `triage` finds that a failure traces back to the spec (`spec_issue`), the loop cap is reached, `build-context` cannot reproduce the ticket, or a setup command fails. GATE 1 and GATE 2 are questions of the same kind. The run does not wait at a terminal. Instead:

1. **Notify and pause** (`on_question: pause`, the default in both workflows). The orchestrator prints the question (and, on macOS, plays a sound and shows a notification unless `HARNESS_NO_NOTIFY=1`, which AgentHub sets), writes it into the next decision file `runs/<feature>_<n>/decision_<feature>_<n>_v<k>.md` with frontmatter `kind: gate | question | setup` and `answered: false`, and the run ends `paused`. There is no timeout.
2. **Answer through AgentHub.** AgentHub surfaces the question (`orchestrator.pending_question` gives it the kind, step, reason, question, decision file and rendered chat prompt). The human's reply reaches an AI user as a ticket comment; the AI user follows the chat rules of the asking skill (`plan` at GATE 1, `triage` for `spec_issue` and the loop cap, `build-context`, `final-report` at GATE 2): when the human agrees on a resolution it **proposes the edit as a high-level summary and applies it only on explicit approval**. The summary is a few plain-language bullets on what changes and why; the human is deciding, not reviewing text, so the diff is shown only when asked. The full diff goes into the decision file as the record. It may change the run's spec, the latest plan or the ticket copy, always by writing the next version (`spec_<feature>_<n>_v2.md`, never in place), so section 1 holds and the pre-edit text stays on disk. It never edits code or test cases: those go through build and testcase-builder so review and tests are not bypassed. It then records the answer under `## Answer` with `answered: true` and runs `agenthub harness resume <run-id>`.
   **Release.** `agenthub-harness resume <run-id>` routes the run from the recorded answer. A question whose decision file does not say `answered: true` stays paused; no chat opens. A gate continues only when `HARNESS_GATE_RELEASE` equals the decision file's name: AgentHub sets it only after the human's reply, so a gate stays paused, even with `answered: true`, until the human has answered.
   **Terminal chat** (`on_question: chat`, kept from the original harness, unused by AgentHub): instead of pausing, the orchestrator launches an interactive Claude session with the same skill, the run artifacts and the question preloaded, under the same rules. The skill writes the decision file with `answered: true` as its last action; a `Stop` hook (`harness/hooks/chat_done.py`) then creates a marker file (`runs/<run-id>/log/chat_done`), and the orchestrator, which waits on the chat process, ends the chat and continues the run. `/exit` or Ctrl+D still ends the chat at any time.
3. **Record.** The skill writes `runs/<feature>_<n>/decision_<feature>_<n>_v<k>.md`: the question, the human's answer, the diff of every approved edit. The run log (5.5) links it.
4. **Route.** The orchestrator, not the skill, picks the re-entry step. When it asks, it records the highest version of the spec, the plan and the ticket copy; once the answer is recorded it looks for new versions and applies the table below. Routing is derived from what actually changed, so `state.json` stays written by the orchestrator only and the skill cannot route itself somewhere surprising.

| New version written after the question | Re-enters at | Why |
|---|---|---|
| Spec | 6 plan | Plan and test cases derive from the spec, so both are regenerated. `plan` writes `plan_<feature>_<n>_v<k+1>.md` as an incremental plan against the code already in the worktree. GATE 1 is reached again. Loop counter resets to 1 and `spec_revisions` is incremented, since a spec fix is not a failed build iteration |
| Only the latest plan | 9 build | Acceptance criteria did not change, so test cases stand. Loop counter not reset |
| Only the ticket copy (step 4 question) | 4 build-context | The premise changed, so context is rebuilt |
| Nothing, but the decision file has an answer | the asking step again (14 or 4) | The answer is injected into the step prompt; `triage` normally returns `new_plan`. A second `spec_issue` for the same question ends the run as `blocked` |
| Nothing and no answer | run stays paused | resume changes nothing until the answer is recorded (with `on_question: chat` it reopens the chat with the same question) |

If several new versions appeared, the earliest step in the table wins (spec beats plan). Every re-entry runs the step from scratch, as 5.1 already requires.

**The spec rule, restated.** "The AI never edits the spec" meant that spec changes are decided by a human, not typed by one. In this design the spec changes only through a diff the human approved in reply to a question, written as a new version and recorded in the decision file. Autonomous steps (`claude -p`) still never touch it.

**Pause or chat.** `defaults.yaml: on_question: pause | chat`, default `pause`. With `chat` the orchestrator opens the terminal chat described above instead of pausing; AgentHub never uses it.

**GATE 1 and GATE 2 use the same mechanism.** GATE 1 is this question with the `plan` chat rules, the same approval rule for spec and plan edits, and the same version-based routing afterwards (new spec version → step 6 again; new plan version or nothing → step 8). GATE 2 follows the `final-report` chat rules for questions about the result; no edits.

### 5.8 Steps that stop unfinished: usage limit, missing output, failure

A step's session is kept when the step stops before its outputs exist. The orchestrator stores the session id as soon as the stream names it and continues that session with `claude -p --resume <session-id>` and the workflow's `continue_prompt` (`prompts/continue-step.md`): why the session stopped, the outputs still owed, and the instruction to go on from what the conversation already holds. A continued step is the same execution: same `_v<k>`, same output names, same transcript file with the new events appended. Its execution record counts `attempts` and keeps the time it sat stopped apart (`waited_s`), so the run log shows working time.

| the step stopped because | what happens |
|---|---|
| the account's usage limit rejected a request (429; the stream's `rate_limit_event` carries the reset time) | `on_rate_limit: wait` (default): the run stays alive, sleeps until the reset plus a minute, then continues the session. `agenthub-harness status` shows `waiting at <step>: usage limit reached, …`. With `pause`, or a reset more than 6 hours away (the weekly limit), the run ends `failed` with the reset time in its error and `agenthub-harness resume` continues the session |
| the session ended normally without writing an output | it is asked for the output in the same session, once per execution. A second time the run fails and resume starts the step over |
| the process failed, timed out or was interrupted | the run ends `failed` (`paused` after Ctrl-C); `agenthub-harness resume` continues the session |
| a continued session stops again with an error | the step starts over in a new session, as the next `_v<k>`, within the same `agenthub-harness run` or `resume`. A second such failure in a row ends the run |

`step_continuations` (default 3) caps how often one execution is continued; with 0, or in a workflow without `continue_prompt`, every resume starts the step over. Each attempt gets the step's full timeout. A continued session reports its running cost total, so the execution's `cost_usd` is the newest figure, not a sum (a lower figure can only come from a process killed before it reported, and is added). `tokens` (`{input, output, cache_creation, cache_read}`, summed over the models of the last result's `modelUsage`) follows the same rule and is saved in `state.json` next to `cost_usd`. Commands and subagents that were still running when the session stopped are not restored; the continue prompt tells the session to start again only what it still needs.

Why: over the first 8 runs, 9 step executions failed and their work was discarded, 100 minutes and $59 of it; 7 of them were the 5-hour usage limit. Not verified against the live CLI: that a session whose last turn ended on a 429 continues cleanly. The last row of the table is the fallback: if the continuation errors, the step starts over, which is what every failure did before.

---

## 6. Loading skills and AGENTS.md per project

### 6.1 Mechanism

Claude Code loads `<repo>/.claude/skills` and `<repo>/CLAUDE.md` for the current repo. The copy puts symlinks and imports there, per worktree, driven by `harness.yaml` in the private root; it writes nothing under the user's home Claude folder:

```yaml
observability: external                      # external | off (5.6)
projects:
  webapp:
    repo: git@github.com:<account>/webapp.git
    default_base: dev
    agentsmd: agentmds/webapp/AGENTS.md      # agentsmd and skills are relative to the private root
    skills: skills/projects/webapp
    setup:                                   # run by step 2 in every new worktree, in order, from its root
      - ./scripts/fetch-env.sh               # secrets, as the project AGENTS.md documents
      - uv sync                              # whatever the project uses: uv sync, npm ci, make setup
  demo:
    # repo, default_base, agentsmd, skills and setup as above
    defaults:                                # optional: defaults.yaml tunables for every run of this project (5.4); `--set` still wins
      langsmith_cleanup: never               # no scratch eval datasets in this project, so step 15c is skipped
```

`link_worktree` (step 2, on every worktree creation; by hand `agenthub-harness link <project> <worktree>`): `<worktree>/.claude/skills/<name>` → each general skill, then each project skill; `<worktree>/CLAUDE.md` with one `@path` import each for `agentmds/GENERAL.md`, the project `AGENTS.md` and `<private root>/agents.md` (when it exists); `.claude/skills/` is added to the worktree's git exclude (`git rev-parse --git-path info/exclude`), so the links never show as changes.

`agentmds/GENERAL.md` documents the three roots and the CLI (`agenthub-harness run | resume | status`, `agenthub-harness obs status | mcp-config`, `agenthub-harness link <project> <worktree>`, `agenthub-harness project add | list`, `agenthub-harness --help`) so every step and AI user session knows the commands exist and can run them directly. Plain operations therefore need no skill; a skill is only written where the task needs a procedure and judgement, which is why there is an `obs-query` skill.

Claude Code also loads `CLAUDE.md` from every ancestor of the cwd, and the worktrees live under the data root, so the step settings file (5.1) sets `claudeMdExcludes` to the `CLAUDE.md` of the code root and of every ancestor folder of it. Steps run with `--setting-sources project,local`, so the human's user settings do not reach them either.

Result: a step in a webapp worktree sees the general and the webapp skills and instructions, and nothing from the human's own Claude setup. No index file has to be read by the model. (A root index that the model reads each session was considered and rejected: it relies on the model, costs context, and does not register skills as slash commands.)

### 6.2 Codex compatibility

The skills carry `agents/openai.yaml`, and some projects use `.agents/skills` and `AGENTS.md`, which are Codex conventions. `agenthub-harness link --codex` can also create `<worktree>/.agents/skills/*` links and a root `AGENTS.md` link. One source file, two entry points.

### 6.3 Adding a project and setting up a worktree

**Adding a project** is one command plus one document:

```
agenthub-harness project add <name> --repo <git url> --base <branch>
```

The command does the mechanical part: clones the repo into `worktrees/<name>/.base/` under the data root (the main clone that all worktrees are created from), adds the `projects.<name>` entry to `harness.yaml` with an empty `setup` list, creates `skills/projects/<name>/` (empty) and `agentmds/<name>/AGENTS.md` from a template (all three under the private root) whose headings are the step 3 list (how to run the app and check a change, run tests, run evals, companion tools, obtain secrets and config, data access rules, branching rules). It then opens an interactive Claude session in the base clone with the `onboard-project` skill loaded, the same launch mechanism as the terminal chats in 5.7. AgentHub calls it without that session (`no_chat`); an AI user then follows `onboard-project` with the human through ticket comments.

`onboard-project` fills the template with the human, section by section:

0. **Check what the harness already has for this project.** Looks only inside the private root: `agentmds/<name>/AGENTS.md` and `skills/projects/<name>/`. If either exists with real content (not just the template), it lists them (AGENTS.md sections present, skill names) and asks: **edit these, or start new?**
   - *Edit*: the existing AGENTS.md is the draft and the existing skills stay; the phases below only ask for what is missing or fails verification.
   - *Start new*: the existing files are moved to `agentmds/<name>/previous_<date>/` and `skills/projects/<name>/previous_<date>/` (never deleted), and the phases below run from the template.
   Nothing there: continue silently.
1. **Draft from the repo.** Reads README, Makefile or task runner files, package manifests, lockfiles, Docker and compose files, CI workflows, launch configs, test directories and any existing `AGENTS.md` or `CLAUDE.md`. Drafts each AGENTS.md section and the `setup` list from what it finds, marking anything inferred rather than read.
2. **Ask only what the repo cannot tell.** Secrets and where they come from, dev servers and databases and the access rules for each, companion repos or tools, branching rules, anything the draft marks as inferred. One question at a time, with the draft answer proposed when there is one. Nothing is asked that the repo already answers.
3. **Verify.** Creates a scratch worktree, runs the `setup` list in it, then the documented commands for running tests and starting the app, and fixes the draft until they work or the human says to stop. The scratch worktree is removed afterwards.
4. **Write.** The AGENTS.md in the file's concise style, the `setup` list into `harness.yaml`, and a short onboarding note at the end of the AGENTS.md: date, what was verified, what the human chose not to set up. Both files are shown as diffs and written on approval. This is the one session in which a skill writes `harness.yaml`; it runs outside any run, so the write boundary in 5.1 does not apply.

The session ends when the human exits. Re-running `agenthub-harness project add` on an existing project skips the clone and reopens the skill, which starts at phase 0 and offers to edit the current files; this is how a project's AGENTS.md gets a structured revision later. `agenthub-harness project list` shows the projects and whether their AGENTS.md still has template placeholders; `agenthub-harness run` refuses to start on a project whose AGENTS.md does.

Tickets reference the project by name in their frontmatter (`project: <name>`); `base_branch` defaults to the project's `default_base` when omitted.

**Worktree setup** is owned by step 2, not by any skill. For every new run the orchestrator:

1. `git fetch` in `worktrees/<project>/.base/`, then `git worktree add worktrees/<project>/<feature>_<n> -b <feature>_<n> origin/<base_branch>`.
2. `link_worktree` (6.1): skill links and the `CLAUDE.md` imports.
3. Runs each command in the project's `setup` list, in order, from the worktree root, with output captured to `runs/<run-id>/log/02-setup.txt`. Any non-zero exit stops the run before the first AI step, prints the failing command and its output, and asks the human (5.7, `kind: setup`) to fix the cause (for example a dev server that holds the secrets is off; the project AGENTS.md says how to turn it on). On resume, step 2 re-runs the setup list from the start; setup commands must therefore be safe to repeat.

The `setup` list is the machine-readable version of what the AGENTS.md says in prose under "how to obtain secrets and config" and "how to run the project": the orchestrator runs the list, the model reads the prose. They must agree; `improve-harness` flags it when a run's build-context had to discover a setup step the list lacks.

Setup commands never write outside the worktree (no `~/.config` edits, no global installs); dependency caches shared across worktrees are the package manager's concern, not the harness's. Dependency folders are excluded from the archive zip (4.4), so a restored archive needs the setup list run again.

---

## 7. Decisions on former open questions

All answered by the human on 2026-11-09:

1. Loop cap default: **3**.
2. `run-tests` **only reports**; it never fixes anything, trivial or not.
3. A project's own eval-running skill is **not** copied into the harness; the regression skills and the project AGENTS.md cover it.
4. `spec` default for `feature-v1`: **`always`**. No `auto` threshold is defined until a workflow uses `auto`.

---

## 8. Feedback and suggestions

- The spec is the contract with the human; the plan is the contract between phases. The spec is frozen after GATE 1 and only a human changes it, through a chat that writes the next version. Every loop iteration produces `plan_<feature>_<n>_v<k>.md`; build reads only the latest.
- Build-context is now the second slowest step after run-tests because it starts the app and reproduces the ticket. Acceptable: it runs once per run, not once per loop iteration.
- Treat steps 13, 13b and 15b as the slowest steps (evals in 13 and 15b, browser sessions in 13b). Let testcase-builder tag cases `smoke` vs `full` and run only `smoke` on iterations 2+ (tunable in `defaults.yaml`).
- Keep step transcripts (`runs/<run-id>/log/<step>.jsonl`, the full `claude -p` output: every model message, tool call with arguments, tool result). SigNoz holds the skeleton (tokens, cost, timings, which tools ran) and is best effort; the transcript holds the content and is the only place to read why a step decided what it did.
- The `_<feature>_<n>` suffix convention keeps files self-identifying outside their folder, and `ls runs/*/plan_*` still gives a cross-run overview. Keep it strict: no generated file without the suffix. Because every execution computes a unique output name (`_v<k>`, section 1), a file already existing at that name can only mean a bug (run-number collision, execution counter not advanced). The orchestrator refuses to start the step in that case and reports it, instead of overwriting.
- Keep specs short. Practitioner guidance is under about three pages; this spec targets two. A spec that cannot fit is a ticket that should be split.

---

## 9. Implementation notes (2026-11-09)

Where the code departs from the text above, and why:

- **Every repeated execution is versioned, not only steps that declare it.** `_compute_outputs` gives every write the next `_v<k>` (max of execution count and highest version on disk + 1), so a re-run of step 4 after a chat writes `context_<feature>_<n>_v2.md`. Decision files are numbered from v1 (`decision_…_v1.md`), as section 5.4 shows.
- **Artifact frontmatter is the orchestrator's input.** Each template starts with YAML frontmatter; the orchestrator reads `status`/`question` (step 4), `decision`/`question` (step 14), `counts` (reviews), `passed`/`total` (tests), `applied`/`skipped` (step 12), `answered` (decision files written in a chat) and `summary` (one-line outcome). The `## Run cost` section is parsed from the body.
- **Write boundary = deny rules + hook.** Steps run with `--permission-mode bypassPermissions` (configurable) and a generated settings file (`runs/<run-id>/log/step_settings.json`; chats use `chat_settings.json`, the same rules plus the `Stop` hook of 5.7) whose `permissions.deny` has one `Edit(...)` rule per protected path (`skills/general/` and `skills/projects/` with their roots, `workflows/`, `agentmds/GENERAL.md`, `harness.yaml` and `harness/`), which Claude Code applies to every file-editing tool; a PreToolUse hook (`harness/hooks/deny_harness_write.py`, protected list from `HARNESS_PROTECTED_PATHS`) also checks Bash commands, by path: it takes the path-like words of the command (words holding `/`, redirect targets), resolves each against the session's folder and against the folder of every `cd` in the command, and refuses only a write-like command one of whose paths lies under a protected path, so a worktree's own `skills/` or `harness/` folder stays writable. A word it cannot resolve (it holds a variable or a command substitution) is judged by the older text rule, which fires on the folder name of a protected path. The settings also set `claudeMdExcludes` (6.1). Verified against the real `claude` binary. A step whose `workflow.yaml` entry has `mcp_servers` also gets `--mcp-config runs/<run-id>/log/mcp_<step>.json`; an MCP server writes files itself, outside the hook, so its output paths must point into the run folder.
- **SigNoz.** The copy runs no stack: the Docker Compose manifest, the dashboard import and the obs commands that started, stopped and opened the stack are gone from it. The collector is run outside the copy, which only probes its port (5.6).
- **Transcripts** are `runs/<run-id>/log/<step>[_v<k>].jsonl` (stream-json of `claude -p`), plus `02-setup.txt`.
- **State additions.** `state.json` also holds `executions` (one record per step execution in run order, which the run log is built from), `pending_chat`, `injected_answer`, `question_history`, `gates`, `branch`, `n`, the effective `defaults`, and `usage`: the last figure of each of the account's limits a step reported in a `rate_limit_event`, written while the step runs, for AgentHub's header. Each execution records `cost_usd` and `tokens` (5.8).
- **Pause** (`on_question: pause`, the default) applies to gates as well as questions; the orchestrator writes the question into the next decision file with `kind` and `answered: false`. `orchestrator.pending_question(layout, run_id)` reads a paused run's pending question, read-only, for AgentHub to surface; a paused gate continues only with `HARNESS_GATE_RELEASE` (5.7).
- **`agenthub-harness run` refuses a project whose AGENTS.md contains `TODO(onboard)`**, the placeholder marker the AGENTS.md template and `onboard-project` use; a new project's AGENTS.md has them until it is onboarded.
- **Worktrees.** Each project's clone is `worktrees/<project>/.base/` under the data root, the base clone that per-run worktrees are created from.
- **Interrupted steps** (Ctrl-C) leave the run `paused` with the execution marked `interrupted`; `agenthub-harness resume` continues the step in its session (5.8), or re-runs it as the next version when the session never started.
- Tests: `harness/tests/` runs the whole graph (happy path, loop and cap chat, spec_issue rewrite, unreproduced ticket, pause/resume, gate release, interruption) against `harness/tests/fake_claude.py`, plus the copy's additions (three roots, the path-based Bash check, tokens, the AgentHub refusals, no Docker, nothing under the home Claude folder); no API calls.

---

## 10. Workflow `regression-v1` (2026-11-11)

Regression only: compare a branch against the commit it forked from on the eval suites and case keys a ticket names, and end with a report. No spec, plan, build or gates; nothing in the project is edited. Lives in `workflows/regression-v1/`; the orchestrator needed no change.

**Ticket.** Same file and frontmatter as section 3, plus:

| field | required | meaning |
|---|---|---|
| `compare_branch` | yes | the branch to test |
| `suites` | one of the two | suites run whole |
| `cases` | one of the two | suite → the case keys to run; a suite is in `suites` or `cases`, not both |
| `repetitions` | no | per case, both sides; default `regression_repetitions` (3) |
| `workers` | no | concurrent eval cases per side; default `regression_workers` (4) |

The orchestrator ignores these fields; step 15b reads them from the frozen ticket copy. The feature name differs from any feature ticket (`reg-<branch>`), and the run id is the LangSmith scratch owner as in `feature-v1`.

**Steps.**

| # | Step | Actor | Output |
|---|---|---|---|
| 1 | Ticket | **H** | `tickets/<feature>.md` |
| 2 | Start | orchestrator | worktree on branch `<feature>_<n>` at `base_branch`, project setup (6.3). The worktree is only where project commands run from (`.env`, dependencies); nothing is built in it and the empty branch stays local |
| 15b | `regression-testing-report` | AI | `regression_<feature>_<n>.csv`, `regression_report_<feature>_<n>.md`, raw results uploaded to the project's results directory |
| 15c | `langsmith-cleanup` | AI | `langsmith_cleanup_<feature>_<n>.md` |
| 16 | `regression-final-report` | AI | `final_report_<feature>_<n>.md` |
| 18 | Run log | orchestrator | `workflow_logs/<run-id>.log` |

Ids are those of the same skills and actions in `feature-v1`, so telemetry and AGENTS.md references to a step id mean one skill in both workflows. The only pause is a failed setup command (5.7).

**Behaviour.**

- Refs: the new side is the tip of `compare_branch`, from `origin/` when the remote has it, otherwise the local branch (a agenthub-harness run branch is on the remote only once its run reached step 18b); the base side is the merge-base of that commit with `base_branch`, so the deltas show only what the branch changed. Both SHAs and where each was found are recorded.
- Before any eval runs, 15b checks that both refs resolve and every named suite and case key exists on both refs; the first failure ends the step with `status: failed` and a header-only CSV.
- Both sides use the same suites, case keys, repetitions and workers. When the project's eval runner applies a case filter to every suite of one command (the project AGENTS.md says), whole suites run in one command and each case-restricted suite in its own, one after another per side, the two sides in parallel.
- A 15b report with `status: failed` does not stop the run: 15c still deletes the scratch datasets and 16 reports the failure. A 15b step that crashes or times out fails the run like any step; `agenthub-harness resume` re-runs it.
- Server: the raw results (per-suite table CSV, details and summary JSON of every eval run) are uploaded as in `feature-v1`, never overwriting; the delta CSV stays in the run folder.

**Final report (step 16).** Read-only; copies numbers and paths, computes only percent time changes. Sections: Compared (branches, commits, selection, repetitions, workers), Accuracy (overall Δ, regressed suites with case keys), Timing (overall mean case time per side with Δ seconds and Δ %, counts of slower, faster and unchanged suites, the three largest slowdowns and speed-ups, workers per side), Deltas per suite (the CSV plus Δ time %), Files (local delta CSV and local regression report, both by absolute path; server paths of every result file per side), Cleanup, Caveats, Feedback. A time change is reported as numbers and never called a regression; only a drop in accuracy marks a suite as regressed.

**Defaults.** `regression_repetitions: 3`, `regression_workers: 4`, `max_iterations: 1`, model `opus` for every AI step with per-step overrides under `model.steps` (or `--set` per run), timeout 300 min for 15b and 60 for the rest. A ticket value wins over the default.

---
name: code-review
description: Review the current Git HEAD against a user-selected comparison branch using specialist subagents for bug and requirements risks, readable incremental changes and architecture, unit-test quality, and documentation-backed frontend compatibility when applicable, followed by a synthesis agent that produces one severity-sorted report. Use when the user asks for a code review, branch review, diff review, pre-PR review, or assessment of whether a feature diff matches its ticket or stated requirements.
---

# Code Review

Review only; do not edit the implementation unless the user separately asks for fixes.

## Collect inputs

Before inspecting the diff, ask the user for:

1. The branch or ref to compare against. Never infer it. This input is required.
2. The ticket, acceptance criteria, or other context describing the intended feature. Explicitly say this input is optional and that the user may skip it.

If the invocation already contains either answer, acknowledge and use it rather than asking for it again. Wait for an explicit answer to the required branch question. Continue without feature context when the user declines or skips it.

## Establish the diff

1. Confirm the working directory is inside a Git repository.
2. Resolve the supplied comparison ref to a commit without guessing between ambiguous refs. Accept a fully qualified ref, a local branch, or an unambiguous remote-tracking branch. If it cannot be resolved, report that and ask for a valid ref.
3. Treat `HEAD` as the review target. Do not include uncommitted working-tree changes unless the user explicitly asks for them.
4. Use the merge-base diff, equivalent to `git diff --find-renames <comparison-ref>...HEAD`, so the review covers changes introduced on the current branch rather than unrelated changes added to the comparison branch after divergence.
5. Inspect at least the diff summary, changed-file list, full patch, and `git diff --check <comparison-ref>...HEAD` output.
6. Read relevant surrounding code, call sites, types, configuration, and existing tests. Do not judge isolated diff fragments without their execution context.
7. If feature context was supplied, turn it into a short checklist and trace each requirement to the changed behavior.

Follow repository-local instructions such as `AGENTS.md` throughout the review.

## Orchestrate the review

Act as the coordinator. After establishing the diff, spawn the three core specialist subagents below and, when the diff can affect browser-delivered CSS or JavaScript, a fourth frontend-compatibility specialist. Start them concurrently when capacity permits; otherwise start the remaining specialists as slots become available. Give every specialist the resolved comparison ref, the `HEAD` target, the merge-base diff command, any requirements checklist, repository-local instructions, and its assigned section below. Tell each specialist to remain read-only, inspect surrounding code rather than only patch fragments, and report only issues introduced by the target diff.

Assign one section to each specialist:

1. `Bug risks and requirements`: analyze correctness, edge cases, compatibility, security, performance, and supplied requirements using the **Bug risks** criteria.
2. `Code readability and architecture`: analyze human reviewability, incremental diff quality, readability, modularity, and simplification opportunities using the **Code readability and incremental changes** criteria.
3. `Unit-test quality`: analyze changed tests, redundant or low-value coverage, missing regression protection, and repository test conventions using the **Unit-test quality** criteria.
4. `Frontend compatibility` (when applicable): inventory and rank the compatibility of every distinct CSS feature and browser-facing JavaScript feature added or behaviorally affected by the diff using the **Frontend compatibility** criteria. This specialist must consult current documentation rather than rely on memory.

Require each specialist to return:

- candidate findings sorted by severity, each with a title, exact file and single-line location when possible, category, concrete trigger or evidence, impact, confidence, and smallest practical remediation;
- section notes, including useful non-blocking suggestions;
- checks run and their results;
- `No findings.` when the section has no actionable finding.

Tell specialists to apply the shared severity definitions below. Do not ask them to edit files. Wait for every applicable specialist to finish before starting synthesis.

Spawn a separate summary subagent after all applicable specialist outputs are available. Give it the resolved comparison ref, requirements checklist, shared severity and reporting rules, check results, and every specialist output verbatim, including the frontend-compatibility report when applicable. Require the summary agent to:

1. Verify candidate findings against the diff and relevant surrounding code.
2. Remove duplicates, unsupported speculation, pre-existing issues, and claims not introduced by the diff.
3. Resolve disagreements and normalize priority using the shared severity definitions.
4. Preserve concrete non-blocking readability or architecture improvements in `Review notes` without promoting them to defects.
5. Verify the frontend feature inventory, rankings, and citations, then preserve the compatibility table in the final report. Do not collapse it into findings alone.
6. Produce the complete final report in the **Report** format below, with the most important findings first.

Return the summary agent's report as the review result. Do not independently rewrite or re-rank it. If subagent creation is unavailable, explain that this workflow requires subagents and ask whether the user wants a single-agent review instead.

## Validate the change

Prioritize correctness findings over style preferences. For every suspected issue, trace a concrete input or execution path and verify that the current code does not already handle it. Run focused tests or static checks when they are safe and reasonably discoverable. State exactly what was and was not run; never imply a test passed when it was not executed.

### Code readability and incremental changes

Treat human reviewability as a requirement. Assess whether a reviewer can understand the intent and verify the behavior without reconstructing the change from scattered context:

- Prefer the smallest coherent diff that delivers the intended behavior. Flag unrelated scope, broad rewrites, or incidental formatting and renaming that obscure the functional change.
- Check that mechanical refactors, behavior changes, and cleanup are separated when combining them makes the diff harder to verify.
- Flag duplicated logic, hidden coupling, mixed responsibilities, unclear names, implicit data flow, or control flow that makes behavior difficult to follow.
- Look for a smaller change, an existing abstraction, or a simpler design that reduces moving parts while preserving the intended behavior. Suggest it when it would make the diff easier to review or the architecture easier to understand.
- Do not recommend decomposition merely to make functions shorter or introduce abstractions without a clear benefit. Suggest a refactor only when it improves cohesion, testability, reuse, comprehension, or the incremental shape of the change.
- Make every readability or architecture suggestion concrete: identify the affected code, explain why the current form is difficult to review or maintain, and describe the smallest useful extraction, rename, reordering, or restructuring.
- Report a maintainability issue as a finding only when it creates meaningful review, change, or defect risk. Put non-blocking ways to simplify the diff or architecture in review notes even when the current implementation is acceptable.

### Unit-test quality

When unit tests are added or changed, evaluate each distinct test constraint:

- Keep tests that protect important behavior, invariants, boundary conditions, error handling, or a plausible regression.
- Confirm the test would fail for a meaningful defect and asserts observable behavior rather than incidental implementation details.
- Identify equivalent inputs or assertions that protect the same constraint. Recommend retaining one representative test and dropping redundant duplicates.
- Recommend dropping tests for trivial constants, framework behavior, simple accessors, or mock interactions that do not protect product behavior.
- Identify important changed behavior that has no suitable regression test.
- Enforce the repository's unit-test conventions as documented in its AGENTS.md (or CLAUDE.md), including any directories those conventions exclude. If the repository documents no conventions, do not invent any.

Do not demand one test per code path when a smaller set protects the same constraint.

### Frontend compatibility

Run this analysis when the diff adds or changes CSS, preprocessors that emit CSS, HTML styles, browser-executed JavaScript or TypeScript, frontend framework code, or build configuration that changes browser output. Skip it when the diff cannot affect browser-delivered code, and state that it was not applicable.

First determine the browser support matrix from explicit requirements, repository documentation, `browserslist` or equivalent configuration, and build/transpilation/polyfill settings. Prefer an explicit project matrix. If none exists, state that limitation and use this default modern-browser matrix: the latest two stable releases available on the review date of Chrome, Edge, Firefox, and Safari on computers, plus current Chrome for Android and Safari on iOS.

Inspect source code and the effective build path. Inventory every distinct browser-dependent feature added or behaviorally affected by the diff:

- CSS properties and values, at-rules, selectors and pseudo-classes/elements, functions, units, layout modes, media queries, and relevant Web Platform features;
- JavaScript syntax not guaranteed to be transformed for the target browsers, browser and DOM APIs, Web APIs, module/loading behavior, events, observers, storage, graphics/media capabilities, and framework behavior that depends on those features.

Do not list ordinary language constructs or code that the configured compiler demonstrably transforms into compatible output. Deduplicate repeated uses of the same feature, but include every changed location where its compatibility context or fallback differs.

For each inventoried feature, consult current compatibility documentation. Prefer MDN browser-compatibility data, standards or browser-vendor documentation, and the project's compiler/polyfill documentation; use Can I Use as corroborating evidence when useful. Include a direct documentation link and the review date for every row. Do not assign a ranking from memory or from an uncited search snippet.

Rank each feature against the selected browser matrix:

- `5/5 Broad`: supported across the matrix without a required prefix, transform, polyfill, or material limitation.
- `4/5 Broad with caveats`: supported across the matrix only through the configured transform/polyfill/prefix or with documented limitations that do not break the intended behavior.
- `3/5 Partial`: unsupported or materially limited in one target browser family or target version.
- `2/5 Narrow`: unsupported or materially limited in multiple target browser families or versions.
- `1/5 Unsafe/obsolete`: experimental, deprecated, disabled by default, or broadly unavailable for the intended use.
- `Unknown`: authoritative compatibility evidence or the effective build behavior cannot be established. Explain what is missing rather than guessing.

Return a `Frontend compatibility` table with one row per distinct feature and these fields: feature, changed file and line, CSS/JavaScript category, target browsers or relevant exceptions, ranking, transform/polyfill/fallback status, documentation link, and evidence-based notes. After the table, report actionable incompatibilities as severity-ranked candidate findings using the shared finding schema. A low ranking is not automatically a defect: trace whether an existing fallback, compiler, prefixer, progressive enhancement path, or stated browser requirement prevents user-visible impact. State the files and build configuration inspected and any browsers or runtime tests actually exercised.

### Bug risks

Look for evidence-backed risks including:

- incorrect conditions, state transitions, data transformations, or boundary handling;
- missing validation, error propagation, cleanup, or rollback behavior;
- null, empty, malformed, duplicate, ordering, retry, timeout, and concurrency cases;
- broken API, schema, configuration, persistence, or backward-compatibility assumptions;
- authorization, data exposure, injection, unsafe file or command handling, and trust-boundary mistakes;
- unbounded work, repeated I/O, or other material performance regressions;
- mismatch with the supplied ticket or acceptance criteria.

Avoid speculative findings that lack a plausible trigger and observable impact.

## Assign severity

Sort findings from highest to lowest severity. Use these labels consistently:

- `Critical`: likely security compromise, unrecoverable data loss, or a broadly unusable system; blocks merge.
- `High`: likely incorrect behavior, outage, serious security exposure, or data corruption in a common or important path; blocks merge.
- `Medium`: real defect or maintainability hazard with a narrower trigger or impact; normally fix before merge.
- `Low`: limited-risk correctness, test-quality, readability, or modularity problem worth addressing but not generally merge-blocking.

Do not inflate severity because a fix is easy or a code pattern looks undesirable.

## Report

Lead with findings, ordered by severity and then by confidence. For each finding include:

- severity and concise title;
- exact file and single-line location in the changed code when possible;
- category: `bug risk`, `requirements`, `modularity/readability`, `unit tests`, or `frontend compatibility`;
- concrete trigger or evidence;
- user-visible or engineering impact;
- the smallest practical remediation.

After the findings, include:

1. `Requirements coverage`: concise status against the supplied context, or state that no ticket/context was provided.
2. `Test assessment`: tests added or changed, redundant or low-value tests, important gaps, and commands/checks run with results.
3. `Frontend compatibility`: when applicable, the verified per-feature compatibility table, browser matrix, documentation review date, build/transformation assumptions, compatibility findings, and any runtime-testing limitations. Otherwise state `Not applicable.`
4. `Review notes`: optional non-blocking readability or modularity improvements and any residual risks or review limitations.

If there are no findings, say `No findings.` explicitly, then still provide all four sections above. Keep the report focused on actionable issues introduced by the diff; do not inventory unrelated pre-existing problems.

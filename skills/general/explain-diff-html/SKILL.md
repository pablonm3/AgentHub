---
name: explain-diff-html
description: Use when the user asks for a rich explanation of a code change, diff, branch, or PR. Produces HTML output.
---

# Explain Diff

Create a rich, interactive explanation of the specified code change as one self-contained HTML file.

## Establish the change

Identify the exact diff, branch, commit range, or pull request the user means. Use explicit user-provided references first. Otherwise infer the target from the current repository context when there is one clear candidate, such as the working-tree diff or current branch against its base. Ask a concise clarifying question only when multiple materially different targets remain plausible.

Inspect the complete diff and broadly explore the surrounding implementation. Trace the relevant callers, data flow, types, configuration, tests, and user-visible behavior. Distinguish verified behavior from inference. Do not explain a patch in isolation when the surrounding system is available.

## Build the explanation

Write for readers with mixed familiarity. Aim for rigorous, engaging technical prose with the clarity and flow associated with Martin Kleppmann's writing, without copying distinctive phrasing.

Produce one long page with a table of contents and these top-level sections, in this order:

1. **Background**
   - Begin with a deep, beginner-friendly explanation of the existing system relevant to the change. Make this clearly skippable for experienced readers.
   - Narrow progressively to the specific components, constraints, and behavior changed by the diff.
2. **Intuition**
   - Explain the essence of the change before its mechanics.
   - Use concrete examples with small toy data.
   - Use a small, consistent family of visual diagrams to show the important relationships or state transitions.
3. **Code**
   - Walk through the changes at a high level, grouped in the conceptual order that best explains them rather than merely following file order.
   - Connect each code change to the intuition and resulting behavior. Include concise excerpts when useful.
4. **Quiz**
   - Include exactly five medium-difficulty multiple-choice questions that require understanding the substance of the change.
   - Make every question interactive. A selection must reveal whether it is correct and provide useful feedback explaining why.
   - Avoid trivia, wording traps, and questions answerable without understanding the change.

Use callouts for definitions, key concepts, assumptions, and important edge cases. Make transitions between sections smooth.

## Visual and interaction requirements

- Use semantic HTML, embedded CSS, and embedded JavaScript only. The document must work when opened locally without network access.
- Do not use tabs for the top-level structure.
- Add basic responsive styling suitable for phone screens and large screens.
- Use diagrams liberally where they materially improve understanding. Prefer reusable visual families such as:
  - a simplified representation of the application UI for user-visible changes;
  - component and data-flow diagrams containing concrete example data;
  - state or sequence diagrams for behavior that changes over time.
- Build diagrams from accessible HTML and CSS. Do not use ASCII art.
- Use HTML list elements for lists.
- Put all code excerpts in `<pre>` elements. If another custom code container is necessary, its CSS must explicitly set `white-space: pre` or `white-space: pre-wrap`.
- Keep colors legible, interactions keyboard-accessible, and quiz feedback understandable without relying on color alone.

## Save and verify

Resolve the project root before writing the deliverable. For a Git worktree, use the top-level directory reported by Git. Create a `docs/diffs_explained` directory under that root when it does not already exist.

Save the deliverable in that directory. The filename must start with the current local date in `YYYY-MM-DD-` format and follow this shape:

`<project-root>/docs/diffs_explained/YYYY-MM-DD-explanation-<descriptive-slug>.html`

Before finishing:

1. Confirm the file is directly inside `<project-root>/docs/diffs_explained/` and the filename uses today's date.
2. Confirm it is a single self-contained HTML file with no network dependencies.
3. Confirm the table of contents links to every top-level section.
4. Confirm all five quiz questions reveal correctness and explanatory feedback.
5. Scan every code block in the HTML source and verify that it is a `<pre>` element or that its container's CSS explicitly uses `white-space: pre` or `pre-wrap`.
6. Open or otherwise inspect the rendered page when tooling permits, and correct obvious layout or interaction defects.

Return a clickable link to the generated HTML file and a concise statement of which change it explains.

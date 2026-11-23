# AgentHub

A board where human users and AI users work tickets and tasks, built around a coding harness.

The repo is at its starting point: it holds only the interface prototype.

## prototype/

`prototype/Main.dc.html` is the source of the interface prototype: a Board tab and a Tasks tab, a card dialog and a terminal dialog, filled with test data only.

It was authored as a claude.ai Design artboard and loads a runtime (`./support.js`) that is not in this repo, so it does not render when opened directly in a browser. Read it as the reference for layout, styles, copy, interactions and test data: the markup is inside `<x-dc>`, the logic is the class in the `<script type="text/x-dc">` block.

"""Coding harness orchestrator, the copy inside AgentHub (`agenthub-harness`).

Sequences the skills of a workflow (workflows/<name>/workflow.yaml), keeps the run
state (runs/<run-id>/state.json), routes between steps, and handles housekeeping:
run numbers, worktrees, telemetry environment, console graph, run log.

See docs/WORKFLOW_SPEC.md section 5.
"""

__version__ = "0.1.0"

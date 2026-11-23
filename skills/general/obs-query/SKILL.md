---
name: obs-query
description: Answer questions about harness runs from SigNoz telemetry through the SigNoz MCP server — cost and tokens per run or step, durations, which step fails most, tool-call counts — translating the question into queries over the harness resource attributes (run_id, feature, step, skill, iteration, workflow, project, app, task_id, ai_user). Never starts or stops anything: the collector is external. Use when the user asks what a run cost, how long steps took, or for any number from the telemetry.
---

# Observability query

Reads, never writes. The harness attribute names below are set by the orchestrator on every `claude -p` step (spec 5.6), so every metric, log and span can be sliced by them.

| attribute | meaning |
|---|---|
| `run_id` | `<feature>_<n>` |
| `feature`, `run_n` | ticket name and run number |
| `step`, `skill` | workflow step id and the skill it ran |
| `iteration` | build-loop iteration |
| `workflow` | workflow version (`feature-v1`) |
| `project` | project name |
| `app` | always `agenthub` |
| `task_id`, `ai_user` | the AgentHub task and AI user that started the run, when it was started from AgentHub |

Claude Code exports metrics `claude_code.cost.usage` (USD), `claude_code.token.usage` (by `type`: input, output, cacheRead, cacheCreation; by `model`), `claude_code.session.count`, `claude_code.lines_of_code.count`, `claude_code.commit.count`, `claude_code.active_time.total`; logs/events `user_prompt`, `tool_result`, `api_request`, `api_error`, `tool_decision`; and with enhanced telemetry, traces with one root span per prompt and child spans per model request and tool call.

## Procedure

1. **Check the collector.** Run `agenthub-harness obs status`. The collector is external: the copy never starts, stops or calls Docker. If it does not answer, say so and stop; the MCP server has nothing to read otherwise. Verify the `signoz` MCP server is available (tools named `signoz_*`); if it is not registered, print the config from `agenthub-harness obs mcp-config` and tell the user to add it to their Claude Code settings (`claude mcp add-json signoz '<json>'`) and restart the session.
2. **Translate the question** into attribute filters and an aggregation. Examples:
   - "what did `filter-recovery_2` cost per step" → `claude_code.cost.usage` summed, filter `run_id = filter-recovery_2`, group by `step`, `skill`.
   - "which step fails most across `feature-v1`" → `api_error` and tool_result failures, filter `workflow = feature-v1`, group by `step`; cross-check with the `status` in each run's `state.json` when the logs disagree.
   - "tokens by model for build-plan" → `claude_code.token.usage` filter `skill = build-plan`, group by `model`, `type`.
   - "what did build-context conclude in run X" → search traces/logs with `run_id = X AND step = 4` and read the exported assistant text (content export is on; values are capped, so point to the transcript `runs/X/log/04.jsonl` under the data root for the full text).
3. **Query** with the SigNoz MCP tools (`signoz_query_metrics`, `signoz_aggregate_logs`, `signoz_search_traces`, `signoz_execute_builder_query`, …). Pass the user's request verbatim in `searchContext`. Pick the time range from the run's `started`/`ended` in `state.json` or the run log; default to the last 7 days.
4. **Answer** with the numbers in a small table, the time range used, and the filters applied, so the user can repeat it in the SigNoz UI. Say when data is missing because telemetry was off for that run (the run log header says `telemetry off`).

Harness-side numbers (this telemetry) and project-side costs (the `## Run cost` sections, copied into the run log) are different things; name which one you report.

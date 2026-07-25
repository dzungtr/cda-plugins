---
name: langfuse-self-improvement
description: Use when conversations involve self-improvement topics — permission friction, slow tool responses, high token usage, cache efficiency, or recurring workflow patterns. Pulls real behavioral data from Langfuse instead of guessing.
---

# Langfuse Self-Improvement

Langfuse captures every Claude Code session as traces with span-level detail. Use the CLI to ground self-improvement discussions in real data. Credentials are already in the shell environment — run commands directly.

## When to reach for Langfuse

| Situation | What to query |
|---|---|
| "Keep getting permission prompts for X" | Count of `claude_code.tool.blocked_on_user` spans |
| "Sessions feel slow" | p50/p90 latency by span name |
| "Want to understand tool usage patterns" | Count by span name, grouped over time |
| "How active have my sessions been?" | `traces list` for session frequency |

## Span reference

| Span name | What it represents |
|---|---|
| `claude_code.interaction` | One user→Claude turn (duration = wall time for that turn) |
| `claude_code.llm_request` | One LLM API call (latency, model, tokens in metadata) |
| `claude_code.tool` | Tool invocation wrapper |
| `claude_code.tool.execution` | Actual tool execution (subprocess, file I/O, etc.) |
| `claude_code.tool.blocked_on_user` | Permission gate — was auto-approved or shown to user |

## Commands

**Session activity (last N days)**
```bash
langfuse api traces list --limit 100 --from-timestamp $(date -v-7d -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -d '7 days ago' -u +%Y-%m-%dT%H:%M:%SZ)
```

**Activity overview — count + latency by span type**
```bash
langfuse api legacy-metrics-v1s list --query '{
  "view": "observations",
  "dimensions": [{"field": "name"}],
  "metrics": [
    {"measure": "count", "aggregation": "count"},
    {"measure": "latency", "aggregation": "p50"},
    {"measure": "latency", "aggregation": "p90"}
  ],
  "fromTimestamp": "YYYY-MM-DDT00:00:00Z",
  "toTimestamp": "YYYY-MM-DDT23:59:59Z",
  "orderBy": [{"field": "count_count", "direction": "desc"}]
}'
```

**Permission pressure — how often is the gate hit?**
```bash
langfuse api legacy-metrics-v1s list --query '{
  "view": "observations",
  "dimensions": [{"field": "name"}],
  "metrics": [{"measure": "count", "aggregation": "count"}],
  "filters": [{"column": "name", "type": "string", "operator": "=", "value": "claude_code.tool.blocked_on_user"}],
  "fromTimestamp": "YYYY-MM-DDT00:00:00Z",
  "toTimestamp": "YYYY-MM-DDT23:59:59Z"
}'
```

**Slow operations — filter by latency threshold**
```bash
langfuse api legacy-metrics-v1s list --query '{
  "view": "observations",
  "dimensions": [{"field": "name"}],
  "metrics": [
    {"measure": "count", "aggregation": "count"},
    {"measure": "latency", "aggregation": "p90"},
    {"measure": "latency", "aggregation": "p99"}
  ],
  "filters": [{"column": "latency", "type": "number", "operator": ">=", "value": 2}],
  "fromTimestamp": "YYYY-MM-DDT00:00:00Z",
  "toTimestamp": "YYYY-MM-DDT23:59:59Z"
}'
```

## Interpreting results

**Permission friction**: High `count_count` on `claude_code.tool.blocked_on_user` relative to `claude_code.tool` means many tools are hitting the permission gate. To see *which* tools and their decisions (accept/reject/unknown), open the trace in the Langfuse UI at http://localhost:3012 or use `langfuse api traces get <traceId>`.

**Slow tools**: p90 latency on `claude_code.tool.execution` > 2s warrants investigation. Compare against `claude_code.tool` latency — the delta is time spent waiting for user permission.

**Token and cache data**: Token counts (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`) are stored in `metadata.attributes` on `claude_code.llm_request` spans, not in standard metric fields. Inspect individual traces via `langfuse api traces get <traceId>` or the UI for per-session token breakdowns.

**Session cadence**: Use `traces list` to see how many sessions ran in a window. Each trace is one user→Claude turn; a conversation is a group of traces sharing the same `sessionId`.

## Notes

- `langfuse api metrics list` (v2) is cloud-only — local self-hosted requires `legacy-metrics-v1s`
- Date flags: macOS uses `date -v-7d`, Linux uses `date -d '7 days ago'`
- Langfuse UI: http://localhost:3012 (user: admin@example.com / adminadmin)

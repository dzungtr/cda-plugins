---
name: self-improvement
description: Use when conversations involve self-improvement topics — permission friction, slow tool responses, high token usage, cache efficiency, or recurring workflow patterns. Pulls real behavioral data from the cc-observability MCP instead of guessing.
---

# Self-Improvement

Claude Code exports span-level telemetry to SigNoz. Use the `cc-observability` MCP tools to ground self-improvement discussions in real data rather than assumptions.

## When to use this skill

| Situation | What to query |
|---|---|
| "Keep getting permission prompts for X" | Count of `claude_code.tool.blocked_on_user` spans |
| "Sessions feel slow" | p50/p90 duration by span name |
| "Want to understand tool usage patterns" | Count by span name, optionally grouped over time |
| "How active have my sessions been?" | Paginated interaction span rows |

## Span reference

| Span name | What it represents |
|---|---|
| `claude_code.interaction` | One user→Claude turn (duration = wall time for that turn) |
| `claude_code.llm_request` | One LLM API call (latency, model, tokens in attributes) |
| `claude_code.tool` | Tool invocation wrapper |
| `claude_code.tool.execution` | Actual tool execution (subprocess, file I/O, etc.) |
| `claude_code.tool.blocked_on_user` | Permission gate — auto-approved or shown to the user |

## Query workflow

Always pass the user's original question as `searchContext`. Use a relative `timeRange` such as `24h` or `7d` unless the user supplies an exact window.

### Discover fields first

Before filtering on an unfamiliar attribute, call `signoz_get_field_keys` with `signal: "traces"` and a focused `searchText`. Confirm candidate values with `signoz_get_field_values`, passing `signal: "traces"`, the field `name`, and `fieldContext` when the same key exists in multiple contexts.

### Session activity

Call `signoz_search_traces` with:

```json
{
  "searchContext": "How active have my sessions been?",
  "operation": "claude_code.interaction",
  "timeRange": "7d",
  "limit": "100",
  "offset": "0"
}
```

The result is paginated span rows. Increase `offset` by `limit` until the requested window is covered or a page contains fewer rows than the limit.

### Activity by span type

Call `signoz_aggregate_traces` three times with `groupBy: "name"`: once with `aggregation: "count"`, then with `aggregation: "p50"` and `aggregation: "p90"` plus `aggregateOn: "duration_nano"`. Keep the same time range and filters across all three calls.

```json
{
  "searchContext": "Show activity and latency by span type",
  "aggregation": "p90",
  "aggregateOn": "duration_nano",
  "groupBy": "name",
  "timeRange": "7d",
  "limit": "100"
}
```

### Permission pressure

Call `signoz_aggregate_traces` with `aggregation: "count"` and `operation: "claude_code.tool.blocked_on_user"`. Compare that count with a second count using `operation: "claude_code.tool"` over the same time range.

```json
{
  "searchContext": "How often am I blocked on permission prompts?",
  "aggregation": "count",
  "operation": "claude_code.tool.blocked_on_user",
  "timeRange": "7d"
}
```

### Full trace inspection

Use a `trace_id` returned by `signoz_search_traces` with `signoz_get_trace_details`. Set `includeSpans: true` and use a `timeRange` that includes the original result.

```json
{
  "searchContext": "Inspect the slow interaction in detail",
  "traceId": "<trace_id>",
  "timeRange": "24h",
  "includeSpans": true
}
```

## Interpreting results

**Permission friction**: A high blocked-on-user count relative to tool invocations means many tools reach the permission gate. Inspect representative traces to identify tool names and approval outcomes before recommending allow-list changes.

**Slow tools**: p90 `duration_nano` on `claude_code.tool.execution` above two seconds warrants investigation. Compare it with `claude_code.tool`; the difference can indicate permission wait or wrapper overhead.

**Token and cache data**: Token counts (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`) are attributes on `claude_code.llm_request` spans. Discover their exact field keys first, then inspect representative traces for per-session breakdowns.

**Session cadence**: Interaction spans represent user→Claude turns. Group conversations using the `session.id` attribute rather than assuming one trace equals one complete conversation.

## Notes

- Prefer one focused query over multiple overlapping calls.
- Use `requestType: "time_series"` only for spikes, trends, or changes over time; scalar is the default for totals and ranked tables.
- Durations use nanoseconds; two seconds is `2000000000`.
- Use the `webUrl` returned by the MCP when linking to SigNoz. Do not construct UI URLs manually.

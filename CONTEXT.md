# CONTEXT — cc-harness plugins

This repository is a multi-plugin distribution repo for Claude Code and Codex.
Each plugin lives self-contained under `plugins/<name>/`. The glossary below
covers the observability and harness terms used by the shipped skills; see
`docs/adr/` for the design history of the plugin layout.

## Glossary

### Tier
One of three Claude capability classes Claude Code uses: **Opus** (high-tier
design/decision work), **Sonnet** (standard agentic work), **Haiku** (cheap
auxiliary calls — titles, summaries, compaction). Naming follows Claude Code's
own model family identifiers; no in-stack router is involved.

### Anthropic Messages API
The wire format Claude Code speaks: `POST /v1/messages` with Anthropic-shaped
content blocks (tool_use, tool_result, thinking, cache_control) and Anthropic
SSE streaming events. The wire format is unchanged whether Claude Code talks
to Anthropic directly or to an OpenAI-compatible provider surfaced under the
same `/v1/messages` shape.

### Interaction
One user prompt and everything it triggers. Claude Code's unit of tracing: each
Interaction is the root of one distributed trace (`claude_code.interaction`),
under which the model requests, tool calls, and hooks it causes are nested. An
Interaction is finer-grained than a Session — a Session contains many
Interactions.

### Session
A single Claude Code conversation, identified by a Session ID. Spans many
Interactions. Claude Code exposes the Session ID two ways: as the
`X-Claude-Code-Session-Id` request header, and as a `session.id` attribute on
its trace spans. The Session is the grouping level a human means by "one
conversation" in the observability backend.

### Completion Trace
A span capturing one model call. In the deprecated gateway era this was emitted
server-side by the gateway and was meant to be a child of the Interaction's
`claude_code.llm_request` span; with the gateway gone, Claude Code's own
`claude_code.llm_request` span is itself the completion-trace view available
in the observability backend. See ADR-0002 for the historical nesting
rationale.

### Trace Context Propagation
Carrying the active trace identity across a process boundary via the W3C
`traceparent` header, so a span emitted on the far side joins the originating
trace instead of starting its own. In Claude Code's setup the *sender* side is
`CLAUDE_CODE_PROPAGATE_TRACEPARENT`; any downstream process that emits OTel
spans needs a W3C propagator engaged (typical `OTEL_PROPAGATORS=tracecontext`)
so its inbound span extracts the header as parent context. If the receiver
side is missing, the far-side span silently becomes an Orphan Trace.

### Orphan Trace
A span emitted as its own trace root with `sessionId: null`, instead of
nesting under the Claude Code Interaction that caused it. Root cause is a
broken receiver side of Trace Context Propagation: when the downstream
process's OTel SDK finds no active parent context (`parent_span is None`) it
falls back to creating a primary root span. Eliminating Orphan Traces means
making the inbound `traceparent` extraction work, not silencing the
downstream telemetry.

### Telemetry Collector
### Telemetry Backend
SigNoz — the observability backend (ADR 0004) that receives OTLP
spans/metrics/logs directly from Claude Code's OTel export. The intermediary
`otelcol` collector was removed; Claude Code exports straight to
`signoz-otel-collector`'s in-network OTLP receiver.

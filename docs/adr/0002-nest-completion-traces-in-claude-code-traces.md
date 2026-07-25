# 2. Nest Model Gateway completion spans inside Claude Code traces via OTel trace-context propagation

Date: 2026-06-07

## Status

Deprecated (2026-07-22): the LiteLLM gateway whose server-side Completion
Traces this ADR addresses has been removed (PR #84). With no in-stack
gateway, Claude Code's own `claude_code.llm_request` span is the only
completion-trace view. The W3C trace-context propagation concepts remain
valid for any future downstream OTel emitter. Retained as a historical
record; see ADR-0004 for the current observability stack.

## Context

ADR-0001 wired the Model Gateway to log every model call to Langfuse via
LiteLLM's **Langfuse SDK callback** (`success_callback: ["langfuse"]`), feeding
the `langfuse-self-improvement` skill. In practice each completion became its own
orphan Langfuse trace named `litellm-completion` with `sessionId: null`. A single
Claude Code conversation produced dozens of unrelated traces with no way to see
which conversation — or which turn — they belonged to.

Separately, Claude Code emits its own OpenTelemetry traces
(`CLAUDE_CODE_ENABLE_TELEMETRY=1`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`) with a
span hierarchy: `claude_code.interaction` → `claude_code.llm_request` /
`claude_code.tool`. These already carry a native `session.id`.

The goal: a model call should appear as a **child span inside the Claude Code
trace that caused it** — one trace per Interaction, the gateway's Completion
Trace nested under `claude_code.llm_request` — not as a sibling orphan.

Investigation established the load-bearing facts empirically:

1. **Claude Code propagates `traceparent`** (the `claude_code.llm_request` span's
   context) on its model request — but **only when `ANTHROPIC_BASE_URL` is unset
   or points at Anthropic**, suppressed for custom gateways unless
   `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1` is set.
2. **The LiteLLM Langfuse SDK callback ignores `traceparent`.** A request carrying
   a `traceparent` still produced a standalone trace — proven by probe. So
   nesting is impossible on the Langfuse-callback path regardless of the header.
3. **The LiteLLM OTel callback honours `traceparent`** (via
   `TraceContextTextMapPropagator`), making its span a child of the inbound
   trace, **and** captures full prompt/response bodies
   (`gen_ai.input.messages` / `gen_ai.output.messages` /
   `gen_ai.content.*`) under `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`.
4. Both Claude Code and the gateway can export OTLP to the same Telemetry
   Collector (`langfuse-otelcol`), which is what lets spans from two independent
   emitters share one trace. (This collector was found crash-looping on an
   SELinux mount-label issue and is fixed separately; it is a hard prerequisite —
   without it no Claude Code trace reaches Langfuse at all.)

The decisive trade-off: the Langfuse SDK callback gives a clean Langfuse-native
trace shape but **cannot nest**; the OTel callback **can nest** and still
captures full bodies, but changes the trace shape the self-improvement skill
reads.

## Decision

Replace the Langfuse SDK callback with LiteLLM's **OTel callback** and propagate
trace context from Claude Code to the gateway.

- **Claude Code:** set `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1` **globally** (in
  `settings.json`, alongside the existing OTEL telemetry env). The header is
  harmless on direct-Anthropic projects (recorded as a span link), so global
  scope is acceptable and keeps the telemetry settings co-located — unlike the
  per-project gateway opt-in of ADR-0001.
- **Model Gateway:** switch `litellm_settings` from `success_callback:
  ["langfuse"]` to `callbacks: ["otel"]`, exporting OTLP to the Telemetry
  Collector (`langfuse-otelcol:4317`), with
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_AND_EVENT` so full
  bodies are still captured.
- **Replace, not run-both.** Keeping both callbacks would re-emit the original
  orphan `litellm-completion` traces (`sessionId: null`) alongside the nested
  spans — reintroducing the exact mess this work removes. The Langfuse callback
  is removed.
- **`langfuse-self-improvement` compatibility is in scope.** Because the trace
  shape changes from Langfuse-SDK to OTel-ingested spans, the skill's queries
  must be verified against the new shape and fixed if needed as part of this
  work.

The resulting trace:

```
claude_code.interaction                         (Claude Code; carries session.id)
└── claude_code.llm_request                     (Claude Code, client-side view)
    └── Model Gateway Completion Trace          (LiteLLM OTel span, nested via traceparent)
        └── gen_ai.input/output messages, tokens, cost
```

## Consequences

**Positive**

- Model calls nest inside the Interaction that caused them; one trace per turn,
  grouped into the Session via Claude Code's native `session.id`.
- Full prompt/response bodies are still captured for self-improvement.
- The orphan-trace / `sessionId: null` problem is eliminated, not masked.

**Negative / risks**

- **Two spans describe one call by design** — Claude Code's client-side
  `claude_code.llm_request` and the gateway's server-side Completion Trace. This
  is intentional (client vs gateway view), not duplication.
- **Self-improvement skill may break** until its queries are adapted to the OTel
  trace shape — explicitly in scope.
- **Hard dependency on the Telemetry Collector.** If it is down, no nesting (and
  no Claude Code tracing at all) occurs.
- **`traceparent` is sent to every backend** under global propagation. Benign for
  Anthropic; only meaningful for the gateway.

## Verification

1. A real Claude Code call through the gateway produces **one** trace whose
   `claude_code.llm_request` span has the gateway Completion Trace as a child
   (same trace id), not two sibling traces.
2. The nested completion span carries full input/output message content and token
   counts.
3. No `litellm-completion` orphan trace with `sessionId: null` is emitted for
   that call.
4. `langfuse-self-improvement` returns data against the new trace shape.

## Correction (2026-06-08): propagation receiver side was missing

The decision above was correct but the **implementation was incomplete**, and in
practice the gateway still emitted Orphan Traces (`litellm_request` and
`Received Proxy Server Request` root spans with `sessionId: null`). Root cause:

Trace Context Propagation is a **two-sided contract**. ADR-0001/0002 wired the
*sender* side (`CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`) but never engaged a W3C
propagator on the *receiver* side. Without `OTEL_PROPAGATORS=tracecontext` on the
gateway, the container's inbound FastAPI instrumentation does not extract the
incoming `traceparent`, so it opens a fresh root span — and the LiteLLM OTel
callback, finding no active parent (`parent_span is None`), falls back to
creating its own primary `litellm_request` root span. Both land as Orphan
Traces. The claim in line 36–38 that "the OTel callback honours `traceparent` via
`TraceContextTextMapPropagator`" only holds once the propagator is actually
configured.

The fix is therefore to **make inbound `traceparent` extraction work**, not to
silence the gateway's telemetry:

- **Gateway container:** set `OTEL_PROPAGATORS=tracecontext,baggage`. This is the
  load-bearing line — it is what makes the FastAPI server span (and hence the
  callback's `parent_span`) adopt Claude Code's context. Do not remove it.
- **Keep** `callbacks: ["otel"]`, the OTLP export to `langfuse-otelcol`, and
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_AND_EVENT` — full I/O
  body capture is a required feature and must survive.
- After nesting works, the FastAPI ingress span (`Received Proxy Server Request`)
  may optionally be suppressed as noise, provided suppression does not re-orphan
  the callback span.

A prior attempt disabled the gateway's OTEL SDK entirely to stop the Orphan
Traces; that was rejected because it discards the proxy-layer I/O bodies this ADR
requires.

## Known limitation (deferred)

Once the gateway's spans correctly nest onto Claude Code's trace id, they also
become writers to that trace's top-level metadata. Langfuse's OTel receiver
applies last-writer-wins to trace-level `resourceAttributes`/`scope`, so a
`claude_code.interaction` trace may display `service.name`/`scope` of `litellm`
in the trace list even though the span hierarchy is correct. This is a
**cosmetic mislabeling only** — structure and I/O capture are unaffected — and is
**deferred, not fixed**, in this work. A future fix would normalize
resource/scope at the Telemetry Collector.

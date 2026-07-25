# 4. Adopt SigNoz as the agent-queryable observability stack replacing Langfuse

Date: 2026-07-13

## Status

Accepted

## Context

Langfuse (ADR 1's observability sink) is failing to collect the logs, metrics, and traces our
Claude Code agents need for self-feedback: agents fall back to scraping conversation history
instead of querying real telemetry. This ADR records the stack selection; the compose wiring and
telemetry repoint follow as separate implementation work.

Hard requirements:

1. **Three signals.** Claude Code emits logs, metrics, and traces as separate signals; the stack
   must ingest all three. Tracing-only tools are rejected outright, however strong.
2. **Agent access via MCP or CLI.** API-only is an acceptable fallback but must be flagged,
   because it forces a thin CLI/MCP wrapper build in the access-layer work.
3. **OTel-compatible and docker-compose friendly.** Telemetry arrives as OTLP — from Claude Code's
   OTel export. (Previously also from the LiteLLM gateway's `otel` callback
   (ADR 1); the gateway was later removed — see teardown section below.)
   ClickHouse as the storage backend is a plus, not a requirement.
4. **LLM queryability.** Token usage, cost usage, session/conversation look-back, and full
   input/output capture of LLM requests must be queryable.

## Candidates and requirement matrix

Evaluated 2026-07-13 (web research with source links below; MCP-server existence claims checked
against live repos).

| Requirement | SigNoz | ClickStack (HyperDX) | Grafana LGTM | OpenObserve | Uptrace | VictoriaMetrics stack | Elastic + EDOT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Logs + metrics + traces | ✅ unified store | ✅ unified store | ✅ federated (Loki/Mimir/Tempo) | ✅ single binary | ✅ unified | ✅ three separate stores | ✅ |
| OTel/OTLP ingestion | ✅ native | ✅ native | ✅ | ✅ native | ✅ native | ✅ | ✅ |
| docker-compose friendly | ✅ official production compose | ⚠️ all-in-one image, explicitly not production | ⚠️ official image is demo-only; production compose is DIY multi-service + object store | ✅ single container | ✅ official compose | ⚠️ demo compose | ⚠️ community compose, heavy footprint |
| ClickHouse backend (plus) | ✅ | ✅ (is the store) | ❌ | ❌ (Parquet/object storage) | ✅ | ❌ | ❌ |
| MCP access | ✅ **official** [`SigNoz/signoz-mcp-server`](https://github.com/SigNoz/signoz-mcp-server) | ⚠️ HyperDX v2 MCP (new/uneven) + generic [`ClickHouse/mcp-clickhouse`](https://github.com/ClickHouse/mcp-clickhouse) | ✅ official [`grafana/mcp-grafana`](https://github.com/grafana/mcp-grafana) | ⚠️ official but **Enterprise-only** | ❌ none | ❌ none | ❌ none found |
| CLI access | ❌ none dedicated | ✅ `clickhouse-client` | ✅ `logcli` / `tempo-cli` | ⚠️ `o2-cli` Enterprise-only | ❌ | ⚠️ API only | ⚠️ API only |
| Query API (fallback) | ✅ query-service REST + raw ClickHouse SQL | ✅ ClickHouse SQL over HTTP | ✅ LogQL / TraceQL / PromQL HTTP | ✅ `_search` SQL API (OSS) | ✅ ClickHouse SQL | ✅ MetricsQL/LogsQL | ✅ ES query DSL |
| Token / cost / session / full-I/O queries | ✅ purpose-built `gen_ai.*` dashboards | ✅ demonstrated, hand-rolled SQL | ⚠️ TraceQL on `gen_ai.*` works, **but Tempo's default `max_attribute_bytes` (2048 B) truncates full prompt/completion capture** | ✅ documented gen_ai support | ✅ strong native gen_ai/cost views | ⚠️ ingestion only, no curated views | ⚠️ tech-preview |
| License | AGPL-3.0 core (+ proprietary `ee/`) | MIT UI + Apache-2.0 CH/OTel | AGPL-3.0 | AGPL-3.0 OSS; MCP/CLI gated to Enterprise | BSL-style OSS core | Apache-2.0 | Elastic License / SSPL |

**Rejected without scoring** (tracing-only or LLM-trace-only, out of scope by the same rule):
Jaeger, Tempo standalone, Arize Phoenix, and Langfuse itself. **Highlight.io** rejected:
standalone self-hosted service sunset February 2026 (folded into LaunchDarkly).

## Decision

Adopt **SigNoz** (self-hosted docker-compose distribution).

It is the only candidate green on every hard requirement simultaneously:

- **All three signals in one ClickHouse store** — no federated Loki/Tempo/Mimir wiring, no
  per-signal correlation config; trace↔log↔metric correlation is native, and raw ClickHouse SQL
  is available when the query builder runs out.
- **Native official MCP server** — [`SigNoz/signoz-mcp-server`](https://github.com/SigNoz/signoz-mcp-server)
  (stdio + HTTP transports) exposes metrics, logs, traces, alerts, and dashboards to agents. **No
  thin CLI/MCP wrapper needs to be built** — registering and configuring the existing server is
  sufficient. Flag: SigNoz has **no dedicated CLI**; if the MCP surface proves insufficient, the
  fallbacks are the query-service REST API and raw ClickHouse SQL
  ([documented](https://signoz.io/docs/operate/clickhouse/clickhouse-queries/)) — not a new
  wrapper unless both fall short.
- **Official production docker-compose** distribution with a moderate service topology
  (otel-collector, ClickHouse, query-service, frontend), matching how everything else in
  `infrastructure/docker-compose.yml` is run.
- **Purpose-built LLM observability** on `gen_ai.*` semantic conventions — token usage and cost
  views out of the box ([signoz.io/llm-observability](https://signoz.io/llm-observability/));
  session look-back is attribute filtering on the session/conversation attributes Claude Code and
  LiteLLM already emit; full prompt/completion bodies land in span events with no documented hard
  truncation limit (unlike Tempo's 2048-byte attribute cap).
- Existing operational familiarity: SigNoz MCP tooling is already used by this user in another
  environment, lowering the learning cost of the access layer.

**Runner-up: ClickStack (HyperDX).** Permissive licensing and SQL-first access are attractive, but
its HyperDX v2 MCP server is new and unevenly rolled out, the all-in-one image is explicitly not
production-grade, and its LLM views are hand-rolled SQL rather than curated. It remains the
fallback if SigNoz disappoints in practice — the telemetry contract (OTLP + `gen_ai.*`) is
portable between the two.

**Why not Grafana LGTM**, despite best-in-class CLIs and a mature official MCP server: the
official single-container compose is demo-only (production compose is a DIY multi-service + MinIO
build), storage is not ClickHouse, and Tempo's default 2048-byte attribute truncation directly
threatens requirement 4's full input/output capture. **Why not OpenObserve:** its MCP server and
`o2-cli` are Enterprise-gated; the free OSS tier leaves only the raw `_search` API, forcing a
wrapper build. **Why not Uptrace:** strongest native gen_ai cost views of the field, but no MCP
server at all — same wrapper penalty.

## Consequences

- **Compose wiring:** add SigNoz services to `infrastructure/docker-compose.yml`. SigNoz runs its
  own ClickHouse container rather than reusing `langfuse-clickhouse`, per its distribution;
  Port allocations must avoid the existing stack (3012, 4317/4318, 8123…).
- **Telemetry flow:** repoint Claude Code OTel export at SigNoz's collector.
  (The LiteLLM `otel` callback was a second producer at decision time but has
  since been removed with the gateway — see teardown section below.)
- **Access layer:** scope fixed to registering/configuring `signoz-mcp-server` (plus, if needed, a
  ClickHouse-SQL fallback path). No wrapper build.
- **Cutover:** the `langfuse-self-improvement` skill must be replaced by a SigNoz-backed
- **Access layer:** scope fixed to registering/configuring `signoz-mcp-server` (plus, if needed, a
  ClickHouse-SQL fallback path). No wrapper build.
- **Cutover:** the `langfuse-self-improvement` skill must be replaced by a SigNoz-backed
  equivalent before Langfuse is decommissioned; Langfuse historical data migration stays out of
  scope.
- License: AGPL-3.0 core is acceptable for an internal, self-hosted, unmodified deployment.

## Measured results

Filled in once the compose wiring landed:

- **Foundry vs. vendored compose.** The vendored-compose approach worked cleanly in practice.
  Separately — and discovered only during implementation, not anticipated by this ADR — upstream
  removed `deploy/docker` after `v0.129.0` in favor of Foundry (`foundryctl forge/cast`).
  Vendoring the last release to ship the official compose pattern (`v0.129.0`) required two
  adaptations — renaming hostnames inside the vendored `cluster.xml`/collector config to the
  prefixed service names, and moving OTLP host ports off 4317/4318, which were already claimed by
  `langfuse-otelcol`. Foundry migration remains a future consideration to revisit at upgrade time
  or at cutover.
- **Boot outcome.** The stack (6 containers, 2 one-shot) reaches `healthy` — ClickHouse,
  ZooKeeper, and SigNoz itself — in roughly 2 minutes on first boot, including schema migrations.
  The only manual step is SigNoz's first-signup requirement: OTLP ingest is gated until an
  org/user exists, so the collector runs as a no-op pipeline until one is created via the UI or
  `POST /api/v1/register`.

Both outcomes validate the stack selection above without surfacing any requirement-matrix
regressions; no fallback to ClickStack was needed.

### Claude Code telemetry wiring

Filled in once the OTLP endpoint repoint landed:

- **One-line repoint, no new config surface.** The full telemetry env block (exporters, beta
  flags, privacy switches) already existed in the tracked root `settings.json` from the Langfuse
  era. Moving Claude Code's OTLP export to SigNoz required changing only
  `OTEL_EXPORTER_OTLP_ENDPOINT` (`http://localhost:4317` → `http://localhost:4327`) — no new
  environment variables, and Claude Code's default resource identity (`service.name =
  claude-code`) needed no explicit `OTEL_SERVICE_NAME` override.
- **Traces beta confirmed working.** `OTEL_TRACES_EXPORTER=otlp` combined with
  `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` produced 5 distinct span types
  (`claude_code.interaction`, `.llm_request`, `.tool`, `.tool.execution`,
  `.tool.blocked_on_user`) from a single headless verification run. All three signals — traces,
  metrics, logs/events — landed in SigNoz within seconds of session end using shortened export
  intervals (10s metrics / 3s logs) for the verification pass.
- **Pre-merge verification pattern (reusable).** `claude -p --settings <override.json>` — the
  highest-precedence settings file — verifies a `settings.json` change end-to-end (prompt → API
  call → tool use → telemetry landing in the backing store) without mutating the live user
  config. Worth reaching for on any future settings-driven wiring change.
- **First-signup gate reconfirmed.** The earlier finding held under a second, independent
  verification: with fresh volumes, OTLP pipelines stay a no-op until `POST /api/v1/register`
  completes org/user setup. Also newly noted: `docker compose up -d signoz
  signoz-otel-collector` does **not** pull in the one-shot `signoz-schema-migrator` service, since
  compose only starts `depends_on` edges and none targets the migrator — it must be run
  explicitly on first boot, not assumed to come up alongside the two named services.

This completes the Claude Code half of the telemetry-flow work: Claude Code's own OTel export now
reaches SigNoz end-to-end, unblocking the query-layer work. The LLM
request/response capture half (formerly via the LiteLLM gateway) is no
longer applicable — the gateway has been removed (PR #84).

### Langfuse and intermediary otelcol teardown

Filled in once the physical removal landed:

- **Full teardown, not just profile-gating.** The six Langfuse services
  (`langfuse-worker`/`-web`/`-clickhouse`/`-minio`/`-redis`/`-postgres`, previously kept around
  behind a `langfuse` compose profile) and their volumes have been removed outright from
  `infrastructure/docker-compose.yml`, per the cutover this ADR's Consequences section flagged.
- **Intermediary `otelcol` also removed.** The convergence-point collector (`otelcol`, formerly
  `langfuse-otelcol`) that Claude Code forwarded through is gone;
  `infrastructure/otelcol-config.yaml` is deleted. Claude Code now exports straight to
  `signoz-otel-collector`'s in-network OTLP receiver (`:4317` gRPC / `:4318` HTTP) —
  root `settings.json`'s `OTEL_EXPORTER_OTLP_ENDPOINT` points there directly.
  (The `litellm-gateway` was a second producer through `otelcol` but has since
  been removed entirely — PR #84.)
- **No remaining postgres-span-filter/event-transform pipeline stage.** That logic lived in the
  now-deleted `otelcol-config.yaml`; nothing currently replaces it downstream of the producers.
- **Host OTLP ports reclaimed to the standard 4317/4318.** `SIGNOZ_OTLP_GRPC_PORT` /
  `SIGNOZ_OTLP_HTTP_PORT` moved back from the 4327/4328 offset (which existed only to avoid
  colliding with the now-removed `otelcol`) to the upstream defaults, and
  `settings.json`'s `OTEL_EXPORTER_OTLP_ENDPOINT` follows suit
  (`http://localhost:4317`). This is a deliberate deviation from the `~/.claude` reference
  config, which keeps the 4327/4328 offset "for stability" as an established running system —
  this workspace is a fresh removal with nothing left to collide, so it reclaims the standard
  ports instead.

# 1. Route Claude Code model traffic through a LiteLLM gateway with per-tier provider substitution

Date: 2026-06-06

## Status

Deprecated (2026-07-22): the LiteLLM gateway container and its config have
been removed from this repo (PR #84). Claude Code now calls model providers
directly. This ADR is retained as a historical record of the gateway-era
design and its trade-offs; see ADR-0004 for the current observability stack.

## Context

Claude Code calls models directly against the Anthropic API. This setup has
four limitations the user wants to remove:

1. **No provider diversity / resilience.** Every request depends on Anthropic.
   There is no token-based indirection that lets a different provider serve a
   request without reconfiguring Claude Code itself.
2. **No per-tier cost control.** All Tiers (Opus / Sonnet / Haiku) are served by
   Anthropic at Anthropic prices, including the high volume of cheap auxiliary
   and background-agent calls.
3. **No prompt/response capture for self-improvement.** Claude Code does not
   emit full LLM input/output in a form the user's `langfuse-self-improvement`
   skill can consume. (OTEL telemetry exists but is not an LLM-native trace.)
4. **No unified cost tracking** across providers.

The user already runs Langfuse in Docker Compose and uses Docker heavily.

Two integration shapes were considered:

- **Point `ANTHROPIC_BASE_URL` straight at DeepSeek's Anthropic-compatible
  endpoint** (`https://api.deepseek.com/anthropic`). Simplest possible setup and
  DeepSeek maps Claude Tiers to its own models server-side. But it forces *all*
  Tiers onto DeepSeek (no Opus-on-real-Claude), gives no cross-provider cost
  tracking, and no Langfuse capture.
- **Insert a LiteLLM gateway** as the single Anthropic-Messages ingress that
  fans out per Tier, with Langfuse + cost tracking on every hop.

The load-bearing technical question was whether LiteLLM's `/v1/messages`
(Anthropic Messages API) endpoint can accept Anthropic-format requests —
including tool_use / tool_result / thinking blocks and SSE streaming — and route
them to *non-Anthropic* providers with faithful translation. The LiteLLM docs
confirm this: the Anthropic `/v1/messages` endpoint works across all supported
providers (openai, anthropic, bedrock, gemini, deepseek, …) with cost tracking,
logging, streaming, and tool use. The only stated limitation (guardrails are
non-streaming only) does not apply here.

## Decision

Insert a **LiteLLM Model Gateway** between Claude Code and the providers.

- Claude Code talks to the gateway **exclusively via the Anthropic Messages API**
  (`ANTHROPIC_BASE_URL` → gateway). The Anthropic Messages API is the contract
  for every hop, regardless of which provider serves the request.
- The gateway routes on the incoming Claude model name (the **Routing Key**),
  per **Tier**:

  | Routing Key      | Served by         | Provider              |
  | ---------------- | ----------------- | --------------------- |
  | `claude-opus-*`  | real Claude Opus  | Anthropic (Passthrough) |
  | `claude-sonnet-*`| `deepseek-v4-pro` | DeepSeek (direct)     |
  | `claude-haiku-*` | `deepseek-v4-flash` | DeepSeek (direct)   |

- **Opus is always Passthrough to Anthropic** — high-tier design/decision work
  stays on real Claude.
- **Deployment:** LiteLLM runs as the `litellm-gateway` service added to the
  existing `infrastructure/docker-compose.yml` (which already hosts Langfuse,
  Milvus, and Memgraph), bound to `127.0.0.1:4141:4000`, `restart:
  unless-stopped`. The service name and host port follow the stack's
  `<stack>-<role>` convention and avoid the ports already in use. Its routing
  config lives at `infrastructure/litellm-gateway-config.yaml`, mounted into the
  container alongside the existing `otelcol-config.yaml`. Claude Code reaches it
  at `ANTHROPIC_BASE_URL=http://localhost:4141`.
- **Auth is two-layered:** real provider keys (`ANTHROPIC_API_KEY`,
  `DEEPSEEK_API_KEY`) and the `LITELLM_MASTER_KEY` live only in a gitignored
  `infrastructure/.env`; Claude Code presents a single LiteLLM **virtual key** as
  `ANTHROPIC_AUTH_TOKEN`. The Langfuse credentials are the existing local dev
  literals (`lf-pub-local` / `lf-secret-local`), not secrets.
- **Observability:** LiteLLM logs full request bodies (system prompt, messages,
  tool definitions) and full response bodies (completion, tool calls, token
  counts, cost) to the existing Langfuse instance (internal host
  `http://langfuse-web:3000`) on every request.
- **Opt-in:** Claude Code is pointed at the gateway via per-project
  `settings.local.json`, not global config — so the gateway is opted in per repo
  and bypassed by removing the override.

## Consequences

**Positive**

- Provider diversity and token-based indirection: swap a Tier's backend by
  editing gateway config, with no Claude Code change. The virtual key can be
  rotated/revoked without touching real provider keys.
- Per-Tier cost control: high-volume Sonnet/Haiku traffic served by cheaper
  DeepSeek models while Opus stays on Claude.
- Full prompt/response capture in Langfuse, feeding the self-improvement skill.
- Unified cross-provider cost tracking at a single ingress.

**Negative / risks**

- **Availability coupling:** when the gateway points at it, Claude Code depends
  on the gateway being up — including for Opus. Mitigated by `restart:
  unless-stopped` and by the per-project opt-in escape hatch (remove the
  `settings.local.json` override to go direct). No automatic Anthropic fallback
  is configured.
- **Translation fidelity:** Provider Substitution relies on LiteLLM's
  Anthropic↔provider translation of tool_use / tool_result / thinking blocks.
  Confirmed supported by docs but must be smoke-tested on a real agentic run
  (a Sonnet-routed background agent completing a file edit) before it is trusted
  for production agent work.
- **Model-quality shift:** Sonnet/Haiku agent work is now served by DeepSeek, a
  behavioural change that may affect agent reliability independent of translation.

## Verification

1. A `claude-opus-*` request appears in Langfuse as served by Anthropic.
2. A `claude-sonnet-*` background agent completes a real file edit through
   DeepSeek with intact tool calls.
3. Langfuse shows full prompt + response bodies and per-request cost for both.
4. Stopping the gateway produces a clear, immediate failure (no silent hang).

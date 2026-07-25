# cc-harness plugins

This repository is a multi-plugin distribution repo for Claude Code and Codex.
It ships self-contained plugins under `plugins/`, each installable from the
same git repository via the harness's native plugin marketplace.

## Plugins

| Plugin | Path | Harnesses | Purpose |
|--------|------|-----------|---------|
| `harness5` | `plugins/harness5/` | Claude Code, Codex | Workflow skills (design-session, multi-task, agentic-memory, memsearch, graphsearch, standup, …) + the `infrastructure/` docker-compose stack (SigNoz, Graphiti memory) |
| `auto-review` | `plugins/auto-review/` | Codex | LLM auto-review hook for `PermissionRequest` events |

## Install

### Claude Code (harness5 only)

```sh
claude plugin marketplace add dzungtr/cc-harness
claude plugin install harness5
```

### Codex (both plugins)

```sh
codex plugin marketplace add dzungtr/cc-harness
codex plugin install harness5      # skills + infra stack
codex plugin install auto-review   # permission auto-review hook
```

### Post-install (harness5)

After installing `harness5`, run the **`harness5-init`** skill — it scaffolds
`infrastructure/.env` from `.env.example`, brings up the shared compose stack,
and waits for the SigNoz healthcheck. Once the stack is up:

- SigNoz UI: <http://localhost:8080> (OTLP via the in-stack collector)

## Repository layout

| Path | Purpose |
|------|---------|
| `plugins/harness5/` | harness5 plugin: `skills/`, `infrastructure/`, `.codex-plugin/`, `.claude-plugin/` |
| `plugins/auto-review/` | auto-review plugin: hook scripts, `.codex-plugin/` |
| `.claude-plugin/marketplace.json` | Claude Code marketplace (lists harness5) |
| `.agents/plugins/marketplace.json` | Codex marketplace (lists both plugins) |
| `docs/adr/` | Architecture Decision Records |
| `README.md`, `CONTEXT.md` | Repo-level docs |

Repo-root content that is **not** part of any plugin (development-only):
`settings.json`, `agents/`, `hooks/`, `scripts/`, `.mcp.json`,
`.memsearch.toml`. These remain at root for local development and are not
shipped by either plugin.

## Design history

- [ADR 0005](docs/adr/0005-harness5-plugin-distribution.md) — original
  root-native single-plugin decision (superseded for layout by ADR 0007).
- [ADR 0006](docs/adr/0006-auto-review-llm-permission-agent.md) — auto-review
  LLM permission agent.
- [ADR 0007](docs/adr/0007-multi-plugin-layout.md) — multi-plugin layout,
  relocating harness5 into `plugins/harness5/`.

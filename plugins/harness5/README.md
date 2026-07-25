# harness5 — Claude Code & Codex Plugin

harness5 ships the cda-plugins workflow skills and a local infrastructure stack
(SigNoz observability, Graphiti memory) as a self-contained plugin under
`plugins/harness5/`. It installs identically into Claude Code and Codex from the
same git repository; the same `skills/` and `infrastructure/` tree ships to both
harnesses with no duplication.

## What ships

| Path | Purpose |
|------|---------|
| `skills/` | Workflow skills: `design-session`, `multi-task`, `scope-review`, `agentic-memory-*`, `memsearch-*`, `graphsearch-*`, `harness5-init`, `standup`, `autobot`, `self-improvement`, `pr-merged-cleanup`, `awsctx`, `sentry-cli` |
| `infrastructure/` | Docker Compose stack + configs (SigNoz, OTel collector, Graphiti memory) |
| `.codex-plugin/plugin.json` | Codex plugin manifest |
| `.claude-plugin/plugin.json` | Claude Code plugin manifest |

After a fresh install, run the **`harness5-init`** skill — it scaffolds
`infrastructure/.env` from `.env.example`, brings up the shared compose stack,
and waits for the SigNoz healthcheck. Once the stack is up:

- SigNoz UI: <http://localhost:8080> (OTLP via the in-stack collector)

## Installation

### Claude Code

```sh
claude plugin marketplace add dzungtr/cda-plugins
claude plugin install harness5
```

### Codex

```sh
codex plugin marketplace add dzungtr/cda-plugins
codex plugin install harness5
```

## Plugin structure

```
plugins/harness5/
├── .codex-plugin/
│   └── plugin.json                 # Codex manifest (skills: ./skills/)
├── .claude-plugin/
│   └── plugin.json                 # Claude Code manifest (skills: ./skills)
├── skills/                         # workflow skills (18 dirs)
├── infrastructure/                 # docker-compose.yml, .env.example, signoz/
├── README.md                       # this file
└── CHANGELOG.md                    # per-version notes
```

The `"skills"` path in both manifests resolves relative to the plugin directory,
so the move from repo-root-native layouts (ADR 0005) to the `plugins/harness5/`
subfolder (ADR 0007) requires no install-side change.

## Plugin-root resolution

`harness5-init` resolves its root from `PLUGIN_ROOT` (Codex) or
`CLAUDE_PLUGIN_ROOT` (Claude Code), then expects `infrastructure/` directly
under that root. Both harnesses set the env var to the installed plugin's own
directory, so the relocation is transparent to the skill.

## Related

- Sibling plugin: `plugins/auto-review/` — LLM auto-review hook for Codex
  `PermissionRequest` events.
- Design history: `docs/adr/0005-harness5-plugin-distribution.md` (original
  root-native decision) and `docs/adr/0007-multi-plugin-layout.md` (this
  refactor).

# harness5 — Claude Code & Codex Plugin

harness5 ships the harness6 workflow skills and a local infrastructure stack
(SigNoz observability, Graphiti memory) as a self-contained plugin under
`plugins/harness5/`. It installs identically into Claude Code and Codex from the
same git repository; the same `skills/` and `infrastructure/` tree ships to both
harnesses with no duplication.

## What ships

| Path | Purpose |
|------|---------|
| `skills/` | Workflow skills: `design-session`, `multi-task`, `scope-review`, `agentic-memory-*`, `memsearch-*`, `graphsearch-*`, `harness5-init`, `standup`, `autobot`, `self-improvement`, `pr-merged-cleanup`, `awsctx`, `sentry-cli` |
| `infrastructure/` | Docker Compose stack + configs (SigNoz, OTel collector, Graphiti memory) |
| `hooks/` | `SessionStart` hook (Codex + Claude Code) + bundled `references/harness5.md` |
| `.codex-plugin/plugin.json` | Codex plugin manifest |
| `.claude-plugin/plugin.json` | Claude Code plugin manifest |

After a fresh install, run the **`harness5-init`** skill — it scaffolds
`infrastructure/.env` from `.env.example`, brings up the shared compose stack,
and waits for the SigNoz healthcheck. Once the stack is up:

- SigNoz UI: <http://localhost:8080> (OTLP via the in-stack collector)

## Installation

### Claude Code

```sh
claude plugin marketplace add dzungtr/harness6
claude plugin install harness5
```

### Codex

```sh
codex plugin marketplace add dzungtr/harness6
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
├── hooks/                          # SessionStart hook (Codex + Claude Code)
│   ├── hooks.json                  # Codex hooks config (auto-discovered)
│   ├── claude/hooks.json           # Claude Code hooks config (manifest-declared)
│   ├── loader.py                   # shared stdlib-only loader, +x
│   ├── validate.py                 # plugin self-check (6 checks)
│   ├── test_loader.py              # loader unit tests
│   ├── test_validate.py            # self-check unit tests
│   └── references/harness5.md      # bundled operating instructions
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

## SessionStart hook

Every Codex or Claude Code session with `harness5` installed starts with the
plugin-bundled operating instructions automatically loaded into context. The
hook reads `plugins/harness5/hooks/references/harness5.md` (a verbatim copy
of the harness5 operating rules) and emits it as `additionalContext` on the
`SessionStart` event. Both harnesses consume the same JSON shape, so a single
loader at `plugins/harness5/hooks/loader.py` serves both.

- **Bundled instructions** live at
  `plugins/harness5/hooks/references/harness5.md`. Update there if you change
  the operating instructions — both harnesses pick them up on the next
  session start after `plugin update harness5` (or a fresh install).
- **Failure mode**: if the bundled file is missing or unreadable, the hook
  emits no JSON, prints a single-line warning to stderr, and exits 0. The
  session still starts normally — the hook never blocks it.
- **Size cap**: a soft warning fires to stderr when the file exceeds 32 KiB,
  but the file is still injected in full (no truncation).
- **Enablement**:
  - **Codex**: the hook is auto-discovered. Open Codex and run `/hooks`,
    locate the `harness5` SessionStart entry, and approve it.
  - **Claude Code**: the plugin manifest declares the hook path. Set the
    project to `trust_level = "trusted"` in `~/.claude/settings.json` (or the
    project's `.claude/settings.json`) so Claude Code will run it.

If you maintain a repo-level `CLAUDE.md` or `AGENTS.md`, prefer the bundled
`hooks/references/harness5.md` and delete the repo-level copy — having two
instruction sources causes drift.

## Related

- Sibling plugin: `plugins/auto-review/` — LLM auto-review hook for Codex
  `PermissionRequest` events.
- Design history: `docs/adr/0005-harness5-plugin-distribution.md` (original
  root-native decision) and `docs/adr/0007-multi-plugin-layout.md` (this
  refactor).

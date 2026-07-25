# cc-harness

This repository is a personal `~/.claude` directory — the global Claude Code configuration that travels with every project.

## What lives here

| Path | Purpose |
|------|---------|
| `CLAUDE.md` | Global instructions loaded into every Claude session: workflow rules, agent dispatch patterns, model selection guidelines |
| `skills/` | Reusable skill definitions (`superpowers:*`, `design-session`, `multi-task`, etc.) invoked via the Skill tool |
| `agents/` | Agent definitions and supporting docs (e.g. `k8s-troubleshooter.md`) |
| `commands/` | Custom slash commands |
| `docs/` | Project documentation including Architecture Decision Records (ADRs) |
| `hooks/` | Hook scripts run by Claude Code (e.g. `guard-destructive-git.sh`) |
| `infrastructure/` | Docker Compose and config files for local services (SigNoz observability stack, Memgraph, Milvus) |
| `scripts/` | Helper shell scripts used by hooks and agents |
| `settings.json` | Claude Code settings: permissions, hooks, MCP server config, keybindings |

## How it works

Claude Code loads `~/.claude/CLAUDE.md` automatically in every project session. That file wires up:

- **Two workflows** — Workflow A (quick background agents) and Workflow B (design-led sessions) — with rules for when to use each
- **Git worktree isolation** — all PR-bound work runs in `.worktrees/<branch>` inside the project, never on the main checkout
- **Team-agent dispatch** — tasks that produce a PR are delegated to a named team agent; the main session stays responsive
- **Security scanning** — Snyk code scan runs on any first-party code added or modified in a supported language

## Skills

Skills are Markdown files that Claude reads on demand when invoked with the Skill tool (or a `/slash-command`). They encode repeatable processes — designing a feature, finishing a branch, running a code review, debugging systematically — so Claude follows the same procedure every time instead of improvising.

## Install as a plugin

`harness5` packages this repo as an installable plugin for both Claude Code and Codex. It ships the shared `skills/` tree and the `infrastructure/` compose stack; it leaves your personal `~/.claude` configuration alone.

### Claude Code

```sh
claude plugin marketplace add dzungtr/cc-harness
claude plugin install harness5
```

### Codex

```sh
codex plugin marketplace add dzungtr/cc-harness
codex plugin install harness5
```

### Post-install

After either install, run the **`harness5-init`** skill — it scaffolds `infrastructure/.env` from `.env.example`, brings up the shared compose stack, and waits for the SigNoz healthcheck. Once the stack is up:

- SigNoz UI: <http://localhost:8080> (OTLP via the in-stack collector)

### What ships vs. what stays machine-local

- **Ships in the plugin**: `skills/`, `infrastructure/` (compose + configs).
- **Stays machine-local**: `settings.json`, `agents/`, `commands/`, `hooks/`, `docs/`, `scripts/`, plus caches, sessions, credentials. A live install in Claude Code 2.1.168 confirms the `commands: []` / `agents: []` settings in the manifest suppress the default scan, so those paths do **not** leak into the plugin install — they only matter if you clone or symlink the repo directly as `~/.claude`.

## Usage

Clone or symlink this repo to `~/.claude`. Claude Code picks it up automatically on next launch.

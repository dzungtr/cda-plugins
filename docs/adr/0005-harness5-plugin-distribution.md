# 5. Distribute cc-harness as the harness5 plugin for Claude Code and Codex

Date: 2026-07-19

## Status

Accepted

## Context

This repo is a personal `~/.claude` global configuration. The only consumption path was
clone/symlink of the entire directory, which couples reusable content (skills, infrastructure
stack) to machine-specific state (settings, caches, sessions, credentials) and makes the repo
unconsumable by Codex, which has its own plugin system. There was no installable, versioned,
shareable unit.

## Decision

Package the repo as a **single plugin named `harness5`**, installable natively by both Claude
Code and Codex from the same git repository:

- **One plugin, not several.** The skills are interdependent and a personal config does not
  justify multiple manifests to maintain.
- **Root-native manifests, no `meta/` folder or build step.** Claude Code reads
  `.claude-plugin/plugin.json` plus `.claude-plugin/marketplace.json` (the repo is its own
  marketplace); Codex reads `.codex-plugin/plugin.json` plus a repo-level marketplace entry.
  Installable directly from git.
- **Shared `skills/` tree.** Both manifests point at the same skills directory; a skill edit
  ships to both harnesses with no duplication.
- **`infrastructure/` ships as cargo.** Both harnesses clone the whole repo into their plugin
  caches, so the compose stack travels with the plugin; it is started by a skill, not by the
  harness.
- **Excluded from the plugin contract:** settings.json, agents/, commands/, hooks/, scripts/,
  and all machine state. (Claude Code may auto-discover commands/agents/hooks
  even when unlisted; if that leaks, those directories are relocated out of the discoverable
  surface.)
- **`harness5-init` skill** scaffolds `infrastructure/.env` from `.env.example` (key list
  verbatim; refinement deferred) and runs `docker compose up -d` from the plugin's own
  directory — one shared local instance for all projects, matching current usage.
- **Plugin-root resolution is always via the harness-provided env var** (`CLAUDE_PLUGIN_ROOT`
  for Claude Code; the Codex equivalent recorded in the PRD issue's Handoffs table). Paths are
  never hardcoded, so the skill survives cache-busted reinstalls and harness layout changes.
- **opencode is out of scope.** A native opencode plugin requires a JS/TS shim; deferred unless
  demand appears.

## Consequences

- A second machine or harness gets skills + infrastructure without inheriting personal state.
- The repo remains a working `~/.claude` directory on the owner's machine; the plugin manifests
  are additive.
- The `.env.example` key list is the contract surface for `harness5-init`; refining it later
  automatically refines the skill.
- If Claude Code auto-discovery forces relocation of commands/agents/hooks, the repo's own
  `~/.claude` usage must keep working (settings.json references) — check before moving.

## Measured results

Outcomes recorded in PRD issue #64 at initiative close (all four child PRs merged: #71, #70, #72,
#73; child issues #65-#68 closed). PRD #64's own `Results` section remained a stub, so these
items are drawn from its `Handoffs` table and `Definition of done` — each cited back to its
source row/PR.

- **Installs in both harnesses.** Claude Code manifest + self-hosted marketplace shipped in PR
  #71 (`ccef66c`); Codex manifest + repo-level marketplace entry shipped in PR #70 (merged
  2026-07-19, `8b1a0b8`). Definition-of-done item "harness5 installs and its skills load in both
  Claude Code and Codex" marked complete. (#64 Definition of done)
- **No commands/agents/hooks auto-discovery leak in Claude Code.** On Claude Code 2.1.168, an
  empty-array manifest suppresses the default `commands/` / `agents/` scan — there is no leak;
  README install docs (#68/PR #73) confirm this. (#64 Handoffs row "Live-install auto-discovery
  finding", produced by #71 reviewer)
- **Plugin-root env vars (verified).** `CLAUDE_PLUGIN_ROOT` (Claude Code) and `PLUGIN_ROOT`
  (Codex, which also sets `CLAUDE_PLUGIN_ROOT`); the `harness5-init` skill checks `PLUGIN_ROOT`
  first then falls back. (#64 Handoffs rows "Codex plugin-root env var name" / "Claude Code
  plugin-root env var")
- **SigNoz default port (verified).** SigNoz UI
  `${SIGNOZ_UI_PORT:-8080}:8080`. Cross-checked by PR #73 against
  `infrastructure/docker-compose.yml`. (The LiteLLM gateway port `4141`
  was removed in PR #84.) (#64 Handoffs row "Gateway / SigNoz default ports",
  produced by #72 skill body)
- **`harness5-init` end-to-end works from a clean install.** Creates `infrastructure/.env` from
  `.env.example` and runs `docker compose up -d` from the plugin's own directory, covering all
  four procedure steps plus the two env-var fallbacks. PR #72 merged 2026-07-18 15:14 UTC. (#64
  Definition of done)
- **README install docs shipped per harness.** PR #73 (`a86ae18`) documents install for both
  Claude Code and Codex, with the port numbers above cross-checked against the compose file. (#64
  Definition of done)
- **Pre-existing validator noise was not introduced by this initiative.** Four unrelated
  skill-naming failures from `validate_plugin.py` (`autobot` `disable-model-invocation`,
  `awsctx`/`sentry-cli` missing `SKILL.md`, `design-session` YAML quoting) were flagged by the
  #66 reviewer as pre-existing, not introduced by #66/PR #70. (#64 Handoffs row "Pre-existing
  validator noise")
- **Scope-creep noted for owner review (not reverted).** Commit `553b828` deletes one
  `superpowers:brainstorming` bullet from `CLAUDE.md`; merged on `main` 2026-07-18 as part of
  PR #71. Owner may revert with a one-liner if undesired. (#64 Handoffs row "Scope-creep on PR
  #71", produced by #71 reviewer)
- **opencode remains out of scope.** A native opencode plugin would require a JS/TS shim; not
  addressed by this initiative. (#64 Solution / Implementation Decisions)

## References

- PRD: GitHub issue #64 (child issues #65–#68)

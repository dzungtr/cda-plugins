# 7. Multi-plugin layout: relocate harness5 into plugins/harness5/

Date: 2026-07-25

## Status

Accepted — supersedes the "root-native manifests" and "one plugin, not
several" clauses of [ADR 0005](0005-harness5-plugin-distribution.md).

## Context

ADR 0005 packaged the repo as a single root-native plugin: `.codex-plugin/`
and `.claude-plugin/` manifests at the repo root, with `skills/` and
`infrastructure/` at the root, sourced via `"source": "./"`. That made sense
when the repo was a personal `~/.claude` config first and a plugin
distribution second.

The repo has since been forked into a dedicated plugin-distribution repo. A
second plugin, `auto-review`, already lives self-contained under
`plugins/auto-review/` (ADR 0006). The root-native harness5 layout is now the
odd one out: two plugins, two different packaging styles, and the root
manifests still describe a single-plugin repo that no longer reflects
reality.

## Decision

Relocate `harness5` into `plugins/harness5/`, mirroring the `auto-review`
pattern, and treat the repo as a multi-plugin distribution repo.

- **Self-contained plugin dir.** `skills/`, `infrastructure/`, and both
  manifests (`.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`) move
  into `plugins/harness5/`. The plugin is fully self-contained, identical in
  shape to `plugins/auto-review/`.
- **Manifests stay relative to the plugin dir.** The `"skills": "./skills/"`
  (Codex) and `"skills": "./skills"` (Claude Code) fields are unchanged —
  they resolve relative to the plugin dir, so the move requires no
  install-side change.
- **Marketplaces list every plugin.** `.claude-plugin/marketplace.json` and
  `.agents/plugins/marketplace.json` enumerate all plugins, each with
  `source` pointing at its `plugins/<name>/` subfolder. The Claude
  marketplace lists only plugins that ship a `.claude-plugin/plugin.json`
  (currently `harness5` only — `auto-review` is Codex-only); the Codex
  marketplace lists both.
- **`.gitignore` exception.** The repo's broad `plugins/**/*` ignore is
  negated for `plugins/auto-review/` and `plugins/harness5/` so tracked
  plugin content is committable without per-file `git add -f`.
- **`harness5-init` is unaffected.** It resolves the plugin root from
  `PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT` and then looks for
  `infrastructure/` directly under that root. Both harnesses set the env
  var to the installed plugin's own directory, so the path-depth change is
  absorbed automatically. Bare `infrastructure/...` paths used by other
  skills (`graphsearch-index`, `agentic-memory-read`) likewise still
  resolve.
- **Repo-root content is development-only.** `settings.json`, `agents/`,
  `hooks/`, `scripts/`, `docs/`, `.memsearch.toml`, `.mcp.json`, and the
  root `README.md`/`CONTEXT.md` remain at repo root but are no longer part
  of any plugin's shipped surface — they never were, and the move makes
  that explicit.

## Consequences

- Two plugins, one packaging style. Adding a third plugin means dropping a
  new folder under `plugins/` and adding a marketplace entry — no manifest
  surgery at the root.
- ADR 0005's "root-native" and "one plugin" clauses are obsolete; its other
  findings (shared `skills/` tree, `infrastructure/` as cargo, env-var
  plugin-root resolution, exclusion of machine state) carry forward
  unchanged.
- The repo is no longer a drop-in `~/.claude` directory. Anyone using it
  that way must point at `plugins/harness5/skills/` explicitly, or install
  via the marketplace. This is intentional: the repo's job is distribution,
  not personal config.
- `.gitignore` now carries explicit per-plugin negations. A new plugin must
  add its own `!plugins/<name>/` lines or remain untracked.

## Measured results

_To be filled at initiative close._

## References

- Supersedes: [ADR 0005](0005-harness5-plugin-distribution.md)
- Sibling plugin decision: [ADR 0006](0006-auto-review-llm-permission-agent.md)
- Plugin source: `plugins/harness5/`
- Plugin manifests: `plugins/harness5/.codex-plugin/plugin.json`,
  `plugins/harness5/.claude-plugin/plugin.json`
- Marketplaces: `.claude-plugin/marketplace.json`,
  `.agents/plugins/marketplace.json`

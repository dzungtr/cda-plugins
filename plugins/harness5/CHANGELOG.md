# Changelog

All notable changes to the `harness5` plugin.

## [0.2.0] - 2026-07-25

Relocated the plugin from repo-root-native manifests into `plugins/harness5/`,
sibling with `plugins/auto-review/`. The repo is now a multi-plugin
distribution repo rather than a personal `~/.claude` config.

### Changed

- **Layout** — `skills/` and `infrastructure/` moved into
  `plugins/harness5/`. The `.codex-plugin/plugin.json` and
  `.claude-plugin/plugin.json` manifests moved alongside them. The plugin is
  now fully self-contained under `plugins/harness5/`, matching the
  `plugins/auto-review/` pattern.
- **Manifests** — descriptions updated to drop the "single installable
  plugin" framing and the personal-`~/.claude` references; version bumped to
  0.2.0. The `"skills"` path fields still resolve relative to the plugin
  dir (`./skills/`), so no install-side change is required.
- **Marketplaces** — `.claude-plugin/marketplace.json` and
  `.agents/plugins/marketplace.json` now list both `harness5` and
  `auto-review`, each with `source` pointing at its `plugins/<name>/`
  subfolder.
- **ADR 0007** supersedes ADR 0005's "root-native manifests, one plugin"
  decision for the multi-plugin layout.

### Notes

- `harness5-init` is unaffected: it resolves the plugin root from
  `PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT`, so the path-depth change is absorbed
  automatically. The bare `infrastructure/...` paths inside skills still
  resolve correctly because an installed plugin's root is its own dir.
- The repo no longer ships `settings.json`, `agents/`, `hooks/`, `scripts/`,
  or `docs/` as part of any plugin; those remain at repo root as
  development-only content.

## [0.1.1] - 2026-07-19

Initial release as a root-native plugin (per ADR 0005). See
`docs/adr/0005-harness5-plugin-distribution.md` for the original decision and
measured results.

# Changelog

All notable changes to the `harness5` plugin.

## [0.2.1] - 2026-07-25

Adds a `SessionStart` hook that injects the bundled `references/harness5.md`
operating instructions into every Codex and Claude Code session.

### Added

- **SessionStart hook** — `plugins/harness5/hooks/hooks.json` (Codex,
  auto-discovered) and `plugins/harness5/hooks/claude/hooks.json` (Claude
  Code, declared via `.claude-plugin/plugin.json`). Both wire to the same
  shared loader at `plugins/harness5/hooks/loader.py`.
- **Bundled instructions file** —
  `plugins/harness5/hooks/references/harness5.md`. Carries the harness5
  operating instructions verbatim so every Codex/Claude Code session with
  harness5 installed starts with them loaded.
- **Loader script** — `plugins/harness5/hooks/loader.py` (Python 3 stdlib
  only, `+x`). Emits the canonical
  `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}`
  shape that both harnesses consume identically.
- **Plugin self-check** — `plugins/harness5/hooks/validate.py` (six
  checks: manifest version, manifest hooks field, hooks files present,
  hooks JSON valid, loader executable, bundled markdown present) plus
  `test_loader.py` and `test_validate.py` (`unittest`, 21 tests total).

### Loader contract

- **Failure mode**: missing or unreadable `harness5.md` → no JSON on
  stdout, single-line warning on stderr, exit 0. The hook never blocks
  a session.
- **Size cap**: soft warning on stderr when `harness5.md` exceeds 32,768
  characters, but the file is still injected without truncation.

### Notes

- The repo-root `CLAUDE.md` is removed in a follow-up slice (#10) so the
  hook becomes the sole source of truth and there is no window where a
  user's CLAUDE.md auto-load and the hook injection disagree.

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

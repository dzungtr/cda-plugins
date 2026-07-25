# Changelog

All notable changes to the `auto-review` Codex plugin.

## [0.1.0] - 2026-07-22

Initial release. Delivers the four-slice MVP from epic
[dzungtr/cc-harness#79](https://github.com/dzungtr/cc-harness/issues/79).

### Added

- **Static deny-bucket engine** (slice #80, PR #86) — instant regex-based
  block for universally destructive commands: `rm -rf` on root/home,
  `git push --force` to `main`/`master`, `git reset --hard`, `git clean -fd/-fx`,
  `git branch -D` on protected branches, `chmod -R 777 /`, `dd`/`mkfs` on
  block devices, fork bomb, and pipe-to-shell remote execution. The
  `--force-with-lease` and feature-branch force-push exceptions are preserved.
- **Bounded-turn LLM agent loop** (slice #81, PR #87) — OpenAI-compatible
  Chat Completions endpoint with `response_format: json_object` protocol,
  max 8 turns, 30-second wall-clock budget, redacted environment snapshot,
  read-only probe allowlist (`git status/diff/log/branch/show`, `git stash list`,
  `git remote -v`, `cat/ls/rg/pwd/head/tail/find/env/which`, `command -v`,
  `npm ls`, `pip show/list`). Decline-on-failure: any infra error, timeout,
  or uncertainty → `decline` so the user gets the normal approval prompt.
- **Decision logger** (slice #82, PR #88) — appends one JSON line per
  review to `$PLUGIN_DATA/reviews.jsonl` (falls back to
  `$XDG_DATA_HOME/auto-review/` then `~/.local/share/auto-review/`).
  Schema: `{ts, tool_name, command (≤500 chars), verdict, turns, reason}`.
  Logging failure is non-fatal.
- **README** (slice #83, this PR) — full user documentation: what the
  plugin does, two-stage pipeline diagram, deny-bucket rules table, agent
  loop protocol, probe allowlist, env-var configuration for OpenRouter /
  Ollama / vLLM, decision log schema + inspection recipes, installation
  via `config.toml` + `/hooks` trust step, plugin structure tree,
  troubleshooting matrix.
- **Plugin self-validator** (slice #83, this PR) — `scripts/validate.py`
  mirrors Codex's `validate_plugin.py` for the slice-#83 acceptance
  criteria, plus plugin-specific checks (env-var documentation, exec
  bits, test presence, README TODO markers). Exits non-zero with a
  per-check `[PASS]/[FAIL]` line and a stderr summary.
- **Test coverage** (this PR) — 19 new tests in `test_validate.py`
  (5 happy-path, 14 negative cases) for the self-validator.

### Notes

- No skills shipped with v1 — a `review-status` skill may be added later.
- The hook is Python 3 stdlib only; no third-party dependencies.
- The plugin fills a gap in Codex's built-in `approvals_reviewer =
  "auto_review"`, which only works with OpenAI-native providers.

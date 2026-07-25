# 6. LLM-agent-based permission auto-review for Codex (auto-review plugin)

Date: 2026-07-22

## Status

Accepted

## Context

Codex ships a built-in `approvals_reviewer = "auto_review"` that auto-approves or denies tool
calls before they reach the human, but it is hard-wired to OpenAI-native providers and models.
On a non-OpenAI provider (e.g. Codex-on-MiniMax via OpenRouter) the built-in reviewer never
fires, so every command that needs approval becomes a manual prompt. The friction cuts both
ways: the user is constantly interrupted to approve commands that are obviously safe (builds,
package installs, feature-branch `git` operations), while truly destructive commands slip
through when the user approves reflexively to clear the queue. There is no way to get
LLM-judged contextual permission review on a non-OpenAI provider, and the static
pre-filtering the built-in reviewer performs on OpenAI is not available off-OpenAI either.

## Decision

Ship a standalone Codex plugin named `auto-review` that intercepts `PermissionRequest` hook
events (which fire only when Codex is about to ask for approval) and runs a two-stage
evaluation:

- **Plugin shape.** Single `auto-review` plugin lives at `plugins/auto-review/` in this repo
  and is enabled via the existing `cc-harness` Codex marketplace. No skills are bundled in
  v1 (hooks-only); a `review-status` or `review-config` skill can be added later. The plugin
  is pure Python 3 stdlib — zero runtime dependencies, no `pip install` needed. (Slice #80,
  PR #86, `e39becb`.)
- **Stage 1 — static deny-bucket.** A regex rule list (`DENY_RULES` in
  `plugins/auto-review/scripts/auto_review.py`) matches universally destructive commands
  instantly with no LLM call: `rm -rf /|~|$HOME`, `git push --force/-f` to `main`/`master`,
  `git reset --hard`, `git clean -fd/-fx`, `git branch -D main|master`, `chmod -R 777 /`,
  `dd` / `mkfs` to block devices, fork bomb `:(){:|:&};:`, and `curl|wget ... | bash|sh|zsh`.
  The regex anchors explicitly allow `--force-with-lease` to `main`/`master` and bare
  `--force`/`-f` on feature branches. (Slice #80, PR #86, `e39becb`.)
- **Stage 2 — bounded-turn LLM agent loop.** Anything not caught by the deny-bucket goes to
  `run_agent_loop`: a `system` prompt + first-turn `user` message containing the tool call
  and `gather_env_snapshot(cwd)` (repo root, current branch, `git status --porcelain`, last
  5 commits, filtered env with secrets redacted), then up to `MAX_TURNS = 8` exchanges with
  the model. The agent may respond with `{"action":"allow"}` (emit the allow JSON),
  `{"action":"deny","reason":"..."}` (emit the deny JSON), or
  `{"action":"probe","command":"..."}` (run the read-only probe and feed the result
  back). The 30s wall-clock budget is enforced via `time.monotonic()` at the top of each
  turn; on exhaustion the agent declines. (Slice #81, PR #87, `1c8f3e6`.)
- **OpenAI-compatible endpoint, configured via env vars.** `call_llm` POSTs to
  `{base_url}/chat/completions` with `response_format: json_object`, `max_tokens: 512`,
  `temperature: 0.1`, and `Authorization: Bearer …`. Three env vars drive configuration:
  `AUTO_REVIEW_BASE_URL`, `AUTO_REVIEW_API_KEY`, `AUTO_REVIEW_MODEL`. Any OpenAI-compatible
  endpoint works (OpenRouter, Ollama, vLLM, etc.). (Slice #81, PR #87, `1c8f3e6`; documented
  in PR #89, `3ad0be0`.)
- **Read-only probe allowlist.** The agent can only request commands matching a fixed
  `PROBE_ALLOWLIST`: `git status|diff|log|branch|show|stash list|remote -v`, `ls`, `find`,
  `pwd`, `cat`, `head`, `tail`, `rg`, `env`, `which`, `command -v`, `npm ls`,
  `pip[3] show|list`. Probes outside the list are refused and the refusal is fed back to
  the agent. Probe output is capped at 4 KiB. (Slice #81, PR #87, `1c8f3e6`.)
- **Fallback-to-approval-prompt contract.** When the agent returns `allow` the hook emits
  the allow JSON and Codex skips the prompt. When it returns `deny` the hook emits the
  deny JSON and the tool call is blocked. When the endpoint is unreachable, returns invalid
  JSON, hits the 30s wall-clock timeout, exhausts max turns, or any `AUTO_REVIEW_*` env var
  is missing, the hook declines: no JSON, exit 0, and Codex's normal approval prompt
  appears. The user is never worse off than without the plugin — only better off when the
  agent successfully auto-approves safe commands or blocks dangerous ones. (Slices #81
  and #82.)
- **Decision audit log.** `log_decision()` appends one JSONL line per review to
  `$PLUGIN_DATA/reviews.jsonl` (fallback chain: `$XDG_DATA_HOME/auto-review/` then
  `~/.local/share/auto-review/`). Schema: `{ts (ISO 8601 UTC), tool_name, command
  (≤500 chars), verdict, turns, reason}`. The full body of `main()` calls it on every exit
  path: deny-bucket hit, agent allow/deny, agent decline, stdin read error, empty stdin,
  malformed JSON, non-dict stdin. The whole helper is `try/except`-wrapped so a logging
  failure never crashes the hook. (Slice #82, PR #88, `a53910a4`.)
- **PermissionRequest output contract.** Confirmed against
  <https://learn.chatgpt.com/docs/hooks#permissionrequest>: emits the
  `hookSpecificOutput.hookEventName = "PermissionRequest"` shape with
  `decision.behavior = "allow"` or `"deny"` (the `permissionDecision` field used by
  `PreToolUse` is not used here).

## Consequences

- **LLM-judged approvals on non-OpenAI providers.** The auto-reviewer fires on MiniMax /
  OpenRouter / Ollama / vLLM / any OpenAI-compatible endpoint, closing the gap left by the
  built-in `approvals_reviewer = "auto_review"`.
- **Hard pre-filter for universally-destructive commands.** The deny-bucket catches the
  obvious-wrong cases before the LLM call, so the agent is never the only line of defence
  against `rm -rf /`, force-push to main, fork bombs, or pipe-to-shell.
- **30s worst-case latency on each PermissionRequest.** The wall-clock budget is enforced,
  but it is real: a slow model or a probing agent can spend the full 30s before declining.
  Codex's normal approval prompt does not appear during that window, but the user is
  waiting.
- **Closed probe allowlist.** The agent cannot `cat` arbitrary files, run network commands,
  or invoke package managers beyond the listed inspectors (`npm ls`, `pip[3] show|list`).
  Transcript/session-history access is deferred (would eat the 30s budget) — see the PRD's
  "Out of Scope" section.
- **Dependency on a user-configured OpenAI-compatible endpoint.** The plugin is inert
  without `AUTO_REVIEW_BASE_URL`, `AUTO_REVIEW_API_KEY`, and `AUTO_REVIEW_MODEL` set; with
  any of them missing it declines, falling through to the normal approval prompt.

- **Non-blocking follow-up (tracked, not blocking merge).** `git push -f origin master`
  with the bare `-f` flag in the middle of the command is not yet denied by the slice #80
  regex: the two end-of-string `-f$` anchors in `auto_review.py` only catch the trailing
  flag. Flagged in the PR #88 review as a TODO and explicitly out of scope for slice #82
  ("don't change deny-bucket rules" constraint). A follow-up PR should add patterns like
  `\bgit\s+push\b\s+-f\b.*(\bmain\b|\bmaster\b)` and its reverse, OR loosen the existing
  `\\s-f$` anchors. (PR #88 review comment, `a53910a4` reviewer.)

## Review notes

**Slice review notes.** Slice #81 had 1 fix round (3 spec deviations: missing `git remote
  -v` from the probe allowlist, missing `max_tokens` / `temperature` in the LLM request
  body, missing 30s wall-clock budget — all fixed in the second commit of `1c8f3e6`).
  Slice #83 had 1 fix round: `ed991e1` added `test_validate.py` to the README structure tree
  after review caught the missing entry. Slices #80 and #82 merged clean on the first pass.
  **`ready-for-human` policy: none** — every slice auto-merged without escalation.

## Measured results

Outcomes recorded at PRD issue #79 close (2026-07-22). All four child slices merged: #80 →
PR #86 (`e39becb`), #81 → PR #87 (`1c8f3e6`), #82 → PR #88 (`a53910a4`), #83 → PR #89
(`3ad0be0`). Children #80–#83 closed. Each item below is cited back to the source
PR/commit/row that produced it.

- **Plugin scaffolded with the deny-bucket engine and PermissionRequest hook entry point.**
  Shipped in PR #86 (`e39becb`): `plugins/auto-review/.codex-plugin/plugin.json`,
  `hooks/hooks.json`, and `scripts/auto_review.py` (~580 lines including the deny-bucket
  check, allow/deny output helpers, and a `main()` that declines on non-match). Hook reads
  `PermissionRequest` JSON from stdin and emits the Codex allow/deny contract or declines
  (no output, exit 0). (#80 Definition of done)
- **Static deny-bucket covers all required cases plus documented exemptions.** The 11-rule
  `DENY_RULES` list (PR #86 (`e39becb`); later refined for the bare `-f` form in PR #87) is
  verified in `scripts/test_deny_bucket.py` and the `DenyBucketTests` class in
  `test_agent_loop.py`: `rm -rf /|~|$HOME`, `git push --force` / `git push -f` to
  `main`/`master` (both orderings plus the end-of-string `-f` anchor), `git reset --hard`,
  `git clean -fd` / `-fx`, `git branch -D main|master`, `chmod -R 777 /`,
  `dd` / `mkfs` to `/dev/(sd|nvme|hd|vd|disk)`, fork bomb `:(){:|:&};:`, and
  `curl|wget ... | bash|sh|zsh` in both orderings. Documented exemptions enforced by the
  regex itself: `--force-with-lease` to `main`/`master` is allowed (the
  `(--force(?!-with-lease))` negative lookahead), and bare `--force`/`-f` on a feature
  branch is allowed (no `main`/`master` match). (#80 Handoffs row "Deny-bucket rule set +
  regex", produced by #80 / consumed by #80)
- **Bounded-turn LLM agent loop with env snapshot, fixed probe allowlist, max 8 turns /
  30s wall-clock.** Shipped in PR #87 (`1c8f3e6`). `run_agent_loop` is bounded by
  `MAX_TURNS = 8` and a `time.monotonic()` wall-clock budget of 30s; the first turn ships
  `gather_env_snapshot(cwd)` (repo root, current branch, `git status --porcelain`, last 5
  commits, filtered env with secrets redacted) alongside the tool call. The agent can
  request one read-only probe per turn from a fixed `PROBE_ALLOWLIST`. Probe output is
  capped at 4 KiB; out-of-allowlist requests are refused and fed back. (#81 Handoffs row
  "Probe allowlist contract", produced by #81 / consumed by #81)
- **OpenAI-compatible endpoint, model configurable via `AUTO_REVIEW_*` env vars.** Three env
  vars drive configuration — `AUTO_REVIEW_BASE_URL`, `AUTO_REVIEW_API_KEY`,
  `AUTO_REVIEW_MODEL` — documented in PR #89 (`3ad0be0`) README with worked examples for
  OpenRouter, Ollama, and vLLM. `call_llm` POSTs to `{base_url}/chat/completions` with
  `response_format: json_object`, `max_tokens: 512`, `temperature: 0.1`, and
  `Authorization: Bearer …`. (#81 Handoffs row "Env var contract (`AUTO_REVIEW_*`)",
  produced by #81 / consumed by #83)
- **Fallback-to-approval-prompt contract.** When the agent returns `allow` the hook emits
  the allow JSON; `deny` emits the deny JSON. Endpoint unreachable, invalid JSON, 30s
  wall-clock timeout, max-turns exhausted, or any `AUTO_REVIEW_*` env var missing →
  `decline()` (no JSON, exit 0), so Codex's normal approval prompt appears. The user is
  never blocked by infrastructure failure. (PR #87 `1c8f3e6`, PR #88 `a53910a4`.)
- **Decision audit log in `$PLUGIN_DATA/reviews.jsonl`.** Shipped in PR #88 (`a53910a4`).
  `log_decision()` writes one JSONL line per review (schema: `ts`, `tool_name`, `command`
  (≤500 chars), `verdict`, `turns`,
  `reason`); wired into every `main()` exit path including stdin read error, empty stdin,
  malformed JSON, and non-dict stdin. `try/except`-wrapped so a logging failure never
  crashes the hook. (#82 Handoffs row "`reviews.jsonl` schema", produced by #82; the
  intended consumer is a future `review-status` skill — not delivered in this initiative
  per the PRD's "Out of Scope" section, but the schema is published and inspectable with
  `tail -f "$PLUGIN_DATA/reviews.jsonl"`.)
- **Test coverage: 55/55 passing.** `python3 -m unittest discover -s
  plugins/auto-review/scripts -p 'test_*.py'` → Ran 55 tests in 0.024s — OK. Coverage
  spans `scripts/test_deny_bucket.py` (every deny rule, positive + negative),
  `test_agent_loop.py` (mocked `urllib.request.urlopen`, scenarios: immediate allow,
  immediate deny, probe-then-allow, probe-then-deny, max turns exhausted → decline, API
  error → decline, unknown action, missing command, plus `DenyBucketTests` and
  `SnapshotAndProbeTests`), `test_logger.py` (4 `log_decision` + 6 `main` wiring tests),
  and `test_validate.py` (5 happy-path + 14 negative cases). PR #88 `a53910a4` reports
  36/36 after the logger/deny-bucket expansion; PR #89 `3ad0be0` adds the 19 validator
  tests for a running 55/55. (#79 Definition of done "Deny-bucket, probe executor, and LLM
  agent loop tests pass")
- **Plugin self-validator + Codex `validate_plugin.py` both green.**
  `plugins/auto-review/scripts/validate.py` runs six self-checks (manifest, hooks,
  hook_script, env_var_docs, tests, readme) — exit 0, `[PASS] all 6 checks passed`.
  Codex's `validate_plugin.py plugins/auto-review` → "Plugin validation passed". (PR #89
  `3ad0be0`.) (#79 Definition of done "Plugin validates with `validate_plugin.py`")
- **README + enablement docs.** `plugins/auto-review/README.md` (~270 lines) covers the
  two-stage pipeline, the deny-bucket rules table (11 rules + 3 allowed exceptions), the
  LLM agent protocol, the read-only probe allowlist, env-var configuration examples for
  OpenRouter, Ollama, and vLLM, the decision-log schema, the `config.toml` enablement
  block, the `/hooks` trust step, the plugin structure tree, and a troubleshooting matrix.
  `plugins/auto-review/CHANGELOG.md` (v0.1.0) lists all three prior slices as shipped.
  (PR #89 `3ad0be0`; structure-tree fix in `ed991e1`.) (#79 Definition of done "Plugin
  enableable via `config.toml` and hook trustable via `/hooks`")

- **Handoffs table — all four rows delivered.** Deny-bucket rule set (PR #86 `e39becb`) →
  consumed by the hook entry point in the same PR. Probe allowlist contract (PR #87
  `1c8f3e6`) → consumed by the agent loop in the same PR. `AUTO_REVIEW_*` env-var contract
  (PR #87 `1c8f3e6`) → documented in PR #89 `3ad0be0` README. `reviews.jsonl` schema (PR
  #88 `a53910a4`) → produced; the intended consumer (a future `review-status` skill) is
  **not delivered** in this initiative per the PRD's "Out of Scope" section, but the
  schema itself is published and inspectable with
  `tail -f "$PLUGIN_DATA/reviews.jsonl"`.

## References

- PRD: GitHub issue #79 (child issues #80, #81, #82, #83)
- Slice PRs: #86 (deny-bucket, `e39becb`), #87 (agent loop, `1c8f3e6`), #88 (decision
  logger + tests, `a53910a4`), #89 (README + validator + enablement, `3ad0be0`)
- Codex `PermissionRequest` hook spec:
  <https://learn.chatgpt.com/docs/hooks#permissionrequest>
- Plugin source: `plugins/auto-review/scripts/auto_review.py`
- Plugin tests: `plugins/auto-review/scripts/test_deny_bucket.py`,
  `test_agent_loop.py`, `test_logger.py`, `test_validate.py`
- Plugin self-validator: `plugins/auto-review/scripts/validate.py`
- Plugin README: `plugins/auto-review/README.md`
- Plugin CHANGELOG: `plugins/auto-review/CHANGELOG.md`

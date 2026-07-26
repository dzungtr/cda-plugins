# Auto Review — Codex Plugin

An LLM-agent-based auto-review hook for Codex `PermissionRequest` events. It denies universally destructive commands instantly with a static regex bucket and forwards everything else to a bounded-turn OpenAI-compatible agent loop that can probe the read-only environment before deciding to allow, deny, or fall back to the human approval prompt.

**Goal:** minimize user approval prompts while maximizing safety. The agent is an *optimization*, not a gatekeeper — when it can't decide, the endpoint is unreachable, or the timeout fires, it declines and Codex's normal approval prompt appears. The user is never worse off than without the plugin; they are only better off when the agent successfully auto-approves safe commands or blocks dangerous ones.

## Table of contents

1. [What it does](#what-it-does)
2. [How the two-stage review works](#how-the-two-stage-review-works)
3. [Deny bucket rules](#deny-bucket-rules)
4. [LLM agent loop](#llm-agent-loop)
5. [Read-only probe allowlist](#read-only-probe-allowlist)
6. [Configuration](#configuration)
7. [Decision log](#decision-log)
8. [Installation](#installation)
9. [Plugin structure](#plugin-structure)
10. [Self-validation](#self-validation)
11. [Troubleshooting](#troubleshooting)

## What it does

When Codex is about to ask for approval on a tool call, the auto-review hook intercepts it and runs a two-stage evaluation:

1. **Static deny-bucket** (instant, no LLM): universally destructive commands are denied immediately via regex matching.
2. **LLM agent loop** (everything else): a bounded-turn agent (max 8 turns, 30s timeout) evaluates the command using an OpenAI-compatible model. It can probe the read-only environment before deciding to allow, deny, or defer to the human.

## How the two-stage review works

The hook is wired to Codex's `PermissionRequest` event for the `Bash` and `apply_patch` matchers (see `hooks/hooks.json`). When Codex fires the event:

```
PermissionRequest
       │
       ▼
   check_deny_bucket ──hit──▶ output_deny  (block + log to reviews.jsonl)
       │
     no hit
       │
       ▼
   run_agent_loop  (≤8 turns, 30s wall-clock)
       │
       ├─ allow   ──▶ output_allow  (skip approval prompt, log)
       ├─ deny    ──▶ output_deny   (block, log)
       └─ decline ──▶ decline       (no JSON, exit 0 — Codex shows normal approval prompt, log)
```

**Decline-on-failure philosophy:** any infra error, timeout, or uncertainty results in `decline` (no JSON output, exit 0). The agent is an optimization; the user is never silently blocked by the plugin.

## Deny bucket rules

These are denied instantly, before the LLM agent runs. The bucket is pure regex — no I/O, no model call. The canonical source is the `DENY_RULES` constant in `scripts/auto_review.py`.

| #  | Pattern (regex)                                                                  | Example command                       | Reason                                                              |
|----|----------------------------------------------------------------------------------|---------------------------------------|---------------------------------------------------------------------|
| 1  | `rm -rf` on `/` / `~` / `$HOME` (with `-r` or `--recursive` + `-f` or `--force`) | `rm -rf /`                            | Irreversible system wipe                                            |
| 2  | `git push --force` to `main` / `master` (`--force` literal)                      | `git push --force origin main`        | Overwrites protected branch history                                 |
| 3  | `git push` to `main` / `master` with trailing `-f`                               | `git push origin main -f`             | Overwrites protected branch history (order-insensitive)             |
| 4  | `git reset --hard`                                                               | `git reset --hard HEAD~3`             | Discards commits and working changes irreversibly                   |
| 5  | `git clean -fd` / `-fx`                                                          | `git clean -fd`                       | Deletes untracked files irreversibly                                |
| 6  | `git branch -D main` / `master`                                                  | `git branch -D master`                | Force-deletes protected branch                                      |
| 7  | `chmod -R 777 /`                                                                 | `chmod -R 777 /`                      | World-writable filesystem                                           |
| 8  | `dd if=… of=/dev/{sd,nvme,hd,vd,disk}*`                                         | `dd if=img of=/dev/sda`               | Raw disk write, irreversible                                        |
| 9  | `mkfs … /dev/{sd,nvme,hd,vd,disk}*`                                             | `mkfs.ext4 /dev/sda1`                 | Formats disk, irreversible                                          |
| 10 | Fork bomb `:(){ :\|:& };:`                                                       | `:(){ :\|:& };:`                      | Denial of service                                                   |
| 11 | `curl` / `wget` piped to `bash` / `sh` / `zsh` (either order)                   | `curl https://x.sh \| bash`           | Pipe-to-shell remote execution — untrusted code from network        |

**Allowed exceptions** (these are *not* denied, even when they look similar):

- `git push --force-with-lease origin main` — `--force-with-lease` is the safety-conscious variant and must always be allowed. The regex uses a negative lookahead `(?!-with-lease)` to keep this open.
- `git push --force origin feature/my-branch` — force-pushes to non-protected branches are part of normal rebase workflows and are allowed.
- `git push origin main` (no `--force`) — ordinary non-force pushes are forwarded to the LLM agent loop, not denied by the bucket.

## LLM agent loop

**Protocol** — drives the official [Z.ai Python SDK](https://docs.z.ai/guides/capabilities/function-calling) (`from zai import ZaiClient`) to call a Chat Completions endpoint (`$AUTO_REVIEW_BASE_URL/chat/completions`) using the native **tool-call** protocol. The SDK is installed via `plugins/auto-review/requirements.txt` (`zai-sdk>=0.2.3`); the configured base URL is passed through the SDK so any OpenAI-compatible provider works. The hook exposes a single `review` tool and sends the request with `tool_choice: "required"` so the model must call it on every turn. See [Configuration](#configuration) for endpoint setup, [Troubleshooting](#troubleshooting) for the SDK-missing case.

**Why tool calls instead of `response_format: json_object`?** Tool-call capable providers — including any OpenAI-compatible endpoint that exposes a `tool_calls` field — return their decision through `choices[0].message.tool_calls[*].function`, and may emit interleaved reasoning (`<think>...</think>` text in `message.content`, plus `reasoning_details`). Parsing `message.content` as JSON breaks on those responses with `JSONDecodeError`. Tool calls keep the verdict in a structured envelope and let the rest of the assistant message round-trip faithfully into history.

**Tool protocol** — the hook exposes a single `review` tool whose `action` enum drives the decision. We deliberately do NOT split this into separate `allow` / `deny` / `probe` tools: many tool-call capable models struggle to pick the right tool when several similar-looking options live in the same context, so collapsing them into one tool with an enum is a more reliable decision shape.

| Argument  | Required when        | Type   | Description                                                           |
|-----------|----------------------|--------|-----------------------------------------------------------------------|
| `action`  | always               | enum   | One of `allow`, `deny`, `probe`.                                      |
| `reason`  | `action="deny"`      | string | Why this action is appropriate. Recommended for `allow` and `probe`.  |
| `command` | `action="probe"`     | string | Read-only shell command to run before deciding.                       |

**Bounded execution** — `MAX_TURNS = 8`. The agent exits immediately on `allow` or `deny`. On `probe` it executes the command, appends the result to the conversation, and continues. If the model returns a missing or unknown `action`, or `action="probe"` with no `command`, the loop feeds the error back to the model and continues — it does not silently auto-approve or auto-deny.

**Per-request timeout** — `LLM_REQUEST_TIMEOUT_SECONDS = 10`. Each LLM call has its own 10-second deadline so the model has room to think while still fitting inside the wall-clock budget.

**Wall-clock budget** — `WALL_CLOCK_BUDGET_SECONDS = 30`. The loop checks elapsed time before each LLM call. If the budget is exhausted, the network errors out, the response has no `tool_calls`, or `tool_call.arguments` is malformed JSON, the loop returns `decline` so the user gets the normal approval prompt. Logging failure is non-fatal.

**Environment snapshot** — the first message to the model includes a redacted environment snapshot (keys matching `KEY|SECRET|TOKEN|PASSWORD|PASSPHRASE|CREDENTIAL|PRIVATE` are replaced with `<redacted>`), plus the repo root, current branch, `git status --porcelain`, and the last five `git log --oneline` lines.

**Model parameters** — `temperature: 0.1`, `max_tokens: 512`. Low temperature keeps the agent's verdicts stable; the cap prevents runaway generation from eating the 30s budget.

**Decline-on-failure** — missing env vars, timeout, HTTP error, malformed JSON, missing model keys, or any uncaught exception → `decline`. The agent only denies when it can articulate a concrete reason; when in doubt, it defers to the human.

## Read-only probe allowlist

The agent can only request commands matching `PROBE_ALLOWLIST` (a fixed list of regexes in `scripts/auto_review.py`). Probes run via `subprocess.run` with a 3-second timeout and output capped at `PROBE_OUTPUT_CAP = 4096` bytes per stream. The allowlist covers the *minimum* a reviewer needs to make a contextual judgment about a Bash tool call; it intentionally excludes anything that mutates the filesystem, the network, or the index.

| Pattern                                          | Examples                                            |
|--------------------------------------------------|-----------------------------------------------------|
| `^git\s+(status\|diff\|log\|branch\|show)(\s\|$)` | `git status`, `git log -5`, `git show HEAD`         |
| `^git\s+stash\s+list(\s\|$)`                      | `git stash list`                                    |
| `^git\s+remote\s+-v(\s\|$)`                       | `git remote -v`                                     |
| `^(cat\|ls\|rg\|pwd\|head\|tail\|find\|env\|which)(\s\|$)` | `cat foo.json`, `ls -la`, `rg pattern src/`         |
| `^command\s+-v(\s\|$)`                           | `command -v rg`                                     |
| `^npm\s+ls(\s\|$)`                                | `npm ls`                                            |
| `^pip(3)?\s+(show\|list)(\s\|$)`                 | `pip show requests`, `pip3 list`                    |

**Refused probes** — anything outside the allowlist is refused and the refusal message is fed back to the agent verbatim. The agent can then ask for a different command or fall through to a verdict.

## Configuration

Three environment variables control the LLM agent. The deny-bucket stage runs even when these are unset; it just declines at the agent stage.

| Variable                | Required | Example                          | Notes                                            |
|-------------------------|----------|----------------------------------|--------------------------------------------------|
| `AUTO_REVIEW_BASE_URL`  | yes      | `https://openrouter.ai/api/v1`   | OpenAI-compatible base URL (no trailing slash).  |
| `AUTO_REVIEW_API_KEY`   | yes      | `sk-or-v1-…`                     | Bearer token for the endpoint.                   |
| `AUTO_REVIEW_MODEL`     | yes      | `<your-model-id>`                | Exact model id the endpoint exposes. Must support OpenAI-style `tool_calls`. |

**OpenRouter (recommended for hosted):**

```bash
export AUTO_REVIEW_BASE_URL="https://openrouter.ai/api/v1"
export AUTO_REVIEW_API_KEY="sk-or-v1-…"
export AUTO_REVIEW_MODEL="<your-model-id>"   # any tool-capable model on OpenRouter
```

**Local Ollama (no API key, local model):**

```bash
export AUTO_REVIEW_BASE_URL="http://localhost:11434/v1"
export AUTO_REVIEW_API_KEY="ollama"               # any non-empty string
export AUTO_REVIEW_MODEL="llama3.1:8b"
```

**vLLM (self-hosted OpenAI-compatible server):**

```bash
export AUTO_REVIEW_BASE_URL="http://localhost:8000/v1"
export AUTO_REVIEW_API_KEY="EMPTY"                # vLLM default; any non-empty value works
export AUTO_REVIEW_MODEL="meta-llama/Meta-Llama-3-8B-Instruct"
```

**Z.ai (the SDK's first-party provider, recommended when you have a Z.ai account):**

```bash
export AUTO_REVIEW_BASE_URL="https://api.z.ai/api/paas/v4"
export AUTO_REVIEW_API_KEY="<your-zai-api-key>"
export AUTO_REVIEW_MODEL="glm-4.6"          # or any tool-capable Z.ai model
```

Any OpenAI-compatible endpoint works — the configured `AUTO_REVIEW_BASE_URL` is passed straight through `zai.ZaiClient(base_url=...)`, so the same hook talks to Z.ai, OpenRouter, Ollama, vLLM, or a self-hosted server without code changes. Set them in your shell profile (`~/.zshrc`, `~/.bashrc`) or in Codex's process environment.

## Decision log

Each review appends one JSON line to `$PLUGIN_DATA/reviews.jsonl` (Codex sets `PLUGIN_DATA` for plugin-bundled hooks). If `PLUGIN_DATA` is unset, the logger falls back to `$XDG_DATA_HOME/auto-review/` then `~/.local/share/auto-review/`. Logging is wrapped in `try/except` and writes to `stderr` at most — a logging failure never crashes the hook.

**Schema:**

```json
{
  "ts":       "2026-07-22T01:23:45+00:00",
  "tool_name":"Bash",
  "command":  "git push --force origin main",
  "verdict":  "deny",
  "turns":    0,
  "reason":   "git push --force to main/master — overwrites protected branch history"
}
```

`verdict` is one of `allow` / `deny` / `decline`. `turns` is `0` for deny-bucket hits and unset-or-0 for declines. `command` is truncated to 500 chars in the log.

**Inspect the log:**

```bash
# Tail the last 20 reviews
tail -20 "$PLUGIN_DATA/reviews.jsonl"

# Filter for denials only
grep '"verdict":"deny"' "$PLUGIN_DATA/reviews.jsonl" | tail -10

# Pretty-print one line
tail -1 "$PLUGIN_DATA/reviews.jsonl" | python3 -m json.tool
```

## Installation

The plugin is bundled in the `cc-harness` marketplace at `https://github.com/dzungtr/cc-harness`. No separate install step is required for the marketplace itself — point Codex at it via your `config.toml`.

**1. Add the marketplace** in `~/.codex/config.toml` (if not already present):

```toml
[marketplaces.cc-harness]
url = "https://github.com/dzungtr/cc-harness"
```

**2. Enable the plugin:**

```toml
[plugins."auto-review@cc-harness"]
enabled = true
```

**3. Install the Z.ai Python SDK and set the LLM endpoint env vars.**

   ```bash
   /usr/bin/python3 -m pip install -r plugins/auto-review/requirements.txt
   ```

   The requirements file requires `zai-sdk>=0.2.3` (the official SDK; the bare `zai` distribution on PyPI is an unrelated 2018 placeholder and is NOT what this hook imports). The static deny-bucket still works without the SDK — only the agent loop declines cleanly with a `zai-sdk is required` reason when it is missing — but installing it lets the hook actually call the model. Then set the three env vars from [Configuration](#configuration) in the environment Codex inherits (your shell profile, `~/.codex/.env`, or the launcher script).

**4. Trust the hook.** Codex requires non-managed hooks to be explicitly trusted before they run. Open the Codex CLI and run:

```
/hooks
```

Then locate the `auto-review` `PermissionRequest` entry and approve it. Until you do this, the hook will not fire and Codex will fall back to the normal approval prompt for every command.

**5. Verify** with a quick sanity check — see [Self-validation](#self-validation).

## Plugin structure

```
plugins/auto-review/
├── .codex-plugin/
│   └── plugin.json                    # manifest: name, version, description, author
├── hooks/
│   └── hooks.json                     # wires auto_review.py to PermissionRequest
├── scripts/
│   ├── auto_review.py                 # deny-bucket + agent loop (Z.ai SDK) + decision logger
│   ├── test_agent_loop.py             # tests: agent loop, deny-bucket, probe allowlist, snapshot, SDK conversion
│   ├── test_logger.py                 # tests: log_decision + main() log-on-every-path wiring
│   ├── test_validate.py               # tests: validate.py (plugin self-check)
│   └── validate.py                    # self-check (plugin-specific; complements Codex's validator)
├── requirements.txt                   # runtime dep: zai-sdk (the official Z.ai Python SDK)
├── README.md                          # this file
└── CHANGELOG.md                       # per-version notes
```

The `auto_review.py` hook is the only runtime entry point. The test files are stdlib-only (`unittest`); the hook itself depends on `zai-sdk` from `requirements.txt`. Run the full suite with `python3 -m unittest discover -s plugins/auto-review/scripts -p 'test_*.py'`.

## Self-validation

Two validators can be run against the plugin tree:

1. **Codex's own validator** (canonical, exhaustive):

   ```bash
   python3 /path/to/validate_plugin.py plugins/auto-review
   ```

2. **The plugin's own self-check** (faster, plugin-specific, also checks env-var documentation, exec bits, and test presence):

   ```bash
   python3 plugins/auto-review/scripts/validate.py
   ```

   Exits `0` on success, non-zero on failure, with a clear error message. See `scripts/validate.py` for the exact checks.

## Troubleshooting

| Symptom                                                          | Cause                                                                 | Fix                                                                                                                                |
|------------------------------------------------------------------|-----------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| Codex shows the normal approval prompt for every command         | The hook isn't trusted yet — `/hooks` step was skipped                | Run `/hooks` in the Codex CLI and trust the `auto-review` `PermissionRequest` entry.                                               |
| Every command declines, log shows `missing env vars`             | `AUTO_REVIEW_BASE_URL` / `AUTO_REVIEW_API_KEY` / `AUTO_REVIEW_MODEL` not set in Codex's env | Export the three vars in the environment Codex inherits (shell profile, launcher, `~/.codex/.env`).                                  |
| Every command declines, log shows `zai-sdk is required ... No module named 'zai'` | The `zai-sdk` Python package is not installed in Codex's interpreter | Run `/usr/bin/python3 -m pip install -r plugins/auto-review/requirements.txt`, matching the interpreter used by `hooks/hooks.json`. The static deny-bucket still fires without the SDK — only the LLM agent stage declines. |
| Every command declines, log shows `zai package is installed but does not export ZaiClient` | The wrong package is installed: the bare `zai` distribution on PyPI is an unrelated 2018 placeholder, NOT the SDK | Uninstall it (`/usr/bin/python3 -m pip uninstall zai`) and install the official SDK: `/usr/bin/python3 -m pip install -r plugins/auto-review/requirements.txt` (which requires at least `zai-sdk>=0.2.3`). |
| Every command declines, log shows `LLM API error or unreachable` | The endpoint is unreachable from Codex's process, the API key is wrong, the model id is invalid, or the SDK raised an unexpected error | Curl the configured `AUTO_REVIEW_BASE_URL/chat/completions` directly with the same key/model to verify, then check `reviews.jsonl` for the declined `reason` (it carries the SDK's error message verbatim). |
| Every command declines with `wall-clock timeout` / `max turns exhausted` | The endpoint is slow, or the model keeps probing without reaching a verdict | Lower `MAX_TURNS` for testing, or switch to a smaller / faster model.                                                              |
| Every command declines with `no tool_calls in assistant message` (or `Expecting ...`) | The endpoint returned a response the hook could not parse as a tool call — e.g. text-only or malformed JSON in `tool_call.arguments` | Check the model supports OpenAI-style `tool_calls` with `tool_choice: "required"`. Confirm with `curl` that the endpoint returns a `tool_calls` array. If the model emits plain text, the hook will safely `decline` rather than mis-parse. |
| `reviews.jsonl` not appearing                                    | `PLUGIN_DATA` not set and the fallback dir not writable              | Set `PLUGIN_DATA` explicitly, or `chmod` the fallback dir (`$XDG_DATA_HOME/auto-review/` or `~/.local/share/auto-review/`).         |
| Hook denied a command the user thinks is safe                    | Static deny-bucket matched a pattern (e.g. `git push -f` to `main`)    | Check the `reason` field in `reviews.jsonl`. If the pattern is wrong, that's a deny-bucket bug — file an issue with the failing command. |
| `validate.py` reports `hook script is not executable`            | `auto_review.py` lost its exec bit                                    | `chmod +x plugins/auto-review/scripts/auto_review.py`                                                                              |

**Note on Codex built-in `approvals_reviewer = "auto_review"`:** that built-in only works with OpenAI-native providers and models, which is the gap this plugin fills. If you have both enabled, the built-in still fires for OpenAI providers; the plugin handles the non-OpenAI case (OpenRouter, Ollama, vLLM, etc.).

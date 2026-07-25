#!/usr/bin/env python3
"""
Auto Review — Codex PermissionRequest hook.

Intercepts Codex PermissionRequest events on Bash and apply_patch tool calls and
runs a static deny-bucket of universally destructive commands. Anything that
does not match the deny-bucket is forwarded to a bounded-turn LLM agent loop
that decides allow / deny via a single native OpenAI-compatible `review` tool
whose `action` enum is one of `allow` / `deny` / `probe`. On infra failure or
model uncertainty the hook DECLINES (no JSON output, exit 0) so Codex falls
back to its normal approval prompt — the user is never worse off than without
the plugin.

Stdlib only — no third-party dependencies.

Output contract:
  Allow:  {"hookSpecificOutput":{"hookEventName":"PermissionRequest",
                                  "decision":{"behavior":"allow"}}}
  Deny:   {"hookSpecificOutput":{"hookEventName":"PermissionRequest",
                                  "decision":{"behavior":"deny","message":"..."}}}
  Decline: no JSON on stdout, exit 0
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import List, Tuple

MAX_TURNS = 8
PROBE_OUTPUT_CAP = 4096
WALL_CLOCK_BUDGET_SECONDS = 30
# Tool-call capable providers negotiate the verdict via native OpenAI-style
# `tool_calls` rather than `response_format: json_object`. The previous
# content-as-JSON protocol broke on responses where `message.content` starts
# with `<think>...</think>` reasoning text — JSON parsing raised
# `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` and every
# review declined. Keep a generous per-request timeout so model round-trips
# complete inside the wall-clock budget.
LLM_REQUEST_TIMEOUT_SECONDS = 10

# A single OpenAI-compatible tool schema exposed to the model. We deliberately
# collapse the decision surface into one tool with an `action` enum instead of
# three separate `allow` / `deny` / `probe` tools because many models struggle
# to pick the right tool when the names are similar and live in the same
# context. With one tool, the model must call it and pick the action — a more
# reliable decision shape across weaker tool-call capable providers.
REVIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "review",
        "description": (
            "Record the reviewer's decision for a Bash or apply_patch tool call. "
            "Call this exactly once per turn with one of three actions: 'allow' "
            "to approve, 'deny' to block, or 'probe' to run a read-only shell "
            "command before deciding."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["allow", "deny", "probe"],
                    "description": "The decision the reviewer is recording.",
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "Why this action is appropriate. Required when action is "
                        "'deny'; recommended for 'allow' and 'probe'."
                    ),
                },
                "command": {
                    "type": "string",
                    "description": (
                        "Read-only shell command to run before deciding. Required "
                        "when action is 'probe'."
                    ),
                },
            },
            "required": ["action"],
            "if": {"properties": {"action": {"const": "deny"}}, "required": ["action"]},
            "then": {"required": ["action", "reason"]},
            "additionalProperties": False,
        },
    },
}
LOG_FILE_NAME = "reviews.jsonl"
SECRET_PATTERN = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|PASSPHRASE|CREDENTIAL|PRIVATE", re.I)
PROBE_ALLOWLIST = [re.compile(pattern) for pattern in (
    r"^git\s+(status|diff|log|branch|show)(\s|$)", r"^git\s+stash\s+list(\s|$)",
    r"^git\s+remote\s+-v(\s|$)",
    r"^(cat|ls|rg|pwd|head|tail|find|env|which)(\s|$)", r"^command\s+-v(\s|$)",
    r"^npm\s+ls(\s|$)", r"^pip(3)?\s+(show|list)(\s|$)",
)]


# ── Static deny bucket ────────────────────────────────────────────────────────
# Each entry: (compiled regex, reason). Matched against the full command string.
# These are denied instantly, before any further evaluation.

DENY_RULES: List[Tuple[re.Pattern, str]] = [
    # rm -rf on root, home, or top-level paths
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f?|--recursive)\s+(/|~|\$HOME)(\s|$|/)"),
        "rm -rf on root or home directory — irreversible system wipe",
    ),
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*r?|--force)\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?(/|~|\$HOME)(\s|$|/)"),
        "rm -rf on root or home directory — irreversible system wipe",
    ),
    # git push --force / -f to main or master.
    # Negative lookahead `(?!-with-lease)` keeps --force-with-lease safe.
    # Negative lookahead `(?![a-z])` keeps `-f` distinct from `--foo`.
    (
        re.compile(r"\bgit\s+push\b.*--force(?!-with-lease)\b.*(\bmain\b|\bmaster\b)"),
        "git push --force to main/master — overwrites protected branch history",
    ),
    (
        re.compile(r"\bgit\s+push\b.*(\bmain\b|\bmaster\b).*--force(?!-with-lease)\b"),
        "git push --force to main/master — overwrites protected branch history",
    ),
    (
        re.compile(r"\bgit\s+push\b.*\bmain\b.*\s-f$"),
        "git push -f to main/master — overwrites protected branch history",
    ),
    (
        re.compile(r"\bgit\s+push\b.*\bmaster\b.*\s-f$"),
        "git push -f to main/master — overwrites protected branch history",
    ),
    # git reset --hard
    (
        re.compile(r"\bgit\s+reset\s+--hard\b"),
        "git reset --hard — discards commits and working changes irreversibly",
    ),
    # git clean -fd / -fx (force delete untracked)
    (
        re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f[a-zA-Z]*[dx]"),
        "git clean with -f and -d/-x — deletes untracked files irreversibly",
    ),
    # git branch -D main / master
    (
        re.compile(r"\bgit\s+branch\s+-D\s+(main|master)\b"),
        "git branch -D on main/master — force-deletes protected branch",
    ),
    # chmod -R 777 on root
    (
        re.compile(r"\bchmod\s+(-R|--recursive)\s+777\s+/(\s|$)"),
        "chmod -R 777 on root — world-writable filesystem",
    ),
    # dd to block devices
    (
        re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|hd|vd|disk)\w*"),
        "dd to block device — raw disk write, irreversible",
    ),
    # mkfs on block devices
    (
        re.compile(r"\bmkfs\b.*/dev/(sd|nvme|hd|vd|disk)\w*"),
        "mkfs on block device — formats disk, irreversible",
    ),
    # fork bomb
    (
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:&\s*\}\s*;"),
        "fork bomb — denial of service",
    ),
    # pipe-to-shell remote execution
    (
        re.compile(r"\b(curl|wget)\b[^|]*\|\s*(bash|sh|zsh)\b"),
        "pipe-to-shell remote execution — untrusted code from network",
    ),
    (
        re.compile(r"\|\s*(bash|sh|zsh)\b[^|]*\b(curl|wget)\b"),
        "pipe-to-shell remote execution — untrusted code from network",
    ),
]


def check_deny_bucket(command: str) -> str | None:
    """Return a deny reason if the command matches a static deny rule, else None.

    Pure function — does no I/O. Safe to call from unit tests.
    """
    if not command:
        return None
    for pattern, reason in DENY_RULES:
        if pattern.search(command):
            return reason
    return None


# ── Output helpers ───────────────────────────────────────────────────────────


def output_allow() -> None:
    """Emit the JSON to auto-approve the request (skip approval prompt)."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow"},
        }
    }
    print(json.dumps(payload))
    sys.exit(0)


def output_deny(message: str) -> None:
    """Emit the JSON to deny the request (block the tool call)."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": message},
        }
    }
    print(json.dumps(payload))
    sys.exit(0)


def decline() -> None:
    """Decline to decide — no JSON output, exit 0.

    Codex shows its normal approval prompt. Slice #81 will replace this with
    a bounded-turn LLM agent loop; until then every non-matched command
    falls through to here.
    """
    sys.exit(0)


def _run_snapshot(command: List[str], cwd: str) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=1)
        return (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def gather_env_snapshot(cwd: str) -> dict:
    env = {key: ("<redacted>" if SECRET_PATTERN.search(key) else value)
           for key, value in sorted(os.environ.items())[:80]}
    return {"repo_root": _run_snapshot(["git", "rev-parse", "--show-toplevel"], cwd),
            "branch": _run_snapshot(["git", "branch", "--show-current"], cwd),
            "git_status": _run_snapshot(["git", "status", "--porcelain"], cwd),
            "recent_commits": _run_snapshot(["git", "log", "--oneline", "-5"], cwd),
            "cwd": cwd, "env": env}


def is_probe_allowed(cmd: str) -> bool:
    command = cmd.strip()
    return bool(command) and any(pattern.match(command) for pattern in PROBE_ALLOWLIST)


def _cap_output(value: str) -> str:
    return value.encode()[:PROBE_OUTPUT_CAP].decode(errors="ignore")


def execute_probe(cmd: str, env_snapshot: dict) -> tuple[str, str]:
    if not is_probe_allowed(cmd):
        return "", f"PROBE REFUSED: {cmd!r} is not allowlisted"
    try:
        result = subprocess.run(cmd, shell=True, cwd=env_snapshot.get("cwd") or None,
                                capture_output=True, text=True, timeout=3)
        return _cap_output(result.stdout or ""), _cap_output(result.stderr or "")
    except subprocess.TimeoutExpired:
        return "", "probe timed out"
    except OSError as error:
        return "", f"probe error: {error}"


def _extract_assistant_message(payload: object) -> dict:
    """Return the assistant message dict from a chat-completions response.

    Preserves the full provider shape — including `content` (which may carry
    `<think>...</think>` reasoning text), `tool_calls`, and `reasoning_details`
    — so the message round-trips faithfully into subsequent conversation turns.
    Returns an empty dict if the response is malformed.
    """
    try:
        message = payload["choices"][0]["message"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return {}
    return message if isinstance(message, dict) else {}


def _parse_first_tool_arguments(message: dict) -> dict:
    """Return the decoded ``arguments`` object for the first tool call.

    Raises ``ValueError`` when the message has no tool calls and the standard
    JSON exceptions (``json.JSONDecodeError`` / ``TypeError``) when arguments
    cannot be decoded as an object. We intentionally do NOT inspect the
    function name — the upstream model has only one tool (``review``) to call,
    so the dispatch reads ``arguments.action`` directly.
    """
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        raise ValueError("no tool_calls in assistant message")
    first = tool_calls[0]
    function = first.get("function", {}) if isinstance(first, dict) else {}
    raw_arguments = function.get("arguments", "{}")
    if not isinstance(raw_arguments, str):
        raw_arguments = json.dumps(raw_arguments)
    arguments = json.loads(raw_arguments)
    if not isinstance(arguments, dict):
        raise ValueError(f"tool arguments must be an object, got {type(arguments).__name__}")
    return arguments


def run_agent_loop(tool_call: dict, env_snapshot: dict) -> dict:
    base_url = os.environ.get("AUTO_REVIEW_BASE_URL")
    api_key = os.environ.get("AUTO_REVIEW_API_KEY")
    model = os.environ.get("AUTO_REVIEW_MODEL")
    if not all((base_url, api_key, model)):
        return {"verdict": "decline", "reason": "missing env vars", "turns": 0}
    messages = [{"role": "user", "content": json.dumps({"tool_call": tool_call, "environment": env_snapshot})}]
    loop_start = time.monotonic()
    for turn in range(1, MAX_TURNS + 1):
        if time.monotonic() - loop_start >= WALL_CLOCK_BUDGET_SECONDS:
            return {"verdict": "decline", "reason": "wall-clock timeout", "turns": turn - 1}
        request = urllib.request.Request(f"{base_url.rstrip('/')}/chat/completions",
            data=json.dumps({"model": model, "messages": messages,
                             "tools": [REVIEW_TOOL], "tool_choice": "required",
                             "max_tokens": 512, "temperature": 0.1}).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=LLM_REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode())
            assistant_message = _extract_assistant_message(payload)
            arguments = _parse_first_tool_arguments(assistant_message)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as error:
            return {"verdict": "decline", "reason": str(error), "turns": turn}
        # Preserve the complete assistant message — content, tool_calls, and any
        # reasoning_details — so the model sees its prior tool calls in history.
        messages.append(assistant_message)
        action = arguments.get("action")
        if action == "allow":
            return {"verdict": "allow", "reason": str(arguments.get("reason", "")), "turns": turn}
        if action == "deny":
            reason = arguments.get("reason")
            return {"verdict": "deny", "reason": str(reason) if reason else "denied by model", "turns": turn}
        if action == "probe":
            command = arguments.get("command", "")
            if command:
                stdout, stderr = execute_probe(command, env_snapshot)
                feedback = {"stdout": stdout, "stderr": stderr}
            else:
                feedback = {"error": "probe missing command"}
            messages.append({"role": "user", "content": json.dumps(feedback)})
            continue
        # Missing or unknown action — feed the error back and let the model retry.
        # MAX_TURNS bounds the total iterations, so this cannot loop forever.
        messages.append({"role": "user", "content": json.dumps(
            {"error": f"unknown or missing action: {action!r}"})})
    return {"verdict": "decline", "reason": "max turns exhausted", "turns": MAX_TURNS}


# ── Decision logging ───────────────────────────────────────────────────────────


def log_decision(
    tool_name: str,
    command: str,
    verdict: str,
    turns: int | None,
    reason: str | None,
) -> None:
    """Append a review decision to $PLUGIN_DATA/reviews.jsonl.

    Reads $PLUGIN_DATA (set by Codex for plugin-bundled hooks). Falls back to
    $XDG_DATA_HOME/auto-review/ or ~/.local/share/auto-review/ if unset.
    Logging failure MUST NOT crash the hook — wrapped in try/except.
    """
    try:
        plugin_data = os.environ.get("PLUGIN_DATA")
        if not plugin_data:
            xdg = os.environ.get("XDG_DATA_HOME")
            if xdg:
                plugin_data = os.path.join(xdg, "auto-review")
            else:
                home = os.path.expanduser("~")
                plugin_data = os.path.join(home, ".local", "share", "auto-review")
        log_path = Path(plugin_data) / LOG_FILE_NAME
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "command": (command or "")[:500],
            "verdict": verdict,
            "turns": turns,
            "reason": reason,
        }
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry) + "\n")
    except Exception as error:
        print(f"auto-review: log_decision failed: {error}", file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    # Read the PermissionRequest JSON from stdin. Malformed/empty input is
    # treated as "nothing to review" → decline cleanly, do not crash.
    try:
        raw_input = sys.stdin.read()
    except OSError as error:
        log_decision("", "", "decline", None, f"stdin read error: {error}")
        decline()
        return

    if not raw_input.strip():
        log_decision("", "", "decline", None, "empty stdin")
        decline()
        return

    try:
        hook_input = json.loads(raw_input)
    except json.JSONDecodeError as error:
        log_decision("", "", "decline", None, f"malformed JSON: {error}")
        decline()
        return

    if not isinstance(hook_input, dict):
        log_decision("", "", "decline", None, "non-dict stdin")
        decline()
        return

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {}) or {}

    # Extract the command string for deny-bucket matching.
    # Bash: tool_input.command. apply_patch: tool_input is a JSON-ish blob.
    command = ""
    if isinstance(tool_input, dict):
        cmd = tool_input.get("command", "")
        if isinstance(cmd, str):
            command = cmd
        else:
            command = json.dumps(tool_input)

    # ── Stage 1: Static deny bucket ──
    deny_reason = check_deny_bucket(command)
    if deny_reason:
        log_decision(tool_name, command, "deny", 0, deny_reason)
        output_deny(deny_reason)
        return

    # ── Stage 2: LLM agent loop ──
    cwd = hook_input.get("cwd", os.getcwd())
    result = run_agent_loop({"tool_name": tool_name, "tool_input": tool_input}, gather_env_snapshot(cwd))
    verdict = result["verdict"]
    turns = result.get("turns")
    reason = result.get("reason")
    log_decision(tool_name, command, verdict, turns, reason)
    if verdict == "allow":
        output_allow()
    if verdict == "deny":
        output_deny(reason or "")
    decline()


if __name__ == "__main__":
    main()

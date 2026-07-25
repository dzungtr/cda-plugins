#!/usr/bin/env bash
# PreToolUse hook: auto-allow `curl` when ALL targets are trusted:
# localhost/127.0.0.1/::1/0.0.0.0, github.com, or raw.githubusercontent.com.
# Falls back to "ask" so Claude Code's normal prompt appears for any other URL.
set -euo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

# Strip quoted substrings so we only match URL tokens, not arbitrary payload text.
stripped=$(printf '%s' "$cmd" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")

# Match bare (schemeless) localhost references.
local_bare_re='(^|[[:space:]=])(https?://)?(localhost|127\.0\.0\.1|0\.0\.0\.0|\[?::1\]?)([:/[:space:]]|$)'

# Trusted host pattern for http(s) URLs.
trusted_url_re='^(https?://)(localhost|127\.0\.0\.1|0\.0\.0\.0|\[?::1\]|github\.com|raw\.githubusercontent\.com)([:/]|$)'

has_trusted=0
has_untrusted=0

if printf '%s' "$stripped" | grep -qE "$local_bare_re"; then
  has_trusted=1
fi

if printf '%s' "$stripped" | grep -qE 'https?://'; then
  urls=$(printf '%s' "$stripped" | grep -oE 'https?://[^[:space:]"'\''`]+')
  if printf '%s' "$urls" | grep -qE "$trusted_url_re"; then
    has_trusted=1
  fi
  if printf '%s' "$urls" | grep -vE "$trusted_url_re" | grep -q .; then
    has_untrusted=1
  fi
fi

if [[ "$has_untrusted" -eq 1 ]]; then
  reason="curl target is not restricted to trusted hosts (localhost, github.com, raw.githubusercontent.com); manual approval required."
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"%s"}}\n' "$reason"
else
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
fi

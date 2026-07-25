#!/usr/bin/env bash
# Guard against destructive git operations.
# Reads PreToolUse JSON from stdin; outputs a "ask" permissionDecision for dangerous patterns.
# Exit 0 = safe, allow through. JSON output with "ask" = show user a confirmation dialog.

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Only care about git commands
echo "$CMD" | grep -qE '^git[[:space:]]' || exit 0

REASON=""

# reset --hard: discards commits and staged/unstaged changes
if echo "$CMD" | grep -qE '[[:space:]]reset[[:space:]]+--hard'; then
    REASON="git reset --hard discards local commits and changes irreversibly"

# clean with -f (force flag required to actually delete): removes untracked files
elif echo "$CMD" | grep -qE '[[:space:]]clean[[:space:]]+-[a-zA-Z]*f'; then
    REASON="git clean -f deletes untracked files (and dirs/gitignored files with -d/-x) irreversibly"

# push --force or push -f: overwrites remote history
elif echo "$CMD" | grep -qE '[[:space:]]push[[:space:]].*(--force[[:space:]=]|-f[[:space:]])'; then
    REASON="git push --force can overwrite remote branch history"

# push -f at end of command (no trailing space)
elif echo "$CMD" | grep -qE '[[:space:]]push[[:space:]].*-f$'; then
    REASON="git push -f can overwrite remote branch history"

# checkout -- <pathspec>: discards uncommitted working-tree changes
elif echo "$CMD" | grep -qF 'checkout -- '; then
    REASON="git checkout -- <path> discards uncommitted changes to those files irreversibly"
fi

if [ -n "$REASON" ]; then
    jq -n --arg reason "$REASON" '{
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": $reason
        }
    }'
fi

exit 0

#!/usr/bin/env python3
"""
PreToolUse hook: auto-approve 'cd <trusted-path> && <approved-command>' patterns.
Allows a command only when BOTH conditions hold:
  1. The cd target is within a trusted path root
  2. The command after && is already in the pre-approved list
"""
import json
import os
import re
import sys
from pathlib import Path

# Mirror of the Bash allow-list prefixes that make sense after a cd.
# Keep in sync with permissions.allow in settings.json.
APPROVED_PREFIXES = [
    "git ", "git\t",
    "gh ",
    "make ", "make\t",
    "go build", "go run", "go test", "go get", "go vet", "go list", "go mod", "go work",
    "node ", "node\t",
    "python ", "python\t",
    "python3 ", "python3\t",
    "docker ",
    "podman ", "podman-compose ",
    "kubectl ",
    "kustomize ",
    "snyk ",
    "conda run",
    "poetry run",
    "npx ",
    "controller-gen ",  # CRD/webhook/RBAC generation
    "uv ",              # Python package manager (runtime/)
    "npm ",             # Node package manager (dashboard/)
    "golangci-lint ",   # Go linter
    "find ", "head ", "sort ", "awk ", "jq ", "ls ",
    "mkdir ", "cp ", "mv ", "echo ",
    "pip show", "pip3 show",
    "openapi-generator-cli ",
    "command -v",
    "GIT_DIR=", "GIT_COMMON=",  # git repo inspection via shell var assignments
    "pytest ",
    "mkdir -p",
]

def is_trusted_path(raw: str) -> bool:
    path = Path(raw.strip("'\"")).expanduser()
    if not path.is_absolute():
        return True  # relative path — stays within current workspace
    cwd = Path(os.getcwd())
    return path.is_relative_to(cwd) or path.is_relative_to(Path("/tmp"))


def is_approved(cmd: str) -> bool:
    cmd = cmd.strip()
    return any(cmd.startswith(p) for p in APPROVED_PREFIXES)


def main():
    try:
        data = json.load(sys.stdin)
        command = data.get("tool_input", {}).get("command", "")

        # Match: cd <path> && <rest>
        # Path may be bare, single-quoted, or double-quoted.
        m = re.match(
            r'^cd\s+(\"[^\"]*\"|\'[^\']*\'|\S+)\s*&&\s*(.+)$',
            command.strip(),
            re.DOTALL,
        )
        if not m:
            sys.exit(0)  # Not a cd+command pattern — pass through to normal handling

        path_token = m.group(1)
        actual_cmd = m.group(2).strip()

        if is_trusted_path(path_token) and is_approved(actual_cmd):
            top = actual_cmd.split()[0]
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": f"cd into trusted path with pre-approved command '{top}'",
                }
            }))
        # else: no output → fall through to normal permission prompt

    except Exception:
        pass  # Any parse error → fall through


if __name__ == "__main__":
    main()

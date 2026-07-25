#!/usr/bin/env python3
"""harness5 SessionStart hook loader.

Reads references/harness5.md from this script's directory and emits it as
the additionalContext payload of a SessionStart hook event. Used by both
Codex and Claude Code — both harnesses accept the same JSON shape.

Failure mode: missing/unreadable file → no JSON on stdout, single-line
warning on stderr, exit 0. Never blocks a session.

Size cap: soft-warn to stderr when file exceeds 32768 chars, but still
inject. No truncation.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SOFT_CAP_CHARS = 32_768
SCRIPT_DIR = Path(__file__).resolve().parent
INSTRUCTIONS_FILE = Path(
    os.environ.get(
        "HARNESS5_INSTRUCTIONS_FILE",
        SCRIPT_DIR / "references" / "harness5.md",
    )
)


def warn(message: str) -> None:
    sys.stderr.write(f"harness5: {message}\n")
    sys.stderr.flush()


def load_instructions() -> str | None:
    try:
        content = INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        warn(f"{INSTRUCTIONS_FILE} not found")
        return None
    except OSError as exc:
        warn(f"failed to read {INSTRUCTIONS_FILE}: {exc}")
        return None
    if len(content) > SOFT_CAP_CHARS:
        warn(
            f"{INSTRUCTIONS_FILE.name} is {len(content)} chars, "
            f"exceeds {SOFT_CAP_CHARS} soft cap; consider trimming"
        )
    return content


def main() -> int:
    content = load_instructions()
    if content is None:
        return 0
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": content,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

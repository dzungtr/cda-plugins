#!/usr/bin/env python3
"""
auto-review plugin self-check.

Mirrors the subset of Codex's `validate_plugin.py` that the slice-#83
acceptance criteria require, plus plugin-specific checks that the generic
validator doesn't cover:

  1. .codex-plugin/plugin.json exists and parses as a JSON object
  2. .codex-plugin/plugin.json carries the required fields (name, version,
     description)
  3. hooks/hooks.json exists, parses, and references the auto_review.py hook
  4. scripts/auto_review.py exists and is executable
  5. All three required env vars (AUTO_REVIEW_BASE_URL, AUTO_REVIEW_API_KEY,
     AUTO_REVIEW_MODEL) are referenced in scripts/auto_review.py and README.md
  6. At least one test file exists in scripts/ (test_*.py)
  7. README.md exists at the plugin root

Exits 0 on success, 1 on failure, and prints a per-check PASS/FAIL line plus a
summary. The summary line is parseable for CI use.

Usage:
    python3 plugins/auto-review/scripts/validate.py [<plugin-root>]

If <plugin-root> is omitted, the script's parent's parent is used (i.e. the
plugin directory is inferred from the location of validate.py).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, List, Tuple

REQUIRED_ENV_VARS: Tuple[str, ...] = (
    "AUTO_REVIEW_BASE_URL",
    "AUTO_REVIEW_API_KEY",
    "AUTO_REVIEW_MODEL",
)

# Hook JSON must reference this exact script name in its `command` field.
HOOK_SCRIPT_NAME = "auto_review.py"


def default_plugin_root() -> Path:
    """Infer the plugin root from this script's location."""
    return Path(__file__).resolve().parent.parent


# ── Individual checks ──────────────────────────────────────────────────────
# Each check returns (passed: bool, message: str). No side effects beyond
# reading files. They never raise; exceptions are caught and reported as
# failures so a single broken file doesn't crash the whole validator.


def check_manifest(plugin_root: Path) -> Tuple[bool, str]:
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        return False, "missing .codex-plugin/plugin.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f".codex-plugin/plugin.json is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return False, ".codex-plugin/plugin.json must be a JSON object"
    missing = [k for k in ("name", "version", "description") if k not in payload]
    if missing:
        return False, f".codex-plugin/plugin.json missing required field(s): {', '.join(missing)}"
    return True, f"manifest ok (name={payload.get('name')!r}, version={payload.get('version')!r})"


def check_hooks(plugin_root: Path) -> Tuple[bool, str]:
    hooks_path = plugin_root / "hooks" / "hooks.json"
    if not hooks_path.is_file():
        return False, "missing hooks/hooks.json"
    try:
        payload = json.loads(hooks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"hooks/hooks.json is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return False, "hooks/hooks.json must be a JSON object"
    # Flatten all `command` strings across the hooks tree so we can verify
    # the runtime entry point is referenced regardless of nesting depth.
    commands: List[str] = []

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            cmd = node.get("command")
            if isinstance(cmd, str):
                commands.append(cmd)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
    if not any(HOOK_SCRIPT_NAME in cmd for cmd in commands):
        return False, (
            f"hooks/hooks.json does not reference {HOOK_SCRIPT_NAME!r} "
            f"in any `command` field (found {len(commands)} command(s))"
        )
    return True, f"hooks ok (references {HOOK_SCRIPT_NAME})"


def check_hook_script(plugin_root: Path) -> Tuple[bool, str]:
    script_path = plugin_root / "scripts" / HOOK_SCRIPT_NAME
    if not script_path.is_file():
        return False, f"missing scripts/{HOOK_SCRIPT_NAME}"
    if not os.access(script_path, os.X_OK):
        return False, f"scripts/{HOOK_SCRIPT_NAME} is not executable (chmod +x)"
    return True, f"hook script ok ({script_path})"


def check_env_var_documentation(plugin_root: Path) -> Tuple[bool, str]:
    """Verify every required env var is named in both source and README."""
    source_path = plugin_root / "scripts" / HOOK_SCRIPT_NAME
    readme_path = plugin_root / "README.md"
    if not source_path.is_file():
        return False, f"missing scripts/{HOOK_SCRIPT_NAME} (cannot check env vars)"
    if not readme_path.is_file():
        return False, "missing README.md (cannot check env vars)"
    try:
        source_text = source_path.read_text(encoding="utf-8")
        readme_text = readme_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"could not read plugin files: {exc}"
    missing_source = [v for v in REQUIRED_ENV_VARS if v not in source_text]
    missing_readme = [v for v in REQUIRED_ENV_VARS if v not in readme_text]
    if missing_source:
        return False, f"env var(s) not referenced in {HOOK_SCRIPT_NAME}: {', '.join(missing_source)}"
    if missing_readme:
        return False, f"env var(s) not documented in README.md: {', '.join(missing_readme)}"
    return True, f"all {len(REQUIRED_ENV_VARS)} required env vars documented"


def check_tests(plugin_root: Path) -> Tuple[bool, str]:
    scripts_dir = plugin_root / "scripts"
    if not scripts_dir.is_dir():
        return False, f"missing scripts/ directory"
    test_files = sorted(scripts_dir.glob("test_*.py"))
    if not test_files:
        return False, "no test files found in scripts/ (expected test_*.py)"
    return True, f"tests present ({len(test_files)} file(s): {', '.join(p.name for p in test_files)})"


def check_readme(plugin_root: Path) -> Tuple[bool, str]:
    readme_path = plugin_root / "README.md"
    if not readme_path.is_file():
        return False, "missing README.md"
    # Warn on placeholder markers so documentation drift is caught.
    try:
        text = readme_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"could not read README.md: {exc}"
    if re.search(r"\[TODO[: ]", text):
        return False, "README.md still contains a [TODO: ...] placeholder"
    return True, f"README.md ok ({len(text)} chars)"


# Order matters for readability of the output. Each entry is (label, function).
CHECKS: List[Tuple[str, Callable[[Path], Tuple[bool, str]]]] = [
    ("manifest",         check_manifest),
    ("hooks",            check_hooks),
    ("hook_script",      check_hook_script),
    ("env_var_docs",     check_env_var_documentation),
    ("tests",            check_tests),
    ("readme",           check_readme),
]


def run(plugin_root: Path) -> int:
    """Run all checks. Returns 0 on success, 1 on any failure."""
    if not plugin_root.is_dir():
        print(f"validate: {plugin_root} is not a directory", file=sys.stderr)
        return 1
    failures: List[str] = []
    for label, fn in CHECKS:
        try:
            passed, message = fn(plugin_root)
        except Exception as exc:  # belt-and-braces — checks should not raise
            passed, message = False, f"{label} raised: {exc}"
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {label}: {message}")
        if not passed:
            failures.append(label)
    if failures:
        print(f"\nvalidate: {len(failures)} failure(s): {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"\nvalidate: all {len(CHECKS)} checks passed for {plugin_root}")
    return 0


def main(argv: List[str]) -> int:
    if len(argv) > 2:
        print("usage: validate.py [<plugin-root>]", file=sys.stderr)
        return 2
    plugin_root = Path(argv[1]).expanduser().resolve() if len(argv) == 2 else default_plugin_root()
    return run(plugin_root)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Unit tests for harness5/hooks/loader.py.

Coverage:
- emits JSON with the correct SessionStart shape on stdout
- additionalContext content matches the file verbatim
- missing file → no stdout, stderr warning, exit 0
- unreadable file (OSError) → no stdout, exit 0
- file > 32K chars → still emits JSON, stderr size-cap warning, no truncation
- JSON parses cleanly with json.loads
- main() returns 0 even on missing file
- main() emits valid JSON when file exists

The loader reads HARNESS5_INSTRUCTIONS_FILE (env var) when set, falling
back to <script_dir>/references/harness5.md. Tests drive the script as a
subprocess with the env var pointing at tmp files; that exercises the
real subprocess boundary instead of mocking, which would not survive a
fresh interpreter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "loader.py"
REAL_FIXTURE = Path(__file__).resolve().parent / "references" / "harness5.md"


def _run_with_file(env_value: str | None) -> subprocess.CompletedProcess:
    """Run loader.py with HARNESS5_INSTRUCTIONS_FILE set (or unset)."""
    env = os.environ.copy()
    if env_value is None:
        env.pop("HARNESS5_INSTRUCTIONS_FILE", None)
    else:
        env["HARNESS5_INSTRUCTIONS_FILE"] = env_value
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


class LoaderScriptTests(unittest.TestCase):
    """Drive loader.py as a subprocess so stdout/stderr/exit are real."""

    def test_emits_valid_session_start_json(self):
        """Loader emits JSON with hookSpecificOutput.hookEventName == 'SessionStart'."""
        result = _run_with_file(str(REAL_FIXTURE))
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr}")
        self.assertNotEqual(result.stdout.strip(), "", "stdout should have JSON")
        payload = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", payload)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("additionalContext", payload["hookSpecificOutput"])

    def test_additional_context_matches_file(self):
        """additionalContext content is exactly the file's text."""
        result = _run_with_file(str(REAL_FIXTURE))
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        expected = REAL_FIXTURE.read_text(encoding="utf-8")
        self.assertEqual(payload["hookSpecificOutput"]["additionalContext"], expected)

    def test_missing_file_silent_pass_through(self):
        """Missing file → no JSON on stdout, warning on stderr, exit 0."""
        result = _run_with_file("/nonexistent/harness5.md")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "", "stdout should be empty on missing file")
        self.assertIn("not found", result.stderr)
        self.assertIn("harness5:", result.stderr)

    def test_unreadable_target_silent_pass_through(self):
        """OSError (e.g. file replaced with a directory) → no JSON, warning, exit 0."""
        # Make a directory where loader.py expects a file — read_text raises IsADirectoryError.
        import tempfile
        with tempfile.TemporaryDirectory(prefix="harness5_unreadable_") as tmpdir:
            result = _run_with_file(tmpdir)  # directory, not a file
            self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr}")
            self.assertEqual(result.stdout, "")
            self.assertIn("failed to read", result.stderr)

    def test_oversize_file_still_injects(self):
        """File > 32K chars → still emits JSON, stderr warns but does not truncate."""
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="harness5_oversize_"
        ) as f:
            big = "x" * (40_000)  # > 32_768
            f.write(big)
            tmp_path = Path(f.name)
        try:
            result = _run_with_file(str(tmp_path))
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["hookSpecificOutput"]["additionalContext"],
                big,
                "loader must not truncate",
            )
            self.assertIn("exceeds 32768 soft cap", result.stderr)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_json_parses_cleanly(self):
        """The stdout payload is parseable JSON."""
        result = _run_with_file(str(REAL_FIXTURE))
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)  # raises if not parseable
        self.assertIsInstance(parsed, dict)

    def test_unset_env_falls_back_to_default(self):
        """Without HARNESS5_INSTRUCTIONS_FILE, loader falls back to references/harness5.md.

        Run from the hooks/ directory so the default relative path resolves correctly.
        """
        env = os.environ.copy()
        env.pop("HARNESS5_INSTRUCTIONS_FILE", None)
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=str(SCRIPT.parent),
        )
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr}")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")


class LoaderModuleTests(unittest.TestCase):
    """Import loader.py as a module and call load_instructions/main directly."""

    def test_load_instructions_returns_content(self):
        import loader
        loader.INSTRUCTIONS_FILE = REAL_FIXTURE
        content = loader.load_instructions()
        self.assertIsNotNone(content)
        self.assertGreater(len(content), 100)

    def test_load_instructions_returns_none_when_missing(self):
        import loader
        loader.INSTRUCTIONS_FILE = Path("/nonexistent/harness5.md")
        content = loader.load_instructions()
        self.assertIsNone(content)

    def test_main_returns_zero_on_missing_file(self):
        import loader
        loader.INSTRUCTIONS_FILE = Path("/nonexistent/harness5.md")
        rc = loader.main()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()

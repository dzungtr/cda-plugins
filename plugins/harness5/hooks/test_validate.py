"""Unit tests for harness5/hooks/validate.py.

Coverage:
- all 6 checks PASS when plugin is fully wired up
- each individual check fails when its precondition is broken
- run() returns 0 on success, 1 on any failure
- exit code matches run() return value
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = Path(__file__).resolve().parent / "validate.py"


class ValidateHappyPathTests(unittest.TestCase):
    """validate.py on a fully-wired plugin returns 0 and prints all PASS lines."""

    def test_runs_clean_on_real_plugin(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATE), str(PLUGIN_ROOT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            msg=f"stderr: {result.stderr}\nstdout: {result.stdout}",
        )
        # All 6 checks should be reported PASS.
        for label in (
            "manifest-version",
            "manifest-hooks-field",
            "hooks-files-exist",
            "hooks-json-valid",
            "loader-executable",
            "harness5-md-present",
        ):
            self.assertIn(f"[PASS] {label}", result.stdout, msg=f"missing PASS for {label}")

    def test_summary_line_present(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATE), str(PLUGIN_ROOT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("all 6 checks passed", result.stdout)


class ValidateFailureTests(unittest.TestCase):
    """validate.py fails (exit 1) when a check's precondition is broken.

    Each test mutates the plugin tree temporarily in a tmpdir copy and
    verifies the relevant check goes FAIL.

    Tests use ``_copy_plugin_normalized`` which first applies the current
    expected manifests state (version 0.2.2 + hooks field) before breaking
    a single precondition. That isolates the assertion: exactly one check
    fails per test.
    """

    EXPECTED_CODEX_HOOKS = "./codex/hooks.json"
    EXPECTED_CLAUDE_HOOKS = "./claude/hooks.json"
    EXPECTED_VERSION = "0.2.2"

    def _copy_plugin(self) -> Path:
        """Copy the plugin tree to a tmp dir so we can mutate it freely."""
        import shutil, tempfile
        tmp = Path(tempfile.mkdtemp(prefix="harness5_validate_test_"))
        dest = tmp / "harness5"
        shutil.copytree(PLUGIN_ROOT, dest)
        return dest

    def _normalize_manifests(self, plugin_copy: Path) -> None:
        """Bring the tmp copy's manifests up to expected state so we test ONE failure at a time."""
        for label, hooks_field in (
            (".codex-plugin", self.EXPECTED_CODEX_HOOKS),
            (".claude-plugin", self.EXPECTED_CLAUDE_HOOKS),
        ):
            manifest = plugin_copy / label / "plugin.json"
            data = json.loads(manifest.read_text())
            data["version"] = self.EXPECTED_VERSION
            data["hooks"] = hooks_field
            manifest.write_text(json.dumps(data, indent=2))

    def _copy_plugin_normalized(self) -> Path:
        """Copy + normalize: tmp plugin that passes all checks except whatever we break next."""
        copy = self._copy_plugin()
        self._normalize_manifests(copy)
        return copy

    """validate.py fails (exit 1) when a check's precondition is broken.

    Each test mutates the plugin tree temporarily in a tempdir copy and
    verifies the relevant check goes FAIL.
    """

    def _copy_plugin(self) -> Path:
        """Copy the plugin tree to a tmp dir so we can mutate it freely."""
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="harness5_validate_test_"))
        dest = tmp / "harness5"
        shutil.copytree(PLUGIN_ROOT, dest)
        return dest

    def test_missing_manifest_version_fails(self):
        """Bumping version back to 0.2.0 fails manifest-version check."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            # Edit both manifests to revert version.
            for label in (".codex-plugin", ".claude-plugin"):
                manifest = plugin_copy / label / "plugin.json"
                data = json.loads(manifest.read_text())
                data["version"] = "0.2.0"
                manifest.write_text(json.dumps(data, indent=2))
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] manifest-version", result.stdout)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)

    def test_missing_claude_hooks_field_fails(self):
        """Clearing hooks field in claude manifest fails manifest-hooks-field check."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            manifest = plugin_copy / ".claude-plugin" / "plugin.json"
            data = json.loads(manifest.read_text())
            del data["hooks"]
            manifest.write_text(json.dumps(data, indent=2))
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] manifest-hooks-field", result.stdout)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)

    def test_missing_loader_fails(self):
        """Deleting loader.py fails hooks-files-exist check."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            (plugin_copy / "hooks" / "loader.py").unlink()
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] hooks-files-exist", result.stdout)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)

    def test_loader_not_executable_fails(self):
        """Stripping +x from loader.py fails loader-executable check."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            loader = plugin_copy / "hooks" / "loader.py"
            loader.chmod(0o644)
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] loader-executable", result.stdout)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)

    def test_missing_harness5_md_fails(self):
        """Deleting references/harness5.md fails harness5-md-present check."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            (plugin_copy / "hooks" / "references" / "harness5.md").unlink()
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] harness5-md-present", result.stdout)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)

    def test_empty_harness5_md_fails(self):
        """Empty harness5.md fails harness5-md-present check."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            (plugin_copy / "hooks" / "references" / "harness5.md").write_text("   \n")
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] harness5-md-present", result.stdout)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)

    def test_malformed_codex_hooks_json_fails(self):
        """Corrupting codex hooks.json fails hooks-json-valid check."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            (plugin_copy / "hooks" / "hooks.json").write_text("{not valid json")
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] hooks-json-valid", result.stdout)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)

    def test_missing_sessionstart_in_hooks_json_fails(self):
        """Removing SessionStart key from hooks.json fails hooks-json-valid check."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            path = plugin_copy / "hooks" / "hooks.json"
            data = json.loads(path.read_text())
            del data["hooks"]["SessionStart"]
            path.write_text(json.dumps(data, indent=2))
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("[FAIL] hooks-json-valid", result.stdout)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)

    def test_stderr_summary_on_failure(self):
        """On failure, a stderr summary lists failed checks."""
        plugin_copy = self._copy_plugin_normalized()
        try:
            (plugin_copy / "hooks" / "references" / "harness5.md").unlink()
            result = subprocess.run(
                [sys.executable, str(VALIDATE), str(plugin_copy)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("failure(s)", result.stderr)
            self.assertIn("harness5-md-present", result.stderr)
            self.assertIn("harness5-md-present", result.stderr)
        finally:
            import shutil
            shutil.rmtree(plugin_copy.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

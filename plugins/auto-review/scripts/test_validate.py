"""Tests for scripts/validate.py — covers the happy path and every negative case.

The validator is plugin-specific, so positive tests run against the real
plugin tree (the directory containing this test file's parent's parent).
Negative tests use a tmp dir that mirrors the real layout with one piece
missing or broken at a time.
"""

import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import validate


PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _make_fake_plugin(root: Path) -> None:
    """Build a minimal but valid plugin tree under root."""
    (root / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({
        "name": "auto-review", "version": "0.1.0", "description": "fake"
    }))
    (root / "hooks").mkdir(parents=True, exist_ok=True)
    (root / "hooks" / "hooks.json").write_text(json.dumps({
        "hooks": {"PermissionRequest": [{"hooks": [{"type": "command",
            "command": "python3 scripts/auto_review.py"}]}]}
    }))
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    script = root / "scripts" / "auto_review.py"
    script.write_text("#!/usr/bin/env python3\nAUTO_REVIEW_BASE_URL = ''\n"
                      "AUTO_REVIEW_API_KEY = ''\nAUTO_REVIEW_MODEL = ''\n")
    script.chmod(0o755)
    (root / "scripts" / "test_smoke.py").write_text("# fake test file\n")
    (root / "README.md").write_text(
        "AUTO_REVIEW_BASE_URL docs\nAUTO_REVIEW_API_KEY docs\nAUTO_REVIEW_MODEL docs\n"
    )
    (root / "requirements.txt").write_text("zai-sdk>=0.2.3\n")


class HappyPathTests(unittest.TestCase):
    """All checks pass when the validator runs against the real plugin tree."""

    def test_run_against_real_plugin_returns_zero(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = validate.run(PLUGIN_ROOT)
        self.assertEqual(rc, 0, msg=f"stdout={out.getvalue()!r} stderr={err.getvalue()!r}")
        self.assertIn("all 7 checks passed", out.getvalue())

    def test_main_no_args_infers_plugin_root(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = validate.main(["validate.py"])
        self.assertEqual(rc, 0, msg=err.getvalue())

    def test_main_with_explicit_path(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = validate.main(["validate.py", str(PLUGIN_ROOT)])
        self.assertEqual(rc, 0, msg=err.getvalue())

    def test_rejects_too_many_args(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = validate.main(["validate.py", "a", "b"])
        self.assertEqual(rc, 2)

    def test_rejects_nonexistent_plugin_root(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = validate.run(Path("/this/does/not/exist/anywhere"))
        self.assertEqual(rc, 1)


class NegativeCaseTests(unittest.TestCase):
    """One tmp plugin tree per test, with exactly one defect, rebuilt per test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _make_fake_plugin(self.root)

    def _run(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = validate.run(self.root)
        return rc, out.getvalue(), err.getvalue()

    def test_missing_manifest(self):
        (self.root / ".codex-plugin" / "plugin.json").unlink()
        rc, out, err = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] manifest", out)
        self.assertIn("missing .codex-plugin/plugin.json", out)

    def test_manifest_invalid_json(self):
        (self.root / ".codex-plugin" / "plugin.json").write_text("{ not valid json")
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] manifest", out)
        self.assertIn("not valid JSON", out)

    def test_manifest_missing_required_field(self):
        # Remove 'description' — must be flagged.
        (self.root / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "auto-review", "version": "0.1.0"}))
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] manifest", out)
        self.assertIn("description", out)

    def test_missing_hooks_file(self):
        (self.root / "hooks" / "hooks.json").unlink()
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] hooks", out)
        self.assertIn("missing hooks/hooks.json", out)

    def test_hooks_does_not_reference_hook_script(self):
        (self.root / "hooks" / "hooks.json").write_text(json.dumps({
            "hooks": {"PermissionRequest": [{"hooks": [{"type": "command",
                "command": "python3 scripts/other_thing.py"}]}]}
        }))
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] hooks", out)
        self.assertIn("does not reference", out)

    def test_hook_script_missing(self):
        (self.root / "scripts" / "auto_review.py").unlink()
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] hook_script", out)
        self.assertIn("missing scripts/auto_review.py", out)

    def test_hook_script_not_executable(self):
        path = self.root / "scripts" / "auto_review.py"
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # remove exec bit
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] hook_script", out)
        self.assertIn("not executable", out)

    def test_env_var_missing_from_source(self):
        path = self.root / "scripts" / "auto_review.py"
        # Strip AUTO_REVIEW_API_KEY from the fake source.
        text = path.read_text().replace("AUTO_REVIEW_API_KEY", "FOO_BAR")
        path.write_text(text)
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] env_var_docs", out)
        self.assertIn("AUTO_REVIEW_API_KEY", out)

    def test_env_var_missing_from_readme(self):
        (self.root / "README.md").write_text(
            "AUTO_REVIEW_BASE_URL docs\nAUTO_REVIEW_MODEL docs\n")
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] env_var_docs", out)
        self.assertIn("AUTO_REVIEW_API_KEY", out)

    def test_no_tests(self):
        (self.root / "scripts" / "test_smoke.py").unlink()
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] tests", out)
        self.assertIn("no test files found", out)

    def test_missing_requirements_file(self):
        (self.root / "requirements.txt").unlink()
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] requirements", out)
        self.assertIn("missing requirements.txt", out)

    def test_requirements_missing_sdk_package(self):
        # requirements.txt exists but omits zai-sdk — must fail.
        (self.root / "requirements.txt").write_text("# nothing here\nhttpx>=0.27\n")
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] requirements", out)
        self.assertIn("zai-sdk", out)

    def test_requirements_with_comments_and_extras_is_ok(self):
        # Comments, blank lines, and extras must not break the parser.
        (self.root / "requirements.txt").write_text(
            "# Pin the Z.ai SDK for the agent loop\n"
            "\n"
            "zai-sdk>=0.2.3  # official Python SDK\n"
            "httpx>=0.27  # transitive but pinned for reproducibility\n"
        )
        rc, out, _ = self._run()
        self.assertEqual(rc, 0, msg=out)
        self.assertIn("[PASS] requirements", out)

    def test_requirements_with_pinned_version_is_ok(self):
        (self.root / "requirements.txt").write_text("zai-sdk==0.2.3\n")
        rc, out, _ = self._run()
        self.assertEqual(rc, 0, msg=out)

    def test_requirements_with_marker_is_ok(self):
        # Environment markers are tolerated.
        (self.root / "requirements.txt").write_text('zai-sdk>=0.2.3; python_version >= "3.8"\n')
        rc, out, _ = self._run()
        self.assertEqual(rc, 0, msg=out)

    def test_missing_readme(self):
        (self.root / "README.md").unlink()
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] readme", out)
        self.assertIn("missing README.md", out)

    def test_readme_with_todo_marker(self):
        (self.root / "README.md").write_text(
            "AUTO_REVIEW_BASE_URL docs\nAUTO_REVIEW_API_KEY docs\n"
            "AUTO_REVIEW_MODEL docs\n\n[TODO: write the real docs]\n"
        )
        rc, out, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] readme", out)
        self.assertIn("[TODO", out)

    def test_failure_summary_in_stderr(self):
        # Drop a README that still mentions every required env var so the
        # env_var_docs check passes; then corrupt it with [TODO: ...] so
        # only the readme check fails. The summary must list the failing
        # check(s) on stderr.
        (self.root / "README.md").write_text(
            "AUTO_REVIEW_BASE_URL docs\nAUTO_REVIEW_API_KEY docs\n"
            "AUTO_REVIEW_MODEL docs\n\n[TODO: fill in real docs]\n"
        )
        rc, out, err = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("validate: 1 failure(s): readme", err)

    def test_multiple_failures_all_reported(self):
        (self.root / "README.md").unlink()
        (self.root / "scripts" / "test_smoke.py").unlink()
        rc, out, err = self._run()
        self.assertEqual(rc, 1)
        # Both failures show up in the per-check output.
        self.assertIn("[FAIL] readme", out)
        self.assertIn("[FAIL] tests", out)
        # Summary lists both labels.
        self.assertIn("readme", err)
        self.assertIn("tests", err)

    def test_requirements_and_tests_both_fail(self):
        # Drop requirements.txt + tests so both new and existing checks fail.
        (self.root / "requirements.txt").unlink()
        (self.root / "scripts" / "test_smoke.py").unlink()
        rc, out, err = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] requirements", out)
        self.assertIn("[FAIL] tests", out)
        self.assertIn("requirements", err)
        self.assertIn("tests", err)


if __name__ == "__main__":
    unittest.main()

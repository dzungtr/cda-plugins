"""Tests for log_decision() and the log_decision wiring in main()."""

import builtins
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import auto_review


class LogDecisionTests(unittest.TestCase):
    """Direct tests for log_decision(): file writes, schema, and failure modes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = self.tmp.name
        # Make sure no fallback paths leak in — pin PLUGIN_DATA explicitly.
        self.env = mock.patch.dict(os.environ, {"PLUGIN_DATA": self.data_dir}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def _read_log_lines(self) -> list:
        log_path = Path(self.data_dir) / auto_review.LOG_FILE_NAME
        if not log_path.exists():
            return []
        return log_path.read_text(encoding="utf-8").splitlines()

    def test_log_decision_writes_jsonl_line(self):
        before = self._read_log_lines()
        auto_review.log_decision("Bash", "ls -la", "allow", 1, "safe")
        lines = self._read_log_lines()
        self.assertEqual(len(lines), len(before) + 1)
        entry = json.loads(lines[-1])
        self.assertEqual(entry["tool_name"], "Bash")
        self.assertEqual(entry["command"], "ls -la")
        self.assertEqual(entry["verdict"], "allow")
        self.assertEqual(entry["turns"], 1)
        self.assertEqual(entry["reason"], "safe")
        # ts must be a parseable ISO8601 UTC string
        self.assertIn("T", entry["ts"])
        self.assertTrue(entry["ts"].endswith("+00:00") or entry["ts"].endswith("Z"))

    def test_log_decision_creates_dir_if_missing(self):
        nested = Path(self.data_dir) / "deep" / "nested" / "logs"
        self.assertFalse(nested.exists())
        with mock.patch.dict(os.environ, {"PLUGIN_DATA": str(nested)}):
            auto_review.log_decision("Bash", "git status", "allow", None, None)
        log_path = nested / auto_review.LOG_FILE_NAME
        self.assertTrue(log_path.exists())
        entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(entry["verdict"], "allow")
        self.assertIsNone(entry["turns"])
        self.assertIsNone(entry["reason"])

    def test_log_decision_truncates_command_at_500_chars(self):
        long_command = "echo " + ("a" * 1000)
        auto_review.log_decision("Bash", long_command, "allow", 0, None)
        lines = self._read_log_lines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(len(entry["command"]), 500)
        self.assertTrue(entry["command"].startswith("echo "))
        self.assertTrue(entry["command"].endswith("a" * (500 - 5)))

    def test_log_decision_does_not_crash_on_write_failure(self):
        real_open = builtins.open
        def boom(*args, **kwargs):
            raise OSError("disk full")
        with mock.patch.object(builtins, "open", side_effect=boom):
            # Must not raise — logging failure is non-fatal.
            auto_review.log_decision("Bash", "ls", "allow", 0, None)
        # And nothing should be written.
        log_path = Path(self.data_dir) / auto_review.LOG_FILE_NAME
        self.assertFalse(log_path.exists())


class MainWiringTests(unittest.TestCase):
    """Verify main() calls log_decision() once per request, on every path."""

    def _run_main(self, stdin_payload, *, log_decision_mock, run_agent_loop_mock,
                  check_deny_bucket_mock=None):
        """Run main() with stdin + collaborators mocked. Returns the mock calls."""
        stdin = io.StringIO(stdin_payload)
        with mock.patch.object(sys, "stdin", stdin), \
             mock.patch.object(sys, "exit") as exit_mock, \
             mock.patch("builtins.print") as print_mock, \
             mock.patch.object(auto_review, "log_decision", log_decision_mock), \
             mock.patch.object(auto_review, "run_agent_loop", run_agent_loop_mock), \
             mock.patch.object(auto_review, "check_deny_bucket",
                               check_deny_bucket_mock or mock.Mock(return_value=None)), \
             mock.patch.object(auto_review, "gather_env_snapshot",
                               mock.Mock(return_value={"cwd": "/tmp", "env": {}})):
            auto_review.main()
        return log_decision_mock.call_args_list

    def test_main_calls_log_decision_on_allow(self):
        log_mock = mock.Mock()
        run_mock = mock.Mock(return_value={"verdict": "allow", "turns": 2, "reason": "safe"})
        calls = self._run_main(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            log_decision_mock=log_mock,
            run_agent_loop_mock=run_mock,
        )
        self.assertEqual(len(calls), 1)
        args, _ = calls[0]
        self.assertEqual(args[0], "Bash")
        self.assertEqual(args[1], "ls")
        self.assertEqual(args[2], "allow")
        self.assertEqual(args[3], 2)
        self.assertEqual(args[4], "safe")

    def test_main_calls_log_decision_on_deny(self):
        log_mock = mock.Mock()
        # Deny from the agent loop, not the static deny-bucket.
        run_mock = mock.Mock(return_value={"verdict": "deny", "turns": 1, "reason": "dangerous"})
        calls = self._run_main(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": "weird-thing"}}),
            log_decision_mock=log_mock,
            run_agent_loop_mock=run_mock,
        )
        self.assertEqual(len(calls), 1)
        args, _ = calls[0]
        self.assertEqual(args[0], "Bash")
        self.assertEqual(args[1], "weird-thing")
        self.assertEqual(args[2], "deny")
        self.assertEqual(args[3], 1)
        self.assertEqual(args[4], "dangerous")

    def test_main_calls_log_decision_on_deny_bucket_hit(self):
        """Deny-bucket hits must log too (turns=0, reason=deny-bucket reason)."""
        log_mock = mock.Mock()
        run_mock = mock.Mock(return_value={"verdict": "allow", "turns": 0, "reason": "ok"})
        deny_bucket = mock.Mock(return_value="rm -rf on root or home directory — irreversible system wipe")
        calls = self._run_main(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}),
            log_decision_mock=log_mock,
            run_agent_loop_mock=run_mock,
            check_deny_bucket_mock=deny_bucket,
        )
        # run_agent_loop must NOT have been called when the deny-bucket fires.
        run_mock.assert_not_called()
        self.assertEqual(len(calls), 1)
        args, _ = calls[0]
        self.assertEqual(args[2], "deny")
        self.assertEqual(args[3], 0)
        self.assertIn("rm -rf", args[4])

    def test_main_calls_log_decision_on_decline(self):
        log_mock = mock.Mock()
        run_mock = mock.Mock(return_value={"verdict": "decline", "turns": 8, "reason": "max turns exhausted"})
        calls = self._run_main(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            log_decision_mock=log_mock,
            run_agent_loop_mock=run_mock,
        )
        self.assertEqual(len(calls), 1)
        args, _ = calls[0]
        self.assertEqual(args[2], "decline")
        self.assertEqual(args[3], 8)
        self.assertEqual(args[4], "max turns exhausted")

    def test_main_calls_log_decision_on_malformed_stdin(self):
        """Malformed-stdin path must still log a decline before exiting."""
        log_mock = mock.Mock()
        run_mock = mock.Mock()
        calls = self._run_main(
            "this is not json {{",
            log_decision_mock=log_mock,
            run_agent_loop_mock=run_mock,
        )
        # Agent loop must not be called on malformed input.
        run_mock.assert_not_called()
        self.assertEqual(len(calls), 1)
        args, _ = calls[0]
        self.assertEqual(args[2], "decline")
        self.assertIn("malformed JSON", args[4])

    def test_main_calls_log_decision_on_empty_stdin(self):
        log_mock = mock.Mock()
        run_mock = mock.Mock()
        calls = self._run_main(
            "",
            log_decision_mock=log_mock,
            run_agent_loop_mock=run_mock,
        )
        run_mock.assert_not_called()
        self.assertEqual(len(calls), 1)
        args, _ = calls[0]
        self.assertEqual(args[2], "decline")
        self.assertEqual(args[4], "empty stdin")


if __name__ == "__main__":
    unittest.main()

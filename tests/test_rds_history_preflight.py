"""Missing history access must be visible, without querying or installing anything."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_obelisk import history_command, preflight


class HistoryPreflightTests(unittest.TestCase):
    def test_missing_cli_reports_setup_and_nonzero_without_inventing_empty_history(self):
        output = io.StringIO()
        with patch("rds_obelisk.shutil.which", return_value=None), \
             patch("rds_obelisk.subprocess.run") as execute, contextlib.redirect_stdout(output):
            self.assertEqual(history_command(SimpleNamespace(subcommand="preflight")), 2)
        execute.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "MISSING")
        self.assertEqual(report["history_coverage"], "NOT_CHECKED")
        self.assertIn("obelisk install", report["setup_commands"])

    def test_runnable_cli_does_not_certify_index_coverage_or_agent_skill(self):
        with patch("rds_obelisk.shutil.which", return_value="obelisk"), \
             patch("rds_obelisk.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "1.2.3\n", "")) as execute:
            report = preflight()
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["version"], "1.2.3")
        self.assertEqual(report["retrieval_skill"], "NOT_CHECKED")
        self.assertEqual(execute.call_args.args[0], ["obelisk", "--version"])

    def test_failed_timeout_and_permission_do_not_become_ready(self):
        failures = [subprocess.CompletedProcess([], 1, "", "broken runtime"),
                    subprocess.TimeoutExpired("obelisk", 10), PermissionError("denied")]
        for failure in failures:
            with self.subTest(failure=str(failure)), patch("rds_obelisk.shutil.which", return_value="obelisk"):
                kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
                with patch("rds_obelisk.subprocess.run", **kwargs):
                    report = preflight()
            self.assertEqual(report["status"], "UNAVAILABLE")
            self.assertEqual(report["history_coverage"], "NOT_CHECKED")


if __name__ == "__main__":
    unittest.main()

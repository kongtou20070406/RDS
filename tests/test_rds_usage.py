"""Local-day counts, concurrent processes, privacy and transparent log failures."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_usage as usage


class UsageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.path = self.folder / "calls.sqlite3"
        environment = patch.dict(os.environ, {"RDS_USAGE_DB": str(self.path)})
        environment.start()
        self.addCleanup(environment.stop)
        state = patch.object(usage, "_last_error", None)
        state.start()
        self.addCleanup(state.stop)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"), *args],
                              cwd=self.folder, capture_output=True, text=True, encoding="utf-8", timeout=15)

    def test_midnight_daily_counts_and_untracked_history(self):
        for moment, command, exit_code in ((datetime(2026, 9, 30, 23, 59), "formal", 0),
                                           (datetime(2026, 10, 1, 0, 1), "status", 1)):
            with patch.object(usage.time, "time", return_value=moment.astimezone().timestamp()):
                self.assertEqual(usage.run_logged(lambda: exit_code, [command], "test"), exit_code)
        result = usage.summarize(since="2026-09-29", until="2026-10-01")
        self.assertEqual([row["calls"] for row in result["daily"]], [None, 1, 1])
        self.assertEqual(result["total_calls"], 2)
        self.assertEqual(result["daily"][1]["successful"], 1)
        self.assertEqual(result["daily"][2]["failed"], 1)

    def test_help_and_argument_errors_are_counted_without_saving_payloads(self):
        secret = "private-prompt-and-token-never-log"
        def help_exit():
            raise SystemExit(0)
        def error_exit():
            raise SystemExit(2)
        with self.assertRaises(SystemExit):
            usage.run_logged(help_exit, ["--root", secret, "formal", "--help"], "test")
        with self.assertRaises(SystemExit):
            usage.run_logged(error_exit, [secret], "test")
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute("SELECT command,mode,exit_code FROM calls ORDER BY id").fetchall()
        self.assertEqual(rows, [("formal", "help", 0), ("other", "command", 2)])
        self.assertNotIn(secret, str(rows))

    def test_storage_failure_does_not_change_original_return_or_exception(self):
        with patch.dict(os.environ, {"RDS_USAGE_DB": str(self.folder)}):
            self.assertEqual(usage.run_logged(lambda: 7, ["status"], "test"), 7)
            with self.assertRaisesRegex(RuntimeError, "original error"):
                usage.run_logged(lambda: (_ for _ in ()).throw(RuntimeError("original error")), ["status"], "test")
        self.assertIsNotNone(usage._last_error)

    def test_concurrent_cli_processes_retain_all_calls(self):
        self.assertEqual(self.cli("--version").returncode, 0)
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(lambda _: self.cli("--version"), range(12)))
        self.assertTrue(all(result.returncode == 0 for result in results), [r.stderr for r in results])
        result = usage.summarize(days=1)
        self.assertEqual(result["total_calls"], 13)
        self.assertEqual(result["modes"], {"version": 13})
        self.assertEqual(result["daily"][0]["successful"], 13)

    def test_actual_cli_queries_are_counted_and_do_not_create_project_state(self):
        first = self.cli("usage", "--days", "2", "--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        report = json.loads(first.stdout)
        self.assertEqual(report["total_calls"], 1)
        self.assertEqual(report["logging"], "ENABLED")
        self.assertFalse((self.folder / ".rds").exists())
        second = self.cli("usage", "--days", "2")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Recorded calls: 2", second.stdout)

    def test_invalid_windows_fail_and_unfinished_starts_remain_visible(self):
        usage._start(["project"], "test")
        self.assertEqual(usage.summarize(days=1)["daily"][0]["unfinished"], 1)
        for options in ({"days": 0}, {"days": 3661}, {"since": ""},
                        {"since": "2026-10-02", "until": "2026-10-01"}):
            with self.assertRaises(ValueError):
                usage.summarize(**options)
        invalid = self.cli("usage", "--days", "0")
        self.assertEqual(invalid.returncode, 1)
        self.assertIn("--days", invalid.stderr)


if __name__ == "__main__":
    unittest.main()

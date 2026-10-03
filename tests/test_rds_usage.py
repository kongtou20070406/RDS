"""Local-day counts, concurrent processes, privacy and transparent log failures."""
from concurrent.futures import ThreadPoolExecutor
import argparse
from contextlib import closing, redirect_stderr
from datetime import datetime
import json
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from usage_cli_fixture import count_diagnostics, dual_sqlite_wait, ledger_snapshot, run_cli, wait_marker

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
        return run_cli([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"), *args],
                       self.folder, self.path)

    def test_cli_fixture_preserves_both_real_logging_waits(self):
        warmup = self.cli("--version")
        self.assertEqual(warmup.returncode, 0)
        began = time.monotonic()
        with dual_sqlite_wait(self.folder, self.path) as probe:
            with patch.dict(os.environ, probe["environment"]):
                result = self.cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, warmup.stdout)
        self.assertEqual(len(probe["intervals"]), 2)
        self.assertTrue(all(value >= 8.2 for value in probe["intervals"]), probe)
        self.assertGreater(time.monotonic() - began, 15)
        report = usage.summarize(days=1)
        self.assertEqual(report["total_calls"], 2)
        self.assertEqual(report["modes"], {"version": 2})
        self.assertEqual(report["daily"][0]["successful"], 2)
        self.assertEqual(report["daily"][0]["unfinished"], 0)
        self.assertTrue(all(row["exit_code"] == 0 for row in ledger_snapshot(self.path)["calls"]))

    def test_cli_fixture_watchdog_keeps_original_error_outputs_and_ledger(self):
        usage.run_logged(lambda: 0, ["status"], "test")
        before = ledger_snapshot(self.path)
        ready = self.folder / "hung-child-ready"
        script = ("import pathlib,sys,time; "
                  "print('synthetic stdout',flush=True); "
                  "print('synthetic stderr',file=sys.stderr,flush=True); "
                  "pathlib.Path(sys.argv[1]).write_text('ready'); "
                  "time.sleep(120)")
        command = [sys.executable, "-B", "-c", script, str(ready)]
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            run_cli(command, self.folder, self.path, watchdog=.2,
                    ready=lambda child: wait_marker(ready, child=child))
        error = caught.exception
        self.assertEqual(error.cmd, command)
        self.assertEqual(error.timeout, .2)
        self.assertIn("synthetic stdout", error.stdout)
        self.assertIn("synthetic stderr", error.stderr)
        diagnostics = json.loads(error.__notes__[0])
        self.assertTrue(diagnostics["fixture_watchdog"])
        self.assertNotEqual(diagnostics["returncode"], 0)
        self.assertEqual(diagnostics["ledger"], before)
        self.assertEqual(ledger_snapshot(self.path), before)
        from rds_project import _alive
        self.assertFalse(_alive(diagnostics["pid"]))

    def test_cli_fixture_does_not_convert_nonzero_to_success(self):
        command = [sys.executable, "-B", "-c",
                   "import sys; print('synthetic failure',file=sys.stderr); sys.exit(7)"]
        result = run_cli(command, self.folder, self.path)
        self.assertEqual(result.returncode, 7)
        self.assertIn("synthetic failure", result.stderr)

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

    def test_usage_labels_cover_every_public_top_level_command(self):
        import rds_cli
        groups = [action for action in rds_cli.parser()._actions
                  if isinstance(action, argparse._SubParsersAction)]
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0].choices), usage.COMMANDS)
        for command in groups[0].choices:
            with self.subTest(command=command):
                self.assertEqual(usage._label([command]), (command, "command"))
                self.assertEqual(usage._label([command, "--help"]), (command, "help"))

    def test_real_host_hook_help_is_recorded_under_its_command(self):
        result = self.cli("host-hook", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("coverage", result.stdout)
        self.assertFalse((self.folder / ".rds").exists())
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT command,mode,exit_code FROM calls ORDER BY id").fetchall()
        self.assertEqual(rows, [("host-hook", "help", 0)])

    def test_storage_failure_does_not_change_original_return_or_exception(self):
        with patch.dict(os.environ, {"RDS_USAGE_DB": str(self.folder)}):
            self.assertEqual(usage.run_logged(lambda: 7, ["status"], "test"), 7)
            with self.assertRaisesRegex(RuntimeError, "original error"):
                usage.run_logged(lambda: (_ for _ in ()).throw(RuntimeError("original error")), ["status"], "test")
        self.assertIsNotNone(usage._last_error)

    def test_concurrent_cli_processes_retain_all_calls(self):
        warmup = self.cli("--version")
        self.assertEqual(warmup.returncode, 0, count_diagnostics(self.path, [warmup]))
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(lambda _: self.cli("--version"), range(12)))
        children = [warmup, *results]
        self.assertTrue(all(result.returncode == 0 for result in results), count_diagnostics(self.path, children))
        try:
            result = usage.summarize(days=1)
        except Exception as exc:
            exc.add_note(count_diagnostics(self.path, children))
            raise
        evidence = count_diagnostics(self.path, children, result)
        self.assertEqual(result["total_calls"], 13, evidence)
        self.assertEqual(result["modes"], {"version": 13}, evidence)
        self.assertEqual(result["daily"][0]["successful"], 13, evidence)

    def test_first_concurrent_invocations_retain_all_calls(self):
        self.assertFalse(self.path.exists())
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(lambda _: self.cli("--version"), range(12)))
        self.assertTrue(all(r.returncode == 0 for r in results), count_diagnostics(self.path, results))
        try:
            report = usage.summarize(days=1)
        except Exception as exc:
            exc.add_note(count_diagnostics(self.path, results))
            raise
        evidence = count_diagnostics(self.path, results, report)
        self.assertEqual(report['total_calls'], 12, evidence)
        self.assertEqual(report['daily'][0]['successful'], 12, evidence)

    def test_persistent_start_lock_reports_loss_but_preserves_real_cli_result(self):
        warmup = self.cli("--version")
        self.assertEqual(warmup.returncode, 0, warmup.stderr)
        before = ledger_snapshot(self.path)
        with closing(sqlite3.connect(self.path)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            with ThreadPoolExecutor(max_workers=1) as pool:
                # Keep the real writer until the child reaches the existing bounded storage failure.
                result = pool.submit(self.cli, "--version").result(timeout=45)
            blocker.rollback()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, warmup.stdout)
        self.assertIn("[RDS-USAGE-DEGRADED] start logging failed (OperationalError/SQLITE_BUSY)", result.stderr)
        self.assertIn("start record not confirmed", result.stderr)
        self.assertEqual(ledger_snapshot(self.path), before)
        diagnostics = count_diagnostics(self.path, [warmup, result], usage.summarize(days=2))
        evidence = json.loads(diagnostics)
        self.assertEqual(evidence["children"][1]["stderr"], result.stderr)
        self.assertGreaterEqual(evidence["children"][1]["elapsed_seconds"], 10)
        self.assertEqual(evidence["ledger"], before)
        # A missing start must still fail complete-count acceptance. The original
        # child result, phase notice and raw dated row survive in that assertion.
        with self.assertRaises(AssertionError) as incomplete:
            self.assertEqual(evidence["report"]["total_calls"], 2, diagnostics)
        self.assertIn("[RDS-USAGE-DEGRADED] start", str(incomplete.exception))
        self.assertIn('"returncode": 0', str(incomplete.exception))
        self.assertIn('"day":', str(incomplete.exception))
        restored = self.cli("--version")
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(restored.stderr, "")
        report = usage.summarize(days=2)
        self.assertEqual(report["total_calls"], 2)
        self.assertEqual(sum(row["successful"] for row in report["daily"]), 2)

    def test_finish_lock_keeps_unfinished_row_and_original_exception_or_exit(self):
        secret = "private-error-payload-never-print"
        for raises in (False, True):
            with self.subTest(raises=raises), closing(sqlite3.connect(self.path)) as blocker:
                def command():
                    blocker.execute("BEGIN IMMEDIATE")
                    if raises:
                        raise RuntimeError(secret)
                    return 7
                warning = io.StringIO()
                with redirect_stderr(warning):
                    if raises:
                        with self.assertRaisesRegex(RuntimeError, secret):
                            usage.run_logged(command, ["status", secret], "test")
                    else:
                        self.assertEqual(usage.run_logged(command, ["status", secret], "test"), 7)
                blocker.rollback()
            self.assertIn("[RDS-USAGE-DEGRADED] finish logging failed (OperationalError/SQLITE_BUSY)", warning.getvalue())
            self.assertIn("exit record not confirmed", warning.getvalue())
            self.assertNotIn(secret, warning.getvalue())
            retained = ledger_snapshot(self.path)["calls"]
            self.assertEqual(len(retained), 2 if raises else 1)
            self.assertTrue(all(row["exit_code"] is None for row in retained))
            self.assertNotIn(secret, json.dumps(retained))

    def test_unavailable_warning_stream_never_replaces_original_result(self):
        with patch.dict(os.environ, {"RDS_USAGE_DB": str(self.folder)}):
            with patch("rds_usage.sys.stderr") as stream:
                stream.write.side_effect = OSError("synthetic closed stderr")
                self.assertEqual(usage.run_logged(lambda: 7, ["status"], "test"), 7)
                with self.assertRaisesRegex(RuntimeError, "original"):
                    usage.run_logged(lambda: (_ for _ in ()).throw(RuntimeError("original")), ["status"], "test")
        self.assertIsNotNone(usage._last_error)

    def test_brief_lock_wait_preserves_call_and_existing_wal_mode(self):
        usage.run_logged(lambda: 0, ['status'], 'test')
        with closing(sqlite3.connect(self.path)) as blocker:
            self.assertEqual(blocker.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            blocker.execute('BEGIN IMMEDIATE')
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(usage.run_logged, lambda: 7, ['status'], 'test')
                time.sleep(0.6)  # Exceeds the old 250 ms limit, within the bounded wait.
                blocker.commit()
                self.assertEqual(future.result(timeout=4), 7)
            self.assertEqual(blocker.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        report = usage.summarize(days=1)
        self.assertEqual(report['total_calls'], 2)
        self.assertEqual(report['daily'][0]['failed'], 1)
        self.assertIsNone(usage._last_error)

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

    def test_lock_contention_longer_than_old_timeout_retains_start_and_exit(self):
        usage.run_logged(lambda: 0, ['status'], 'test')
        with closing(sqlite3.connect(self.path)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            with ThreadPoolExecutor(max_workers=1) as pool:
                entering = threading.Event()
                def invoke():
                    entering.set()
                    return usage.run_logged(lambda: 7, ['status'], 'test')
                pending = pool.submit(invoke)
                self.assertTrue(entering.wait(timeout=2))
                time.sleep(2.4)  # Deterministic contention beyond the original 2-second wait.
                blocker.commit()
                self.assertEqual(pending.result(timeout=12), 7)
        report = usage.summarize(days=1)
        self.assertEqual(report['total_calls'], 2)
        self.assertEqual(report['daily'][0]['failed'], 1)
        self.assertIsNone(usage._last_error)

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

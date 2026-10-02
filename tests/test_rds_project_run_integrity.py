"""Synthetic retained-run corruption: reject reads without inventing another attempt's outcome."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parent),
                str(Path(__file__).resolve().parents[1] / "scripts")]
import test_rds_project as base
from rds_project import ProjectStore, RunIntegrityError, canonical

CLI = Path(__file__).resolve().parents[1] / "scripts" / "rds_cli.py"


def rows(store):
    with closing(sqlite3.connect(store.path)) as db:
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                for table in ("budget", "runs", "receipts", "events", "exposures", "output_claims")}


def damage(store, body, run_id="r1"):
    with store._db() as db:
        db.execute("UPDATE runs SET body=? WHERE id=?", (body, run_id))


def cli(store, *argv):
    return subprocess.run([sys.executable, "-B", str(CLI), "--root", str(store.root), "project", *argv],
                          capture_output=True, text=True, timeout=60,
                          env={**os.environ, "RDS_USAGE_DB": str(store.root / "usage.sqlite3")})


def invalid_bodies(run):
    return {
        "malformed": "{", "array": "[]", "null": "null", "string": '"run"',
        "number": "1", "boolean": "true", "empty object": "{}",
        "deep nesting": "[" * 10000 + "]" * 10000,
        "repeated key": '{"id":"other",' + canonical(run)[1:],
        "other identity": canonical({**run, "id": "other"}),
        "other status": canonical({**run, "status": "RUNNING"}),
        "non-scalar status": canonical({**run, "status": []}),
        "missing manifest": canonical({key: value for key, value in run.items() if key != "manifest"}),
        "edited manifest": canonical({**run, "manifest": {**run["manifest"], "timeout_seconds": 123}}),
        "missing process identity": canonical({key: value for key, value in run.items() if key != "pid"}),
        "invalid measured cost": canonical({**run, "observed_wall_seconds": "unknown"}),
        "overflowing integer cost": canonical({**run, "observed_wall_seconds": 10 ** 400}),
        "NaN": canonical(run)[:-1] + ',"extra":NaN}',
        "overflow float": canonical(run)[:-1] + ',"extra":1e400}',
        "lone surrogate": canonical(run)[:-1] + ',"extra":"\\ud800"}',
    }


class ProjectRunIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.fx = base.ProjectTests("test_execution_policy_is_opt_in_and_frozen")
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)

    def test_all_invalid_prior_runs_reject_every_cli_entry_without_writing(self):
        fx = self.fx
        store = fx.store
        run = store.register(fx.spec())
        first = store.execute("r1")
        self.assertEqual(first["run_status"], "SUCCEEDED", first)
        run = store.snapshot()["runs"][0]
        store.register(fx.spec("r2"))
        manifest = fx.root / "r3-manifest.json"
        manifest.write_text(canonical(fx.spec("r3")), encoding="utf-8")
        actions = (["create", "--manifest", str(manifest)], ["status", "--brief"], ["next"],
                   ["execute", "--id", "r2"], ["recover", "--id", "r2"],
                   ["recover", "--id", "r1"])
        for name, body in invalid_bodies(run).items():
            # A terminal r1's valid status is COMPLETED, so RUNNING is a row/body mismatch.
            damage(store, body)
            before = rows(store)
            for argv in actions:
                with self.subTest(body=name, argv=argv):
                    result = cli(store, *argv)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn("[RDS-REJECT] Project run integrity failure: run 'r1' body", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(rows(store), before)
        damage(store, canonical(run))
        self.assertEqual(store.recover("r1"), first)
        result = cli(store, "execute", "--id", "r2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["run_status"], "SUCCEEDED")

    def test_route_admission_uses_validated_history_instead_of_sql_json_predicate(self):
        store = self.fx.new_store(policy={"schema": 1, "max_attempts": 2})
        run = store.register(self.fx.spec())
        for body in ("{", "[]"):
            damage(store, body)
            before = rows(store)
            with self.assertRaises(RunIntegrityError):
                store.register(self.fx.spec("r2"))
            self.assertEqual(rows(store), before)
        damage(store, canonical(run))
        with self.assertRaisesRegex(ValueError, "observe or recover existing run r1"):
            store.register(self.fx.spec("r2"))

    def test_writer_spellings_and_optional_policy_aliases_remain_compatible(self):
        store = self.fx.store
        run = store.register(self.fx.spec())
        # Optional aliases and policy fields do not become new required state.
        legacy = {key: value for key, value in run.items() if key not in {"run_id", "run_status"}}
        legacy["note"] = "Δ résumé 😀"
        for body in (canonical(legacy), json.dumps(legacy, ensure_ascii=True, indent=1)):
            damage(store, body)
            before = rows(store)
            self.assertEqual(store.snapshot()["runs"], [legacy])
            self.assertEqual(store.recover("r1")["attempt_id"], None)
            self.assertEqual(rows(store), before)
        result = store.execute("r1")
        self.assertEqual(result["run_status"], "SUCCEEDED", result)
        self.assertEqual(store.recover("r1"), result)


class ProjectRunIntegrityClaimTests(unittest.TestCase):
    def setUp(self):
        self.fx = base.StopPolicyAndMaintenanceTests("test_maintenance_allowance_admits_declared_runs_and_is_exhausted")
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.store = self.fx.contract_with(maintenance_allowance={"schema": 1, "wall_seconds": 16, "max_uses": 4})
        self.first = self.fx.run_spec(self.fx.spec("r1", timeout=0.25, maintenance=True))
        self.retained = self.store.snapshot()["runs"][0]
        self.store.register(self.fx.spec("r2", timeout=0.25, maintenance=True))
        self.attempt = "a" * 32
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            run = self.store._run(db, "r2")
            run.update(attempt_id=self.attempt, worker_pid=os.getpid())
            self.store._save(db, run)

    def test_bad_prior_run_never_becomes_a_failed_claim_and_same_attempt_continues(self):
        store = self.store
        for name, body in invalid_bodies(self.retained).items():
            damage(store, body)
            before = rows(store)
            with self.subTest(body=name):
                with self.assertRaisesRegex(RunIntegrityError, "run 'r1' body"):
                    store._execute_claim("r2", self.attempt)
                self.assertEqual(rows(store), before)
        damage(store, canonical(self.retained))
        result = store._execute_claim("r2", self.attempt)
        # The synthetic command really times out: retain that original outcome,
        # not an integrity/admission failure manufactured before launch.
        self.assertTrue(result["process_started"], result)
        self.assertEqual(result["attempt_id"], self.attempt)
        self.assertEqual(result["run_status"], "FAILED")
        self.assertIn("Process timeout", result["errors"])
        self.assertEqual(result["assessment"]["task_gain"], "UNKNOWN")
        before = rows(store)
        self.assertEqual(store.recover("r2"), result)
        self.assertEqual(store.recover("r2"), result)
        with self.assertRaisesRegex(ValueError, "already dispatched"):
            store.execute("r2")
        self.assertEqual(rows(store), before)
        state = store.snapshot()
        self.assertEqual(len(state["receipts"]), 2)
        self.assertEqual(len(state["exposures"]), 2)
        self.assertEqual(state["budget"]["cpu_seconds"]["charged_estimate"], 2)
        self.assertEqual(state["budget"]["cpu_seconds"]["reserved"], 0)
        with store._db(True) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE json_extract(body,'$.kind')="
                                       "'ATTEMPT_FINISHED' AND json_extract(body,'$.run_id')='r2'").fetchone()[0], 1)

    def test_late_corruption_before_settlement_retains_budget_and_attempt(self):
        store = self.store
        damage(store, "[]")
        before = rows(store)
        with self.assertRaises(RunIntegrityError):
            store._finish("r2", self.attempt, "FAILED", None, None, False, ["synthetic late settlement"])
        self.assertEqual(rows(store), before)

    def test_prelaunch_integrity_error_does_not_become_an_execution_failure(self):
        store = self.store
        check = store._check_start
        checks = 0
        baseline = rows(store)

        def corrupt_before_launch(db, run):
            nonlocal checks
            checks += 1
            if checks == 2:
                # Inject an external damage already committed at this boundary,
                # inside the fixture's current transaction without SQLite races.
                db.execute("UPDATE runs SET body='[]' WHERE id='r1'")
                db.commit()
                db.execute("BEGIN IMMEDIATE")
            return check(db, run)

        with patch.object(store, "_check_start", side_effect=corrupt_before_launch):
            with self.assertRaises(RunIntegrityError):
                store._execute_claim("r2", self.attempt)
        after = rows(store)
        self.assertEqual(after["budget"], baseline["budget"])
        self.assertEqual(after["receipts"], baseline["receipts"])
        self.assertEqual(len(after["exposures"]), len(baseline["exposures"]) + 1)
        damage(store, canonical(self.retained))
        with store._db() as db:
            run = store._run(db, "r2")
            self.assertEqual(run["attempt_id"], self.attempt)
            self.assertEqual(run["status"], "RUNNING")
            self.assertIsNone(run["pid"])
            # Simulate the failed controller having exited: recovery must retain
            # unknown outcome and costs rather than launch a replacement.
            run["worker_pid"] = None
            store._save(db, run)
        result = store.recover("r2")
        self.assertEqual(result["run_status"], "INTERRUPTED")
        self.assertIsNone(result["process_started"])
        self.assertEqual(result["attempt_id"], self.attempt)
        self.assertEqual(result["assessment"]["task_gain"], "UNKNOWN")
        before = rows(store)
        self.assertEqual(store.recover("r2"), result)
        self.assertEqual(rows(store), before)


if __name__ == "__main__":
    unittest.main()

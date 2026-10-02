"""A damaged project-ledger receipt row is a named rejection, never a crash or a result (#104).

Synthetic fixtures only: the receipts table is append-only by trigger, so each case
drops that guard to simulate a damaged or copied local ledger, as the existing
owned-completion test does.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_rds_project as base  # noqa: E402  (module import: its classes are not rediscovered here)
from rds_project import ProjectStore, canonical  # noqa: E402

CLI = Path(__file__).resolve().parents[1] / "scripts" / "rds_cli.py"


def damaged_bodies(receipt):
    other = {**receipt, "run_id": "r9"}
    resealed = {**receipt, "sha256": "0" * 64}
    return {"array": ("[]", "is a JSON array, not an object"),
            "null": ("null", "is a JSON null, not an object"),
            "string": ('"receipt"', "is a JSON string, not an object"),
            "number": ("3", "is a JSON number, not an object"),
            "boolean": ("true", "is a JSON boolean, not an object"),
            "malformed": ("{", "is not valid JSON"),
            "empty object": ("{}", "names a different run"),
            "other run": (canonical(other), "names a different run"),
            "sha256 mismatch": (canonical(resealed), "sha256 differs from its row")}


def ledger_rows(store):
    with sqlite3.connect(store.path) as db:
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                for table in ("budget", "runs", "receipts", "events", "exposures", "output_claims")}


def damage(store, run_id, body):
    with store._db() as db:
        db.execute("DROP TRIGGER IF EXISTS receipts_no_update")
        db.execute("UPDATE receipts SET body=? WHERE run_id=?", (body, run_id))


def cli(store, *argv):
    return subprocess.run([sys.executable, "-B", str(CLI), "--root", str(store.root), "project", *argv],
                          capture_output=True, text=True, timeout=60,
                          env={**os.environ, "RDS_USAGE_DB": str(store.root / "usage.sqlite3")})


class ProjectReceiptShapeCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = base.ProjectTests("test_execution_policy_is_opt_in_and_frozen")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def policy_store(self):
        store = self.fixture.new_store(policy={"schema": 1, "max_attempts": 2})
        store.register(self.fixture.spec())
        return store, store.execute("r1")

    def test_valid_receipt_reads_are_unchanged(self):
        store, receipt = self.policy_store()
        self.assertEqual(store.snapshot()["receipts"], [receipt])
        self.assertEqual(store.recover("r1"), receipt)
        observed = store.execute("r1")
        self.assertFalse(observed["execution_started"])
        self.assertEqual(observed["sha256"], receipt["sha256"])
        for argv in (["status", "--brief"], ["next"], ["recover", "--id", "r1"], ["execute", "--id", "r1"]):
            with self.subTest(argv=argv):
                result = cli(store, *argv)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("integrity failure", result.stderr)

    def test_damaged_receipt_is_a_named_rejection_on_every_project_read(self):
        store, receipt = self.policy_store()
        for name, (body, reason) in damaged_bodies(receipt).items():
            damage(store, "r1", body)
            before = ledger_rows(store)
            for argv in (["execute", "--id", "r1"], ["recover", "--id", "r1"], ["status", "--brief"], ["next"]):
                with self.subTest(body=name, argv=argv):
                    result = cli(store, *argv)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertIn("[RDS-REJECT] Project receipt integrity failure: run r1 body " + reason,
                                  result.stderr)
                    self.assertIn("inspect retained state", result.stderr)
                    # Rejected before anything is reserved, refunded, rerun or recorded as settled.
                    self.assertEqual(ledger_rows(store), before)
                    self.assertNotIn("execute run r1", result.stdout)

    def test_restoring_the_retained_body_restores_every_read(self):
        store, receipt = self.policy_store()
        damage(store, "r1", "[]")
        with self.assertRaisesRegex(ValueError, "Project receipt integrity failure"):
            store.snapshot()
        damage(store, "r1", canonical(receipt))
        self.assertEqual(store.snapshot()["receipts"], [receipt])
        self.assertEqual(store.recover("r1"), receipt)
        self.assertFalse(store.execute("r1")["execution_started"])


class ProjectReceiptShapeMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = base.StopPolicyAndMaintenanceTests("test_maintenance_allowance_admits_declared_runs_and_is_exhausted")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_maintenance_spend_rejects_a_damaged_prior_receipt_without_admitting(self):
        fx = self.fixture
        store = fx.contract_with(maintenance_allowance={"schema": 1, "wall_seconds": 16, "max_uses": 4})
        receipt = fx.run_spec(fx.spec("r1", timeout=0.25, maintenance=True))
        manifest = fx.root / "r2-manifest.json"
        manifest.write_text(canonical(fx.spec("r2", timeout=0.25, maintenance=True)), encoding="utf-8")
        for body in ("[]", "{}"):
            with self.subTest(body=body):
                damage(store, "r1", body)
                before = ledger_rows(store)
                result = cli(store, "create", "--manifest", str(manifest))
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("[RDS-REJECT] Project receipt integrity failure: run r1 body", result.stderr)
                self.assertEqual(ledger_rows(store), before)
        # The retained body restores admission; the prior maintenance cost is still counted.
        damage(store, "r1", canonical(receipt))
        result = cli(store, "create", "--manifest", str(manifest))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["id"], "r2")


if __name__ == "__main__":
    unittest.main()

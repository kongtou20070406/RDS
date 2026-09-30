import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_project import ProjectStore, canonical, digest, file_sha


SCRIPT = '''import json, pathlib, sys, time
mode, output = sys.argv[1:]
print("real project stdout", flush=True)
print("real project stderr", file=sys.stderr, flush=True)
if mode == "timeout": time.sleep(3)
if mode == "nonzero": sys.exit(7)
if mode.startswith("mutate-"):
    pathlib.Path(mode[7:]+".json").write_text('{"changed":true}')
if mode != "missing":
    rows = json.loads(pathlib.Path("data.json").read_text())
    pathlib.Path(output).write_text(json.dumps({"mean":sum(rows)/len(rows),"n":len(rows)}))
'''


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rds project ")
        self.root = Path(self.tmp.name)
        files = {"code": ("code.py", SCRIPT), "config": ("config.json", "{}"),
                 "data": ("data.json", "[1,2,3]"), "evaluator": ("evaluator.json", "{}")}
        for name, content in files.values():
            (self.root / name).write_text(content, encoding="utf-8")
        protocol = {"code_sha256": file_sha(self.root / "code.py"), "config_sha256": file_sha(self.root / "config.json"),
                    "data_sha256": file_sha(self.root / "data.json"), "data_split": "development-only",
                    "init": "none", "seed": 0, "checkpoint": "none", "schedule": "one calculation",
                    "sample_work": {"rows": 3}, "numeric_protocol": "Python float"}
        (self.root / "protocol.json").write_text(json.dumps(protocol), encoding="utf-8")
        files["protocol"] = ("protocol.json", "")
        self.contract = {"schema": 1, "bindings": [{"role": role, "path": name, "sha256": file_sha(self.root / name)}
                                                  for role, (name, _) in files.items()],
                         "allowed_commands": [[sys.executable, "-B", "code.py", mode, f"outputs/{rid}.json"]
                                              for rid in ("r1", "r2", "r3")
                                              for mode in ("ok", "missing", "nonzero", "timeout", "mutate-evaluator", "mutate-protocol")],
                         "output_roots": ["outputs"], "budget": {"wall_seconds": 20, "cpu_seconds": 10, "gpu_seconds": 0}}
        self.store = ProjectStore(self.root)
        self.store.initialize(self.contract)

    def tearDown(self):
        self.tmp.cleanup()

    def spec(self, rid="r1", mode="ok", timeout=2):
        return {"schema": 1, "id": rid, "arm": "control", "control_id": None,
                "protocol": {"path": "protocol.json", "sha256": file_sha(self.root / "protocol.json")},
                "argv": [sys.executable, "-B", "code.py", mode, f"outputs/{rid}.json"],
                "outpaths": [f"outputs/{rid}.json"], "resource_estimates": {"wall_seconds": timeout + 0.2, "cpu_seconds": 1, "gpu_seconds": 0},
                "timeout_seconds": timeout}

    def run_spec(self, spec):
        self.store.register(spec)
        return self.store.execute(spec["id"])

    def test_real_success_receipt_and_distinct_costs(self):
        receipt = self.run_spec(self.spec())
        self.assertEqual(receipt["run_status"], "SUCCEEDED")
        self.assertEqual(receipt["process_status"], "COMPLETED")
        self.assertEqual(json.loads((self.root / "outputs/r1.json").read_text()), {"mean": 2.0, "n": 3})
        self.assertEqual(receipt["assessment"], {"task_gain": "UNKNOWN", "mechanism": "UNKNOWN"})
        self.assertGreater(receipt["resources"]["wall_seconds"]["measured"], 0)
        self.assertIsNone(receipt["resources"]["cpu_seconds"]["measured"])
        self.assertEqual(receipt["resources"]["cpu_seconds"]["charged_estimate"], 1)
        self.assertEqual(receipt["sha256"], digest({k: v for k, v in receipt.items() if k != "sha256"}))
        for artifact in receipt["artifacts"]:
            self.assertEqual(file_sha(self.root / artifact["path"]), artifact["sha256"])
        snap = self.store.snapshot()
        self.assertEqual(snap["runs"][0]["status"], "COMPLETED")
        self.assertEqual(snap["runs"][0]["run_status"], "SUCCEEDED")
        self.assertEqual(snap["budget"]["cpu_seconds"]["charged_estimate"], 1)
        self.assertEqual(snap["budget"]["wall_seconds"]["reserved"], 0)
        self.assertEqual(len(snap["exposures"]), 1)

    def test_exit_zero_missing_artifact_is_failure(self):
        receipt = self.run_spec(self.spec(mode="missing"))
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(receipt["run_status"], "FAILED")
        self.assertTrue(any("Missing output" in err for err in receipt["errors"]))

    def test_protocol_and_evaluator_drift_are_failures(self):
        for mode in ("mutate-evaluator", "mutate-protocol"):
            with self.subTest(mode=mode):
                saved = (self.root / (mode[7:] + ".json")).read_bytes()
                rid = "r1" if mode == "mutate-evaluator" else "r2"
                receipt = self.run_spec(self.spec(rid, mode))
                self.assertEqual(receipt["exit_code"], 0)
                self.assertEqual(receipt["run_status"], "FAILED")
                self.assertNotEqual(receipt["bindings_before"], receipt["bindings_after"])
                (self.root / (mode[7:] + ".json")).write_bytes(saved)

    def test_binding_drift_before_start_does_not_launch(self):
        self.store.register(self.spec())
        (self.root / "config.json").write_text('{"changed":true}')
        receipt = self.store.execute("r1")
        self.assertFalse(receipt["process_started"])
        self.assertEqual(receipt["run_status"], "FAILED")
        self.assertFalse((self.root / "outputs/r1.json").exists())
        self.assertEqual(self.store.snapshot()["budget"]["cpu_seconds"]["charged_estimate"], 1)
        self.assertIsNone(receipt["resources"]["cpu_seconds"]["measured"])

    def test_nonzero_and_timeout_keep_costs(self):
        failed = self.run_spec(self.spec("r1", "nonzero"))
        timed = self.run_spec(self.spec("r2", "timeout", 0.15))
        self.assertEqual(failed["exit_code"], 7)
        self.assertEqual(timed["run_status"], "FAILED")
        self.assertTrue(timed["timeout"])
        self.assertGreater(failed["resources"]["wall_seconds"]["measured"], 0)
        self.assertGreater(timed["resources"]["wall_seconds"]["measured"], 0)
        self.assertEqual(self.store.snapshot()["budget"]["cpu_seconds"]["charged_estimate"], 2)

    def test_append_only_receipts_and_exposures(self):
        self.run_spec(self.spec())
        with self.store._db() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE receipts SET body='{}'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM exposures")

    def test_duplicate_run_pending_and_terminal_never_restart(self):
        self.store.register(self.spec())
        with self.assertRaises(ValueError):
            self.store.register(self.spec())
        pending = self.store.recover("r1")
        self.assertEqual(pending["status"], "RESERVED")
        original = self.store.execute("r1")
        with self.assertRaises(ValueError):
            self.store.execute("r1")
        self.assertEqual(self.store.recover("r1")["sha256"], original["sha256"])
        with self.assertRaises(ValueError):
            self.store.recover("missing")

    def test_interrupted_recovery_preserves_unknown_cost_and_no_rerun(self):
        self.store.register(self.spec())
        with self.store._db() as db:
            run = self.store._run(db, "r1")
            run.update(status="RUNNING", attempt_id="lost-attempt", worker_pid=None, pid=None,
                       started_at=time.time() - 2, observed_wall_seconds=0.3)
            self.store._save(db, run)
        receipt = self.store.recover("r1")
        self.assertEqual(receipt["run_status"], "INTERRUPTED")
        self.assertIsNone(receipt["resources"]["wall_seconds"]["measured"])
        self.assertEqual(receipt["resources"]["wall_seconds"]["charged_estimate"], 2.2)
        self.assertEqual(receipt["resources"]["wall_seconds"]["observed_lower_bound"], 0.3)
        with self.assertRaises(ValueError):
            self.store.execute("r1")
        self.assertFalse((self.root / "outputs/r1.json").exists())

    def test_recover_does_not_stop_live_or_foreign_process(self):
        self.store.register(self.spec())
        with self.store._db() as db:
            run = self.store._run(db, "r1")
            run.update(status="RUNNING", attempt_id="live", worker_pid=os.getpid())
            self.store._save(db, run)
        self.assertEqual(self.store.recover("r1")["status"], "RUNNING")
        self.assertEqual(self.store.snapshot()["budget"]["cpu_seconds"]["reserved"], 1)

    def test_atomic_budget_vector_and_dimension_limits(self):
        self.contract["budget"]["wall_seconds"] = 3
        # A frozen contract cannot be reset to a larger or smaller budget.
        with self.assertRaises(ValueError):
            self.store.initialize(self.contract)
        with self.store._db() as db:
            db.execute("UPDATE budget SET cap=3 WHERE resource='wall_seconds'")
        def reserve(rid):
            try:
                self.store.register(self.spec(rid))
                return True
            except ValueError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, ["r1", "r2"]))
        self.assertEqual(sum(results), 1)
        self.assertAlmostEqual(self.store.snapshot()["budget"]["wall_seconds"]["reserved"], 2.2)
        other = self.spec("r3")
        other["resource_estimates"]["gpu_seconds"] = 0.01
        with self.assertRaises(ValueError):
            self.store.register(other)

    def test_paths_commands_and_handwritten_verification_rejected(self):
        for edit in ({"outpaths": ["../escape.json"]}, {"outpaths": [str(self.root.parent / "escape.json")]},
                     {"argv": [sys.executable, "-c", "print('unauthorized')"]}, {"verified": True},
                     {"timeout_seconds": float("nan")}, {"timeout_seconds": True}, {"schema": True}):
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.store.register({**self.spec(), **edit})
        with self.assertRaises(ValueError):
            ProjectStore._command(["cmd.exe" if os.name == "nt" else "/bin/sh", "-c", "echo test"])

    def test_protocol_identity_must_match_real_bindings(self):
        protocol = json.loads((self.root / "protocol.json").read_text())
        protocol["data_sha256"] = "0" * 64
        (self.root / "protocol.json").write_text(json.dumps(protocol))
        # Even updating its declared hash cannot make conflicting data identities valid.
        for b in self.contract["bindings"]:
            if b["role"] == "protocol":
                b["sha256"] = file_sha(self.root / "protocol.json")
        with self.store._db() as db:
            # New test store so no frozen contract is modified.
            pass
        with tempfile.TemporaryDirectory(prefix="rds identity ") as other:
            import shutil
            for path in self.root.iterdir():
                if path.is_file():
                    shutil.copyfile(path, Path(other) / path.name)
            other_store = ProjectStore(other)
            other_store.initialize(self.contract)
            with self.assertRaises(ValueError):
                other_store.register(self.spec())

    def test_existing_output_cannot_supply_stale_success(self):
        (self.root / "outputs").mkdir()
        (self.root / "outputs/r1.json").write_text('{}')
        with self.assertRaises(ValueError):
            self.store.register(self.spec())

    def test_readonly_snapshot_preserves_budget_and_receipts(self):
        self.store.register(self.spec())
        first = self.store.snapshot()
        self.assertEqual(first, self.store.snapshot())
        with self.store._db(True) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("UPDATE budget SET cap=1000")

    def test_snapshot_hashes_only_on_explicit_binding_check(self):
        with patch.object(self.store, "_bindings", wraps=self.store._bindings) as check:
            self.store.snapshot()
            check.assert_not_called()
            (self.root / "config.json").write_text('{"changed":true}')
            checked = self.store.snapshot(check_bindings=True)
            self.assertTrue(checked["binding_check"]["errors"])
            self.assertEqual(check.call_count, 1)

    def test_duplicate_file_roles_hash_once_per_boundary(self):
        contract = {**self.contract, "bindings": [*self.contract["bindings"],
                    {"path": "code.py", "role": "evaluator", "sha256": file_sha(self.root / "code.py")} ]}
        with patch("rds_project.file_sha", wraps=file_sha) as hashed:
            files, errors = self.store._bindings(contract)
        self.assertFalse(errors)
        self.assertEqual(hashed.call_count, 5)
        self.assertEqual(len(files), 6)

    @unittest.skipUnless(os.name == "nt", "Windows scheduler dispatch guard")
    def test_scheduler_failure_is_recorded_and_never_restarted(self):
        self.store.register(self.spec())
        with patch.object(self.store, "_schedule", side_effect=OSError("recorded denial")):
            receipt = self.store.execute("r1", background=True)
        self.assertEqual(receipt["run_status"], "FAILED")
        self.assertEqual(receipt["scheduler"]["task_id"].split("-")[:2], ["RDS", "Project"])
        with self.assertRaises(ValueError):
            self.store.execute("r1", background=True)

    @unittest.skipUnless(os.name == "nt", "Windows scheduler dispatch race")
    def test_dispatch_error_cannot_close_an_already_claimed_worker(self):
        self.store.register(self.spec())
        def partial_dispatch(run):
            with self.store._db() as db:
                current = self.store._run(db, run["id"])
                current.update(status="RUNNING", worker_pid=os.getpid())
                self.store._save(db, current)
            raise OSError("Controller failed after worker claimed attempt")
        with patch.object(self.store, "_schedule", side_effect=partial_dispatch):
            state = self.store.execute("r1", background=True)
        self.assertEqual(state["status"], "RUNNING")
        self.assertFalse(self.store.snapshot()["receipts"])
        self.assertEqual(self.store.snapshot()["budget"]["cpu_seconds"]["reserved"], 1)
        with self.assertRaises(ValueError):
            self.store.execute("r1", background=True)

    def test_nonwindows_background_is_explicitly_unsupported(self):
        self.store.register(self.spec())
        with patch("rds_project.os.name", "posix"):
            with self.assertRaises(NotImplementedError):
                self.store.execute("r1", background=True)
        self.assertIsNone(self.store.snapshot()["runs"][0]["attempt_id"])


if __name__ == "__main__":
    unittest.main()

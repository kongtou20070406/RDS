import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
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

    def new_store(self, budget=None, commands=()):
        root = self.root / "other-project"
        root.mkdir()
        for binding in self.contract["bindings"]:
            shutil.copyfile(self.root / binding["path"], root / binding["path"])
        contract = json.loads(canonical(self.contract))
        if budget is not None:
            contract["budget"] = budget
        contract["allowed_commands"].extend(commands)
        store = ProjectStore(root)
        store.initialize(contract)
        return store

    def reserve_overrun_pair(self):
        store = self.new_store({"wall_seconds": 0.002, "cpu_seconds": 2, "gpu_seconds": 0})
        for rid in ("r1", "r2"):
            spec = self.spec(rid, "timeout", 0.001)
            spec["resource_estimates"]["wall_seconds"] = 0.001
            store.register(spec)
        return store

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

    def test_recover_during_foreground_startup_preserves_reservation(self):
        self.store.register(self.spec())
        claimed, resume = threading.Event(), threading.Event()
        execute_claim = self.store._execute_claim

        def pause_claim(run_id, attempt_id):
            claimed.set()
            self.assertTrue(resume.wait(5))
            return execute_claim(run_id, attempt_id)

        with patch.object(self.store, "_execute_claim", side_effect=pause_claim), \
                concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            execution = pool.submit(self.store.execute, "r1")
            try:
                self.assertTrue(claimed.wait(5))
                recovered = self.store.recover("r1")
                self.assertEqual(recovered.get("status"), "RESERVED")
                self.assertEqual(recovered["worker_pid"], os.getpid())
                snapshot = self.store.snapshot()
                self.assertFalse(snapshot["receipts"])
                self.assertEqual(snapshot["budget"]["cpu_seconds"]["reserved"], 1)
                with self.assertRaises(ValueError):
                    self.store.execute("r1")
            finally:
                resume.set()
            receipt = execution.result(timeout=5)
        self.assertEqual(receipt["run_status"], "SUCCEEDED")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(self.store.snapshot()["budget"]["cpu_seconds"]["charged_estimate"], 1)

    def test_stale_recovery_cannot_settle_a_newly_claimed_worker(self):
        # An existing reservation may predate foreground controller identity.
        self.store.register(self.spec())
        with self.store._db() as db:
            run = self.store._run(db, "r1")
            run["attempt_id"] = "pending-attempt"
            self.store._save(db, run)
        recovering, claimed = threading.Event(), threading.Event()
        resume_recovery, resume_execution = threading.Event(), threading.Event()
        bindings = self.store._bindings

        def pause_bindings(contract):
            if threading.current_thread().name.startswith("recover"):
                recovering.set()
                self.assertTrue(resume_recovery.wait(5))
            else:
                claimed.set()
                self.assertTrue(resume_execution.wait(5))
            return bindings(contract)

        with patch.object(self.store, "_bindings", side_effect=pause_bindings), \
                concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="recover") as recovery_pool, \
                concurrent.futures.ThreadPoolExecutor(max_workers=1) as execution_pool:
            recovery = recovery_pool.submit(self.store.recover, "r1")
            try:
                self.assertTrue(recovering.wait(5))
                execution = execution_pool.submit(self.store._execute_claim, "r1", "pending-attempt")
                self.assertTrue(claimed.wait(5))
                resume_recovery.set()
                state = recovery.result(timeout=5)
                self.assertEqual(state.get("status"), "RUNNING")
                self.assertEqual(state["worker_pid"], os.getpid())
                self.assertFalse(self.store.snapshot()["receipts"])
                self.assertEqual(self.store.snapshot()["budget"]["cpu_seconds"]["reserved"], 1)
            finally:
                resume_recovery.set()
                resume_execution.set()
            receipt = execution.result(timeout=5)
        self.assertEqual(receipt["run_status"], "SUCCEEDED")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(len(self.store.snapshot()["exposures"]), 1)
        self.assertEqual(self.store.snapshot()["budget"]["cpu_seconds"]["charged_estimate"], 1)

    def test_stale_recovery_returns_normal_receipt_without_double_settlement(self):
        self.store.register(self.spec())
        with self.store._db() as db:
            run = self.store._run(db, "r1")
            run["attempt_id"] = "pending-attempt"
            self.store._save(db, run)
        recovering, resume = threading.Event(), threading.Event()
        bindings = self.store._bindings

        def pause_bindings(contract):
            if threading.current_thread().name.startswith("recover"):
                recovering.set()
                self.assertTrue(resume.wait(5))
            return bindings(contract)

        with patch.object(self.store, "_bindings", side_effect=pause_bindings), \
                concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="recover") as pool:
            recovery = pool.submit(self.store.recover, "r1")
            try:
                self.assertTrue(recovering.wait(5))
                receipt = self.store._execute_claim("r1", "pending-attempt")
                budget = self.store.snapshot()["budget"]
            finally:
                resume.set()
            self.assertEqual(recovery.result(timeout=5), receipt)
        snapshot = self.store.snapshot()
        self.assertEqual(receipt["run_status"], "SUCCEEDED")
        self.assertEqual(snapshot["budget"], budget)
        self.assertEqual(len(snapshot["receipts"]), 1)
        self.assertEqual(len(snapshot["exposures"]), 1)
        with self.assertRaises(ValueError):
            self.store.execute("r1")

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

    def test_start_uses_existing_reservation_without_double_counting(self):
        store = self.new_store({"wall_seconds": 4.4, "cpu_seconds": 2, "gpu_seconds": 0})
        store.register(self.spec("r1"))
        store.register(self.spec("r2"))
        self.assertAlmostEqual(store.snapshot()["budget"]["wall_seconds"]["remaining"], 0)
        self.assertEqual(store.execute("r1")["run_status"], "SUCCEEDED")
        self.assertEqual(store.execute("r2")["run_status"], "SUCCEEDED")

    def test_real_overrun_blocks_reserved_dispatch_and_preserves_charges(self):
        store = self.reserve_overrun_pair()
        receipt = store.execute("r1")
        self.assertTrue(receipt["process_started"])
        self.assertTrue(receipt["timeout"])
        self.assertGreater(receipt["resources"]["wall_seconds"]["measured"], 0.002)
        before = store.snapshot()
        self.assertLess(before["budget"]["wall_seconds"]["remaining"], 0)
        for background in ([False, True] if os.name == "nt" else [False]):
            with self.subTest(background=background), patch.object(store, "_schedule") as schedule:
                with self.assertRaisesRegex(ValueError, "Insufficient wall_seconds budget before start"):
                    store.execute("r2", background=background)
                schedule.assert_not_called()
        after = store.snapshot()
        self.assertEqual(before["budget"], after["budget"])
        self.assertEqual(before["receipts"], after["receipts"])
        pending = next(run for run in after["runs"] if run["id"] == "r2")
        self.assertEqual(pending["status"], "RESERVED")
        self.assertIsNone(pending["attempt_id"])
        self.assertFalse((store.root / "outputs/r2.json").exists())

    def test_queued_worker_rechecks_budget_after_another_run_overruns(self):
        store = self.reserve_overrun_pair()
        with store._db() as db:
            run = store._run(db, "r2")
            run["attempt_id"] = "queued-attempt"
            run["scheduler"] = {"task_id": "RDS-Project-queued", "status": "REGISTERED"}
            store._save(db, run)
        store.execute("r1")
        before = store.snapshot()
        with self.assertRaisesRegex(ValueError, "Insufficient wall_seconds budget before start"):
            store._execute_claim("r2", "queued-attempt")
        self.assertEqual(before, store.snapshot())
        self.assertEqual(store.recover("r2")["status"], "RESERVED")
        with self.assertRaises(ValueError):
            store.execute("r2")

    def test_overrun_during_preflight_blocks_popen_and_retains_failure_cost(self):
        store = self.reserve_overrun_pair()
        preflight, resume = threading.Event(), threading.Event()
        bindings = store._bindings

        def pause_bindings(contract):
            if threading.current_thread().name.startswith("pending") and not preflight.is_set():
                preflight.set()
                self.assertTrue(resume.wait(5))
            return bindings(contract)

        with patch.object(store, "_bindings", side_effect=pause_bindings), \
                concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="pending") as pool:
            execution = pool.submit(store.execute, "r2")
            try:
                self.assertTrue(preflight.wait(5))
                first = store.execute("r1")
                self.assertTrue(first["process_started"])
                self.assertLess(store.snapshot()["budget"]["wall_seconds"]["remaining"], 0)
            finally:
                resume.set()
            receipt = execution.result(timeout=5)
        self.assertFalse(receipt["process_started"])
        self.assertEqual(receipt["run_status"], "FAILED")
        self.assertTrue(any("Insufficient wall_seconds budget before start" in error for error in receipt["errors"]))
        self.assertFalse((store.root / "outputs/r2.json").exists())
        budget = store.snapshot()["budget"]
        self.assertEqual(budget["cpu_seconds"]["charged_estimate"], 2)
        self.assertEqual(budget["cpu_seconds"]["reserved"], 0)
        with self.assertRaises(ValueError):
            store.execute("r2")

    def test_legacy_relative_output_claim_is_same_as_absolute_claim(self):
        self.store.register(self.spec())
        with self.store._db() as db:
            db.execute("UPDATE output_claims SET path='outputs/./r1.json' WHERE run_id='r1'")
        self.assertEqual(self.store._output_key("outputs/./r1.json"),
                         self.store._output_key(self.root / "outputs/r1.json"))
        self.assertEqual(self.store.execute("r1")["run_status"], "SUCCEEDED")

    @unittest.skipUnless(os.name == "nt", "Windows physical output aliases")
    def test_windows_output_alias_cannot_claim_legacy_absolute_path(self):
        argv = [sys.executable, "-B", "code.py", "ok", "outputs/R1.json"]
        store = self.new_store(commands=[argv])
        store.register(self.spec("r1"))
        with store._db() as db:
            db.execute("UPDATE output_claims SET path=? WHERE run_id='r1'",
                       (str(store.root / "outputs/r1.json"),))
        spec = self.spec("r2")
        spec.update(argv=argv, outpaths=["outputs/./R1.json"])
        before = store.snapshot()
        with self.assertRaisesRegex(ValueError, "Output is already claimed"):
            store.register(spec)
        self.assertEqual(before, store.snapshot())
        self.assertEqual(store.execute("r1")["run_status"], "SUCCEEDED")
        self.assertTrue((store.root / "outputs/R1.json").samefile(store.root / "outputs/r1.json"))

    @unittest.skipUnless(os.name == "nt", "Existing Windows ledger aliases")
    def test_legacy_conflicting_windows_claims_block_controller_and_worker(self):
        argv = [sys.executable, "-B", "code.py", "ok", "outputs/R1.json"]
        store = self.new_store(commands=[argv])
        store.register(self.spec("r1"))
        store.register(self.spec("r2"))
        # Reproduce the two raw, case-distinct keys admitted by the old runner.
        with store._db() as db:
            run = store._run(db, "r2")
            run["manifest"].update(argv=argv, outpaths=["outputs/R1.json"])
            run["manifest_sha256"] = digest(run["manifest"])
            store._save(db, run)
            db.execute("UPDATE output_claims SET path=? WHERE run_id='r1'",
                       (str(store.root / "outputs/r1.json"),))
            db.execute("UPDATE output_claims SET path=? WHERE run_id='r2'",
                       (str(store.root / "outputs/R1.json"),))
        before = store.snapshot()
        with self.assertRaisesRegex(ValueError, "not exclusively claimed"):
            store.execute("r1")
        with patch.object(store, "_schedule") as schedule:
            with self.assertRaisesRegex(ValueError, "not exclusively claimed"):
                store.execute("r2", background=True)
            schedule.assert_not_called()
        self.assertEqual(before, store.snapshot())
        with store._db() as db:
            run = store._run(db, "r2")
            run["attempt_id"] = "legacy-queued"
            run["scheduler"] = {"task_id": "RDS-Project-legacy", "status": "REGISTERED"}
            store._save(db, run)
        before = store.snapshot()
        with self.assertRaisesRegex(ValueError, "not exclusively claimed"):
            store._execute_claim("r2", "legacy-queued")
        self.assertEqual(before, store.snapshot())

    @unittest.skipUnless(os.name == "nt", "Windows strips output suffix dots/spaces")
    def test_windows_suffix_aliases_cannot_get_two_success_receipts(self):
        aliases = ["outputs/r1.json.", "outputs/r1.json ", "outputs/r1.json. ",
                   "outputs./r1.json", "outputs /r1.json", "outputs. /r1.json"]
        commands = [[sys.executable, "-B", "code.py", "ok", path] for path in aliases]
        store = self.new_store(commands=commands)
        store.register(self.spec("r1"))
        before = store.snapshot()
        for path, argv in zip(aliases, commands):
            with self.subTest(path=path):
                spec = self.spec("r2")
                spec.update(argv=argv, outpaths=[path])
                with self.assertRaisesRegex(ValueError, "Windows output path components"):
                    store.register(spec)
                self.assertEqual(before, store.snapshot())
        receipt = store.execute("r1")
        self.assertEqual(receipt["run_status"], "SUCCEEDED")
        for path in aliases[:4]:
            self.assertTrue((store.root / path).samefile(store.root / "outputs/r1.json"))
        self.assertEqual(len(store.snapshot()["runs"]), 1)
        self.assertEqual(len(store.snapshot()["exposures"]), 1)

    @unittest.skipUnless(os.name == "nt", "Legacy Win32 output suffix aliases")
    def test_windows_legacy_suffix_key_normalizes_before_file_creation(self):
        self.store.register(self.spec("r1"))
        legacy = "outputs././r1.json. "
        self.assertFalse((self.root / "outputs/r1.json").exists())
        self.assertEqual(self.store._output_key(legacy), self.store._output_key("outputs/r1.json"))
        self.assertEqual(self.store._output_key(self.root / legacy), self.store._output_key("outputs/r1.json"))
        with self.store._db() as db:
            db.execute("UPDATE output_claims SET path=? WHERE run_id='r1'", (legacy,))
        self.assertEqual(self.store.execute("r1")["run_status"], "SUCCEEDED")
        self.assertTrue((self.root / legacy).samefile(self.root / "outputs/r1.json"))

    @unittest.skipUnless(os.name == "nt", "Legacy Win32 suffix ownership conflict")
    def test_windows_legacy_suffix_owners_block_controller_scheduler_and_worker(self):
        self.store.register(self.spec("r1"))
        self.store.register(self.spec("r2"))
        with self.store._db() as db:
            db.execute("UPDATE output_claims SET path=? WHERE run_id='r2'", (str(self.root / "outputs. /r1.json. "),))
        before = self.store.snapshot()
        with self.assertRaisesRegex(ValueError, "not exclusively claimed"):
            self.store.execute("r1")
        with patch.object(self.store, "_schedule") as schedule:
            with self.assertRaisesRegex(ValueError, "not exclusively claimed"):
                self.store.execute("r1", background=True)
            schedule.assert_not_called()
        self.assertEqual(before, self.store.snapshot())
        with self.store._db() as db:
            run = self.store._run(db, "r1")
            run.update(attempt_id="legacy-queued", scheduler={"task_id": "RDS-Project-legacy", "status": "REGISTERED"})
            self.store._save(db, run)
        before = self.store.snapshot()
        with self.assertRaisesRegex(ValueError, "not exclusively claimed"):
            self.store._execute_claim("r1", "legacy-queued")
        self.assertEqual(before, self.store.snapshot())
        self.assertFalse((self.root / "outputs/r1.json").exists())

    @unittest.skipUnless(os.name == "nt", "Old Windows suffix manifests")
    def test_windows_legacy_suffix_manifest_cannot_dispatch(self):
        self.store.register(self.spec("r1"))
        with self.store._db() as db:
            run = self.store._run(db, "r1")
            run["manifest"]["outpaths"] = ["outputs/r1.json. "]
            run["manifest_sha256"] = digest(run["manifest"])
            self.store._save(db, run)
        before = self.store.snapshot()
        with self.assertRaisesRegex(ValueError, "Windows output path components"):
            self.store.execute("r1")
        self.assertEqual(before, self.store.snapshot())

    @unittest.skipUnless(os.name != "nt", "POSIX suffix names are distinct files")
    def test_posix_suffix_outputs_remain_independent(self):
        aliases = ["outputs/r1.json.", "outputs/r1.json "]
        commands = [[sys.executable, "-B", "code.py", "ok", path] for path in aliases]
        store = self.new_store(commands=commands)
        store.register(self.spec("r1"))
        for rid, path, argv in zip(("r2", "r3"), aliases, commands):
            spec = self.spec(rid)
            spec.update(argv=argv, outpaths=[path])
            store.register(spec)
        for rid in ("r1", "r2", "r3"):
            self.assertEqual(store.execute(rid)["run_status"], "SUCCEEDED")
        for path in aliases:
            self.assertFalse((store.root / path).samefile(store.root / "outputs/r1.json"))

    @unittest.skipUnless(os.name != "nt", "Native case-distinct output paths")
    def test_case_distinct_outputs_remain_independent_on_posix(self):
        argv = [sys.executable, "-B", "code.py", "ok", "outputs/R1.json"]
        store = self.new_store(commands=[argv])
        store.register(self.spec("r1"))
        spec = self.spec("r2")
        spec.update(argv=argv, outpaths=["outputs/R1.json"])
        store.register(spec)
        self.assertEqual(store.execute("r1")["run_status"], "SUCCEEDED")
        self.assertEqual(store.execute("r2")["run_status"], "SUCCEEDED")
        self.assertFalse((store.root / "outputs/R1.json").samefile(store.root / "outputs/r1.json"))

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
        self.assertEqual(receipt["scheduler"]["status"], "FAILED")
        self.assertEqual(self.store.snapshot()["runs"][0]["scheduler"], receipt["scheduler"])
        with self.assertRaises(ValueError):
            self.store.execute("r1", background=True)

    @unittest.skipUnless(os.name == "nt", "Windows scheduler dispatch race")
    def test_dispatch_error_cannot_close_an_already_claimed_worker(self):
        self.store.register(self.spec())
        def partial_dispatch(run):
            with self.store._db() as db:
                current = self.store._run(db, run["id"])
                current.update(status="RUNNING", worker_pid=os.getpid())
                current["scheduler"]["status"] = "RUNNING"
                self.store._save(db, current)
            raise OSError("Controller failed after worker claimed attempt")
        with patch.object(self.store, "_schedule", side_effect=partial_dispatch):
            state = self.store.execute("r1", background=True)
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["scheduler"]["status"], "RUNNING")
        self.assertFalse(self.store.snapshot()["receipts"])
        self.assertEqual(self.store.snapshot()["budget"]["cpu_seconds"]["reserved"], 1)
        with self.assertRaises(ValueError):
            self.store.execute("r1", background=True)

    def test_scheduled_worker_completion_records_terminal_lifecycle(self):
        # Start the same worker path without requiring an OS scheduler in CI.
        for rid, mode, terminal in (("r1", "ok", "COMPLETED"), ("r2", "nonzero", "FAILED")):
            with self.subTest(mode=mode):
                self.store.register(self.spec(rid, mode))
                task_id = "RDS-Project-" + rid
                with self.store._db() as db:
                    run = self.store._run(db, rid)
                    run["attempt_id"] = rid
                    run["scheduler"] = {"task_id": task_id, "status": "REGISTERED"}
                    self.store._save(db, run)
                receipt = self.store._execute_claim(rid, rid)
                scheduler = {"task_id": task_id, "status": terminal}
                self.assertEqual(receipt["scheduler"], scheduler)
                live = next(r for r in self.store.snapshot()["runs"] if r["id"] == rid)
                self.assertEqual(live["status"], terminal)
                self.assertEqual(live["scheduler"], scheduler)
                self.assertEqual(receipt["sha256"], digest({k:v for k,v in receipt.items() if k!="sha256"}))

    def test_nonwindows_background_is_explicitly_unsupported(self):
        self.store.register(self.spec())
        with patch("rds_project.os.name", "posix"):
            with self.assertRaises(NotImplementedError):
                self.store.execute("r1", background=True)
        self.assertIsNone(self.store.snapshot()["runs"][0]["attempt_id"])


if __name__ == "__main__":
    unittest.main()

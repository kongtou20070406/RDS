import copy
from contextlib import closing
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_checkpoints import restore_checkpoint, save_checkpoint

ROOT = Path(__file__).resolve().parents[1]


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".rds").mkdir()
        self.db = self.root / ".rds" / "project.sqlite3"
        sqlite3.connect(self.db).close()
        self.state = {"contract": {"project_id": "study", "data_sha256": "a"},
                      "budget": {"wall_seconds": {"cap": 10, "reserved": 4, "spent_measured": 2, "remaining": 4}},
                      "exposures": [{"split": "dev", "purpose": "select"}],
                      "runs": {"r1": {"status": "RESERVED"}}}

    def test_four_boundaries_preserve_live_cost_exposure_and_run_identity(self):
        for index, status in enumerate(("RESERVED", "RUNNING", "COMPLETED", "FAILED")):
            state = copy.deepcopy(self.state)
            state["runs"]["r1"]["status"] = status
            if status == "FAILED":
                state["budget"]["wall_seconds"]["remaining"] = 0
            save_checkpoint(self.root, f"c{index}", state, kind="project",
                            decision={"question": "What should follow this result?", "pending_evidence": ["original metrics"]})
            recovered = restore_checkpoint(self.root, f"c{index}", state, kind="project")
            self.assertEqual(recovered["status"], "RESUMABLE_HANDOFF")
            self.assertEqual(recovered["live_budget"], state["budget"])
            self.assertEqual(recovered["live_exposures"], state["exposures"])
            self.assertFalse(recovered["execution_started"])
            self.assertFalse(recovered["state_replaced"])

    def test_progress_does_not_restore_old_budget_or_reexecute_completed_run(self):
        save_checkpoint(self.root, "before", self.state, kind="project")
        live = copy.deepcopy(self.state)
        live["runs"]["r1"]["status"] = "COMPLETED"
        live["budget"]["wall_seconds"].update(reserved=0, spent_measured=6)
        result = restore_checkpoint(self.root, "before", live, kind="project")
        self.assertEqual(result["live_budget"], live["budget"])
        self.assertEqual(result["completed_runs"][0]["run_id"], "r1")
        self.assertIn("budget", [item["field"] for item in result["updates"]])

    def test_contract_drift_and_missing_run_are_conflicts(self):
        save_checkpoint(self.root, "frozen", self.state, kind="project")
        live = copy.deepcopy(self.state)
        live["contract"]["data_sha256"] = "different"
        live["runs"] = {}
        result = restore_checkpoint(self.root, "frozen", live, kind="project")
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual({item["field"] for item in result["conflicts"]}, {"contract", "runs"})

    def test_record_is_append_only_and_tampering_is_detected(self):
        save_checkpoint(self.root, "one", self.state, kind="project")
        with self.assertRaises(ValueError):
            save_checkpoint(self.root, "one", self.state, kind="project")
        with closing(sqlite3.connect(self.db)) as db, db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM checkpoints")
            db.execute("DROP TRIGGER checkpoint_no_update")
            db.execute("UPDATE checkpoints SET body='{}'")
        with self.assertRaisesRegex(ValueError, "integrity"):
            restore_checkpoint(self.root, "one", self.state, kind="project")

    def test_live_file_drift_cannot_be_hidden_by_unchanged_contract_body(self):
        save_checkpoint(self.root, "before-drift", self.state, kind="project")
        live = copy.deepcopy(self.state)
        live["binding_check"] = {"errors": ["Binding changed: evaluator.py"]}
        result = restore_checkpoint(self.root, "before-drift", live, kind="project")
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["conflicts"][0]["field"], "bindings")

    def test_reference_recovery_keeps_execution_and_plan_identity_separate(self):
        self.db.rename(self.root / ".rds/state.sqlite3")
        state = {"contract": self.state["contract"], "budget": {}, "plans": {
            "P1": {"run_id": "RUN-recorded", "run_status": "RESERVED"}}}
        save_checkpoint(self.root, "before-reference", state, kind="reference")
        for status, bucket in (("SUCCEEDED", "completed_runs"), ("RECOVERY_REQUIRED", "interrupted_runs")):
            state["plans"]["P1"]["run_status"] = status
            result = restore_checkpoint(self.root, "before-reference", state, kind="reference")
            self.assertEqual(result[bucket][0]["run_id"], "RUN-recorded")
            self.assertEqual(result[bucket][0]["plan_id"], "P1")
            self.assertFalse(result["execution_started"])


class ReferenceCheckpointCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for source in (ROOT / "examples/reference-run").iterdir():
            if source.is_file():
                shutil.copyfile(source, self.root / source.name)
        self.call("init", "--contract", self.root / "contract.json")
        self.call("hypothesis", "add", "--spec", self.root / "hypothesis.json")

    def call(self, *arguments, expected=0):
        process = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                                  "--root", str(self.root), *map(str, arguments)],
                                 cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(process.returncode, expected, process.stderr + process.stdout)
        return json.loads(process.stdout)

    def reserve(self):
        self.call("plan", "create", "--spec", self.root / "plan.json")
        self.call("checkpoint", "save", "--id", "before", "--kind", "reference")

    def test_completed_reference_restores_real_run_id_and_current_budget(self):
        self.reserve()
        executed = self.call("run", "execute", "--id", "P1")
        live = self.call("status")
        restored = self.call("checkpoint", "restore", "--id", "before", "--kind", "reference")
        self.assertEqual(restored["completed_runs"][0]["run_id"], executed["run_id"])
        self.assertEqual(restored["completed_runs"][0]["plan_id"], "P1")
        self.assertEqual(restored["live_budget"], live["budget"])
        self.assertFalse(restored["execution_started"])
        # The returned identity is directly usable by the documented evidence command.
        self.assertEqual(self.call("decide", "--run", restored["completed_runs"][0]["run_id"])["assessment"]["task_gain"], "EXPLORATORY")
        # Completed source remains in its immutable receipt; treatment edits are proposals.
        (self.root / "model.py").write_text("def control(x): return x\ndef treatment(x): return 3*x\n")
        self.assertEqual(self.call("checkpoint", "restore", "--id", "before")["status"], "RESUMABLE_HANDOFF")

    def test_reference_drift_is_conflict_with_nonzero_exit(self):
        self.reserve()
        source = self.root / "model.py"
        original_source = source.read_bytes()
        data = self.root / "development.csv"
        original_data = data.read_bytes()
        for role, path, changed in (
            ("pending_source", source, b"def control(x): return x\ndef treatment(x): return 3*x\n"),
            ("baseline_control", source, b"def control(x): return 0\ndef treatment(x): return 2*x\n"),
            ("split:development", data, b"sample_id,x,y\nchanged,1,100\n")):
            source.write_bytes(original_source)
            data.write_bytes(original_data)
            path.write_bytes(changed)
            with self.subTest(role=role):
                result = self.call("checkpoint", "restore", "--id", "before", "--kind", "reference", expected=1)
                self.assertEqual(result["status"], "CONFLICT")
                self.assertTrue(any(role in row["reason"] for row in result["conflicts"]))
                self.assertFalse(result["execution_started"])

    def test_binding_check_reads_each_path_once_and_checks_engine_once(self):
        from rds_cli import RDSState, _reference_binding_check, read_bounded
        self.reserve()
        snapshot = self.call("status")
        reads = []
        def counted(path, cap):
            reads.append(Path(path))
            return read_bounded(path, cap)
        with patch("rds_cli.read_bounded", side_effect=counted), patch("rds_cli.engine_id", return_value="changed-engine") as engine:
            result = _reference_binding_check(RDSState(self.root), snapshot)
        self.assertEqual(len(reads), len(set(reads)))
        self.assertEqual(len(reads), 2)
        engine.assert_called_once_with()
        self.assertTrue(any("engine changed" in error for error in result["errors"]))

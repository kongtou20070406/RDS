import copy
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_checkpoints import restore_checkpoint, save_checkpoint


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

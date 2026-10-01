"""The public score/Advisor loop must preserve unmeasured and invalid evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_rds_advancement import fixture

ROOT = Path(__file__).resolve().parents[1]


class AdvancementCLITests(unittest.TestCase):
    def invoke(self, root, *arguments):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                               "--root", str(root), *arguments], cwd=ROOT, capture_output=True,
                              encoding="utf-8", timeout=15)

    def test_missing_confirmation_then_numeric_fail_cannot_be_self_signed_pass(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            protocol, trajectories, confirmations = fixture()
            for name, value in (("protocol", protocol), ("trajectories", trajectories)):
                (root / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
            args = ["advancement", "score", "--protocol", str(root / "protocol.json"),
                    "--trajectories", str(root / "trajectories.json")]
            result = self.invoke(root, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "UNMEASURED")
            self.assertIsNone(report["primary_metric"]["advisor"]["rate"])
            confirmations[0]["success"] = True
            confirmations[0]["observed"] = 999
            (root / "confirmations.json").write_text(json.dumps(confirmations), encoding="utf-8")
            result = self.invoke(root, *args, "--confirmations", str(root / "confirmations.json"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["paired_tasks"][0]["baseline"]["status"], "FAIL")
            self.assertFalse((root / ".rds").exists())

    def test_invalid_identity_is_a_visible_report_not_cli_execution_success(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            protocol, trajectories, confirmations = fixture()
            trajectories[0]["protocol_version"] = "other-version"
            paths = []
            for name, value in (("protocol", protocol), ("trajectories", trajectories), ("confirmations", confirmations)):
                path = root / (name + ".json")
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.extend(["--" + name, str(path)])
            result = self.invoke(root, "advancement", "score", *paths)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "INVALID")
            self.assertIsNone(report["primary_metric"]["paired_difference"])
            self.assertFalse((root / ".rds").exists())

    def test_deep_duplicate_or_oversized_input_rejects_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "invalid.json"
            for value in ("[" * 2000 + "0" + "]" * 2000, '{"schema_version":1,"schema_version":2}', " " * (1024 * 1024 + 1)):
                path.write_text(value, encoding="utf-8")
                result = self.invoke(root, "advancement", "score", "--protocol", str(path), "--trajectories", str(path))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("[RDS-REJECT]", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_example_exercises_fixture_and_frontier_without_claiming_ai_improvement(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "new"
            result = subprocess.run([sys.executable, "-B", str(ROOT / "examples/advancement-loop/run.py"),
                                     "--workspace", str(root)], capture_output=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["before_confirmation"], "UNMEASURED")
            self.assertEqual(report["fixture_score_status"], "MEASURED")
            self.assertEqual(report["scientific_gain"], "UNMEASURED")
            self.assertEqual(report["ai_calls"], 0)
            self.assertIn("MODEL_FAILURE", report["next_question_kinds"])
            before = (root / "checkpoint.json").read_bytes()
            again = subprocess.run(result.args, capture_output=True, encoding="utf-8", timeout=15)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((root / "checkpoint.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

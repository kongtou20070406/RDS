"""Evidence boundaries in reflection, repair, telemetry and advice."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark.run import C7_CONTROL, C7_FORMAL, Project
from rds_adversary import AlignmentEvaluator, AutoRepairEngine
from rds_advisor import RDSAdvisor
from rds_compress import compress_training_log
from rds_meta import reflect_from_state
from rds_probe import parse_source


class SupportTests(unittest.TestCase):
    def test_reflection_uses_each_receipts_assessment(self):
        receipts = [{"plan_id": "P1", "run_id": "R1", "run_status": "SUCCEEDED", "result": {"gain": "0"}},
                    {"plan_id": "P2", "run_id": "R2", "run_status": "SUCCEEDED", "result": {"gain": "0"}}]
        state = {"hypotheses": {"last": {"task_gain": "EXPLORATORY"}}, "plans": {
            "P1": {"assessment": {"run_id": "R1", "task_gain": "INCONCLUSIVE"}},
            "P2": {"assessment": {"run_id": "R2", "task_gain": "INCONCLUSIVE"}},
        }}
        rule_ids = lambda: {rule["id"] for rule in reflect_from_state(state, receipts)}
        self.assertIn("parameter-tuning-without-causal-gain", rule_ids())
        state["hypotheses"]["last"]["task_gain"] = "INCONCLUSIVE"
        state["plans"]["P2"]["assessment"]["task_gain"] = "EXPLORATORY"
        self.assertNotIn("parameter-tuning-without-causal-gain", rule_ids())
        state["hypotheses"] = {}
        state["plans"]["P2"]["assessment"]["task_gain"] = "INCONCLUSIVE"
        receipts[1]["run_status"] = "FAILED"
        self.assertNotIn("parameter-tuning-without-causal-gain", rule_ids())
        receipts[1]["run_status"] = "SUCCEEDED"
        receipts[1]["run_id"] = "different-run"
        self.assertNotIn("parameter-tuning-without-causal-gain", rule_ids())

    def test_rule_lint_is_never_alignment_validation(self):
        rule = {"id": "c7-boundary", "scope": "test", "trigger": "c7 boundary counterexample",
                "correction": "Check the declared boundary", "alternatives": ["alternative"],
                "discriminator": "case replay", "primary_gate": "actual cases",
                "falsifier": "wrong case outcome", "sources": ["test"]}
        evaluator = AlignmentEvaluator(ROOT)
        report = evaluator.evaluate_rule(rule)
        self.assertTrue(report["lint_passed"])
        self.assertEqual(report["assurance"], "HEURISTIC_ONLY")
        for key in ("is_aligned", "verified", "auto_apply"):
            self.assertFalse(report[key])
        for key in ("precision", "false_positive_rate", "true_positives", "false_positives"):
            self.assertIsNone(report[key])
        self.assertEqual(report["cases_evaluated"], 0)
        self.assertFalse(evaluator.evaluate_rule({**rule, "correction": "guaranteed_gain"})["lint_passed"])

    def test_repair_reads_current_sqlite_and_never_applies_unverified_rules(self):
        project = Project(source=C7_CONTROL + "def treatment(x): return 25*x/(20*(1+x))\n")
        self.addCleanup(project.close)
        (project.root / "dev.csv").write_text("sample_id,x,y\ndev-1,10,1\n", encoding="utf-8")
        project.init(C7_FORMAL).run()
        # A stale legacy snapshot must not hide a real refutation.
        (project.root / ".rds/state.json").write_text('{"hypotheses": {}}', encoding="utf-8")
        graph = project.root / "graph.json"
        graph.write_text('{"schema": 1, "nodes": []}', encoding="utf-8")
        db = project.root / ".rds/state.sqlite3"
        original = (db.read_bytes(), graph.read_bytes())
        engine = AutoRepairEngine(project.root, graph)
        for dry_run in (True, False):
            report = engine.run_self_repair(dry_run=dry_run)
            self.assertEqual(report["status"], "CANDIDATES_ONLY")
            self.assertEqual(report["dry_run"], dry_run)
            self.assertEqual(report["repaired_rules"], [])
            self.assertTrue(any(rule["rule_id"].startswith("refuted-boundary") for rule in report["candidate_rules"]))
            self.assertTrue(all(not rule["applied"] for rule in report["candidate_rules"]))
            self.assertEqual((db.read_bytes(), graph.read_bytes()), original)

    def test_log_boundaries_and_loss_types(self):
        log = ("INFO: initializing inference; finance ready\n"
               "step=1 train_loss=1e0 val_loss=2.5 1e2 samples/s grad_norm=.5\n"
               "step=2 train_loss=.5 val_loss=3.0 2e2 samples/s gnorm=1E+1\n"
               "eval_loss=-2e-3 loss_val=+4. mse=1.2.3 loss=1e+\n")
        report = compress_training_log(log, max_samples=1)
        self.assertFalse(report["nan_or_inf"])
        self.assertEqual(report["loss_type"], "train_loss")
        self.assertEqual(report["loss_trend"], "DECREASING")
        self.assertEqual(report["loss_series"]["val_loss"]["loss_trend"], "EXPLODING")
        self.assertEqual(report["loss_series"]["train_loss"]["samples"], [0.5])
        self.assertEqual(report["loss_series"]["eval_loss"]["final_loss"], -0.002)
        self.assertNotIn("mse", report["loss_series"])
        self.assertNotIn("loss", report["loss_series"])
        self.assertEqual(report["mean_throughput"], 150.0)
        self.assertEqual(report["peak_grad_norm"], 10.0)
        self.assertNotIn("token_reduction_rate", report)
        self.assertEqual(compress_training_log("loss=1")["loss_trend"], "UNKNOWN")
        for text in ("loss=NaN", "gnorm=-Infinity", "loss=1e309"):
            with self.subTest(text=text):
                self.assertTrue(compress_training_log(text)["nan_or_inf"])
        with self.assertRaises(ValueError):
            compress_training_log("loss=1", max_samples=0)

    def test_advisor_requires_evidence_before_fit_or_model_patch(self):
        advisor = RDSAdvisor(ROOT)
        report = advisor.diagnose_fit_status(1.2, 1.3, 1.25)
        self.assertEqual(report["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report["assurance"], "HEURISTIC_ONLY")
        self.assertTrue(report["observations"])
        self.assertEqual(report["forbidden_actions"], [])
        self.assertEqual(report["required_actions"], [])
        self.assertEqual(advisor.diagnose_fit_status(0.01, 0.5, 1)["verdict"], "INSUFFICIENT_EVIDENCE")
        for losses in ((1, 1, None), (1, 1, 0), (-1, 1, 1), (1, 1, -1)):
            with self.subTest(losses=losses):
                result = advisor.diagnose_fit_status(*losses)
                self.assertEqual(result["verdict"], "INSUFFICIENT_EVIDENCE")
                json.dumps(result, allow_nan=False)
        for losses in ((float("nan"), 1, 1), (1, float("inf"), 1), (True, 1, 1)):
            with self.subTest(losses=losses), self.assertRaises(ValueError):
                advisor.diagnose_fit_status(*losses)
        self.assertEqual(advisor.advise_on_loss_dynamics({})["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(advisor.advise_on_loss_dynamics({"peak_grad_norm": float("inf")})["status"], "CRITICAL_ANOMALY")
        source_advice = advisor.advise_on_rejection("Formal gate FAIL", {})
        self.assertEqual(source_advice["assurance"], "HEURISTIC_ONLY")
        self.assertEqual(source_advice["recommended_patch"], {})
        self.assertTrue(source_advice["minimal_test"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

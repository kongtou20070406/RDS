"""Regression checks for evidence boundaries in the programmatic advisor."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_advisor import RDSAdvisor


class AdvisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.advisor = RDSAdvisor(self.root)

    def structured(self, advice):
        for field in ("observations", "alternative_explanations", "minimal_test", "limitations", "evidence"):
            self.assertIn(field, advice)
            self.assertIsInstance(advice[field], list)
        json.dumps(advice, allow_nan=False)

    def test_single_loss_pair_never_certifies_fit_or_forces_training(self):
        for losses in ((1.2, 1.3, 1.25), (0.001, 10, 1), (2, 2, None), (-4, -3, -2), (0, 0, 0), (-1e308, 1e308, None)):
            with self.subTest(losses=losses):
                result = self.advisor.diagnose_fit_status(*losses)
                self.structured(result)
                self.assertEqual(result["verdict"], "INSUFFICIENT_EVIDENCE")
                self.assertEqual(result["required_actions"], [])
                self.assertEqual(result["forbidden_actions"], [])

    def test_nonfinite_or_boolean_fit_values_are_rejected(self):
        for value in (float("nan"), float("inf"), True, "1.0", 10**1000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.advisor.diagnose_fit_status(value, 1)

    def test_curve_patterns_require_protocol_and_calibrated_tolerance(self):
        telemetry = {"train_loss_history": [3, 2, 1], "val_loss_history": [1, 2, 3],
                     "losses_comparable": True, "matched_checkpoints": True, "trend_tolerance": 0.1}
        self.assertEqual(self.advisor.diagnose_fit_status(1, 3, telemetry=telemetry)["verdict"],
                         "POSSIBLE_GENERALIZATION_GAP")
        for key in ("losses_comparable", "matched_checkpoints", "trend_tolerance"):
            incomplete = {k: v for k, v in telemetry.items() if k != key}
            self.assertEqual(self.advisor.diagnose_fit_status(1, 3, telemetry=incomplete)["verdict"],
                             "INSUFFICIENT_EVIDENCE")
        with self.assertRaisesRegex(ValueError, "endpoints"):
            self.advisor.diagnose_fit_status(2, 3, telemetry=telemetry)
        plateau = {**telemetry, "train_loss_history": [0, 0.01, 0], "val_loss_history": [-3, -3, -3]}
        self.assertEqual(self.advisor.diagnose_fit_status(0, -3, telemetry=plateau)["verdict"],
                         "POSSIBLE_OPTIMIZATION_PLATEAU")

    def test_nan_has_priority_and_locates_fault_before_hyperparameters(self):
        result = self.advisor.advise_on_loss_dynamics({"nan_or_inf": True, "peak_grad_norm": 95,
            "grad_norm_limit": 30, "loss_trend": "STAGNANT"})
        self.structured(result)
        self.assertEqual(result["status"], "CRITICAL_ANOMALY")
        self.assertIn("首个非有限", result["action_items"][0])
        self.assertFalse(any("eps=1e-7" in item or "缩小 5" in item for item in result["action_items"]))
        direct = self.advisor.advise_on_loss_dynamics({"peak_grad_norm": float("inf")})
        self.structured(direct)
        self.assertEqual(direct["status"], "CRITICAL_ANOMALY")

    def test_gradient_and_plateau_preserve_severity_without_universal_threshold(self):
        result = self.advisor.advise_on_loss_dynamics({"peak_grad_norm": 95})
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        result = self.advisor.advise_on_loss_dynamics({"peak_grad_norm": 95, "grad_norm_limit": 30,
                                                      "loss_trend": "STAGNANT"})
        self.assertEqual(result["status"], "GRADIENT_SPIKE_SUSPECTED")
        self.assertTrue(any("平台" in item for item in result["diagnostics"]))
        self.assertFalse(any("2~3" in item or "max_norm=1" in item for item in result["action_items"]))

    def test_exploding_trend_and_sparse_telemetry(self):
        self.assertEqual(self.advisor.advise_on_loss_dynamics({"loss_trend": "EXPLODING"})["status"],
                         "DIVERGENCE_REPORTED")
        self.assertEqual(self.advisor.advise_on_loss_dynamics({})["status"], "INSUFFICIENT_EVIDENCE")
        with self.assertRaises(ValueError):
            self.advisor.advise_on_loss_dynamics({"nan_or_inf": "false"})
        with self.assertRaises(ValueError):
            self.advisor.advise_on_loss_dynamics({"loss_variance": -1})

    def test_rejection_never_invents_inverse_or_model_patch(self):
        plan = {"id": "P1", "source": "original.py", "split_id": "actual-dev"}
        before = copy.deepcopy(plan)
        result = self.advisor.advise_on_rejection("Formal gate FAIL: m < 1", plan)
        self.structured(result)
        self.assertEqual(result["recommended_patch"], {})
        self.assertEqual(plan, before)
        result = self.advisor.advise_on_rejection("Budget unavailable or protected for confirmation", plan)
        self.assertEqual(result["recommended_patch"], {})

    def test_supplied_graph_and_real_state_affect_review(self):
        state = {"active_branch": "b", "branches": {"b": {"status": "STAGNATING", "stagnation_count": 3,
                 "orthogonal_dimension": "representation", "hypotheses": ["H1"]}},
                 "hypotheses": {"H1": {"task_gain": "EXPLORATORY", "mechanism": "NOT_TESTED"}}}
        graph = {"nodes": [{"id": "custom-rule", "scope": "local", "discriminator": "unique real test",
                            "sources": ["source-anchor"]}]}
        before = copy.deepcopy((state, graph))
        results = self.advisor.recommend_next_directions(state, graph)
        for result in results:
            self.structured(result)
        branching = next(r for r in results if r["type"] == "ORTHOGONAL_BRANCH_RECOMMENDATION")
        self.assertNotIn("representation", [d["dimension"] for d in branching["candidate_dimensions"]])
        self.assertNotIn("FFT", json.dumps(branching, ensure_ascii=False))
        review = next(r for r in results if r["type"] == "JUDGMENT_GRAPH_REVIEW")
        self.assertEqual(review["candidate_rules"][0]["discriminator"], "unique real test")
        self.assertEqual(review["observations"][0]["mechanism"], "NOT_TESTED")
        self.assertEqual((state, graph), before)

    def test_cache_advice_does_not_promote_unverified_entries(self):
        state = {"baseline_cache": {"key": {"observations": {"s1": {"control": "1"}}, "first_run_id": "RUN-a"}}}
        result = next(r for r in self.advisor.recommend_next_directions(state, {}) if r["type"] == "COMPUTE_REUSE_ADVICE")
        self.assertEqual(result["observations"][0]["first_run_id"], "RUN-a")
        self.assertTrue(any("未独立验证" in s for s in result["limitations"]))
        self.assertNotIn("100%", json.dumps(result))

    def test_ingestion_is_anchored_unreviewed_and_idempotent(self):
        document = self.root / "guide.md"
        document.write_text("# A guide\nLearning rate choice depends on the task.\n欠拟合须先检查数据。\n", encoding="utf-8")
        result = self.advisor.ingest_document(document)
        self.structured(result)
        self.assertEqual(result["rules_extracted"], 2)
        self.assertEqual(result["adoption_status"], "UNREVIEWED")
        self.assertEqual(result["evidence"][0]["line_number"], 2)
        self.assertEqual(len(result["evidence"][0]["source_sha256"]), 64)
        self.assertEqual(self.advisor.ingest_document(document)["rules_extracted"], 0)
        recommendation = next(r for r in self.advisor.recommend_next_directions({}, {}) if r["type"] == "DOC_REVIEW_CANDIDATES")
        self.assertEqual(recommendation["adoption_status"], "UNREVIEWED")

    def test_bad_knowledge_is_preserved_and_invalid_literature_is_reported(self):
        document = self.root / "guide.md"
        document.write_text("learning rate\n", encoding="utf-8")
        knowledge = self.root / ".rds/advisor_knowledge.json"
        knowledge.parent.mkdir()
        for invalid in ('{"not":"a list"}', '["not an object"]', "broken json"):
            knowledge.write_text(invalid, encoding="utf-8")
            with self.assertRaises(ValueError):
                self.advisor.ingest_document(document)
            self.assertEqual(knowledge.read_text(encoding="utf-8"), invalid)
            self.assertTrue(any(r["type"] == "KNOWLEDGE_LOAD_ERROR" for r in self.advisor.recommend_next_directions({}, {})))
        library = self.root / "references/scientific_tuning_principles.json"
        library.parent.mkdir()
        library.write_text('["not an object"]', encoding="utf-8")
        advisor = RDSAdvisor(self.root)
        self.assertEqual(advisor.literature_principles, [])
        self.assertTrue(advisor.literature_load_errors)

    def test_short_and_chinese_literature_queries(self):
        library = self.root / "references/scientific_tuning_principles.json"
        library.parent.mkdir()
        library.write_text(json.dumps([{"id": "lr-record", "topic": "learning rate"},
                                       {"id": "fit-record", "topic": "underfitting already recorded"}]), encoding="utf-8")
        advisor = RDSAdvisor(self.root)
        for query in ("lr", "学习率", "如何选择学习率"):
            self.assertEqual([p["id"] for p in advisor.query_literature_principles(query)], ["lr-record"])
        self.assertEqual([p["id"] for p in advisor.query_literature_principles("欠拟合")], ["fit-record"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

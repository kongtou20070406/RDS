"""Broader formulations are sourced questions, never inherited guarantees."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_frontier import discover_frontier
from rds_frontier_proposals import review_proposals


def fixture():
    source = {"source": "synthetic development specification", "available_on": "2026-01-01"}
    spec = {"schema_version": 1, "as_of": "2026-01-02",
        "nodes": [{"id": "recurrence", "kind": "model", **source},
                  {"id": "quality", "kind": "observable", **source}],
        "edges": [{"from": "recurrence", "to": "quality", "relation": "predicts", "status": "SUPPORTED", **source}],
        "goals": [{"id": "goal", "target": "quality", "anchors": ["recurrence"],
                   "relations": ["predicts"], "decision": "Review formulations under the same objective", **source,
                   "reformulation": {"current_model": "recurrence", "reason": "Local checks do not establish task improvement", **source}}]}
    gap = discover_frontier(spec)["gaps"][0]
    proposal = {"id": "lift", "gap_id": gap["id"],
        "new_nodes": [{"id": "state", "kind": "model", "label": "General discrete state-space formulation", **source}],
        "relations": [{"from": "recurrence", "to": "state", "relation": "proposed_embedding"},
                      {"from": "state", "to": "quality", "relation": "predicts"}],
        "theory_bridge": {"kind": "exact_reduction", "source_model": "recurrence", "candidate_model": "state",
            "mapping": "h=x; F(h,u)=T(h); output(h)=h; same discrete clock",
            "preserved_claim": "Every original discrete trajectory and its quality measurement",
            "changed_assumptions": ["The broader family permits additional input; the embedded case ignores it"],
            "applicability_conditions": ["Same domain, initial state, update operator and output map"], **source},
        "assumptions": ["The supplied recurrence is the actual implementation"],
        "test": {"kind": "proof_check", "protocol": "Check update/output equality and induction on the original domain",
                 "measurement": "Preservation of each trajectory", "stop_condition": "Stop at an unclosed premise",
                 "outcomes": ["verified", "counterexample", "unresolved"]},
        "next_if_positive": "Compare a separately defined extension against the embedded baseline",
        "next_if_negative": "Repair or discard the claimed embedding"}
    return spec, proposal


class ReformulationTests(unittest.TestCase):
    def setUp(self):
        self.spec, self.proposal = fixture()

    def review(self):
        return review_proposals(discover_frontier(self.spec), self.spec,
            {"schema_version": 1, "proposals": [self.proposal]})["proposals"][0]

    def test_explicit_request_broadens_even_when_reported_graph_is_reachable(self):
        report = discover_frontier(self.spec)
        self.assertEqual([g["kind"] for g in report["gaps"]], ["THEORY_REFORMULATION"])
        gap = report["gaps"][0]
        self.assertEqual((gap["target"], gap["decision"]), ("quality", self.spec["goals"][0]["decision"]))
        self.assertFalse(gap["execution_authorized"])
        self.assertEqual(gap["uncertainty"], "UNKNOWN_SCIENTIFIC_SUPPORT")
        del self.spec["goals"][0]["reformulation"]
        self.assertEqual(discover_frontier(self.spec)["gaps"], [])

    def test_proof_route_needs_no_invented_rival_but_does_not_prove_gain(self):
        original = deepcopy((self.spec, self.proposal))
        report = self.review()
        self.assertEqual(report["status"], "NEEDS_EVIDENCE")
        self.assertNotIn("prediction", report)
        self.assertEqual(report["theory_bridge"]["preservation_status"], "UNKNOWN")
        self.assertEqual(report["scientific_support"], "UNKNOWN")
        self.assertFalse(report["candidate_eligible"])
        self.assertFalse(report["execution_authorized"])
        self.assertEqual((self.spec, self.proposal), original)

    def test_current_model_is_target_still_requires_candidate_return_path(self):
        self.spec["goals"][0]["target"] = "recurrence"
        self.proposal["relations"][1]["to"] = "recurrence"
        report = self.review()
        self.assertEqual(report["status"], "NEEDS_EVIDENCE", report["definition_errors"])
        self.assertFalse(report["candidate_eligible"])
        self.assertFalse(report["execution_authorized"])
        self.proposal["relations"].pop()
        report = self.review()
        self.assertEqual(report["status"], "NEEDS_DEFINITION")
        self.assertTrue(any("path" in error for error in report["definition_errors"]))

    def test_unrelated_formal_certificate_is_not_executed_or_inherited(self):
        self.proposal.update(formal_obligation={"some": "unrelated theorem"}, formal_certificate={"status": "PASS"})
        self.proposal["theory_bridge"].update(applicability_status="PASS", preservation_status="PASS")
        with patch("rds_frontier_proposals.formal_gate", side_effect=AssertionError("must not run")):
            report = self.review()
        self.assertFalse(report["candidate_eligible"])
        self.assertEqual(report["theory_bridge"]["applicability_status"], "UNKNOWN")

    def test_optional_relation_labels_remain_unverified_descriptions(self):
        for kind in ("exact_reduction", "approximation", "analogy", "alternative", "other proposed relation"):
            self.proposal["theory_bridge"].update(kind=kind, domain="declared finite domain", error_bound="unproved epsilon bound")
            report = self.review()
            self.assertEqual(report["status"], "NEEDS_EVIDENCE", report)
            self.assertEqual(report["theory_bridge"]["relation_status"], "PROPOSED")
        self.proposal["theory_bridge"]["kind"] = {"invalid": "object"}
        self.assertEqual(self.review()["status"], "NEEDS_DEFINITION")

    def test_approximation_requires_domain_and_error_claim(self):
        self.proposal["theory_bridge"]["kind"] = "approximation"
        report = self.review()
        self.assertEqual(report["status"], "NEEDS_DEFINITION")
        self.assertTrue(any("domain" in e for e in report["definition_errors"]))
        self.assertTrue(any("error_bound" in e for e in report["definition_errors"]))

    def test_mapping_candidate_or_source_cannot_be_omitted(self):
        for field in ("mapping", "candidate_model", "source"):
            with self.subTest(field=field):
                proposal = deepcopy(self.proposal)
                del self.proposal["theory_bridge"][field]
                self.assertEqual(self.review()["status"], "NEEDS_DEFINITION")
                self.proposal = proposal

    def test_existing_goal_and_premises_fill_routine_fields_without_classification(self):
        for field in ("kind", "source_model", "preserved_claim", "changed_assumptions", "applicability_conditions"):
            del self.proposal["theory_bridge"][field]
        report = self.review()
        self.assertEqual(report["status"], "NEEDS_EVIDENCE")
        bridge = report["theory_bridge"]
        self.assertEqual(bridge["kind"], "unspecified")
        self.assertEqual(bridge["source_model"], "recurrence")
        self.assertEqual(bridge["applicability_conditions"], self.proposal["assumptions"])
        self.assertIn("quality", bridge["preserved_claim"])
        self.assertEqual(bridge["preservation_status"], "UNKNOWN")

    def test_stray_broader_theory_cannot_use_unrelated_old_path(self):
        self.proposal["relations"] = [{"from": "recurrence", "to": "quality", "relation": "predicts"},
                                     {"from": "state", "to": "state", "relation": "related_to"}]
        report = self.review()
        self.assertEqual(report["status"], "NEEDS_DEFINITION")
        self.assertTrue(any("Candidate theory must lie" in e for e in report["definition_errors"]))

    def test_unknown_or_wrong_current_model_is_not_silently_substituted(self):
        self.proposal["theory_bridge"]["source_model"] = "different"
        self.assertEqual(self.review()["status"], "NEEDS_DEFINITION")
        self.spec["goals"][0]["reformulation"]["current_model"] = "missing"
        with self.assertRaisesRegex(ValueError, "current_model"):
            discover_frontier(self.spec)

    def test_future_and_undated_review_requests_are_excluded(self):
        for when in (None, "2026-01-03"):
            request = self.spec["goals"][0]["reformulation"]
            request.pop("available_on", None)
            if when:
                request["available_on"] = when
            report = discover_frontier(self.spec)
            self.assertEqual(report["gaps"], [])
            self.assertEqual(report["excluded"][0]["record_type"], "reformulations")

    def test_future_bridge_and_new_node_cannot_leak_into_historical_review(self):
        for record in (self.proposal["theory_bridge"], self.proposal["new_nodes"][0]):
            record["available_on"] = "2026-01-03"
            self.assertEqual(self.review()["status"], "NEEDS_DEFINITION")
            del record["available_on"]
            self.assertEqual(self.review()["status"], "NEEDS_DEFINITION")
            record["available_on"] = "2026-01-01"

    def test_empirical_extension_requires_different_observable_predictions(self):
        self.proposal["test"]["kind"] = "empirical"
        self.assertEqual(self.review()["status"], "NEEDS_DEFINITION")
        self.proposal["prediction"] = {"observable": "quality", "if_proposal": "changes with the released constraint",
                                       "if_rival": "unchanged under the matched intervention"}
        self.assertEqual(self.review()["status"], "NEEDS_EVIDENCE")

    def test_timeouts_or_invalid_proofs_cannot_be_collapsed_into_counterexamples(self):
        self.proposal["test"]["outcomes"] = ["verified", "counterexample"]
        self.assertEqual(self.review()["status"], "NEEDS_DEFINITION")

    def test_request_limits_and_source_metadata_remain_bounded(self):
        self.spec["edges"] = []
        self.spec["limits"] = {"max_gaps": 1}
        report = discover_frontier(self.spec)
        self.assertTrue(report["truncation"]["truncated"])
        self.assertEqual(report["statistics"]["gaps_by_kind"]["THEORY_REFORMULATION"], 1)
        self.spec["goals"][0]["reformulation"]["source"] = {"path": "record", "dump": "x" * 1024}
        with self.assertRaisesRegex(ValueError, "1024"):
            discover_frontier(self.spec)

    def test_preloaded_tools_are_small_on_demand_and_unknown_signals_do_not_expand(self):
        self.spec.pop("as_of")
        request = self.spec["goals"][0]["reformulation"]
        request["signals"] = ["trajectory_degradation", "local_global_gap"]
        tools = discover_frontier(self.spec)["gaps"][0]["theory_tools"]
        self.assertEqual(tools["selection"], "TAG_MATCH_ONLY")
        self.assertGreater(len(tools["cards"]), 0)
        self.assertLessEqual(len(tools["cards"]), 3)
        self.assertLess(len(json.dumps(tools).encode()), 2048)
        request["signals"] = ["not_a_known_diagnostic"]
        self.assertEqual(discover_frontier(self.spec)["gaps"][0]["theory_tools"]["cards"], [])
        del request["signals"]
        self.assertNotIn("theory_tools", discover_frontier(self.spec)["gaps"][0])

    def test_new_tool_catalogue_cannot_leak_into_earlier_frontier(self):
        self.spec["goals"][0]["reformulation"]["signals"] = ["trajectory_degradation"]
        tools = discover_frontier(self.spec)["gaps"][0]["theory_tools"]
        self.assertEqual(tools, {"status": "UNAVAILABLE_AT_CUTOFF", "cards": []})

    def test_signal_bounds_are_validated_before_retrieval(self):
        for signals in ("trajectory_degradation", ["x"] * 33, [{}], ["x" * 81]):
            self.spec["goals"][0]["reformulation"]["signals"] = signals
            with self.assertRaisesRegex(ValueError, "signals"):
                discover_frontier(self.spec)

    def test_cli_preserves_full_reformulation_review_in_compact_cas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frontier.json").write_text(json.dumps(self.spec), encoding="utf-8")
            (root / "proposals.json").write_text(json.dumps({"schema_version": 1, "proposals": [self.proposal]}), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"), "--root", tmp,
                "advise", "--frontier", str(root / "frontier.json"), "--frontier-proposals", str(root / "proposals.json"), "--brief"],
                capture_output=True, encoding="utf-8", timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = json.loads(result.stdout)
            saved = json.loads(Path(digest["record"]).read_text(encoding="utf-8"))
            report = saved["recommendations"][0]["frontier"]["proposal_review"]["proposals"][0]
            self.assertEqual(report["status"], "NEEDS_EVIDENCE")
            self.assertFalse(report["execution_authorized"])
            self.assertEqual(report["theory_bridge"]["source_model"], "recurrence")


if __name__ == "__main__":
    unittest.main()

"""Only replayed native side conditions enter the formal candidate pool."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rds_lean_verify as lean
from rds_frontier import discover_frontier
from rds_frontier_proposals import formal_gate, review_proposals
from rds_verify import verify


STATEMENT = {"schema": 1, "kind": "lean_obligation", "relation": "lt",
             "left": "1/2", "right": "3/4"}


class FrontierFormalTests(unittest.TestCase):
    def setUp(self):
        self.native = mock.patch.object(lean, "_native_check", return_value={
            "lean_version": "Lean (version 4.33.1, test)",
            "lean_executable_sha256": "a" * 64, "stdout": lean.AXIOM_AUDIT})
        self.native.start()
        self.addCleanup(self.native.stop)
        self.spec = {"schema_version": 1,
            "nodes": [{"id": "candidate", "kind": "operation", "source": "frozen recipe"}],
            "formal_records": [{"id": "side-condition", "node": "candidate",
                "source": "declared mathematical model", "statement": deepcopy(STATEMENT)}]}
        self.proposal = {"id": "proof", "new_nodes": [], "relations": [],
            "assumptions": ["The declared mathematical side condition is the intended one"],
            "prediction": {"observable": "candidate", "if_proposal": "The condition is proved",
                           "if_rival": "The condition remains unproved"},
            "test": {"protocol": "Replay the bound native theorem", "measurement": "Kernel status",
                     "stop_condition": "Block unproved application"},
            "next_if_positive": "Review the candidate", "next_if_negative": "Close the premise gap",
            "formal_obligation": deepcopy(STATEMENT)}

    def test_unclosed_record_becomes_exact_obligation_gap(self):
        original = deepcopy(self.spec)
        report = discover_frontier(self.spec)
        self.assertEqual(report["gaps"][0]["kind"], "FORMAL_OBLIGATION")
        self.assertEqual(report["gaps"][0]["formal_obligation"], STATEMENT)
        self.assertFalse(report["formal_checks"][0]["admitted"])
        self.assertEqual(self.spec, original)

    def test_replayed_native_record_closes_only_mathematical_gap(self):
        self.spec["formal_records"][0]["certificate"] = verify(STATEMENT)["certificate"]
        report = discover_frontier(self.spec)
        self.assertEqual(report["gaps"], [])
        self.assertTrue(report["formal_checks"][0]["admitted"])
        self.assertEqual(report["scientific_support"], "UNKNOWN")

    def test_formal_proposal_preserves_statement_and_does_not_adopt_science(self):
        frontier = discover_frontier(self.spec)
        self.proposal["gap_id"] = frontier["gaps"][0]["id"]
        pack = {"schema_version": 1, "proposals": [self.proposal]}
        report = review_proposals(frontier, self.spec, pack)
        self.assertEqual(report["candidate_pool"], ["proof"])
        self.assertEqual(report["adopted_relations"], 0)
        self.assertFalse(report["proposals"][0]["execution_authorized"])
        self.assertEqual(report["proposals"][0]["scientific_support"], "UNKNOWN")
        self.proposal["formal_obligation"]["right"] = "1"
        report = review_proposals(frontier, self.spec, pack)
        self.assertEqual(report["candidate_pool"], [])
        self.assertEqual(report["proposals"][0]["status"], "NEEDS_DEFINITION")

    def test_forged_or_mismatched_certificate_cannot_enter_pool(self):
        certificate = verify(STATEMENT)["certificate"]
        for statement, proof in ((STATEMENT, {"status": "PASS", "assurance": "LEAN_KERNEL_CHECKED"}),
                ({**STATEMENT, "left": "2"}, certificate)):
            with self.subTest(statement=statement):
                self.assertFalse(formal_gate(statement, proof)["admitted"])

    def test_fallback_or_conditional_law_does_not_authorize_application(self):
        for assurance, application in (("CERTIFICATE_CHECKED", "PASS"),
                                        ("LEAN_KERNEL_CHECKED", "UNKNOWN")):
            with self.subTest(assurance=assurance, application=application), \
                    mock.patch("rds_verify.checked_result", return_value={
                        "status": "PASS", "assurance": assurance, "certificate": {},
                        "application_status": application}):
                self.assertFalse(formal_gate(STATEMENT, {})["admitted"])
        self.assertFalse(formal_gate(None)["admitted"])

    def test_future_formal_record_is_excluded_before_replay(self):
        self.spec["as_of"] = "2026-10-01"
        self.spec["nodes"][0]["available_on"] = "2026-09-30"
        self.spec["formal_records"][0]["available_on"] = "2026-10-02"
        with mock.patch("rds_frontier_proposals.formal_gate") as gate:
            report = discover_frontier(self.spec)
        gate.assert_not_called()
        self.assertEqual(report["formal_checks"], [])
        self.assertEqual(report["excluded"][0]["reason"], "FUTURE_RECORD")


if __name__ == "__main__":
    unittest.main()

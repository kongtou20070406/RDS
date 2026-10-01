"""AND/OR semantics, unproved-rule obligations and bounded fail-closed output."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_hypergraph import ASSURANCE, analyze_hypergraph, audit_sources


def graph(statuses, rules, goals, **limits):
    return {"schema": 1,
            "nodes": [{"id": name, "status": status, "source": "node source " + name}
                      for name, status in statuses.items()],
            "hyperedges": [{"id": name, "premises": tails, "conclusion": head,
                            "status": status, "source": "rule source " + name}
                           for name, tails, head, status in rules],
            "goals": goals, "limits": limits}


class HypergraphTests(unittest.TestCase):
    def test_and_requires_every_premise(self):
        spec = graph({"A": "SUPPORTED", "B": "UNKNOWN", "C": "UNKNOWN"},
                     [("ab", ["A", "B"], "C", "SUPPORTED")], ["C"])
        spec["nodes"][0]["allow_direct_evidence"] = False
        result = analyze_hypergraph(spec)
        self.assertEqual(result["declared_supported_closure"], ["A"])
        self.assertEqual(result["goals"]["C"]["minimal_missing_evidence_sets"],
                         [["node:B"]])
        spec["nodes"][1]["status"] = "SUPPORTED"
        self.assertEqual(analyze_hypergraph(spec)["declared_supported_closure"], ["A", "B", "C"])

    def test_empty_unanchored_cycle_never_self_proves(self):
        spec = graph({"A": "UNKNOWN", "B": "UNKNOWN"},
                     [("a", ["A"], "B", "SUPPORTED"),
                      ("b", ["B"], "A", "SUPPORTED")], ["A", "B"])
        result = analyze_hypergraph(spec)
        self.assertEqual(result["declared_supported_closure"], [])
        for goal in result["goals"].values():
            self.assertEqual(goal["minimal_missing_evidence_sets"], [])
            self.assertEqual(goal["status"], "UNRESOLVED")
            self.assertNotIn([], goal["minimal_missing_evidence_sets"])

    def test_proposed_rule_is_an_obligation_not_supported(self):
        spec = graph({"A": "SUPPORTED", "C": "UNKNOWN"},
                     [("proposal", ["A"], "C", "PROPOSED")], ["C"])
        result = analyze_hypergraph(spec)
        self.assertEqual(result["declared_supported_closure"], ["A"])
        self.assertEqual(result["goals"]["C"]["minimal_missing_evidence_sets"],
                         [["rule:proposal"]])
        self.assertEqual(result["ready_obligations"][0]["token"], "rule:proposal")

    def test_proposed_rule_still_requires_all_unknown_tails(self):
        spec = graph({"A": "UNKNOWN", "B": "UNKNOWN", "C": "UNKNOWN"},
                     [("proposal", ["A", "B"], "C", "PROPOSED")], ["C"])
        result = analyze_hypergraph(spec)
        self.assertIn(["node:A", "node:B", "rule:proposal"],
                      result["goals"]["C"]["minimal_missing_evidence_sets"])
        self.assertFalse(any(row["token"] == "rule:proposal" for row in result["ready_obligations"]))

    def test_alternative_rules_are_or_and_dominated_sets_removed(self):
        spec = graph({"A": "UNKNOWN", "B": "UNKNOWN", "C": "UNKNOWN", "D": "UNKNOWN"},
                     [("a", ["A"], "D", "SUPPORTED"),
                      ("bc", ["B", "C"], "D", "SUPPORTED"),
                      ("abc", ["A", "B", "C"], "D", "SUPPORTED")], ["D"])
        self.assertEqual(analyze_hypergraph(spec)["goals"]["D"]["minimal_missing_evidence_sets"],
                         [["node:A"], ["node:B", "node:C"]])

    def test_empty_supported_rule_is_an_explicit_reported_anchor(self):
        spec = graph({"A": "UNKNOWN"}, [("axiom", [], "A", "SUPPORTED")], ["A"])
        result = analyze_hypergraph(spec)
        self.assertEqual(result["declared_supported_closure"], ["A"])
        self.assertEqual(result["goals"]["A"]["minimal_missing_evidence_sets"], [[]])

    def test_contradicted_rules_and_nodes_never_silently_activate(self):
        spec = graph({"A": "SUPPORTED", "B": "CONTRADICTED", "C": "UNKNOWN"},
                     [("conflict", ["A"], "B", "SUPPORTED"),
                      ("rejected", ["A"], "C", "CONTRADICTED"),
                      ("blocked", ["B"], "C", "SUPPORTED")], ["B", "C"])
        spec["nodes"][1]["allow_direct_evidence"] = True
        result = analyze_hypergraph(spec)
        self.assertEqual(result["declared_supported_closure"], ["A"])
        self.assertEqual(result["active_contradicted_conclusion_rules"], ["conflict"])
        self.assertEqual(result["goals"]["B"]["status"], "CONTRADICTED")
        self.assertEqual(result["goals"]["B"]["minimal_missing_evidence_sets"], [])
        self.assertEqual(result["goals"]["C"]["minimal_missing_evidence_sets"], [])
        self.assertEqual(result["goals"]["C"]["status"], "UNRESOLVED")

    def test_work_truncation_discards_partial_blockers(self):
        spec = graph({"A": "UNKNOWN", "B": "UNKNOWN", "C": "UNKNOWN"},
                     [("ab", ["A", "B"], "C", "SUPPORTED")], ["C"], max_combinations=1)
        result = analyze_hypergraph(spec)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["declared_supported_closure"], [])
        self.assertEqual(result["goals"]["C"]["minimal_missing_evidence_sets"], [])
        self.assertFalse(result["goals"]["C"]["blocker_sets_complete"])

    def test_family_truncation_is_fail_closed(self):
        spec = graph({"A": "UNKNOWN", "B": "UNKNOWN"},
                     [("ab", ["A"], "B", "SUPPORTED")], ["B"], max_blocker_sets=1)
        spec["nodes"][1]["allow_direct_evidence"] = True
        result = analyze_hypergraph(spec)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["goals"]["B"]["minimal_missing_evidence_sets"], [])

    def test_source_preservation_and_no_input_mutation(self):
        spec = graph({"A": "SUPPORTED", "B": "UNKNOWN"},
                     [("a", ["A"], "B", "PROPOSED")], ["B"])
        spec["nodes"][0]["source"] = {"locator": "paper, page 7", "extra": [1, 2]}
        original = deepcopy(spec)
        result = analyze_hypergraph(spec)
        self.assertEqual(spec, original)
        self.assertEqual(result["reported_nodes"], original["nodes"])
        self.assertEqual(result["reported_hyperedges"], original["hyperedges"])
        self.assertEqual(result["assurance"], ASSURANCE)
        result["reported_nodes"][0]["source"]["extra"].append(3)
        self.assertEqual(spec, original)

    def test_derived_goal_has_only_intermediate_gap_not_goal_atom(self):
        spec = graph({"anchor": "SUPPORTED", "gap": "UNKNOWN", "middle": "UNKNOWN", "goal": "UNKNOWN"},
                     [("m", ["anchor", "gap"], "middle", "SUPPORTED"),
                      ("g", ["middle"], "goal", "SUPPORTED")], ["goal"])
        result = analyze_hypergraph(spec)
        self.assertEqual(result["goals"]["goal"]["minimal_missing_evidence_sets"], [["node:gap"]])
        self.assertEqual(result["direct_evidence_node_ids"], ["gap"])
        self.assertFalse(any("node:goal" in row for row in result["goals"]["goal"]["minimal_missing_evidence_sets"]))

    def test_explicit_direct_proof_is_a_separate_serious_alternative(self):
        spec = graph({"A": "UNKNOWN", "goal": "UNKNOWN"},
                     [("r", ["A"], "goal", "SUPPORTED")], ["goal"])
        spec["nodes"][1]["allow_direct_evidence"] = True
        result = analyze_hypergraph(spec)
        self.assertEqual(result["goals"]["goal"]["minimal_missing_evidence_sets"],
                         [["node:A"], ["node:goal"]])
        self.assertIn("DIRECT_PROOF_ALTERNATIVE", [row["kind"] for row in result["ready_obligations"]])

    def test_explicit_false_leaf_stays_unresolved_without_fake_unlock(self):
        spec = graph({"leaf": "UNKNOWN"}, [], ["leaf"])
        spec["nodes"][0]["allow_direct_evidence"] = False
        result = analyze_hypergraph(spec)
        self.assertEqual(result["goals"]["leaf"]["status"], "UNRESOLVED")
        self.assertEqual(result["goals"]["leaf"]["minimal_missing_evidence_sets"], [])
        self.assertEqual(result["ready_obligations"], [])
        self.assertTrue(result["goals"]["leaf"]["blocker_sets_complete"])

    def test_direct_evidence_flag_must_be_boolean(self):
        spec = graph({"A": "UNKNOWN"}, [], ["A"])
        for invalid in (0, 1, "true", None):
            with self.subTest(invalid=invalid):
                spec["nodes"][0]["allow_direct_evidence"] = invalid
                with self.assertRaises(ValueError):
                    analyze_hypergraph(spec)

    def test_invalid_input_rejects_unknown_refs_duplicates_and_limits(self):
        base = graph({"A": "UNKNOWN"}, [], ["A"])
        cases = [dict(base, limits={"max_nodes": 0}),
                 dict(base, limits={"max_nodes": True}),
                 dict(base, goals=["missing"]),
                 dict(base, nodes=base["nodes"] * 2),
                 graph({"A": "UNKNOWN", "B": "UNKNOWN"}, [], ["A"], max_nodes=1),
                 graph({"A": "UNKNOWN"}, [("x", ["missing"], "A", "SUPPORTED")], ["A"])]
        for spec in cases:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                analyze_hypergraph(spec)

    def test_optional_hash_audit_checks_bytes_without_upgrading_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.txt"
            path.write_bytes(b"evidence bytes")
            spec = graph({"A": "UNKNOWN"}, [], ["A"])
            spec["nodes"][0]["source"] = {"locator": "local evidence", "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertTrue(audit_sources(spec, directory)["all_requested_files_match"])
            analyzed = analyze_hypergraph(spec)
            self.assertEqual(analyzed["declared_supported_closure"], [])
            self.assertEqual(analyzed["goals"]["A"]["minimal_missing_evidence_sets"], [["node:A"]])
            path.write_bytes(b"changed")
            self.assertFalse(audit_sources(spec, directory)["all_requested_files_match"])
            spec["limits"] = {"max_source_bytes": 1}
            self.assertEqual(audit_sources(spec, directory)["audits"][0]["status"], "BYTE_LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()

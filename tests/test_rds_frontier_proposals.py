"""New AI concepts can be defined without a prewritten rule or a success flag."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_frontier_proposals import review_proposals


class FrontierProposalTests(unittest.TestCase):
    def setUp(self):
        self.spec = {"nodes": [{"id": "observation"}, {"id": "target"}]}
        self.frontier = {"gaps": [{"id": "gap", "anchors": ["observation"], "target": "target",
            "decision": "Explain the mismatch", "evidence_refs": [{"source": "original observation"}]}], "excluded": []}
        self.proposal = {"id": "new-idea", "gap_id": "gap",
            "new_nodes": [{"id": "hidden_state", "kind": "model", "label": "Previously unmodelled state"}],
            "relations": [{"from": "observation", "to": "hidden_state", "relation": "constrains"},
                          {"from": "hidden_state", "to": "target", "relation": "predicts"}],
            "assumptions": ["The original comparison has matched measurements"],
            "prediction": {"observable": "target", "if_proposal": "The mismatch changes with state",
                           "if_rival": "The mismatch does not depend on state"},
            "test": {"protocol": "Matched frozen-state replay", "measurement": "Paired residual",
                     "stop_condition": "Stop if the comparison is unmatched"},
            "next_if_positive": "Develop state-dependent model", "next_if_negative": "Retain rival explanation"}

    def review(self):
        return review_proposals(self.frontier, self.spec, {"schema_version": 1, "proposals": [self.proposal]})

    def test_graph_outside_concept_is_retained_for_evidence_and_input_is_unchanged(self):
        original = deepcopy((self.frontier, self.spec, self.proposal))
        result = self.review()
        proposal = result["proposals"][0]
        self.assertEqual(proposal["status"], "NEEDS_EVIDENCE")
        self.assertEqual(proposal["subgraph"]["nodes"][0]["id"], "hidden_state")
        self.assertEqual(proposal["scientific_support"], "UNKNOWN")
        self.assertFalse(proposal["execution_authorized"])
        self.assertEqual((result["adopted_relations"], result["executed_tests"]), (0, 0))
        self.assertEqual((self.frontier, self.spec, self.proposal), original)

    def test_signed_success_fields_cannot_adopt_nodes_or_relations(self):
        self.proposal.update(success=True, scientific_support="SUPPORTED", execution_authorized=True)
        self.proposal["new_nodes"][0].update(verified=True, status="SUPPORTED")
        self.proposal["relations"][0]["status"] = "SUPPORTED"
        self.proposal["test"]["execution_authorized"] = True
        result = self.review()["proposals"][0]
        self.assertEqual(result["status"], "NEEDS_EVIDENCE")
        self.assertNotIn("verified", result["subgraph"]["nodes"][0])
        self.assertTrue(all(edge["status"] == "PROPOSED" for edge in result["subgraph"]["edges"]))
        self.assertNotIn("execution_authorized", result["test"])

    def test_required_explanation_cannot_be_replaced_by_relatedness(self):
        self.frontier["gaps"][0]["relations"] = ["explains"]
        for relation in self.proposal["relations"]:
            relation["relation"] = "related_to"
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")
        self.proposal["relations"][0]["relation"] = "explains"
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")
        self.proposal["relations"][1]["relation"] = "explains"
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_EVIDENCE")

    def test_new_relation_can_extend_an_existing_available_path(self):
        self.spec["nodes"].append({"id": "intermediate"})
        self.spec["edges"] = [{"from": "observation", "to": "intermediate",
                              "relation": "explains", "status": "SUPPORTED"}]
        self.frontier["gaps"][0]["relations"] = ["explains"]
        self.proposal["new_nodes"] = []
        self.proposal["relations"] = [{"from": "intermediate", "to": "target", "relation": "explains"}]
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_EVIDENCE")
        self.frontier["excluded"] = [{"record_type": "edges", "id": "edge:0", "reason": "FUTURE_RECORD"}]
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")

    def test_an_unrelated_new_edge_cannot_claim_an_existing_bridge(self):
        self.spec["edges"] = [{"from": "observation", "to": "target", "relation": "explains", "status": "SUPPORTED"}]
        self.proposal["relations"] = [{"from": "hidden_state", "to": "hidden_state", "relation": "related_to"}]
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")

    def test_duplicate_optional_edge_ids_do_not_exclude_an_available_path(self):
        from rds_frontier import discover_frontier
        spec = {"schema_version": 1, "as_of": "2000-01-01",
            "nodes": [{"id": node, "kind": "observable", "source": "record", "available_on": "1999-01-01"}
                      for node in ("observation", "target", "intermediate")],
            "edges": [{"id": "same", "from": "observation", "to": "intermediate", "relation": "explains",
                       "status": "SUPPORTED", "source": "record", "available_on": "1999-01-01"},
                      {"id": "same", "from": "observation", "to": "target", "relation": "explains",
                       "status": "SUPPORTED", "source": "future record", "available_on": "2001-01-01"}],
            "goals": [{"id": "goal", "target": "target", "anchors": ["observation"], "relations": ["explains"],
                       "decision": "Explain the mismatch", "source": "record", "available_on": "1999-01-01"}]}
        frontier = discover_frontier(spec)
        proposal = deepcopy(self.proposal)
        proposal.update(gap_id=frontier["gaps"][0]["id"], new_nodes=[],
                        relations=[{"from": "intermediate", "to": "target", "relation": "explains"}])
        result = review_proposals(frontier, spec, {"schema_version": 1, "proposals": [proposal]})
        self.assertEqual(result["proposals"][0]["status"], "NEEDS_EVIDENCE")

    def test_no_bridge_or_unknown_endpoint_needs_definition(self):
        for endpoint in ("ghost", "observation"):
            with self.subTest(endpoint=endpoint):
                self.proposal["relations"][-1]["to"] = endpoint
                self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")

    def test_target_in_anchors_cannot_admit_unrelated_proposal(self):
        self.frontier["gaps"][0]["anchors"].append("target")
        self.proposal["relations"] = [self.proposal["relations"][0]]
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")

    def test_future_node_is_unavailable_to_proposal_definitions(self):
        self.frontier["excluded"] = [{"record_type": "nodes", "id": "observation", "reason": "FUTURE_RECORD"}]
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")

    def test_same_prediction_or_unchanged_next_decision_needs_definition(self):
        self.proposal["prediction"]["if_rival"] = self.proposal["prediction"]["if_proposal"]
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")
        self.proposal["prediction"]["if_rival"] = "Another result"
        self.proposal["next_if_negative"] = self.proposal["next_if_positive"]
        self.assertEqual(self.review()["proposals"][0]["status"], "NEEDS_DEFINITION")

    def test_large_duplicate_or_invalid_proposal_pack_fails_explicitly(self):
        for pack in ({"schema_version": 1, "proposals": [self.proposal] * 17},
                     {"schema_version": 1, "proposals": [self.proposal] * 2},
                     {"schema_version": True, "proposals": []}):
            with self.subTest(pack=pack["schema_version"]):
                with self.assertRaises(ValueError):
                    review_proposals(self.frontier, self.spec, pack)


if __name__ == "__main__":
    unittest.main()

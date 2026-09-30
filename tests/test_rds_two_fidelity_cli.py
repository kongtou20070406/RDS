"""Exercise the optional planner through real CLI and artifact/manual merging."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_rds_development_cli as development_cli
from test_rds_advisor_search import node
from test_rds_two_fidelity import context, leaf


class TwoFidelityCLITests(unittest.TestCase):
    write = development_cli.DevelopmentCLITests.write
    advice = development_cli.DevelopmentCLITests.advice

    def setUp(self):
        development_cli.DevelopmentCLITests.setUp(self)
        self.write("graph.json", {"nodes": [node("a"), node("b")], "edges": []})

    def test_real_cli_opt_in_and_default_are_separate(self):
        tree = context(leaf("a", 8), leaf("b", 4))
        for record in tree["tree"]["nodes"][1:]:
            record["candidate_id"] = record["id"] + ":" + record["id"] + "-test"
        self.write("manual.json", {"decision": "choose", "two_fidelity": tree})
        answer, search = self.advice("--research-context", str(self.root / "manual.json"))
        recommendation = next(row for row in answer["recommendations"] if "search" in row)
        selection = recommendation["two_fidelity_selection"]
        self.assertEqual(selection["candidate_id"], "a:a-test")
        self.assertEqual(selection["status"], "SEPARATED")
        self.assertFalse(selection["execution_authorized"])
        self.assertEqual(recommendation["assurance"], "HEURISTIC_ONLY")
        self.assertEqual(len(search["candidates"]), 2)
        self.assertTrue(all(row["evidence_status"] == "INPUT_REPORTED" for row in selection["provenance"]))
        self.write("manual.json", {"decision": "choose"})
        default, _ = self.advice("--research-context", str(self.root / "manual.json"))
        self.assertFalse(any("two_fidelity_selection" in row for row in default["recommendations"]))
        self.assertFalse((self.root / ".rds").exists())

    def test_artifact_merge_keeps_planner_but_unknown_graph_facts_block_it(self):
        tree = context(leaf("a", 8), leaf("b", 4))
        for record in tree["tree"]["nodes"][1:]:
            record["candidate_id"] = record["id"] + ":" + record["id"] + "-test"
        self.write("manual.json", {"two_fidelity": tree})
        graph = {"nodes": [node("a", [{"fact": "missing", "value": True}]),
                           node("b", [{"fact": "missing", "value": True}])], "edges": []}
        self.write("graph.json", graph)
        answer, search = self.advice("--artifacts", str(self.root / "manifest.json"),
                                    "--research-context", str(self.root / "manual.json"))
        selection = next(row["two_fidelity_selection"] for row in answer["recommendations"] if "search" in row)
        self.assertIsNone(selection["candidate_id"])
        self.assertFalse(selection["execution_authorized"])
        self.assertEqual(selection["status"], "NEEDS_EVIDENCE")
        self.assertTrue(all(row["status"] == "NEEDS_EVIDENCE" for row in search["candidates"]))


if __name__ == "__main__":
    unittest.main()

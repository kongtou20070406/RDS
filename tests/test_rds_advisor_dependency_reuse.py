"""Operation-local graph reuse must preserve current candidate review and evidence."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_advisor_search as search_module
import rds_hypergraph
from rds_advisor import RDSAdvisor


def fixture():
    action = {"kind": "OBLIGATION_CHECK", "target": "lemma", "claim": "A scoped synthetic lemma",
              "description": "Inspect a declared premise", "required_observables": ["proof-result"],
              "outcomes": [{"observation": label, "next_decision": "review " + label}
                           for label in ("verified", "counterexample", "unresolved")],
              "goal_contribution": {"target": "goal", "path": ["lemma", "goal"], "source": "fixture"}}
    graph = {"nodes": [{"id": "route" + str(i), "executable": {"decisions": ["next"],
                "preconditions": [], "action": {**deepcopy(action), "id": "inspect" + str(i)}}}
                       for i in range(3)], "edges": []}
    context = {"research_mode": "theory", "decision": {"id": "next", "goal_revision": "g1",
                "scope": {"domain": "synthetic"}, "goal_conditions": [{"fact": "goal", "value": True}]},
               "facts": {"goal": {"value": False, "source": "fixture"}},
               "dependency_map": {"schema": 1,
                   "nodes": [{"id": name, "status": "UNKNOWN", "source": "fixture"}
                             for name in ("lemma", "goal")],
                   "hyperedges": [{"id": "bridge", "premises": ["lemma"], "conclusion": "goal",
                                   "status": "SUPPORTED", "source": "fixture"}], "goals": ["goal"]}}
    return graph, context


class DependencyReuseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.advisor = RDSAdvisor.__new__(RDSAdvisor)
        self.advisor.root_dir = Path(self.directory.name)

    def recommend(self, graph, context):
        advice = self.advisor.recommend_next_directions({"advisor_context": context}, graph)
        return next(row["search"] for row in advice if row["type"] == "EXECUTABLE_DIRECTION_SEARCH")

    def test_search_and_advisor_with_templates_analyze_once(self):
        for consumer in (search_module.search_directions, self.recommend):
            for templates in (None, []):
                with self.subTest(consumer=consumer.__name__, templates=templates):
                    graph, context = fixture()
                    if templates is not None:
                        context["templates"] = templates
                    before = deepcopy((graph, context))
                    with patch.object(search_module, "_dependency_review", wraps=search_module._dependency_review) as review, \
                         patch.object(rds_hypergraph, "analyze_hypergraph", wraps=rds_hypergraph.analyze_hypergraph) as analyze:
                        result = consumer(graph, context)
                    self.assertEqual(review.call_count, 1)
                    self.assertEqual(analyze.call_count, 1)
                    self.assertEqual(result["selection_review"]["ready_graph_directions"], 3)
                    self.assertEqual(result["selection_review"]["authorization"], "UNCHANGED")
                    self.assertEqual((graph, context), before)

    def test_history_filter_still_changes_final_selection(self):
        graph, context = fixture()
        initial = []

        def filter_history(state, current, result):
            initial.append(len(result["candidates"]))
            self.assertNotIn("selection_review", result)
            result["candidates"].clear()
            result["ranking"]["dominance"].clear()
            return None

        with patch.object(self.advisor, "_review_loop_history", side_effect=filter_history), \
             patch.object(rds_hypergraph, "analyze_hypergraph", wraps=rds_hypergraph.analyze_hypergraph) as analyze:
            result = self.recommend(graph, context)
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(initial[0], 3)
        self.assertEqual(result["selection_review"]["ready_graph_directions"], 0)
        self.assertEqual(result["selection_review"]["basis"], "NO_READY_DIRECTION")
        self.assertEqual(result["selection_review"]["candidates"], [])

    def test_next_operation_rechecks_changed_graph_and_ignores_reported_cache(self):
        graph, context = fixture()
        context["selection_review"] = {"dependency_review": {"status": "ANALYZED"}}
        context["_dependency"] = {"status": "ANALYZED"}
        with patch.object(rds_hypergraph, "analyze_hypergraph", wraps=rds_hypergraph.analyze_hypergraph) as analyze:
            first = self.recommend(graph, context)["selection_review"]
            context["dependency_map"]["nodes"][0]["status"] = "CONTRADICTED"
            second = self.recommend(graph, context)["selection_review"]
        self.assertEqual(analyze.call_count, 2)
        self.assertNotEqual(first["dependency_review"]["input_sha256"], second["dependency_review"]["input_sha256"])
        self.assertEqual(first["candidates"][0]["goal_contribution"]["graph_path"]["status"], "DECLARED_CONNECTED_PATH")
        self.assertEqual(second["candidates"][0]["goal_contribution"]["status"], "UNKNOWN")
        self.assertIn("GOAL_CONTRIBUTION_INVALID", [row["kind"] for row in second["flags"]])

    def test_snapshot_and_returned_reports_are_independent(self):
        graph, context = fixture()
        dependency = search_module._operation_dependency(context)
        original_map = deepcopy(context["dependency_map"])
        context["dependency_map"]["nodes"][0]["status"] = "CONTRADICTED"
        first = search_module.review_selection({"candidates": []}, context, _dependency=dependency)
        expected = search_module._dependency_review({"dependency_map": original_map})
        self.assertEqual(first["dependency_review"], expected)
        first["dependency_review"]["reported_nodes"][0]["status"] = "CONTRADICTED"
        second = search_module.review_selection({"candidates": []}, context, _dependency=dependency)
        self.assertEqual(second["dependency_review"], expected)
        graph, context = fixture()
        context["templates"] = []
        result = self.recommend(graph, context)
        nested = result["experiment_composition"]["rule_search"]["selection_review"]["dependency_review"]
        final = result["selection_review"]["dependency_review"]
        nested["reported_nodes"][0]["status"] = "CONTRADICTED"
        self.assertEqual(final["reported_nodes"][0]["status"], "UNKNOWN")
        self.assertEqual(context["dependency_map"]["nodes"][0]["status"], "UNKNOWN")

    def test_no_graph_and_invalid_or_oversized_graph_keep_existing_semantics(self):
        for spec in (None, {}, {"padding": "x" * (128 * 1024)}, {"bad": float("nan")}):
            with self.subTest(spec_type=type(spec).__name__):
                graph, context = fixture()
                if spec is None:
                    context.pop("dependency_map")
                else:
                    context["dependency_map"] = spec
                context["templates"] = []
                expected = search_module._dependency_review(context)
                with patch.object(search_module, "_dependency_review", wraps=search_module._dependency_review) as review:
                    result = self.recommend(graph, context)["selection_review"]
                if spec is None:
                    self.assertNotIn("dependency_review", result)
                else:
                    self.assertEqual(review.call_count, 1)
                    self.assertEqual(result["dependency_review"], expected)
                    self.assertEqual(result["dependency_review"]["status"], "UNKNOWN")

    def test_real_template_uses_same_analysis_without_copying_unrelated_facts(self):
        graph, context = fixture()
        template = json.loads((ROOT / "examples/experiment-templates/templates.json").read_text(encoding="utf-8"))["templates"][0]
        template["rules"], template["decisions"] = ["route0"], ["next"]
        context["templates"] = [template]
        context["target_types"] = {"claimed_route_enabled": "boolean"}
        with patch.object(rds_hypergraph, "analyze_hypergraph", wraps=rds_hypergraph.analyze_hypergraph) as analyze:
            result = self.recommend(graph, context)
        self.assertEqual(analyze.call_count, 1)
        self.assertIn("rule_search", result["experiment_composition"])
        self.assertEqual(result["experiment_composition"]["rule_search"]["selection_review"]["ready_graph_directions"], 3)

    def test_real_cli_preserves_bounded_review_and_input(self):
        graph, context = fixture()
        context["templates"] = []
        directory = Path(self.directory.name)
        graph_path, context_path = directory / "graph.json", directory / "context.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        context_path.write_text(json.dumps(context), encoding="utf-8")
        command = [sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"), "--root", str(directory), "advise",
                   "--research-context", str(context_path), "--graph", str(graph_path)]
        proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        search = next(row["search"] for row in report["recommendations"] if row["type"] == "EXECUTABLE_DIRECTION_SEARCH")
        self.assertEqual(search["selection_review"]["ready_graph_directions"], 3)
        self.assertEqual(search["selection_review"]["dependency_review"]["authorization"], "UNCHANGED")
        self.assertEqual(json.loads(context_path.read_text(encoding="utf-8")), context)


if __name__ == "__main__":
    unittest.main()

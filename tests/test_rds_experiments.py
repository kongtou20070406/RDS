"""Finite proposal composition must preserve evidence and intervention identity."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_experiments import compose_experiments, validate_template
from rds_advisor_search import search_directions, evaluate_condition, _cost


def fixture():
    templates = json.loads((ROOT / "examples/experiment-templates/templates.json").read_text(encoding="utf-8"))["templates"]
    for template in templates:
        template["rules"] = ["rule-a" if template["id"] == "disable-claimed-route" else "rule-b"]
    nodes = []
    for rid in ("rule-a", "rule-b"):
        nodes.append({"id": rid, "sources": ["declared test fixture"], "executable": {
            "decisions": ["mechanism-attribution"], "preconditions": [{"fact": "matched_recipe", "op": "eq", "value": True}],
            "action": {"id": rid + "-check", "description": "Review a matched comparison",
                       "competing_explanations": ["mechanism", "alternative"], "required_observables": ["primary metric"],
                       "outcomes": [{"observation": "gain", "next_decision": "continue"},
                                    {"observation": "no gain", "next_decision": "revise"}]}}})
    context = {"decision": "mechanism-attribution", "target_types": {
        "claimed_route_enabled": "boolean", "normalized_row_mass": "number"}, "facts": {
            name: {"value": True, "source": "fixture:" + name}
            for name in ("matched_recipe", "same_data_split", "same_primary_metric")}}
    context["facts"]["baseline_receipt"] = {"value": "control-1", "source": "fixture:control"}
    return {"nodes": nodes, "edges": []}, context, templates


class ExperimentTests(unittest.TestCase):
    def test_constraint_aware_composition_keeps_all_steps_and_distinct_alias_methods(self):
        graph, context, templates = fixture()
        context['method_constraints'] = [{'id': 'search', 'quote': 'No heuristic candidate search',
            'source': 'user:fixture', 'status': 'CONFIRMED', 'when': {'purpose': 'candidate_search'},
            'forbid': {'technique': 'heuristic'}}]
        for node in graph['nodes']:
            node['executable']['action']['methods'] = {'purpose': 'verification'}
        first = deepcopy(templates[0])
        first['methods'] = {'purpose': 'proof'}
        alias = deepcopy(first)
        alias['id'] = 'heuristic-alias'
        alias['methods'] = [{'purpose': 'proof'}, {'purpose': 'candidate_search', 'technique': 'heuristic'}]
        report = compose_experiments(graph, context, [first, alias])
        self.assertEqual(len(report['candidates']), 2)
        compatible = [c for c in report['candidates'] if c['method_review']['status'] == 'COMPATIBLE']
        blocked = [c for c in report['candidates'] if c['status'] == 'BLOCKED_METHOD']
        self.assertEqual(len(compatible), 1)
        self.assertEqual(compatible[0]['template_ids'], [first['id']])
        self.assertEqual(len(blocked), 1)
        self.assertIn(alias['id'], blocked[0]['template_ids'])
        self.assertNotEqual(compatible[0]['id'], blocked[0]['id'])

    def test_distinct_interventions_and_unknown_future_measurements(self):
        graph, context, templates = fixture()
        before = deepcopy((graph, context, templates))
        report = compose_experiments(graph, context, templates)
        singleton = [c for c in report["candidates"] if len(c["interventions"]) == 1]
        self.assertEqual({i["target"]["name"] for c in singleton for i in c["interventions"]},
                         {"claimed_route_enabled", "normalized_row_mass"})
        self.assertTrue(all(c["candidate_only"] and not c["execution_authorized"] for c in report["candidates"]))
        self.assertTrue(all(o["truth"] == "UNKNOWN" for c in report["candidates"] for o in c["observables"]))
        self.assertTrue(all(c["incremental_cost"]["status"] == "UNKNOWN" for c in report["candidates"]))
        self.assertTrue(all(c["rule_ids"] and c["derivation"] for c in report["candidates"]))
        self.assertEqual((graph, context, templates), before)
        def assert_no_estimates(value):
            if isinstance(value, dict):
                self.assertFalse({"probability", "information_gain", "eig"} & set(value))
                for item in value.values():
                    assert_no_estimates(item)
            elif isinstance(value, list):
                for item in value:
                    assert_no_estimates(item)
        assert_no_estimates(report)

    def test_false_invariant_and_incompatible_type_block_proposal(self):
        graph, context, templates = fixture()
        context["facts"]["same_data_split"]["value"] = False
        report = compose_experiments(graph, context, templates)
        self.assertEqual(report["candidates"], [])
        self.assertEqual(len(report["blocked_templates"]), 2)
        context["facts"]["same_data_split"]["value"] = True
        context["target_types"]["claimed_route_enabled"] = "number"
        report = compose_experiments(graph, context, templates)
        self.assertTrue(any(c["reason"] == "incompatible target type" for c in report["blocked_templates"]))
        self.assertFalse(any(i["target"]["name"] == "claimed_route_enabled" for c in report["candidates"] for i in c["interventions"]))

    def test_target_conflicts_excluded_and_alias_interventions_deduplicated(self):
        graph, context, templates = fixture()
        first = templates[0]
        alias = deepcopy(first)
        alias["id"] = "route-alias"
        report = compose_experiments(graph, context, [first, alias])
        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(set(report["candidates"][0]["template_ids"]), {first["id"], alias["id"]})
        alias["intervention"]["choices"] = [True]
        report = compose_experiments(graph, context, [first, alias])
        self.assertEqual(len(report["candidates"]), 2)
        self.assertTrue(any("same target" in c["reason"] for c in report["excluded_combinations"]))

    def test_bounds_report_truncation_and_unknown_types_remain_unknown(self):
        graph, context, templates = fixture()
        report = compose_experiments(graph, context, templates, max_combinations=1)
        self.assertEqual(report["combinations_examined"], 1)
        self.assertTrue(report["truncation"]["truncated"])
        report = compose_experiments(graph, context, templates, max_candidates=1)
        self.assertEqual(len(report["candidates"]), 1)
        self.assertIn("candidate limit", report["truncation"]["reasons"])
        report = compose_experiments(graph, context, templates, max_depth=1)
        self.assertIn("depth limit", report["truncation"]["reasons"])
        context.pop("target_types")
        self.assertTrue(all(c["status"] == "NEEDS_EVIDENCE" for c in compose_experiments(graph, context, templates)["candidates"]))

    def test_sourced_cost_does_not_bypass_budget_or_unknown_observables(self):
        graph, context, templates = fixture()
        rid = templates[0]["cost"]["record_id"]
        context["costs"] = {rid: {"value": 5, "unit": "seconds", "comparison_group": "cpu-fixture", "source": "fixture:elapsed"}}
        context["budget"] = {"value": 3, "unit": "seconds", "comparison_group": "cpu-fixture", "source": "fixture:budget"}
        candidate = compose_experiments(graph, context, templates[:1])["candidates"][0]
        self.assertEqual(candidate["status"], "BLOCKED_BUDGET")
        self.assertEqual(candidate["observables"][0]["truth"], "UNKNOWN")

    def test_existing_search_composes_only_when_explicitly_requested(self):
        graph, context, templates = fixture()
        self.assertNotIn("experiment_composition", search_directions(graph, context))
        report = search_directions(graph, {**context, "templates": templates})
        self.assertTrue(report["experiment_composition"]["candidates"])
        bad = deepcopy(templates[0])
        bad["intervention"]["choices"] = [1]
        with self.assertRaises(ValueError):
            validate_template(bad)
        bad["intervention"] = []
        with self.assertRaises(ValueError):
            validate_template(bad)

    def test_resource_budget_only_binds_matching_interventions(self):
        graph, context, templates = fixture()
        rid = templates[0]["cost"]["record_id"]
        context["costs"] = {rid: {"value": 5, "resource": "gpu", "unit": "seconds",
                                  "comparison_group": "same-trial", "source": "fixture:elapsed"}}
        context["budget"] = {"value": 3, "resource": "cpu", "unit": "seconds",
                             "comparison_group": "same-trial", "source": "fixture:budget"}
        candidate = compose_experiments(graph, context, templates[:1])["candidates"][0]
        self.assertEqual(candidate["incremental_cost"]["resource"], "gpu")
        self.assertEqual(candidate["budget_status"], "UNKNOWN")
        self.assertNotEqual(candidate["status"], "BLOCKED_BUDGET")
        context["budget"]["resource"] = "gpu"
        self.assertEqual(compose_experiments(graph, context, templates[:1])["candidates"][0]["status"], "BLOCKED_BUDGET")
        context["budget"].pop("resource")
        self.assertEqual(compose_experiments(graph, context, templates[:1])["candidates"][0]["budget_status"], "UNKNOWN")

    def test_composition_keeps_mixed_resource_totals_unknown(self):
        graph, context, templates = fixture()
        context["costs"] = {t["cost"]["record_id"]: {"value": 2, "resource": resource, "unit": "seconds",
                            "comparison_group": "same-trial", "source": "fixture:elapsed"}
                            for t, resource in zip(templates, ("cpu", "gpu"))}
        context["budget"] = {"value": 3, "resource": "cpu", "unit": "seconds",
                             "comparison_group": "same-trial", "source": "fixture:budget"}
        report = compose_experiments(graph, context, templates)
        mixed = [c for c in report["candidates"] if len(c["interventions"]) == 2]
        self.assertTrue(mixed)
        self.assertTrue(all(c["incremental_cost"]["status"] == "UNKNOWN" and c["budget_status"] == "UNKNOWN" for c in mixed))
        for cost in context["costs"].values():
            cost["resource"] = "cpu"
        combined = [c for c in compose_experiments(graph, context, templates)["candidates"] if len(c["interventions"]) == 2]
        self.assertTrue(all((c["incremental_cost"]["value"], c["incremental_cost"]["resource"], c["status"])
                            == (4, "cpu", "BLOCKED_BUDGET") for c in combined))

    def test_versioned_pack_and_early_return_preserve_limits(self):
        graph, context, templates = fixture()
        for schema in (None, 2, True):
            with self.subTest(schema=schema), self.assertRaisesRegex(ValueError, "schema 1"):
                compose_experiments(graph, context, {"schema": schema, "templates": templates})
        report = search_directions(graph, {"templates": {"schema": 1, "templates": templates}}, max_nodes=1)
        self.assertTrue(report["truncation"]["truncated"])
        self.assertEqual(report["experiment_composition"]["candidates"], [])
        self.assertIn("node limit", report["experiment_composition"]["truncation"]["reasons"])

    def test_imported_provenance_cannot_be_claimed_by_a_json_flag(self):
        from rds_artifacts import ArtifactFact
        observed = ArtifactFact({"kind": "OBSERVED", "value": 2, "unit": "seconds",
                                "comparison_group": "cpu", "source": {"path": "fixture", "locator": "elapsed"}})
        facts = {"elapsed": observed}
        self.assertEqual(evaluate_condition({"fact": "elapsed", "value": 2}, facts)["evidence_status"], "ARTIFACT_OBSERVED")
        self.assertEqual(_cost(["elapsed"], facts)["evidence_statuses"], ["ARTIFACT_OBSERVED"])
        forged = dict(observed, provenance_status="ARTIFACT_OBSERVED")
        self.assertEqual(evaluate_condition({"fact": "elapsed", "value": 2}, {"elapsed": forged})["evidence_status"], "INPUT_REPORTED")
        observed.update(value=None, reliable=False)
        self.assertEqual(evaluate_condition({"fact": "elapsed", "value": 2}, facts)["truth"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

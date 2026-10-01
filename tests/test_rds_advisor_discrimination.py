"""Conditional rival coverage; the scalar fixture checks software behavior only."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_advisor_search import search_directions

FAULTS = ["optimizer_step_omitted", "zero_lr", "incorrect_targets"]
SOURCE = {"path": "tests/test_rds_advisor_discrimination.py", "locator": "scalar_fault"}
UPDATE = {FAULTS[0]: ["no optimizer step"], FAULTS[1]: ["optimizer step called"],
          FAULTS[2]: ["optimizer step called"]}
TARGET = {FAULTS[0]: ["canonical target"], FAULTS[1]: ["canonical target"],
          FAULTS[2]: ["incorrect target"]}


def scalar_fault(fault):
    """One actual CPU gradient step on (weight * 1 - target)**2, without ML dependencies."""
    weight, canonical_target = 0.0, 1.0
    target = -1.0 if fault == "incorrect_targets" else canonical_target
    learning_rate = 0.0 if fault == "zero_lr" else 0.25
    optimizer_calls = 0
    gradient = 2 * (weight - target)
    if fault != "optimizer_step_omitted":
        optimizer_calls += 1
        weight -= learning_rate * gradient
    return {"weight": weight, "update": "optimizer step called" if optimizer_calls else "no optimizer step",
            "target": "canonical target" if target == canonical_target else "incorrect target"}


def probe(name, predictions):
    labels = sorted({label for values in predictions.values() for label in values})
    return {"id": name, "executable": {"decisions": ["diagnose"], "preconditions": [],
            "action": {"id": name + "-check", "description": "Read " + name + " evidence",
                       "competing_explanations": list(FAULTS), "required_observables": [name],
                       "outcomes": [{"observation": label, "next_decision": "inspect" if i == 0 else "repair"}
                                    for i, label in enumerate(labels)],
                       "discrimination": {"scope_id": "single-scalar-step-v1", "source": deepcopy(SOURCE),
                                          "predictions": deepcopy(predictions)}}}}


def fixture():
    graph = {"nodes": [probe("update", UPDATE), probe("target", TARGET)], "edges": []}
    context = {"decision": "diagnose", "facts": {}, "costs": {
        name + "-check": {"value": value, "resource": "cpu", "unit": "seconds",
                          "comparison_group": "declared-fixture-cost", "source": "synthetic test cost"}
        for name, value in (("update", 1), ("target", 2))}}
    return graph, context


def candidates(report):
    return {candidate["rule_id"]: candidate for candidate in report["candidates"]}


class DiscriminationTests(unittest.TestCase):
    def test_cpu_fault_observations_support_distinct_pair_frontiers(self):
        observations = {fault: scalar_fault(fault) for fault in FAULTS}
        self.assertEqual([observations[fault]["weight"] for fault in FAULTS], [0.0, 0.0, -0.5])
        for fault in FAULTS:
            self.assertIn(observations[fault]["update"], UPDATE[fault])
            self.assertIn(observations[fault]["target"], TARGET[fault])
        graph, context = fixture()
        original = deepcopy((graph, context))
        report = search_directions(graph, context)
        selected = candidates(report)
        coverage = lambda name: {frozenset(pair) for pair in selected[name]["discrimination"]["conditional_distinguishing_pairs"]}
        self.assertEqual(coverage("update"), {frozenset((FAULTS[0], FAULTS[1])), frozenset((FAULTS[0], FAULTS[2]))})
        self.assertEqual(coverage("target"), {frozenset((FAULTS[0], FAULTS[2])), frozenset((FAULTS[1], FAULTS[2]))})
        self.assertEqual(set(report["ranking"]["pareto_front"]), {"update:update-check", "target:target-check"})
        self.assertEqual(report["ranking"]["dominance"], [])
        self.assertEqual(selected["update"]["discrimination"]["source"], SOURCE)
        self.assertEqual(selected["update"]["discrimination"]["evidence_status"], "INPUT_REPORTED")
        self.assertEqual((graph, context), original)

    def test_same_pair_coverage_and_lower_cost_allows_dominance(self):
        graph, context = fixture()
        graph["nodes"][1] = probe("target", UPDATE)
        for outcome in graph["nodes"][1]["executable"]["action"]["outcomes"]:
            outcome["next_decision"] = "alternative wording: " + outcome["next_decision"]
        report = search_directions(graph, context)
        self.assertEqual(report["ranking"]["pareto_front"], ["update:update-check"])
        self.assertEqual(candidates(report)["target"]["dominated_by"], ["update:update-check"])
        self.assertIn("conditional distinguishing pairs", report["ranking"]["dominance"][0]["basis"])
        self.assertNotIn("observed", report["ranking"]["dominance"][0]["basis"])

    def test_extra_decision_labels_do_not_improve_equal_scientific_coverage(self):
        graph, context = fixture()
        graph["nodes"][1] = probe("target", UPDATE)
        graph["nodes"][0]["executable"]["action"]["outcomes"].append(
            {"observation": "other observation", "next_decision": "a third decision label"})
        context["costs"]["target-check"]["value"] = 1
        report = search_directions(graph, context)
        self.assertGreater(len(candidates(report)["update"]["decision_coverage"]),
                           len(candidates(report)["target"]["decision_coverage"]))
        self.assertEqual(report["ranking"]["dominance"], [])
        self.assertEqual(len(report["ranking"]["pareto_front"]), 2)

    def test_strict_pair_superset_is_an_improvement_at_equal_cost(self):
        graph, context = fixture()
        graph["nodes"][0] = probe("update", {fault: [fault] for fault in FAULTS})
        context["costs"]["target-check"]["value"] = 1
        report = search_directions(graph, context)
        self.assertEqual(report["ranking"]["pareto_front"], ["update:update-check"])
        self.assertEqual(candidates(report)["target"]["dominated_by"], ["update:update-check"])

    def test_more_scientific_coverage_at_higher_cost_preserves_the_tradeoff(self):
        graph, context = fixture()
        graph["nodes"][0] = probe("update", {fault: [fault] for fault in FAULTS})
        context["costs"]["update-check"]["value"] = 3
        report = search_directions(graph, context)
        self.assertEqual(report["ranking"]["dominance"], [])
        self.assertEqual(len(report["ranking"]["pareto_front"]), 2)

    def test_unknown_cost_is_not_zero_for_comparable_scientific_coverage(self):
        graph, context = fixture()
        graph["nodes"][1] = probe("target", UPDATE)
        context["costs"].pop("update-check")
        report = search_directions(graph, context)
        cost = candidates(report)["update"]["incremental_cost"]
        self.assertEqual(cost["status"], "UNKNOWN")
        self.assertNotIn("value", cost)
        self.assertEqual(report["ranking"]["cost_unknown"], ["update:update-check"])
        self.assertEqual(report["ranking"]["dominance"], [])
        self.assertEqual(len(report["ranking"]["pareto_front"]), 2)

    def test_all_overlapping_predictions_are_unresolved_and_do_not_support_dominance(self):
        graph, context = fixture()
        predictions = graph["nodes"][0]["executable"]["action"]["discrimination"]["predictions"]
        predictions[FAULTS[1]] = ["no optimizer step", "optimizer step called"]
        report = search_directions(graph, context)
        distinction = candidates(report)["update"]["discrimination"]
        self.assertEqual({frozenset(pair) for pair in distinction["conditional_distinguishing_pairs"]},
                         {frozenset((FAULTS[0], FAULTS[2]))})
        self.assertEqual(len(distinction["unresolved_pairs"]), 2)
        self.assertEqual(report["ranking"]["dominance"], [])
        graph, context = fixture()
        for node in graph["nodes"]:
            action = node["executable"]["action"]
            common_label = action["outcomes"][0]["observation"]
            action["discrimination"]["predictions"] = {fault: [common_label] for fault in FAULTS}
        report = search_directions(graph, context)
        self.assertEqual(report["ranking"]["dominance"], [])
        for candidate in report["candidates"]:
            distinction = candidate["discrimination"]
            self.assertTrue(distinction["valid_prediction_support"])
            self.assertEqual(distinction["conditional_distinguishing_pairs"], [])
            self.assertEqual(len(distinction["unresolved_pairs"]), 3)
            self.assertTrue(all(pair["reason"] == "allowed predictions overlap" for pair in distinction["unresolved_pairs"]))

    def test_missing_invalid_or_unreliable_prediction_support_is_unresolved(self):
        for invalid in ("source", "unreliable", "scope", "missing explanation", "unknown explanation", "unknown observation"):
            with self.subTest(invalid=invalid):
                graph, context = fixture()
                spec = graph["nodes"][0]["executable"]["action"]["discrimination"]
                if invalid == "source":
                    spec.pop("source")
                elif invalid == "unreliable":
                    spec["reliable"] = False
                elif invalid == "scope":
                    spec.pop("scope_id")
                elif invalid == "missing explanation":
                    spec["predictions"].pop(FAULTS[0])
                elif invalid == "unknown explanation":
                    spec["predictions"]["unmodeled"] = ["no optimizer step"]
                else:
                    spec["predictions"][FAULTS[0]] = ["unrecorded label"]
                report = search_directions(graph, context)
                distinction = candidates(report)["update"]["discrimination"]
                self.assertFalse(distinction["valid_prediction_support"])
                self.assertEqual(distinction["conditional_distinguishing_pairs"], [])
                self.assertEqual(len(distinction["unresolved_pairs"]), 3)
                self.assertTrue(distinction["issues"])
                self.assertEqual(report["ranking"]["dominance"], [])

    def test_condition_truth_and_source_are_traced_without_guessing_applicability(self):
        for value, truth in ((True, "TRUE"), (False, "FALSE"), (None, "UNKNOWN")):
            with self.subTest(value=value):
                graph, context = fixture()
                graph["nodes"][1] = probe("target", UPDATE)
                for node in graph["nodes"]:
                    node["executable"]["action"]["discrimination"]["conditions"] = [{"fact": "same_recipe", "value": True}]
                if value is not None:
                    context["facts"]["same_recipe"] = {"value": value, "source": "fixture recipe identity"}
                report = search_directions(graph, context)
                distinction = candidates(report)["update"]["discrimination"]
                self.assertEqual(distinction["applicability"], truth)
                self.assertEqual(distinction["conditions"][0]["truth"], truth)
                self.assertEqual(distinction["valid_prediction_support"], value is True)
                if value is True:
                    self.assertEqual(distinction["conditions"][0]["source"], "fixture recipe identity")
                    self.assertEqual(report["ranking"]["pareto_front"], ["update:update-check"])
                else:
                    self.assertEqual(distinction["conditional_distinguishing_pairs"], [])
                    self.assertEqual(report["ranking"]["dominance"], [])

    def test_different_scope_explanation_universe_or_legacy_action_stays_incomparable(self):
        for mismatch in ("scope", "explanations", "legacy"):
            with self.subTest(mismatch=mismatch):
                graph, context = fixture()
                graph["nodes"][1] = probe("target", UPDATE)
                action = graph["nodes"][1]["executable"]["action"]
                if mismatch == "scope":
                    action["discrimination"]["scope_id"] = "another-training-recipe"
                elif mismatch == "explanations":
                    action["competing_explanations"].remove(FAULTS[2])
                    action["discrimination"]["predictions"].pop(FAULTS[2])
                else:
                    action.pop("discrimination")
                report = search_directions(graph, context)
                self.assertEqual(report["ranking"]["dominance"], [])
                self.assertEqual(len(report["ranking"]["pareto_front"]), 2)

    def test_both_legacy_actions_stay_incomparable_without_scientific_support(self):
        graph, context = fixture()
        for node in graph["nodes"]:
            node["executable"]["action"].pop("discrimination")
        report = search_directions(graph, context)
        self.assertEqual(report["ranking"]["dominance"], [])
        self.assertEqual(set(report["ranking"]["pareto_front"]), {"update:update-check", "target:target-check"})
        self.assertTrue(all("discrimination" not in candidate for candidate in report["candidates"]))

    def test_malformed_operator_does_not_suppress_other_candidates(self):
        for operator in ([], {}, None, 1, 'unknown'):
            with self.subTest(operator=operator):
                graph, context = fixture()
                graph['nodes'][0]['executable']['action']['discrimination']['conditions'] = [
                    {'fact': 'same_recipe', 'op': operator, 'value': True}]
                context['facts']['same_recipe'] = {'value': True, 'source': 'fixture recipe identity'}
                report = search_directions(graph, context)
                self.assertEqual(len(report['candidates']), 2)
                distinction = candidates(report)['update']['discrimination']
                self.assertFalse(distinction['valid_prediction_support'])
                self.assertEqual(distinction['applicability'], 'UNKNOWN')
                self.assertEqual(distinction['conditional_distinguishing_pairs'], [])
                self.assertEqual(len(distinction['unresolved_pairs']), 3)
                self.assertTrue(candidates(report)['target']['discrimination']['valid_prediction_support'])
                self.assertEqual(report['ranking']['dominance'], [])

    def test_malformed_and_over_limit_conditions_cannot_claim_coverage(self):
        for conditions in (["not a predicate"], [{"fact": "same_recipe", "value": True}] * 33):
            with self.subTest(condition_count=len(conditions)):
                graph, context = fixture()
                graph["nodes"][0]["executable"]["action"]["discrimination"]["conditions"] = conditions
                context["facts"]["same_recipe"] = {"value": True, "source": "fixture recipe identity"}
                report = search_directions(graph, context)
                distinction = candidates(report)["update"]["discrimination"]
                self.assertFalse(distinction["valid_prediction_support"])
                self.assertEqual(distinction["applicability"], "UNKNOWN")
                self.assertEqual(report["ranking"]["dominance"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Deterministic trust-boundary and interval-policy checks; no MC utility claim."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_artifacts import ArtifactFact
from rds_two_fidelity import anytime_radius, select_next


def evidence(**values):
    return {"source": "synthetic-fixture", "unit": "reward", "scope": "finite-fixture", **values}


def cost(amount=1, **extra):
    return {"value": amount, "status": "ESTIMATE", "source": "synthetic-cost",
            "resource": "cpu", "unit": "seconds", "comparison_group": "fixture", **extra}


def slow(samples=(), **extra):
    return evidence(**{"samples": list(samples), "sigma": 1, "bias_bound": 0, "iid": True,
                       "sub_gaussian": True, "targets_node_value": True, **extra})


def leaf(nid, value=None, bound=0, **extra):
    record = {"id": nid, "operator": "LEAF", "children": [], "candidate_id": nid,
              "status": "READY", "costs": {"slow": cost()}, **extra}
    if value is not None:
        record["fast"] = evidence(value=value, bias_bound=bound)
    return record


def context(a=None, b=None, **extra):
    return {"objective": {"direction": "MAX", "metric": "fixture reward", "unit": "reward", "scope": "finite-fixture"},
            "tree": {"root": "r", "nodes": [{"id": "r", "operator": "MAX", "children": ["a", "b"], "expanded": True},
                                         a or leaf("a", 5, 2), b or leaf("b", 4, 2)]},
            "delta": .05, "epsilon": 0,
            "budget": {"remaining": 10, "source": "synthetic-budget", "resource": "cpu", "unit": "seconds", "comparison_group": "fixture"}, **extra}


class TwoFidelityTests(unittest.TestCase):
    def test_single_point_misranking_requires_interval_evidence(self):
        c = context(leaf("a", 10, 5), leaf("b", 9))
        self.assertEqual(select_next(c)["status"], "NEEDS_EVIDENCE")
        c["tree"]["nodes"][1]["slow"] = slow([7], sigma=0)
        result = select_next(c)
        self.assertEqual((result["status"], result["candidate_id"]), ("SEPARATED", "b"))
        self.assertTrue(result["conditional_on_oracle_assumptions"])
        self.assertFalse(result["execution_authorized"])

    def test_two_tail_anytime_radius_and_node_allocation(self):
        expected = math.sqrt(2 * math.log(math.pi ** 2 / (3 * .025)))
        self.assertAlmostEqual(anytime_radius(1, 1, .025), expected)
        self.assertGreater(expected, math.sqrt(2 * math.log(math.pi ** 2 / (6 * .025))))
        c = context(leaf("a", slow=slow([0, 3])), leaf("b", -10))
        result = select_next(c)
        self.assertEqual(result["delta_v"], .025)
        self.assertAlmostEqual(result["root_intervals"]["a"]["upper"], expected)
        self.assertLess(expected, 1.5 + anytime_radius(2, 1, .025))

    def test_all_prefix_conflict_is_not_clipped_to_exact(self):
        result = select_next(context(leaf("a", slow=slow([0, 10], sigma=0)), leaf("b", 4)))
        self.assertEqual(result["status"], "CONFLICT")
        self.assertIsNone(result["candidate_id"])
        self.assertTrue(any("slow prefixes" in x["reason"] for x in result["conflicts"]))

    def test_fast_slow_and_children_conflicts_are_retained(self):
        c = context(leaf("a", 5, slow=slow([0], sigma=0)), leaf("b", 4))
        self.assertEqual(select_next(c)["status"], "CONFLICT")
        c["tree"]["nodes"][1] = {"id": "a", "operator": "MIN", "children": ["x"], "expanded": True,
                                    "candidate_id": "a", "status": "READY", "fast": evidence(value=5, bias_bound=0)}
        c["tree"]["nodes"].append(leaf("x", 0))
        self.assertEqual(select_next(c)["status"], "CONFLICT")

    def test_missing_fast_envelope_can_use_qualified_slow(self):
        c = context(leaf("a", slow=slow([8], sigma=0)), leaf("b", 4))
        self.assertEqual(select_next(c)["candidate_id"], "a")
        c["tree"]["nodes"][1]["slow"]["iid"] = False
        self.assertEqual(select_next(c)["status"], "NEEDS_EVIDENCE")
        c["tree"]["nodes"][1]["fast"] = evidence(value=8, bias_bound=0)
        self.assertEqual(select_next(c)["candidate_id"], "a")

    def test_missing_all_bounds_do_not_invent_values(self):
        result = select_next(context(leaf("a"), leaf("b")))
        self.assertEqual(result["status"], "NEEDS_EVIDENCE")
        self.assertIsNone(result["root_intervals"]["a"]["lower"])
        json.dumps(result, allow_nan=False)

    def test_epsilon_and_minimum_root_stop(self):
        c = context(leaf("a", 5, 1), leaf("b", 4, 1), epsilon=1)
        self.assertEqual(select_next(c)["status"], "SEPARATED")
        c["epsilon"] = .99
        self.assertEqual(select_next(c)["status"], "NEEDS_EVIDENCE")
        c["objective"]["direction"] = "MIN"
        c["tree"]["nodes"][0]["operator"] = "MIN"
        c["epsilon"] = 1
        self.assertEqual(select_next(c)["candidate_id"], "b")

    def test_only_ready_and_external_eligible_candidates_are_selected(self):
        c = context(leaf("a", 10, status="BLOCKED"), leaf("b", 4))
        self.assertEqual(select_next(c)["candidate_id"], "b")
        self.assertIsNone(select_next(c, eligible_ids=[])["candidate_id"])
        c["tree"]["nodes"][1]["status"] = "UNKNOWN"
        self.assertEqual(select_next(c, eligible_ids=["a", "b"])["candidate_id"], "b")
        c["tree"]["nodes"][1].pop("status")
        self.assertEqual(select_next(c, eligible_ids=["a"])["candidate_id"], "a")

    def test_source_identity_cannot_be_json_self_signed(self):
        c = context(leaf("a", slow=slow([{"fact_id": "x"}], sigma=0)), leaf("b", 4))
        raw = {"value": 8, "kind": "OBSERVED", "source": {"path": "fixture", "locator": "/x"}, "provenance_status": "ARTIFACT_OBSERVED"}
        result = select_next(c, {"x": raw})
        self.assertEqual(result["provenance"][0]["evidence_status"], "INPUT_REPORTED")
        imported = ArtifactFact(raw)
        result = select_next(c, {"x": imported})
        self.assertEqual(result["provenance"][0]["evidence_status"], "ARTIFACT_OBSERVED")
        self.assertEqual(result["provenance"][0]["protocol_status"], "SOURCE_PROTOCOL_UNVERIFIED")
        self.assertEqual(result["assurance"], "CONDITIONAL_ON_DECLARED_ORACLE_MODEL")

    def test_missing_source_or_fact_unit_scope_never_certifies(self):
        c = context(leaf("a", 8), leaf("b", 4))
        c["tree"]["nodes"][1]["fast"].pop("source")
        self.assertEqual(select_next(c)["status"], "NEEDS_EVIDENCE")
        c["tree"]["nodes"][1]["fast"] = evidence(fact_id="x", bias_bound=0)
        for field, bad in (("unit", "accuracy"), ("scope", "other dataset")):
            result = select_next(c, {"x": evidence(value=8, **{field: bad})})
            self.assertEqual(result["status"], "NEEDS_EVIDENCE")

    def test_protocol_binding_conflicts_override_manual_scope(self):
        c = context(leaf("a", slow=slow([{"fact_id": "x"}], sigma=0)), leaf("b", 4))
        c["objective"]["binding"] = {"data_sha256": "fixture-sha", "data_split": "test", "metric": {"definition": "reward"}}
        raw = evidence(value=8, kind="OBSERVED", binding={**c["objective"]["binding"], "data_split": "train"})
        self.assertEqual(select_next(c, {"x": ArtifactFact(raw)})["status"], "CONFLICT")
        raw["binding"] = copy.deepcopy(c["objective"]["binding"])
        self.assertEqual(select_next(c, {"x": ArtifactFact(raw)})["provenance"][0]["protocol_status"], "TARGET_BINDING_MATCH")

    def test_reused_fact_and_alias_locator_are_not_extra_iid_samples(self):
        raw = ArtifactFact(evidence(value=8, kind="OBSERVED", source={"path": "fixture", "sha256": "fixture-sha", "locator": "/x"}))
        for sample_ids in (("x", "x"), ("x", "alias")):
            c = context(leaf("a", slow=slow([{"fact_id": fid} for fid in sample_ids], sigma=0)), leaf("b", 4))
            result = select_next(c, {"x": raw, "alias": ArtifactFact(raw)})
            self.assertIsNone(result["root_intervals"]["a"]["lower"])
            self.assertTrue(any("repeated slow observation" in x["reason"] for x in result["pending_evidence"]))
        c = context(leaf("a", slow=slow([8, 8], sigma=0)), leaf("b", 4))
        self.assertEqual(select_next(c)["status"], "SEPARATED")

    def test_cost_budget_must_be_finite_future_and_same_resource(self):
        c = context(leaf("a", 5, 2, slow=slow()), leaf("b", 4, 2))
        self.assertEqual(select_next(c)["next_action"]["kind"], "SLOW_EVIDENCE")
        for extra in ({"historical": True}, {"prediction_status": "UNKNOWN"}, {"resource": "gpu"}, {"unit": "steps"}, {"comparison_group": "other"}, {"value": None}):
            changed = copy.deepcopy(c)
            changed["tree"]["nodes"][1]["costs"]["slow"].update(extra)
            self.assertEqual(select_next(changed)["status"], "NEEDS_EVIDENCE")
        c["budget"]["remaining"] = .5
        self.assertEqual(select_next(c)["status"], "BUDGET_INSUFFICIENT")
        c["budget"]["remaining"] = None
        self.assertEqual(select_next(c)["status"], "NEEDS_EVIDENCE")

    def test_bool_nonfinite_and_bad_shapes_report_invalid(self):
        for bad in (True, False, float("inf"), float("nan"), "5"):
            c = context()
            c["tree"]["nodes"][1]["fast"]["value"] = bad
            self.assertEqual(select_next(c)["status"], "INVALID")
        for name, bad in (("costs", None), ("costs", []), ("slow", []), ("interval", []), ("fast", None)):
            c = context()
            c["tree"]["nodes"][1][name] = bad
            expected = "NEEDS_EVIDENCE" if name == "fast" else "INVALID"
            self.assertEqual(select_next(c)["status"], expected)
        for field in ("sigma", "bias_bound"):
            c = context(leaf("a", slow=slow([1])), leaf("b", 4))
            c["tree"]["nodes"][1]["slow"][field] = True
            self.assertEqual(select_next(c)["status"], "INVALID")
        c = context()
        c["tree"]["nodes"][1]["costs"]["slow"]["value"] = True
        self.assertEqual(select_next(c)["status"], "INVALID")

    def test_bad_tree_cycles_shared_and_unreachable_children(self):
        for mutate in (lambda c: c["tree"]["nodes"][0].update(children=["a", "missing"]),
                       lambda c: c["tree"]["nodes"][0].update(children=["a", "a"]),
                       lambda c: c["tree"]["nodes"].append(leaf("extra")),
                       lambda c: c["tree"]["nodes"][1].update(operator="MIN", expanded=True, children=["r"])):
            c = context()
            mutate(c)
            self.assertEqual(select_next(c)["status"], "INVALID")

    def test_expand_then_replay_backup_without_mutating_input(self):
        a = {"id": "a", "candidate_id": "a", "status": "READY", "operator": "MIN", "children": ["x", "y"],
             "expanded": False, "fast": evidence(value=5, bias_bound=5), "slow": slow(), "costs": {"expand": cost(.5), "slow": cost(3)}}
        c = context(a, leaf("b", 4))
        c["tree"]["nodes"].extend([leaf("x", 8), leaf("y", 7)])
        original = copy.deepcopy(c)
        result = select_next(c)
        self.assertEqual(result["next_action"]["kind"], "FAST_EXPAND")
        self.assertEqual(c, original)
        c["tree"]["nodes"][1]["expanded"] = True
        self.assertEqual(select_next(c)["candidate_id"], "a")
        json.dumps(result, allow_nan=False)

    def test_four_endpoint_witness_cases(self):
        for operator, side, expected in (("MIN", "L", "x"), ("MAX", "U", "y"), ("MAX", "L", "y"), ("MIN", "U", "x")):
            direction = "MAX" if side == "L" else "MIN"
            a = {"id": "a", "candidate_id": "a", "status": "READY", "operator": operator,
                 "children": ["x", "y"], "expanded": True}
            c = context(a, leaf("b", 0 if direction == "MAX" else 20, 20))
            c["objective"]["direction"] = direction
            c["tree"]["nodes"][0]["operator"] = direction
            c["tree"]["nodes"].extend([leaf("x", 5, 3, slow=slow()), leaf("y", 8, 5, slow=slow())])
            # Make a the wider root obligation and b a narrower unresolved challenger.
            c["tree"]["nodes"][2]["fast"] = evidence(value=3 if direction == "MAX" else (14 if operator == "MAX" else 10), bias_bound=3)
            result = select_next(c)
            self.assertEqual(result["critical_witness"]["node_id"], expected, (operator, side, result))
            self.assertEqual(result["next_action"]["node_id"], expected)


if __name__ == "__main__":
    unittest.main()

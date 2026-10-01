"""Finite frontier calculations must not certify caller-reported science."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_frontier import discover_frontier


DAY = "1999-01-01"


def record(**fields):
    return {"source": {"locator": "explicit software fixture"}, "available_on": DAY, **fields}


def node(nid, kind="observation", **fields):
    return record(id=nid, kind=kind, **fields)


def edge(start, end, status="SUPPORTED", relation="predicts", **fields):
    return record(**{"from": start, "to": end, "relation": relation, "status": status, **fields})


def fixture():
    return {"schema_version": 1, "as_of": "2000-01-01", "nodes": [
        node("a", label="local diagnostic", description="Eight-step calculation"),
        node("model", "model"), node("target", "phenomenon", label="long-chain quality")],
        "edges": [], "goals": [record(id="goal", target="target", anchors=["a"], decision="explain")],
        "observations": [], "dimension_requests": [], "transfers": []}


def observation(**fields):
    return record(id="residual", model="model", node="target", observed=5, predicted=2,
                  tolerance=1, protocol={"observed_unit": "seconds", "predicted_unit": "seconds"}, **fields)


def add_dimensions(spec):
    spec["nodes"].extend([node("samples", dimensions={"N": 1}), node("time", dimensions={"T": 1}),
                          node("throughput", "quantity", dimensions={"N": 1, "T": -1})])
    spec["dimension_requests"].append(record(id="rate", target="throughput", variables=["samples", "time"], decision="measure"))


def transfer(**fields):
    return record(**{"id": "local-global", "from": "a", "to": "target", "decision": "test transfer",
                     "source_scope": {"runtime": "diagnostic", "metric": "lambda", "horizon": 8},
                     "target_scope": {"runtime": "original", "metric": "quality", "horizon": 256}, **fields})


def of_kind(report, kind):
    return [gap for gap in report["gaps"] if gap["kind"] == kind]


class FrontierTests(unittest.TestCase):
    def test_disconnected_pairs_without_anchored_goals_are_not_opportunities(self):
        spec = fixture()
        spec["goals"] = []
        self.assertEqual(discover_frontier(spec)["gaps"], [])
        spec["goals"] = [record(id="bad", target="target", anchors=[], decision="choose")]
        with self.assertRaisesRegex(ValueError, "anchors"):
            discover_frontier(spec)

    def test_goal_gap_has_sources_open_status_and_explained_node_kinds(self):
        report = discover_frontier(fixture())
        gap = report["gaps"][0]
        self.assertEqual(gap["kind"], "MISSING_BRIDGE")
        self.assertEqual(gap["anchors"], ["a"])
        self.assertEqual(gap["target"], "target")
        self.assertEqual(gap["status"], "OPEN")
        self.assertEqual(gap["evidence_status"], "INPUT_REPORTED")
        self.assertEqual(gap["cost"], {"status": "UNKNOWN"})
        self.assertTrue(gap["reachability_only"])
        for phrase in ("kind=observation", "local diagnostic", "Eight-step calculation", "kind=phenomenon", "long-chain quality"):
            self.assertIn(phrase, gap["question"])
        self.assertEqual(len(gap["evidence_refs"]), 3)
        self.assertEqual(set(gap["required_proposal_fields"]),
                         {"assumptions", "relations", "prediction", "test", "next_if_positive", "next_if_negative"})

    def test_supported_directed_path_and_cycles_do_not_create_false_holes(self):
        spec = fixture()
        spec["edges"] = [edge("a", "model"), edge("model", "target"), edge("target", "model")]
        report = discover_frontier(spec)
        self.assertEqual(report["gaps"], [])
        self.assertTrue(report["reachability_only"])
        self.assertEqual(report["scientific_support"], "UNKNOWN")
        spec["edges"] = [edge("target", "a")]
        self.assertEqual(len(of_kind(discover_frontier(spec), "MISSING_BRIDGE")), 1)

    def test_proposed_and_contradicted_edges_do_not_close_a_bridge(self):
        for status in ("PROPOSED", "CONTRADICTED"):
            with self.subTest(status=status):
                spec = fixture()
                spec["edges"] = [edge("a", "target", status)]
                self.assertEqual(len(of_kind(discover_frontier(spec), "MISSING_BRIDGE")), 1)

    def test_wrong_relation_does_not_hide_an_explanation_gap(self):
        spec = fixture()
        spec["edges"] = [edge("a", "target", relation="related_to")]
        spec["goals"][0]["relations"] = ["explains", "predicts"]
        spec["goals"].append(record(id="topology", target="target", anchors=["a"], decision="locate citation"))
        gaps = of_kind(discover_frontier(spec), "MISSING_BRIDGE")
        self.assertEqual([gap["goal_id"] for gap in gaps], ["goal"])
        self.assertEqual(gaps[0]["relations"], ["explains", "predicts"])

    def test_only_unreachable_goal_anchors_are_reported(self):
        spec = fixture()
        spec["goals"][0]["anchors"] = ["a", "model", "target"]
        spec["edges"] = [edge("model", "target")]
        self.assertEqual(discover_frontier(spec)["gaps"][0]["anchors"], ["a"])

    def test_future_edge_cannot_erase_historical_gap(self):
        spec = fixture()
        baseline = discover_frontier(spec)["gaps"]
        spec["edges"] = [edge("a", "target", available_on="2001-01-01")]
        report = discover_frontier(spec)
        self.assertEqual(report["gaps"], baseline)
        self.assertEqual(report["statistics"]["supported_edges_used"], 0)
        self.assertEqual(report["excluded"][0]["reason"], "FUTURE_RECORD")

    def test_duplicate_optional_edge_ids_cannot_exclude_available_edge(self):
        spec = fixture()
        spec["edges"] = [edge("a", "model", id="same"),
                         edge("a", "target", id="same", available_on="2001-01-01")]
        report = discover_frontier(spec)
        self.assertEqual(report["excluded"], [{"record_type": "edges", "id": "edge:1",
                         "reason": "FUTURE_RECORD", "available_on": "2001-01-01"}])
        self.assertEqual(report["statistics"]["supported_edges_used"], 1)
        excluded_ids = {row["id"] for row in report["excluded"] if row["record_type"] == "edges"}
        retained = [row for index, row in enumerate(spec["edges"]) if f"edge:{index}" not in excluded_ids]
        self.assertEqual(retained, [spec["edges"][0]])
        spec["edges"][1]["id"] = "arbitrary-other-id"
        self.assertEqual(discover_frontier(spec), report)

    def test_future_node_is_filtered_before_the_node_budget(self):
        spec = fixture()
        spec["limits"] = {"max_nodes": 3}
        baseline = discover_frontier(spec)["gaps"]
        spec["nodes"].insert(0, node("later-answer", available_on="2001-01-01"))
        report = discover_frontier(spec)
        self.assertEqual(report["gaps"], baseline)
        self.assertFalse(report["truncation"]["truncated"])

    def test_unknown_historical_availability_is_isolated(self):
        spec = fixture()
        spec["edges"] = [edge("a", "target")]
        spec["edges"][0].pop("available_on")
        report = discover_frontier(spec)
        self.assertEqual(len(of_kind(report, "MISSING_BRIDGE")), 1)
        self.assertEqual(report["excluded"][0]["reason"], "UNKNOWN_AVAILABILITY")
        spec["nodes"][0].pop("available_on")
        report = discover_frontier(spec)
        self.assertEqual(report["gaps"], [])
        self.assertTrue(any(row["reason"] == "UNAVAILABLE_NODE" for row in report["unknown"]))

    def test_no_as_of_uses_unscoped_context_without_today_filter(self):
        spec = fixture()
        spec.pop("as_of")
        spec["edges"] = [edge("a", "target", available_on="9999-01-01")]
        spec["nodes"][0].pop("available_on")
        report = discover_frontier(spec)
        self.assertEqual(report["temporal_policy"], "UNSCOPED")
        self.assertIsNone(report["as_of"])
        self.assertEqual(report["excluded"], [])
        self.assertEqual(report["gaps"], [])

    def test_future_decisive_requests_cannot_generate_any_family(self):
        spec = fixture()
        spec["goals"][0]["available_on"] = "2001-01-01"
        spec["observations"] = [observation()]
        spec["transfers"] = [transfer()]
        add_dimensions(spec)
        for name in ("observations", "transfers", "dimension_requests"):
            spec[name][0]["available_on"] = "2001-01-01"
        report = discover_frontier(spec)
        self.assertEqual(report["gaps"], [])
        self.assertEqual(report["program_proposals"], [])
        self.assertEqual(report["statistics"]["combinations_examined"], 0)
        self.assertEqual(len(report["excluded"]), 4)

    def test_graph_budget_truncation_cannot_manufacture_disconnection(self):
        spec = fixture()
        spec["edges"] = [edge("a", "model"), edge("model", "target")]
        spec["limits"] = {"max_edges": 1}
        report = discover_frontier(spec)
        self.assertEqual(report["gaps"], [])
        self.assertIn("edge limit", report["truncation"]["reasons"])
        self.assertTrue(any(row["reason"] == "REACHABILITY_SEARCH_TRUNCATED" for row in report["unknown"]))
        spec["limits"] = {"max_nodes": 2}
        report = discover_frontier(spec)
        self.assertEqual(report["gaps"], [])
        self.assertIn("node limit", report["truncation"]["reasons"])

    def test_numeric_residual_is_a_question_not_a_causal_conclusion(self):
        spec = fixture()
        spec["observations"] = [observation()]
        gap = of_kind(discover_frontier(spec), "MODEL_FAILURE")[0]
        self.assertEqual(gap["residual"], 3)
        self.assertEqual(gap["status"], "OPEN")
        self.assertEqual(gap["uncertainty"], "UNKNOWN_SCIENTIFIC_SUPPORT")
        spec["observations"][0]["tolerance"] = 3
        report = discover_frontier(spec)
        self.assertEqual(of_kind(report, "MODEL_FAILURE"), [])
        self.assertFalse(report["residual_checks"][0]["exceeds_tolerance"])

    def test_absent_prediction_is_not_assumed_zero(self):
        spec = fixture()
        spec["observations"] = [observation()]
        spec["observations"][0].pop("predicted")
        report = discover_frontier(spec)
        self.assertEqual(of_kind(report, "MODEL_FAILURE"), [])
        self.assertEqual(report["unknown"][0]["missing_fields"], ["predicted"])
        self.assertEqual(report["unknown"][0]["status"], "UNKNOWN")

    def test_incompatible_numeric_units_do_not_refute_a_model(self):
        spec = fixture()
        spec["observations"] = [observation()]
        spec["observations"][0]["protocol"]["predicted_unit"] = "metres"
        report = discover_frontier(spec)
        self.assertEqual(of_kind(report, "MODEL_FAILURE"), [])
        self.assertEqual(report["unknown"][0]["reason"], "INCOMPATIBLE_UNITS")

    def test_nonfinite_boolean_and_negative_tolerance_are_validation_errors(self):
        for key, value in (("observed", float("inf")), ("predicted", True), ("tolerance", -1)):
            with self.subTest(key=key, value=value):
                spec = fixture()
                spec["observations"] = [observation()]
                spec["observations"][0][key] = value
                with self.assertRaises(ValueError):
                    discover_frontier(spec)

    def test_residual_overflow_remains_unknown_and_json_finite(self):
        spec = fixture()
        spec["observations"] = [observation()]
        spec["observations"][0].update(observed=1e308, predicted=-1e308)
        report = discover_frontier(spec)
        self.assertEqual(of_kind(report, "MODEL_FAILURE"), [])
        self.assertEqual(report["unknown"][0]["reason"], "NONFINITE_RESIDUAL")
        json.dumps(report, allow_nan=False)
        spec["observations"][0].update(observed=int(1e308), predicted=-int(1e308))
        self.assertEqual(discover_frontier(spec)["unknown"][0]["reason"], "NONFINITE_RESIDUAL")
        spec["observations"][0].update(observed=10**308, predicted=-(10**308))
        report = discover_frontier(spec)
        self.assertEqual(of_kind(report, "MODEL_FAILURE"), [])
        self.assertEqual(report["unknown"][0]["reason"], "NONFINITE_RESIDUAL")
        json.dumps(report, allow_nan=False)

    def test_sample_throughput_formula_has_a_negative_exponent(self):
        spec = fixture()
        add_dimensions(spec)
        report = discover_frontier(spec)
        proposals = report["program_proposals"]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["exponents"], {"samples": 1, "time": -1})
        self.assertEqual(proposals[0]["ast"]["terms"], [{"node_id": "samples", "exponent": 1}, {"node_id": "time", "exponent": -1}])
        self.assertEqual(proposals[0]["dimension_check"]["actual"], {"N": 1, "T": -1})
        self.assertEqual(proposals[0]["status"], "PROPOSED")
        self.assertEqual(proposals[0]["scientific_support"], "UNKNOWN")
        self.assertEqual(proposals[0]["evidence_status"], "INPUT_REPORTED")

    def test_dimensionless_primitive_dedup_preserves_reciprocal_orientations(self):
        spec = {"schema_version": 1, "nodes": [node("x", dimensions={"L": 1}), node("y", dimensions={"L": 1}),
                                               node("ratio", dimensions={})],
                "dimension_requests": [record(id="ratios", variables=["x", "y"], target="ratio", decision="form ratio")]}
        report = discover_frontier(spec)
        vectors = {tuple(proposal["exponents"].values()) for proposal in report["program_proposals"]}
        self.assertEqual(vectors, {(1, -1), (-1, 1)})
        self.assertTrue(all(proposal["exponent_gcd"] == 1 for proposal in report["program_proposals"]))
        self.assertNotIn((0, 0), vectors)

    def test_nonhomogeneous_solution_is_not_broken_by_gcd_reduction(self):
        spec = {"schema_version": 1, "nodes": [node("length", dimensions={"L": 1}), node("area", dimensions={"L": 2})],
                "dimension_requests": [record(id="area", variables=["length"], target="area", decision="form area")]}
        proposal = discover_frontier(spec)["program_proposals"][0]
        self.assertEqual(proposal["exponents"], {"length": 2})
        self.assertEqual(proposal["exponent_gcd"], 2)
        self.assertEqual(proposal["dimension_check"]["actual"], {"L": 2})

    def test_wrong_dimensions_and_missing_dimensions_are_not_success(self):
        spec = fixture()
        add_dimensions(spec)
        next(n for n in spec["nodes"] if n["id"] == "time")["dimensions"] = {"N": 1}
        report = discover_frontier(spec)
        self.assertEqual(report["program_proposals"], [])
        self.assertEqual(report["unknown"][0]["reason"], "NO_FORMULA_IN_BOUNDED_DOMAIN")
        next(n for n in spec["nodes"] if n["id"] == "throughput").pop("dimensions")
        self.assertEqual(discover_frontier(spec)["unknown"][0]["reason"], "MISSING_DIMENSIONS")

    def test_integer_matrix_rejects_boolean_and_fractional_dimension_powers(self):
        for power in (True, 0.5, "1"):
            with self.subTest(power=power):
                spec = fixture()
                spec["nodes"][0]["dimensions"] = {"L": power}
                with self.assertRaisesRegex(ValueError, "integer"):
                    discover_frontier(spec)

    def test_combination_and_term_limits_are_finite_without_claiming_impossibility(self):
        spec = fixture()
        add_dimensions(spec)
        spec["limits"] = {"max_combinations": 1}
        report = discover_frontier(spec)
        self.assertEqual(report["statistics"]["combinations_examined"], 1)
        self.assertIn("combination limit", report["truncation"]["reasons"])
        self.assertEqual(report["unknown"][0]["reason"], "SEARCH_TRUNCATED")
        spec["limits"] = {"max_terms": 1}
        report = discover_frontier(spec)
        self.assertEqual(report["program_proposals"], [])
        self.assertEqual(report["statistics"]["combinations_examined"], 8)
        self.assertEqual(report["unknown"][0]["status"], "UNKNOWN")

    def test_dimension_requests_share_enumeration_budget(self):
        spec = {"schema_version": 1, "nodes": [node("x", dimensions={"L": 1}), node("target", dimensions={"L": 1})],
                "dimension_requests": [record(id=f"r{i}", target="target", variables=["x"], decision="derive") for i in range(2)],
                "limits": {"max_combinations": 2}}
        report = discover_frontier(spec)
        self.assertEqual({proposal["request_id"] for proposal in report["program_proposals"]}, {"r0", "r1"})
        self.assertEqual(report["statistics"]["combinations_examined"], 2)

    def test_exact_enumeration_budget_completion_is_not_truncation(self):
        spec = fixture()
        add_dimensions(spec)
        spec["limits"] = {"max_combinations": 24}
        report = discover_frontier(spec)
        self.assertEqual(report["statistics"]["combinations_examined"], 24)
        self.assertFalse(report["truncation"]["truncated"])

    def test_runtime_metric_and_horizon_mismatch_generates_transfer_question(self):
        spec = fixture()
        spec["transfers"] = [transfer()]
        gap = of_kind(discover_frontier(spec), "TRANSFER_GAP")[0]
        self.assertEqual({row["field"] for row in gap["scope_comparison"]["conflicts"]}, {"runtime", "metric", "horizon"})
        self.assertEqual(gap["scope_comparison"]["status"], "MISMATCH")
        self.assertEqual(gap["status"], "OPEN")
        self.assertEqual(gap["uncertainty"], "UNKNOWN_SCIENTIFIC_SUPPORT")

    def test_identical_declared_scopes_do_not_create_transfer_gap(self):
        spec = fixture()
        spec["transfers"] = [transfer()]
        spec["transfers"][0]["target_scope"] = deepcopy(spec["transfers"][0]["source_scope"])
        report = discover_frontier(spec)
        self.assertEqual(of_kind(report, "TRANSFER_GAP"), [])
        self.assertEqual(report["transfer_checks"][0]["status"], "IDENTICAL_DECLARED_SCOPE")
        self.assertEqual(report["scientific_support"], "UNKNOWN")

    def test_missing_scope_or_scope_field_stays_unknown(self):
        for missing in ("source_scope", "horizon"):
            with self.subTest(missing=missing):
                spec = fixture()
                spec["transfers"] = [transfer()]
                spec["transfers"][0]["target_scope"] = deepcopy(spec["transfers"][0]["source_scope"])
                if missing == "source_scope":
                    spec["transfers"][0].pop("source_scope")
                else:
                    spec["transfers"][0]["source_scope"].pop("horizon")
                report = discover_frontier(spec)
                self.assertEqual(of_kind(report, "TRANSFER_GAP"), [])
                self.assertEqual(report["transfer_checks"][0]["status"], "UNKNOWN")
                self.assertEqual(report["unknown"][0]["reason"], "MISSING_SCOPE_FIELDS")

    def test_transfer_must_be_relevant_to_an_anchored_goal(self):
        spec = fixture()
        spec["transfers"] = [transfer(to="model")]
        report = discover_frontier(spec)
        self.assertEqual(of_kind(report, "TRANSFER_GAP"), [])
        self.assertEqual(report["transfer_checks"][0]["status"], "OUTSIDE_GOAL_SCOPE")
        spec["edges"] = [edge("a", "model"), edge("model", "target")]
        self.assertEqual(len(of_kind(discover_frontier(spec), "TRANSFER_GAP")), 1)
        spec["goals"] = []
        self.assertEqual(of_kind(discover_frontier(spec), "TRANSFER_GAP"), [])

    def test_scope_fields_are_bounded_json_atoms(self):
        for scope in ({"runtime": {"nested": True}}, {str(i): i for i in range(17)}):
            with self.subTest(scope=scope):
                spec = fixture()
                spec["transfers"] = [transfer(source_scope=scope)]
                with self.assertRaisesRegex(ValueError, "scope"):
                    discover_frontier(spec)

    def test_family_round_robin_protects_three_other_families(self):
        spec = fixture()
        spec["goals"] = [record(id=f"g{i}", target="target", anchors=["a"], decision="explain") for i in range(10)]
        spec["observations"] = [observation()]
        spec["transfers"] = [transfer()]
        add_dimensions(spec)
        spec["limits"] = {"max_gaps": 4}
        report = discover_frontier(spec)
        self.assertEqual([gap["kind"] for gap in report["gaps"]],
                         ["MISSING_BRIDGE", "MODEL_FAILURE", "DIMENSIONAL_BRIDGE", "TRANSFER_GAP"])
        self.assertIn("gap limit", report["truncation"]["reasons"])
        self.assertEqual(report["statistics"]["gaps_generated"], 13)
        self.assertEqual(report["statistics"]["gaps_emitted"], 4)

    def test_self_signed_success_and_graph_flags_never_certify_proposals(self):
        spec = fixture()
        add_dimensions(spec)
        spec.update(status="PASS", verified=True, scientific_support="PROVEN")
        for row in [*spec["nodes"], *spec["dimension_requests"]]:
            row.update(verified=True, status="PASS")
            row["source"]["verified"] = True
        report = discover_frontier(spec)
        self.assertEqual(report["scientific_support"], "UNKNOWN")
        self.assertTrue(all(gap["status"] == "OPEN" for gap in report["gaps"]))
        self.assertTrue(all(proposal["status"] == "PROPOSED" and proposal["scientific_support"] == "UNKNOWN"
                            for proposal in report["program_proposals"]))
        self.assertTrue(all(proposal["evidence_status"] == "INPUT_REPORTED" for proposal in report["program_proposals"]))

    def test_source_flags_without_a_locator_do_not_pass_validation(self):
        for source in (None, "", {"verified": True}, {"source_id": "good"}):
            with self.subTest(source=source):
                spec = fixture()
                spec["nodes"][0]["source"] = source
                with self.assertRaisesRegex(ValueError, "source locator"):
                    discover_frontier(spec)

    def test_source_byte_budget_applies_to_every_record_family(self):
        for family in ("nodes", "edges", "goals", "observations", "dimension_requests", "transfers"):
            with self.subTest(family=family):
                spec = fixture()
                spec["edges"] = [edge("a", "target")]
                spec["observations"] = [observation()]
                spec["transfers"] = [transfer()]
                add_dimensions(spec)
                spec[family][0]["source"] = {"locator": "fixture", "padding": "x" * 1000}
                with self.assertRaisesRegex(ValueError, r"source exceeds 1024 UTF-8 JSON bytes"):
                    discover_frontier(spec)

    def test_protocol_metadata_has_the_same_small_byte_budget(self):
        spec = fixture()
        spec["observations"] = [observation()]
        spec["observations"][0]["protocol"]["padding"] = "x" * 1000
        with self.assertRaisesRegex(ValueError, r"protocol exceeds 1024 UTF-8 JSON bytes"):
            discover_frontier(spec)

    def test_metadata_budget_counts_utf8_bytes_instead_of_characters(self):
        spec = fixture()
        spec["nodes"][0]["source"] = {"locator": "fixture", "padding": "中" * 400}
        with self.assertRaisesRegex(ValueError, "1024 UTF-8 JSON bytes"):
            discover_frontier(spec)

    def test_permitted_source_padding_is_not_repeated_in_many_formulas(self):
        spec = {"schema_version": 1, "nodes": [node(f"q{i}", "quantity", dimensions={}) for i in range(6)]
                                              + [node("ratio", "quantity", dimensions={})],
                "dimension_requests": [record(id="ratios", target="ratio", variables=[f"q{i}" for i in range(6)], decision="derive") ]}
        baseline = discover_frontier(spec)
        self.assertGreater(baseline["statistics"]["program_proposals_generated"], 100)
        for row in [*spec["nodes"], *spec["dimension_requests"]]:
            row["source"]["padding"] = "x" * 200
        original = deepcopy(spec)
        padded = discover_frontier(spec)
        self.assertEqual(padded, baseline)
        self.assertEqual(len(json.dumps(padded)), len(json.dumps(baseline)))
        self.assertEqual(spec, original)
        self.assertTrue(all("padding" not in ref["source"] for proposal in padded["program_proposals"]
                            for ref in proposal["evidence_refs"]))

    def test_locator_projection_preserves_source_identity_without_certification(self):
        spec = fixture()
        spec["nodes"][0]["source"] = {"source_id": "evidence-1", "locator": "exact source position",
                                      "url": "https://example.test/source", "verified": True, "note": "caller metadata"}
        gap = discover_frontier(spec)["gaps"][0]
        ref = next(ref for ref in gap["evidence_refs"] if ref["id"] == "a")
        self.assertEqual(ref["source"], {"source_id": "evidence-1", "locator": "exact source position",
                                        "url": "https://example.test/source"})
        self.assertEqual(gap["evidence_status"], "INPUT_REPORTED")

    def test_schema_dates_ids_and_limit_types_raise_identifiable_value_errors(self):
        for schema in (None, True, 1.0, 2):
            with self.subTest(schema=schema), self.assertRaisesRegex(ValueError, "schema_version"):
                discover_frontier({"schema_version": schema})
        for limits in ({"max_power": 7}, {"max_combinations": 4097}, {"max_gaps": True}, {"unknown": 1}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                discover_frontier({**fixture(), "limits": limits})
        with self.assertRaisesRegex(ValueError, "ISO date"):
            discover_frontier({**fixture(), "as_of": "20000101"})
        spec = fixture()
        spec["edges"] = [edge([], "target")]
        with self.assertRaisesRegex(ValueError, "endpoints"):
            discover_frontier(spec)

    def test_variable_count_cap_and_empty_dimension_requests_reject(self):
        spec = {"schema_version": 1, "nodes": [node(f"v{i}", dimensions={"L": 1}) for i in range(7)]}
        for variables in ([], [f"v{i}" for i in range(7)]):
            with self.subTest(variables=variables):
                spec["dimension_requests"] = [record(id="many", target="v0", variables=variables, decision="derive")]
                with self.assertRaisesRegex(ValueError, "1..6"):
                    discover_frontier(spec)

    def test_target_cannot_be_a_variable_to_create_a_vacuous_identity(self):
        spec = {"schema_version": 1, "nodes": [node("t", dimensions={"T": 1})],
                "dimension_requests": [record(id="self", target="t", variables=["t"], decision="derive new relation")]}
        with self.assertRaisesRegex(ValueError, "target cannot also be a variable"):
            discover_frontier(spec)
        spec["nodes"].append(node("other", dimensions={"L": 1}))
        spec["dimension_requests"][0]["variables"].append("other")
        with self.assertRaisesRegex(ValueError, "target cannot also be a variable"):
            discover_frontier(spec)

    def test_determinism_and_no_input_or_return_alias_mutation(self):
        spec = fixture()
        add_dimensions(spec)
        spec["observations"] = [observation()]
        spec["transfers"] = [transfer()]
        original = deepcopy(spec)
        report = discover_frontier(spec)
        self.assertEqual(spec, original)
        self.assertEqual(report, discover_frontier(spec))
        report["gaps"][0]["evidence_refs"][0]["source"]["locator"] = "changed return"
        report["program_proposals"][0]["dimension_check"]["target"]["N"] = 99
        self.assertEqual(spec, original)


if __name__ == "__main__":
    unittest.main()

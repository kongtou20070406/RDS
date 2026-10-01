"""Independent numeric confirmation is distinct from a claimed scientific jump."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_advancement import evaluate_advancement


FROZEN = "2026-01-01T00:00:00Z"
SELECTED = "2026-01-02T00:00:00Z"
PREDICTED = "2026-01-03T00:00:00Z"
OBSERVED = "2026-01-04T00:00:00Z"


def fixture(count=4):
    """Four matched, single-intervention tasks; outcomes execute y=2*x locally.

    This is a scripted software fixture, not an AI-benefit benchmark. The model
    baseline makes one prediction error; generation labels never change scores.
    """
    protocol = {"schema_version": 1, "id": "paired-fixture", "version": 1,
        "frozen_at": FROZEN, "model_id": "scripted-fixture-v1", "starting_evidence_sha256": "a" * 64,
        "budget": {"wall_seconds": {"cap": 100, "unit": "seconds"},
                   "model_tokens": {"cap": 100, "unit": "tokens"}}, "tasks": []}
    trajectories, confirmations = [], []
    for index in range(count):
        tid, cid = f"task-{index}", f"holdout-{index}"
        digest = hashlib.sha256(f"intervene:x={index + 3}".encode()).hexdigest()
        protocol["tasks"].append({"id": tid, "kind": "extension_challenge" if index < 2 else "retention_control",
            "confirmations": [{"id": cid, "intervention_sha256": digest, "metric": "response",
                               "unit": "units", "tolerance": 0.1}]})
        observed = 2 * (index + 3)
        for arm in ("baseline", "advisor"):
            binding = {"task_id": tid, "arm": arm, "protocol_id": protocol["id"], "protocol_version": protocol["version"]}
            trajectories.append({**binding, "model_id": protocol["model_id"],
                "starting_evidence_sha256": protocol["starting_evidence_sha256"], "selected_at": SELECTED,
                "selection_used_ids": [], "predictions": [{"confirmation_id": cid,
                    "value": observed - 1 if arm == "baseline" and index == 0 else observed,
                    "metric": "response", "unit": "units", "predicted_at": PREDICTED}],
                "attempts": [{"id": "run-1", "status": "SUCCEEDED", "costs": costs(1, 3)}],
                "generation": {"operator_ids": ["retain"] if arm == "baseline" else ["scale"]},
                "selection": {"policy_id": arm}, "source": {"locator": "scripted trajectory"}})
            confirmations.append({**binding, "confirmation_id": cid, "intervention_sha256": digest,
                "observed": observed, "metric": "response", "unit": "units", "observed_at": OBSERVED,
                "used_for_selection": False, "costs": costs(1, 0), "source": {"locator": "local intervention y=2*x"}})
    return protocol, trajectories, confirmations


def costs(seconds, tokens):
    return {"wall_seconds": {"value": seconds, "unit": "seconds"}, "model_tokens": {"value": tokens, "unit": "tokens"}}


def task(report, index=0):
    return report["paired_tasks"][index]


def add_confirmation(protocol, trajectories, confirmations):
    contract = {**protocol["tasks"][0]["confirmations"][0], "id": "second-holdout", "intervention_sha256": "b" * 64}
    protocol["tasks"][0]["confirmations"].append(contract)
    for row in trajectories[:2]:
        row["predictions"].append({**row["predictions"][0], "confirmation_id": "second-holdout", "value": 3})
    for row in list(confirmations[:2]):
        confirmations.append({**deepcopy(row), "confirmation_id": "second-holdout", "intervention_sha256": "b" * 64, "observed": 3})


class AdvancementTests(unittest.TestCase):
    def test_paired_real_numeric_fixture_and_fixed_denominator(self):
        report = evaluate_advancement(*fixture())
        self.assertEqual(report["status"], "MEASURED")
        self.assertEqual(report["primary_metric"]["baseline"]["rate"], 0.75)
        self.assertEqual(report["primary_metric"]["advisor"]["rate"], 1)
        self.assertEqual(report["primary_metric"]["paired_difference"], 0.25)
        self.assertEqual([row["paired_difference"] for row in report["paired_tasks"]], [1, 0, 0, 0])
        self.assertEqual(report["primary_metric"]["advisor"]["denominator"], 4)
        self.assertEqual(report["costs"]["per_arm"]["advisor"]["wall_seconds"]["value"], 8)
        self.assertEqual(report["assurance"], "INPUT_REPORTED")
        self.assertEqual(report["mechanism_truth"], "UNMEASURED")

    def test_regression_is_negative_paired_difference(self):
        p, t, c = fixture()
        t[3]["predictions"][0]["value"] += 1
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report, 1)["paired_difference"], -1)
        self.assertEqual(report["primary_metric"]["paired_difference"], 0)
        self.assertEqual(task(report, 1)["advisor"]["status"], "FAIL")

    def test_retaining_correct_model_passes_and_structure_does_not_claim_truth(self):
        p, t, c = fixture()
        t[5]["generation"]["replaced_incumbent"] = True
        report = evaluate_advancement(p, t, c)
        self.assertEqual(report["task_kind_summaries"]["extension_challenge"]["advisor"]["conditional_success_rate"], 1)
        self.assertEqual(report["task_kind_summaries"]["retention_control"]["advisor"]["conditional_failure_rate"], 0)
        self.assertEqual(task(report, 2)["advisor"]["status"], "PASS")
        self.assertTrue(report["structure_changes"][2]["generation"]["changed"])
        self.assertEqual(report["false_replacement"]["status"], "UNMEASURED")

    def test_all_frozen_confirmations_must_pass(self):
        p, t, c = fixture()
        add_confirmation(p, t, c)
        c[-1]["observed"] = 4
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["advisor"]["status"], "FAIL")
        self.assertEqual(len(task(report)["advisor"]["confirmation_checks"]), 2)

    def test_known_failure_plus_unmeasured_has_no_possible_success(self):
        p, t, c = fixture(1)
        add_confirmation(p, t, c)
        t[1]["predictions"][0]["value"] = 1
        c[-1]["observed"] = None
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["advisor"]["status"], "UNMEASURED")
        self.assertFalse(task(report)["advisor"]["possible_success"])
        self.assertEqual(report["primary_metric"]["advisor"]["bounds"], {"lower": 0, "upper": 0})

    def test_tolerance_is_frozen_and_inclusive(self):
        p, t, c = fixture(1)
        p["tasks"][0]["confirmations"][0]["tolerance"] = 1
        c[0]["tolerance"] = 1000
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["baseline"]["status"], "PASS")
        p["tasks"][0]["confirmations"][0]["tolerance"] = 0
        self.assertEqual(task(evaluate_advancement(p, t, c))["baseline"]["status"], "FAIL")

    def test_self_signed_success_cannot_override_numeric_failure(self):
        p, t, c = fixture(1)
        c[0].update(success=True, verified=True)
        self.assertEqual(task(evaluate_advancement(p, t, c))["baseline"]["status"], "FAIL")

    def test_success_without_observation_is_invalid(self):
        p, t, c = fixture(1)
        c[1].update(observed=None, success=True)
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["advisor"]["status"], "INVALID")
        self.assertIsNone(report["primary_metric"]["advisor"]["rate"])

    def test_missing_numeric_stays_unknown_with_bounds(self):
        p, t, c = fixture()
        c[1]["observed"] = None
        report = evaluate_advancement(p, t, c)
        self.assertEqual(report["status"], "UNMEASURED")
        self.assertIsNone(report["primary_metric"]["advisor"]["rate"])
        self.assertEqual(report["primary_metric"]["advisor"]["bounds"], {"lower": 0.75, "upper": 1})
        self.assertEqual(report["conditional_measured_pairs"]["denominator"], 3)
        self.assertEqual(len(report["unmeasured"]), 1)

    def test_missing_entire_task_never_shrinks_denominator(self):
        p, t, c = fixture()
        report = evaluate_advancement(p, t[2:], c[2:])
        self.assertEqual(len(report["paired_tasks"]), 4)
        self.assertEqual(report["primary_metric"]["baseline"]["denominator"], 4)
        self.assertIsNone(report["primary_metric"]["paired_difference"])
        self.assertEqual(report["costs"]["budget_status"]["baseline"], "UNKNOWN")

    def test_missing_prediction_and_confirmation_are_both_listed(self):
        p, t, c = fixture(1)
        t[1]["predictions"] = []
        report = evaluate_advancement(p, t, c[:1])
        missing = task(report)["advisor"]["missing"]
        self.assertIn("holdout-0:prediction", missing)
        self.assertIn("holdout-0:confirmation", missing)
        self.assertEqual(report["costs"]["budget_status"]["advisor"], "UNKNOWN")

    def test_empty_measurements_not_empty_protocol_are_unmeasured(self):
        p, _, _ = fixture()
        report = evaluate_advancement(p, [], [])
        self.assertEqual(report["status"], "UNMEASURED")
        self.assertEqual(report["primary_metric"]["advisor"]["denominator"], 4)
        self.assertIsNone(report["primary_metric"]["advisor"]["rate"])

    def test_empty_or_duplicate_frozen_tasks_are_rejected(self):
        for change in (lambda p: p.update(tasks=[]), lambda p: p["tasks"].append(deepcopy(p["tasks"][0])),
                       lambda p: p["tasks"][0].update(confirmations=[])):
            with self.subTest(change=change):
                p, t, c = fixture()
                change(p)
                with self.assertRaises(ValueError):
                    evaluate_advancement(p, t, c)

    def test_failed_interrupted_and_timed_out_costs_are_charged(self):
        for status in ("FAILED", "INTERRUPTED", "TIMED_OUT"):
            with self.subTest(status=status):
                p, t, c = fixture()
                t[0]["attempts"].append({"id": "retry", "status": status, "costs": costs(5, 20)})
                report = evaluate_advancement(p, t, c)
                self.assertEqual(report["costs"]["per_arm"]["baseline"]["wall_seconds"]["value"], 13)
                self.assertEqual(report["costs"]["per_arm"]["baseline"]["model_tokens"]["value"], 32)

    def test_total_arm_overbudget_invalidates_all_tasks(self):
        p, t, c = fixture()
        p["budget"]["wall_seconds"]["cap"] = 10
        t[0]["attempts"].append({"id": "failed-expensive", "status": "FAILED", "costs": costs(5, 20)})
        report = evaluate_advancement(p, t, c)
        self.assertEqual(report["costs"]["per_arm"]["baseline"]["wall_seconds"]["status"], "OVER_BUDGET")
        self.assertEqual(report["costs"]["per_arm"]["baseline"]["wall_seconds"]["known_subtotal"], 13)
        self.assertTrue(all(row["baseline"]["status"] == "INVALID" for row in report["paired_tasks"]))
        self.assertIsNone(report["primary_metric"]["baseline"]["rate"])
        self.assertEqual(report["costs"]["budget_status"]["advisor"], "IN_BUDGET")

    def test_unknown_costs_not_zero_and_prevent_budget_claim(self):
        p, t, c = fixture()
        t[1]["attempts"][0]["costs"]["model_tokens"]["value"] = None
        report = evaluate_advancement(p, t, c)
        self.assertEqual(report["costs"]["budget_status"]["advisor"], "UNKNOWN")
        self.assertEqual(report["costs"]["per_arm"]["advisor"]["model_tokens"]["known_subtotal"], 9)
        self.assertIsNone(report["costs"]["per_arm"]["advisor"]["model_tokens"]["value"])
        self.assertTrue(all(row["advisor"]["status"] == "UNMEASURED" for row in report["paired_tasks"]))

    def test_empty_attempt_ledger_is_not_free_execution(self):
        p, t, c = fixture(1)
        t[1]["attempts"] = []
        self.assertEqual(evaluate_advancement(p, t, c)["costs"]["budget_status"]["advisor"], "UNKNOWN")

    def test_unbudgeted_currency_is_separate_unknown_not_converted(self):
        p, t, c = fixture(1)
        t[1]["attempts"][0]["costs"]["money"] = {"value": 5, "unit": "USD"}
        report = evaluate_advancement(p, t, c)
        extra = report["costs"]["non_budget_costs"][0]
        self.assertEqual(extra["status"], "UNKNOWN")
        self.assertEqual(extra["record"]["unit"], "USD")
        self.assertNotIn("money", report["costs"]["per_arm"]["advisor"])
        self.assertEqual(report["costs"]["per_arm"]["advisor"]["wall_seconds"]["value"], 2)

    def test_incompatible_resource_unit_invalidates_arm_without_conversion(self):
        p, t, c = fixture(1)
        c[1]["costs"]["wall_seconds"]["unit"] = "milliseconds"
        report = evaluate_advancement(p, t, c)
        self.assertEqual(report["costs"]["budget_status"]["advisor"], "INVALID")
        self.assertEqual(task(report)["advisor"]["status"], "INVALID")

    def test_prediction_observation_units_and_metrics_must_match_contract(self):
        for field, value in (("unit", "milliseconds"), ("metric", "accuracy")):
            with self.subTest(field=field):
                p, t, c = fixture(1)
                t[1]["predictions"][0][field] = value
                c[1][field] = value
                self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_protocol_model_evidence_and_intervention_bindings(self):
        for target, field, value in (("trajectory", "protocol_version", "1"), ("trajectory", "protocol_id", "other"),
                ("trajectory", "model_id", "stronger-model"), ("trajectory", "starting_evidence_sha256", "c" * 64),
                ("confirmation", "protocol_version", 2), ("confirmation", "intervention_sha256", "c" * 64)):
            with self.subTest(target=target, field=field):
                p, t, c = fixture(1)
                (t if target == "trajectory" else c)[1][field] = value
                self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_optional_protocol_content_hash_is_checked(self):
        p, t, c = fixture(1)
        digest = hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        t[1]["protocol_sha256"] = c[1]["protocol_sha256"] = digest
        self.assertEqual(evaluate_advancement(p, t, c)["status"], "MEASURED")
        p["budget"]["wall_seconds"]["cap"] = 101
        self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_explicit_attempt_model_switch_is_invalid_but_tools_need_no_model_id(self):
        p, t, c = fixture(1)
        self.assertEqual(evaluate_advancement(p, t, c)["status"], "MEASURED")
        t[1]["attempts"][0]["model_id"] = "different-model"
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["advisor"]["status"], "INVALID")
        self.assertEqual(report["costs"]["per_arm"]["advisor"]["wall_seconds"]["known_subtotal"], 2)

    def test_late_freeze_and_prediction_after_observation_invalid(self):
        for change in (lambda p, t, c: p.update(frozen_at=OBSERVED),
                       lambda p, t, c: t[1]["predictions"][0].update(predicted_at=OBSERVED),
                       lambda p, t, c: c[1].update(observed_at=SELECTED),
                       lambda p, t, c: t[1].update(selected_at="2026-01-02")):
            with self.subTest(change=change):
                p, t, c = fixture(1)
                change(p, t, c)
                self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_frozen_holdout_cannot_be_selection_input_even_from_another_task(self):
        for identity in ("holdout-0", "holdout-1", "task-1:holdout-1", hashlib.sha256(b"intervene:x=4").hexdigest()):
            with self.subTest(identity=identity):
                p, t, c = fixture()
                t[1]["selection_used_ids"] = [identity]
                self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_explicit_independence_disclosure_required_not_falseish(self):
        for value in (None, True, "false", 0):
            with self.subTest(value=value):
                p, t, c = fixture(1)
                c[1]["used_for_selection"] = value
                self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")
        p, t, c = fixture(1)
        del t[1]["selection_used_ids"]
        self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_numeric_zero_is_observed_and_bool_is_not_numeric(self):
        p, t, c = fixture(1)
        t[1]["predictions"][0]["value"] = c[1]["observed"] = 0
        self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "PASS")
        for field in ("observed", "cost"):
            with self.subTest(field=field):
                p, t, c = fixture(1)
                if field == "observed":
                    c[1]["observed"] = True
                else:
                    t[1]["attempts"][0]["costs"]["model_tokens"]["value"] = False
                self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_nonfinite_json_rejected_and_finite_int_residual_overflow_is_unknown(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            p, t, c = fixture(1)
            c[1]["observed"] = value
            with self.assertRaises(ValueError):
                evaluate_advancement(p, t, c)
        p, t, c = fixture(1)
        t[1]["predictions"][0]["value"] = 10 ** 308
        c[1]["observed"] = -(10 ** 308)
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["advisor"]["status"], "UNMEASURED")
        self.assertIn("holdout-0:nonfinite_residual", task(report)["advisor"]["missing"])

    def test_duplicate_attempt_and_confirmation_invalid_but_charges_retained(self):
        for target in ("attempt", "confirmation", "trajectory"):
            with self.subTest(target=target):
                p, t, c = fixture(1)
                if target == "attempt":
                    t[1]["attempts"].append(deepcopy(t[1]["attempts"][0]))
                elif target == "confirmation":
                    c.append(deepcopy(c[1]))
                else:
                    t.append(deepcopy(t[1]))
                report = evaluate_advancement(p, t, c)
                self.assertEqual(task(report)["advisor"]["status"], "INVALID")
                self.assertEqual(report["costs"]["per_arm"]["advisor"]["wall_seconds"]["known_subtotal"], 3)

    def test_unknown_cohort_records_invalidate_primary_and_charge_known_arm(self):
        p, t, c = fixture(1)
        extra = deepcopy(t[1])
        extra["task_id"] = "extra-task"
        t.append(extra)
        report = evaluate_advancement(p, t, c)
        self.assertEqual(report["status"], "INVALID")
        self.assertIsNone(report["primary_metric"]["advisor"]["rate"])
        self.assertTrue(report["validation_errors"])
        self.assertEqual(report["costs"]["per_arm"]["advisor"]["wall_seconds"]["known_subtotal"], 3)

    def test_missing_source_and_bounded_metadata_cannot_authenticate_success(self):
        for value in (None, {"status": "VERIFIED"}, {"locator": "source", "padding": "x" * 1024}):
            with self.subTest(value=value):
                p, t, c = fixture(1)
                c[1]["source"] = value
                self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_oversized_manifest_not_copied_to_output(self):
        p, t, c = fixture(1)
        t[1]["generation"] = {"padding": "x" * 1100}
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["advisor"]["status"], "INVALID")
        self.assertIsNone(report["structure_changes"][0]["generation"]["advisor"])
        self.assertIsNone(report["structure_changes"][0]["generation"]["changed"])

    def test_oversized_extra_cost_metadata_is_invalid_not_amplified(self):
        p, t, c = fixture(1)
        t[1]["attempts"][0]["costs"]["other"] = {"padding": "x" * 4100}
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["advisor"]["status"], "INVALID")
        self.assertEqual(report["costs"]["non_budget_costs"], [])

    def test_schema_scale_and_kind_caps_reject_invalid_protocol(self):
        for change in (lambda p: p.update(schema_version=True), lambda p: p["tasks"][0].update(kind="jump-score"),
                       lambda p: p["tasks"][0]["confirmations"][0].update(tolerance=True),
                       lambda p: p.update(tasks=[{**deepcopy(p["tasks"][0]), "id": str(i)} for i in range(65)])):
            with self.subTest(change=change):
                p, t, c = fixture(1)
                change(p)
                with self.assertRaises(ValueError):
                    evaluate_advancement(p, t, c)

    def test_unhashable_record_identity_is_recognizable_invalid(self):
        for field in ("task_id", "arm"):
            with self.subTest(field=field):
                p, t, c = fixture(1)
                t[1][field] = []
                self.assertEqual(evaluate_advancement(p, t, c)["status"], "INVALID")
        p, t, c = fixture(1)
        t[1]["predictions"][0]["confirmation_id"] = []
        self.assertEqual(task(evaluate_advancement(p, t, c))["advisor"]["status"], "INVALID")

    def test_general_kind_default_and_inputs_remain_unchanged(self):
        p, t, c = fixture(1)
        del p["tasks"][0]["kind"]
        original = deepcopy((p, t, c))
        report = evaluate_advancement(p, t, c)
        self.assertEqual(task(report)["kind"], "general")
        self.assertEqual((p, t, c), original)
        self.assertEqual(report, evaluate_advancement(p, t, c))
        report["structure_changes"][0]["generation"]["advisor"]["operator_ids"].append("malicious-output-edit")
        self.assertEqual((p, t, c), original)


if __name__ == "__main__":
    unittest.main()

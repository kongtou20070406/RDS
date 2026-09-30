"""Actual replay, independent adoption checks, and lossless isolated rollback."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_meta import apply_rule, load_judgment_graph, rollback_rule, reflect_from_state, validate_rule
from rds_rsi import commit_casepack, evaluate_candidate


def fixture():
    directory = ROOT / "examples/rsi"
    return tuple(json.loads((directory / name).read_text(encoding="utf-8"))
                 for name in ("base-graph.json", "candidate-rule.json", "cases.json"))


class RSITests(unittest.TestCase):
    def test_execution_reflection_requires_registered_failed_receipt(self):
        receipt = {"run_id": "dev-test-1", "attempt_id": "attempt-1", "sha256": "fixture-receipt-identity",
                   "run_status": "FAILED", "errors": ["Nonzero process exit: 1"],
                   "assessment": {"task_gain": "UNKNOWN", "mechanism": "UNKNOWN"}}
        state = {"runs": [{"run_id": "dev-test-1", "attempt_id": "attempt-1"}]}
        proposals = reflect_from_state(state, [receipt])
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["scope"], "execution-protocol-review")
        self.assertEqual(proposals[0]["source_receipt"]["sha256"], receipt["sha256"])
        self.assertFalse(proposals[0]["auto_apply"])
        self.assertEqual(validate_rule(proposals[0])["id"], proposals[0]["id"])
        for changed in ({**receipt, "run_status": "SUCCEEDED"}, {**receipt, "sha256": None},
                        {**receipt, "attempt_id": "another-attempt"}):
            self.assertEqual(reflect_from_state(state, [changed]), [])
        self.assertEqual(reflect_from_state({}, [receipt]), [])

    def test_baseline_candidate_replay_measures_finite_heldout_change(self):
        graph, rule, cases = fixture()
        original = deepcopy((graph, rule, cases))
        report = evaluate_candidate(rule, graph, cases)
        self.assertEqual(report["status"], "ACCEPTABLE_REGRESSION_CHANGE")
        self.assertEqual(report["cases_evaluated"], 4)
        self.assertEqual(report["replays_executed"], 8)
        self.assertEqual(report["counts"], {"baseline_passed": 1, "candidate_passed": 4,
                         "heldout_cases": 3, "heldout_improvements": 2, "regressions": 0})
        self.assertFalse(report["research_policy_gain_measured"])
        self.assertFalse(report["auto_apply"])
        self.assertTrue(report["bindings"]["program"]["files"])
        self.assertEqual((graph, rule, cases), original)

    def test_no_cases_only_development_overlap_rewritten_expectations_and_budget_rejected(self):
        graph, rule, cases = fixture()
        variants = []
        zero = deepcopy(cases); zero["cases"] = []; variants.append(zero)
        development = deepcopy(cases)
        for case in development["cases"]:
            case["partition"] = "development"
        development["heldout_ids"] = []
        variants.append(commit_casepack(development))
        overlap = deepcopy(cases); overlap["proposed_on_ids"].append(overlap["heldout_ids"][0]); variants.append(overlap)
        rewritten = deepcopy(cases); rewritten["cases"][0]["expected"] = {"minimum_candidates": 0}; variants.append(rewritten)
        limit = deepcopy(cases); limit["budget"]["max_cases"] = 1; variants.append(limit)
        for pack in variants:
            with self.subTest(pack=pack):
                report = evaluate_candidate(rule, graph, pack)
                self.assertEqual(report["status"], "REJECTED")
                self.assertFalse(report["adoption_eligible"])
        cyclic = deepcopy(graph)
        cyclic["edges"] = [{"from": "engineering-utility", "to": "engineering-utility", "relation": "prerequisite_for"}]
        self.assertIn("Cyclic", " ".join(evaluate_candidate(rule, cyclic, cases)["rejection_reasons"]))
        limit = deepcopy(cases); limit["budget"]["max_nodes"] = 1
        self.assertEqual(evaluate_candidate(rule, graph, limit)["status"], "REJECTED")
        timed = deepcopy(cases); timed["budget"]["max_runtime_ms"] = 1
        with patch("rds_rsi.time.perf_counter", side_effect=[0, .002, .003]):
            self.assertIn("wall-time", " ".join(evaluate_candidate(rule, graph, timed)["rejection_reasons"]))

    def test_replay_detects_regression_and_prose_only_noop(self):
        graph, rule, cases = fixture()
        changed = deepcopy(rule)
        changed["executable"]["preconditions"] = []
        report = evaluate_candidate(changed, graph, cases)
        self.assertFalse(report["adoption_eligible"])
        self.assertLess(report["counts"]["candidate_passed"], 4)
        prose = deepcopy(rule); prose.pop("executable")
        self.assertFalse(evaluate_candidate(prose, graph, cases)["adoption_eligible"])

    def test_replay_executes_composition_and_rejects_its_budget_truncation(self):
        graph, rule, cases = fixture()
        template = json.loads((ROOT / "examples/experiment-templates/templates.json").read_text())["templates"][0]
        template["rules"] = [rule["id"]]
        context = {"decision": "mechanism-attribution", "target_types": {"claimed_route_enabled": "boolean"},
                   "facts": {name: {"value": True, "source": "fixture:" + name}
                             for name in ("actual_crossing", "matched_recipe", "same_data_split", "same_primary_metric")}}
        context["facts"]["baseline_receipt"] = {"value": "control-1", "source": "fixture:control"}
        intervention = {"type": "ablation", "target": {"name": "claimed_route_enabled", "type": "boolean"}, "value": False}
        cases["cases"][0].update(engine="compose", context=context, templates={"schema": 1, "templates": [template]},
                                  expected={"required_interventions": [intervention], "no_ready": True})
        heldout = deepcopy(cases["cases"][0])
        heldout.update(id="holdout-compose", partition="heldout")
        cases["cases"].append(heldout)
        cases["heldout_ids"].append(heldout["id"])
        report = evaluate_candidate(rule, graph, commit_casepack(cases))
        self.assertTrue(report["adoption_eligible"], report["rejection_reasons"])
        self.assertEqual(report["replays_executed"], 10)
        self.assertEqual(report["counts"]["heldout_improvements"], 3)
        # Search can invoke composition too: its nested limits must be enforced.
        template["intervention"]["choices"] = [False, True]
        cases["cases"][0].update(engine="search", context={**context, "templates": {"schema": 1, "templates": [template]}})
        cases["budget"]["max_combinations"] = 1
        truncated = evaluate_candidate(rule, graph, commit_casepack(cases))
        self.assertFalse(truncated["adoption_eligible"])
        self.assertIn("limits", " ".join(truncated["rejection_reasons"]))

    def test_apply_replays_and_rollback_restores_exact_original_graph(self):
        graph, rule, cases = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            original = ("  " + json.dumps(graph, indent=3) + "\n\n").encode()
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                apply_rule(rule, path)
            self.assertEqual(path.read_bytes(), original)
            report = evaluate_candidate(rule, graph, cases)
            adopted = apply_rule(rule, path, evaluation=report, cases=cases)
            self.assertTrue(adopted["adopted"])
            self.assertIn(rule["id"], {n["id"] for n in load_judgment_graph(path)[1]["nodes"]})
            record = json.loads(Path(adopted["record_path"]).read_text())
            self.assertEqual(record["status"], "ADOPTED")
            self.assertEqual(Path(record["backup_path"]).read_bytes(), original)
            self.assertTrue(list((Path(directory) / ".rds/rsi/candidates").glob("*.json")))
            self.assertEqual(rollback_rule(adopted["record_path"], path)["status"], "ROLLED_BACK")
            self.assertEqual(path.read_bytes(), original)

    def test_self_signed_modified_rule_casepack_report_and_version_cannot_adopt(self):
        graph, rule, cases = fixture()
        report = evaluate_candidate(rule, graph, cases)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            original = path.read_bytes()
            signed = deepcopy(report); signed["cases_evaluated"] = 0
            modified = deepcopy(report); modified["results"][0]["candidate_grade"]["passed"] = False
            altered_cases = deepcopy(cases); altered_cases["cases"][0]["context"]["facts"]["actual_crossing"]["value"] = False
            altered_rule = deepcopy(rule); altered_rule["scope"] += " changed"
            for r, p, e in ((rule, cases, signed), (rule, cases, modified),
                            (rule, altered_cases, report), (altered_rule, cases, report)):
                with self.assertRaises(ValueError):
                    apply_rule(r, path, evaluation=e, cases=p)
                self.assertEqual(path.read_bytes(), original)
            with patch("rds_rsi.program_version", return_value={"version": "changed", "files": {}, "sha256": "changed"}):
                with self.assertRaises(ValueError):
                    apply_rule(rule, path, evaluation=report, cases=cases)
            self.assertEqual(path.read_bytes(), original)

    def test_force_does_not_bypass_gate_and_rollback_preserves_newer_work(self):
        graph, rule, cases = fixture()
        graph["nodes"].append({**deepcopy(rule), "executable": {**rule["executable"], "preconditions": []}})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_rule(rule, path, force=True)
            report = evaluate_candidate(rule, graph, cases)
            adopted = apply_rule(rule, path, force=True, evaluation=report, cases=cases)
            self.assertEqual(adopted["action"], "UPDATED")
            path.write_bytes(path.read_bytes() + b"\n# unrelated newer edit\n")
            newer = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "newer edits"):
                rollback_rule(adopted["record_path"], path)
            self.assertEqual(path.read_bytes(), newer)

    def test_dry_run_lints_without_adopting_and_record_tamper_is_rejected(self):
        graph, rule, cases = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            original = path.read_bytes()
            checked = apply_rule(rule, path, dry_run=True)
            self.assertEqual(checked["status"], "VALIDATED_ONLY")
            self.assertFalse(checked["adopted"])
            self.assertEqual(path.read_bytes(), original)
            report = evaluate_candidate(rule, graph, cases)
            adopted = apply_rule(rule, path, evaluation=report, cases=cases)
            record_path = Path(adopted["record_path"])
            record = json.loads(record_path.read_text()); record["before_raw_sha256"] = "forged"
            record_path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "record was changed"):
                rollback_rule(record_path, path)


if __name__ == "__main__":
    unittest.main()

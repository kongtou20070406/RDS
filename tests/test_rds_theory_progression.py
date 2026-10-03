import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_lean_verify
import rds_theory_progression as progression
from rds_verify_types import digest


SPEC = {
    "schema": 1,
    "claim_id": progression.CLAIM_ID,
    "domain": ["0", "1"],
    "assumptions": [],
    "transport_obligations": list(progression.TRANSPORTS),
    "limits": {"max_domain_size": 4, "max_native_pairs": 16, "egraph_iterations": 8},
}


def native_pass(spec):
    return {"status": "PASS", "assurance": "LEAN_KERNEL_CHECKED", "backend": "lean4_closed_rational",
            "certificate": {"spec_sha256": digest(spec), "verdict": "PASS"}}


def installed_native_lean():
    try:
        rds_lean_verify._executable()
        return True
    except (rds_lean_verify.NoNativeLean, ValueError, OSError):
        return False


class TheoryProgressionTests(unittest.TestCase):
    def test_three_existing_checks_bind_the_same_claim_and_all_domain_pairs(self):
        seen = []

        def check(spec):
            seen.append(spec)
            return native_pass(spec)

        result = progression.run_progression(SPEC, native_verify=check)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["assurance"], "FINITE_DOMAIN_EXHAUSTIVE_PLUS_NATIVE_LEAVES")
        self.assertEqual(result["scientific_assurance"], "UNKNOWN")
        self.assertEqual(result["application_status"], "UNKNOWN")
        self.assertEqual([stage["name"] for stage in result["stages"]], list(progression.STAGES))
        model, egraph, native = result["stages"]
        self.assertEqual(model["result"]["assurance"], "BOUNDED_FINITE_MODEL_VERIFIED")
        self.assertEqual(model["result"]["combinations_checked"], 4)
        self.assertEqual(egraph["result"]["assurance"], "BOUNDED_REWRITE_CHECK")
        self.assertEqual(egraph["result"]["certificate_status"], "NOT_EMITTED")
        self.assertEqual(egraph["result"]["transport"]["status"], "PASS")
        self.assertEqual(native["result"]["assurance"], "LEAN_KERNEL_CHECKED")
        self.assertEqual(native["result"]["transport"]["pairs_checked"], 4)
        self.assertEqual(len(seen), 4)
        self.assertTrue(all(leaf["certificate"] and leaf["status"] == "PASS"
                            for leaf in native["result"]["leaves"]))
        self.assertEqual([(item["left"], item["right"]) for item in seen],
                         [("0", "0"), ("0", "0"), ("0", "0"), ("1", "1")])
        self.assertTrue(all(item["kind"] == "lean_obligation" and item["relation"] == "eq"
                            for item in seen))
        for index, stage in enumerate(result["stages"]):
            self.assertTrue(progression._check_handoff(
                stage, progression.STAGES[index], result["claim_sha256"],
                None if index == 0 else result["stages"][index - 1]["stage_sha256"]))
            self.assertEqual(stage["claim_sha256"], result["claim_sha256"])

    def test_empty_invalid_unrelated_and_oversized_declarations_stay_unknown(self):
        cases = []
        for domain in ([], ["0", "0/1"], ["0", "1", "2", "3", "4"]):
            cases.append({**SPEC, "domain": domain})
        cases.extend(({**SPEC, "claim_id": "unrelated_claim"},
                      {**SPEC, "assumptions": ["assume the result"]},
                      {**SPEC, "transport_obligations": list(reversed(progression.TRANSPORTS))},
                      {**SPEC, "stages": [{"status": "PASS", "assurance": "LEAN_KERNEL_CHECKED"}]},
                      {**SPEC, "domain": [True]},
                      {**SPEC, "domain": [0.5]},
                      {**SPEC, "limits": {**SPEC["limits"], "max_native_pairs": 17}},
                      {**SPEC, "limits": {**SPEC["limits"], "max_domain_size": True}},
                      {"schema": True}))
        with mock.patch("rds_operators.BoundedFiniteModelOperator.verify_cayley_property") as unused:
            unused.side_effect = AssertionError("Invalid input must be rejected before a stage dispatch")
            for case in cases:
                with self.subTest(case=case):
                    result = progression.run_progression(case, native_verify=native_pass)
                    self.assertEqual(result["status"], "UNKNOWN")
                    self.assertEqual([stage["result"]["status"] for stage in result["stages"]],
                                     ["SKIPPED"] * 3)
                    unused.assert_not_called()

    def test_budget_skip_is_visible_and_does_not_upgrade_egraph_pass(self):
        spec = {**SPEC, "limits": {**SPEC["limits"], "max_native_pairs": 3}}
        result = progression.run_progression(spec, native_verify=native_pass)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual([item["result"]["status"] for item in result["stages"]],
                         ["PASS", "PASS", "SKIPPED"])
        self.assertIn("budget", result["stages"][2]["result"]["reason"])

    def test_missing_or_lower_assurance_lean_never_becomes_pass(self):
        for answer in ({"status": "UNKNOWN", "assurance": "NONE", "reason": "native Lean unavailable"},
                       {"status": "PASS", "assurance": "CERTIFICATE_CHECKED", "certificate": {}}):
            with self.subTest(answer=answer):
                result = progression.run_progression(SPEC, native_verify=lambda _spec: answer)
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertEqual(result["stages"][-1]["result"]["status"], "UNKNOWN")
                self.assertEqual(result["stages"][-1]["result"]["assurance"], "NONE")

    def test_bounded_values_cannot_be_promoted_by_a_different_assurance(self):
        with mock.patch("rds_operators.BoundedFiniteModelOperator.verify_cayley_property",
                        return_value={"status": "PASS", "assurance": "CERTIFICATE_CHECKED",
                                      "property": "commutative", "domain_size": 2,
                                      "combinations_checked": 4}):
            result = progression.run_progression(SPEC, native_verify=native_pass)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual([item["result"]["status"] for item in result["stages"]],
                         ["UNKNOWN", "SKIPPED", "SKIPPED"])

    def test_egraph_unknown_skips_lean_and_keeps_unknown(self):
        answer = {"status": "UNKNOWN", "assurance": "NONE", "certificate_status": "NOT_EMITTED"}
        with mock.patch("rds_operators.EGraphEquivalenceOperator.verify_algebraic_equivalence",
                        return_value=answer):
            result = progression.run_progression(SPEC, native_verify=native_pass)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["stages"][1]["result"]["status"], "UNKNOWN")
        self.assertEqual(result["stages"][2]["result"]["status"], "SKIPPED")

    def test_egraph_pass_with_a_supplied_certificate_is_not_accepted(self):
        answer = {"status": "PASS", "assurance": "BOUNDED_REWRITE_CHECK", "equivalent": True,
                  "domain": "rational_polynomials", "variables": ["a", "b"],
                  "input_sha256": "a" * 64, "certificate_status": "CERTIFICATE_CHECKED"}
        with mock.patch("rds_operators.EGraphEquivalenceOperator.verify_algebraic_equivalence",
                        return_value=answer):
            result = progression.run_progression(SPEC, native_verify=native_pass)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["stages"][1]["result"]["status"], "UNKNOWN")
        self.assertEqual(result["stages"][1]["result"]["reported_status"], "PASS")
        self.assertEqual(result["stages"][1]["result"]["transport"]["status"], "UNKNOWN")
        self.assertEqual(result["stages"][2]["result"]["status"], "SKIPPED")

    def test_failed_finite_counterexample_stops_later_stages(self):
        counterexample = {"status": "FAIL", "assurance": "COUNTEREXAMPLE_FOUND",
                          "property": "commutative", "counterexample": {"witness": ["0", "1"]}}
        with mock.patch("rds_operators.BoundedFiniteModelOperator.verify_cayley_property",
                        return_value=counterexample):
            result = progression.run_progression(SPEC, native_verify=native_pass)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual([stage["result"]["status"] for stage in result["stages"]],
                         ["FAIL", "SKIPPED", "SKIPPED"])

    def test_nonclosed_domain_does_not_misstate_a_failed_finite_check_as_refutation(self):
        result = progression.run_progression({**SPEC, "domain": ["1", "2"]}, native_verify=native_pass)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["stages"][0]["result"]["assurance"], "CLOSURE_VIOLATION")
        self.assertEqual(result["stages"][1]["result"]["status"], "SKIPPED")

    def test_tampered_or_foreign_stage_handoff_is_rejected(self):
        result = progression.run_progression(SPEC, native_verify=native_pass)
        finite = result["stages"][0]
        self.assertFalse(progression._check_handoff({**finite, "claim_sha256": "f" * 64},
                                                    progression.STAGES[0], result["claim_sha256"], None))
        self.assertFalse(progression._check_handoff({**finite, "stage_sha256": "0" * 64},
                                                    progression.STAGES[0], result["claim_sha256"], None))
        egraph = result["stages"][1]
        self.assertFalse(progression._check_handoff(egraph, progression.STAGES[1],
                                                    result["claim_sha256"], "foreign-stage"))

    def test_json_loader_rejects_duplicate_keys_float_nonfinite_and_oversized_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.json"
            for raw in (b'{"schema":1,"schema":1}', b'{"x":NaN}', b'{"x":1.0}',
                        b" " * (progression.MAX_SPEC_BYTES + 1)):
                path.write_bytes(raw)
                with self.subTest(prefix=raw[:32]), self.assertRaises(progression.InvalidProgression):
                    progression.load_spec(path)

    def test_real_cli_fails_closed_without_native_lean_and_reports_skipped_work(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/rds_theory_tools.py"),
                   "--progression", str(ROOT / "examples/theory-reformulation/progression.json")]
        with tempfile.TemporaryDirectory() as folder:
            env = os.environ.copy()
            env["RDS_LEAN_EXECUTABLE"] = str(Path(folder) / "missing-lean")
            result = subprocess.run(command, cwd=folder, env=env, capture_output=True,
                                    encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual([stage["result"]["status"] for stage in report["stages"]],
                         ["PASS", "PASS", "UNKNOWN"])
        self.assertNotIn("certificate", report["stages"][-1]["result"])

    @unittest.skipUnless(installed_native_lean(), "No native Lean toolchain is installed")
    def test_real_cli_native_lean_progression(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/rds_theory_tools.py"),
                   "--progression", str(ROOT / "examples/theory-reformulation/progression.json")]
        result = subprocess.run(command, cwd=ROOT, capture_output=True,
                                encoding="utf-8", timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout[-2000:])
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["stages"][-1]["result"]["assurance"], "LEAN_KERNEL_CHECKED")
        self.assertEqual(report["stages"][-1]["result"]["transport"]["pairs_checked"], 4)


if __name__ == "__main__":
    unittest.main()

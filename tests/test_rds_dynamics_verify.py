"""Exact affine-map certificate and obligation regressions."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_dynamics_verify as dynamics
from rds_verify_types import MAX_CERTIFICATE_BYTES


def spec(matrix, bias=None, kind="affine_contraction", threshold="1", point=None):
    result = {"schema": 1, "kind": kind, "model": {
        "matrix": matrix, "bias": bias if bias is not None else ["0"] * len(matrix)}}
    if kind in {"affine_contraction", "affine_dynamics"}:
        result["threshold"] = threshold
    if kind in {"affine_fixed_point", "affine_dynamics"}:
        result["point"] = point
    return result


class AffineDynamicsTests(unittest.TestCase):
    def test_example_contracts_and_preserves_nonzero_fixed_point(self):
        value = json.loads((ROOT / "examples/formal/affine_dynamics.json").read_text(encoding="utf-8"))
        result = dynamics.verify(value)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["assurance"], "CERTIFICATE_CHECKED")
        self.assertEqual(result["certificate"]["induced_norm"], "3/4")
        self.assertEqual(result["certificate"]["fixedpoint_residual"], ["0", "0"])
        self.assertTrue(dynamics.check_certificate(value, result["certificate"]))

    def test_nonnormal_matrix_has_exact_norm_counterexample(self):
        value = spec([["0", "2"], ["0", "0"]])
        result = dynamics.verify(value)
        self.assertEqual(result["status"], "FAIL")
        witness = result["certificate"]["witness"]["contraction"]
        self.assertEqual(witness["direction"], ["0", "1"])
        self.assertEqual(witness["image"], ["2", "0"])
        self.assertEqual(witness["image_norm"], "2")
        self.assertIn("infinity norm", result["scope"])

    def test_sign_witness_handles_negative_coefficients_and_bias_cancels(self):
        value = spec([["-1/2", "-3/4"], ["0", "0"]], bias=["9", "-4"])
        result = dynamics.verify(value)
        witness = result["certificate"]["witness"]["contraction"]
        self.assertEqual(witness["direction"], ["-1", "-1"])
        self.assertEqual(witness["image"], ["5/4", "0"])
        self.assertTrue(dynamics.check_certificate(value, result["certificate"]))

    def test_strict_contraction_threshold_boundary(self):
        self.assertEqual(dynamics.verify(spec([["1"]]))["status"], "FAIL")
        self.assertEqual(dynamics.verify(spec([["1/2"]], threshold="1/2"))["status"], "FAIL")
        self.assertEqual(dynamics.verify(spec([["499/1000"]], threshold="1/2"))["status"], "PASS")
        for threshold in ("0", "-1", "1001/1000"):
            with self.assertRaises(ValueError):
                dynamics.verify(spec([["0"]], threshold=threshold))

    def test_fixed_point_obligation_does_not_require_contraction(self):
        value = spec([["2"]], bias=["-2"], kind="affine_fixed_point", point=["2"])
        result = dynamics.verify(value)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["certificate"]["obligations"]["contraction"], "NOT_APPLICABLE")
        self.assertEqual(result["certificate"]["induced_norm"], "2")

    def test_bias_is_required_in_fixed_point_residual(self):
        value = spec([["1/2"]], bias=["1"], kind="affine_fixed_point", point=["0"])
        result = dynamics.verify(value)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["certificate"]["fixedpoint_residual"], ["1"])
        self.assertEqual(result["certificate"]["witness"]["fixed_point"]["mapped_point"], ["1"])

    def test_combined_contracting_map_with_wrong_point_cannot_pass(self):
        value = spec([["1/2"]], bias=["1"], kind="affine_dynamics", point=["0"])
        result = dynamics.verify(value)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["certificate"]["obligations"], {"contraction": "PASS", "fixed_point": "FAIL"})
        value["point"] = ["2"]
        self.assertEqual(dynamics.verify(value)["status"], "PASS")

    def test_combined_records_two_failed_obligations(self):
        value = spec([["2"]], bias=["1"], kind="affine_dynamics", point=["0"])
        certificate = dynamics.verify(value)["certificate"]
        self.assertEqual(certificate["case"], "contraction_and_fixed_point_counterexamples")
        self.assertEqual(set(certificate["witness"]), {"contraction", "fixed_point"})
        self.assertTrue(dynamics.check_certificate(value, certificate))

    def test_checker_is_independent_of_certificate_generator(self):
        value = spec([["1/2"]])
        certificate = dynamics.verify(value)["certificate"]
        with patch.object(dynamics, "verify", side_effect=AssertionError("must not regenerate")):
            self.assertTrue(dynamics.check_certificate(value, certificate))

    def test_forged_pass_norm_residual_and_witness_are_rejected(self):
        value = spec([["2"]], bias=["1"], kind="affine_dynamics", point=["0"])
        certificate = dynamics.verify(value)["certificate"]
        mutations = [
            ("verdict", "PASS"), ("row_norms", ["0"]), ("induced_norm", "0"),
            ("fixedpoint_residual", ["0"]), ("obligations", {"contraction": "PASS", "fixed_point": "PASS"}),
            ("witness", {}), ("dimension", True), ("version", True),
        ]
        for field, fake in mutations:
            with self.subTest(field=field):
                bad = {**certificate, field: fake}
                self.assertFalse(dynamics.check_certificate(value, bad))
        bad = copy.deepcopy(certificate)
        bad["witness"]["contraction"]["direction"] = ["-1"]
        self.assertFalse(dynamics.check_certificate(value, bad))
        bad = copy.deepcopy(certificate)
        bad["witness"]["fixed_point"]["coordinate"] = False
        self.assertFalse(dynamics.check_certificate(value, bad))

    def test_certificate_binds_full_spec_including_bias_point_and_threshold(self):
        value = spec([["1/2"]], bias=["1"], kind="affine_dynamics", point=["2"])
        certificate = dynamics.verify(value)["certificate"]
        changes = [lambda v: v.update(point=["0"]), lambda v: v.update(threshold="3/4"),
                   lambda v: v["model"].update(bias=["2"]),
                   lambda v: v["model"].update(matrix=[["1/3"]])]
        for mutate in changes:
            changed = copy.deepcopy(value)
            mutate(changed)
            self.assertFalse(dynamics.check_certificate(changed, certificate))

    def test_dimension_and_shape_bounds(self):
        for matrix in ([], [["0", "0"]], [["0"]] * 65):
            with self.assertRaises(ValueError):
                dynamics.verify(spec(matrix))
        with self.assertRaises(ValueError):
            dynamics.verify(spec([["0"]], bias=[]))
        with self.assertRaises(ValueError):
            dynamics.verify(spec([[0]]))
        matrix = [["1/2" if i == j else "0" for j in range(64)] for i in range(64)]
        self.assertEqual(dynamics.verify(spec(matrix))["status"], "PASS")

    def test_exact_arithmetic_and_certificate_byte_limits(self):
        denominator = str(2 ** 4095)
        huge_but_bounded = spec([["1/" + denominator]])
        self.assertEqual(dynamics.verify(huge_but_bounded)["status"], "PASS")
        with self.assertRaises(ValueError):
            dynamics.verify(spec([[str(2 ** 4096)]]))
        value = spec([[str(2 ** 4095)]], kind="affine_fixed_point", point=["2"])
        with self.assertRaises(ValueError):
            dynamics.verify(value)
        base = spec([["0"]])
        certificate = dynamics.verify(base)["certificate"]
        certificate["spec_sha256"] = "x" * (MAX_CERTIFICATE_BYTES + 1)
        self.assertFalse(dynamics.check_certificate(base, certificate))


if __name__ == "__main__":
    unittest.main()

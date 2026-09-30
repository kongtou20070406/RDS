"""Spectral certificates must separate exact spectra from sufficient bounds."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_matrix_verify as matrix_verifier
from rds_verify_types import MAX_CERTIFICATE_BYTES


def spec(matrix, threshold="1", kind="matrix_spectral_bound"):
    return {"schema": 1, "kind": kind, "matrix": matrix, "threshold": threshold}


class SpectralCertificateTests(unittest.TestCase):
    def test_nonnormal_stable_triangular_matrix_is_exactly_certified(self):
        value = spec([["1/2", "100"], ["0", "1/2"]])
        result = matrix_verifier.verify(value)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["certificate"]["method"], "exact_triangular")
        self.assertEqual(result["certificate"]["bound"], "1/2")
        self.assertEqual(result["certificate"]["row_bounds"], ["201/2", "1/2"])
        self.assertTrue(matrix_verifier.check_certificate(value, result["certificate"]))

    def test_lower_triangular_and_negative_diagonals(self):
        result = matrix_verifier.verify(spec([["1/3", "0"], ["-100", "2/5"]]))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["certificate"]["bound"], "2/5")
        result = matrix_verifier.verify(spec([["-5/4", "1"], ["0", "-1/2"]]))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["certificate"]["bound"], "5/4")

    def test_gershgorin_certifies_only_a_sufficient_strict_bound(self):
        value = spec([["1/10", "1/5"], ["-1/5", "1/10"]])
        result = matrix_verifier.verify(value)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["certificate"]["method"], "gershgorin")
        self.assertEqual(result["certificate"]["bound"], "3/10")
        self.assertIsNone(result["certificate"]["diagonal"])
        self.assertTrue(matrix_verifier.check_certificate(value, result["certificate"]))

    def test_nonsymmetric_cycle_large_sufficient_bound_is_unknown(self):
        # Actual eigenvalues are +/- 1/2, but the row bound alone is 4.
        result = matrix_verifier.verify(spec([["0", "4"], ["1/16", "0"]]))
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["bound"], "4")
        self.assertNotIn("certificate", result)

    def test_threshold_equality_fails_only_the_exact_triangular_case(self):
        self.assertEqual(matrix_verifier.verify(spec([["1", "99"], ["0", "1/2"]]))["status"], "FAIL")
        self.assertEqual(matrix_verifier.verify(spec([["0", "1"], ["9/10", "0"]]))["status"], "UNKNOWN")

    def test_exact_kind_does_not_approximate_rotation_eigenvalues(self):
        value = spec([["0", "1"], ["-1", "0"]], threshold="2", kind="matrix_spectral_exact")
        self.assertEqual(matrix_verifier.verify(value)["status"], "UNKNOWN")
        value["kind"] = "matrix_spectral_bound"
        self.assertEqual(matrix_verifier.verify(value)["status"], "PASS")
        self.assertEqual(matrix_verifier.verify(spec([["1/2"]], kind="matrix_spectral_exact"))["status"], "PASS")

    def test_no_float_tolerance_or_threshold_at_most_one_restriction(self):
        tiny = "1." + "0" * 199 + "1"
        self.assertEqual(matrix_verifier.verify(spec([[tiny]]))["status"], "FAIL")
        self.assertEqual(matrix_verifier.verify(spec([["100"]], threshold="101"))["status"], "PASS")
        for threshold in ("0", "-1"):
            with self.assertRaises(ValueError):
                matrix_verifier.verify(spec([["0"]], threshold=threshold))
        with self.assertRaises(ValueError):
            matrix_verifier.verify(spec([[0.5]]))

    def test_checker_does_not_call_generator(self):
        value = spec([["1/2", "100"], ["0", "1/2"]])
        certificate = matrix_verifier.verify(value)["certificate"]
        with patch.object(matrix_verifier, "verify", side_effect=AssertionError("must not generate")):
            self.assertTrue(matrix_verifier.check_certificate(value, certificate))

    def test_forged_verdict_rows_diagonal_and_method_are_rejected(self):
        value = spec([["1", "99"], ["0", "1/2"]])
        certificate = matrix_verifier.verify(value)["certificate"]
        mutations = [("verdict", "PASS"), ("bound", "0"), ("row_bounds", ["0", "0"]),
                     ("diagonal", ["0", "0"]), ("method", "gershgorin"), ("version", True)]
        for field, fake in mutations:
            with self.subTest(field=field):
                self.assertFalse(matrix_verifier.check_certificate(value, {**certificate, field: fake}))
        value = spec([["1/10", "1/5"], ["-1/5", "1/10"]])
        certificate = matrix_verifier.verify(value)["certificate"]
        self.assertFalse(matrix_verifier.check_certificate(value, {
            **certificate, "method": "exact_triangular", "diagonal": ["1/10", "1/10"], "bound": "1/10"}))

    def test_certificate_binds_matrix_threshold_and_kind(self):
        value = spec([["1/2"]])
        certificate = matrix_verifier.verify(value)["certificate"]
        for changed in (spec([["2"]]), spec([["1/2"]], threshold="2"),
                        spec([["1/2"]], kind="matrix_spectral_exact")):
            self.assertFalse(matrix_verifier.check_certificate(changed, certificate))

    def test_dimension_shape_bits_and_certificate_bounds(self):
        for value in (spec([]), spec([["0", "0"]]), spec([["0"]] * 65)):
            with self.assertRaises(ValueError):
                matrix_verifier.verify(value)
        matrix = [["1/2" if i == j else "0" for j in range(64)] for i in range(64)]
        self.assertEqual(matrix_verifier.verify(spec(matrix))["status"], "PASS")
        bounded_fraction = "1/" + str(2 ** 4095)
        self.assertEqual(matrix_verifier.verify(spec([[bounded_fraction]]))["status"], "PASS")
        with self.assertRaises(ValueError):
            matrix_verifier.verify(spec([[str(2 ** 4096)]]))
        huge = str(2 ** 4095)
        with self.assertRaises(ValueError):
            matrix_verifier.verify(spec([[huge, huge], ["0", "0"]]))
        value = spec([["0"]])
        certificate = matrix_verifier.verify(value)["certificate"]
        certificate["spec_sha256"] = "x" * (MAX_CERTIFICATE_BYTES + 1)
        self.assertFalse(matrix_verifier.check_certificate(value, certificate))


if __name__ == "__main__":
    unittest.main()

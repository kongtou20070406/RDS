"""Adversarial tactic chains: no crashes, infinite search or guessed precision."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_verify import LeanFormalEngine, verify, check_certificate
from rds_verify_types import rational
import rds_nn_verify
import rds_probe


def network():
    return {"schema": 1, "kind": "network_bounds", "model": {"input_dim": 1,
            "layers": [{"kind": "linear", "weight": [["1"], ["-1"]], "bias": ["0", "0"]},
                       {"kind": "relu"}]}, "input_box": [["-1", "1"]],
            "output_bounds": [["0", "1"], ["0", "1"]]}


class TacticAdversarialTests(unittest.TestCase):
    def test_six_tactic_chain_accepts_only_independently_checked_evidence(self):
        engine = LeanFormalEngine()
        result = engine.verify(network(), tactics=["gershgorin", "spectral_radius", "scale_invariance", "lean4", "interval", "rule"])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual([t["status"] for t in result["tactics"][:4]], ["UNKNOWN"] * 4)
        self.assertTrue(check_certificate(network(), result["certificate"]))

    def test_unavailable_tactics_do_not_convert_numerical_guesses_to_proofs(self):
        for tactic in ("gershgorin", "spectral_radius", "scale_invariance", "lean4"):
            with self.subTest(tactic=tactic):
                answer = LeanFormalEngine().verify(network(), [tactic])
                self.assertEqual(answer["status"], "UNKNOWN")
                self.assertNotIn("certificate", answer)

    def test_unsupported_nonlinearity_fail_closed_for_every_tactic(self):
        spec = network()
        spec["model"]["layers"][1] = {"kind": "sigmoid"}
        for tactic in LeanFormalEngine.TACTICS:
            with self.subTest(tactic=tactic):
                self.assertEqual(LeanFormalEngine().verify(spec, [tactic])["status"], "UNKNOWN")

    def test_forged_generator_pass_is_rejected_without_using_reported_precision(self):
        fake = {"status": "PASS", "assurance": "CERTIFICATE_CHECKED", "precision": 1.0,
                "certificate": {"verdict": "PASS", "spec_sha256": "0" * 64}}
        with patch.object(rds_nn_verify, "verify", return_value=fake):
            self.assertEqual(verify(network())["status"], "UNKNOWN")

    def test_interval_dependency_is_inconclusive_not_a_counterexample(self):
        spec = network()
        spec["model"]["layers"] = [
            {"kind": "linear", "weight": [["1"], ["1"]], "bias": ["0", "0"]},
            {"kind": "linear", "weight": [["1", "-1"]], "bias": ["0"]}]
        spec["output_bounds"] = [["0", "0"]]
        with patch.object(rds_nn_verify, "verify", wraps=rds_nn_verify.verify) as generate:
            answer = LeanFormalEngine().verify(spec, ["rule", "interval"])
        self.assertEqual(answer["status"], "UNKNOWN")
        generate.assert_called_once()  # no repeated symbolic/interval effort

    def test_duplicate_tactics_and_unbounded_chain_are_rejected(self):
        for chain in ([], ["rule"] * 100, ["rule", "rule"], ["import os"], [True]):
            self.assertEqual(LeanFormalEngine().verify(network(), chain)["status"], "UNKNOWN")

    def test_definition_and_theorem_cycles_terminate_without_search(self):
        spec = {"schema": 1, "kind": "theorem_module", "definitions": {"a": {"$ref": "b"}, "b": {"$ref": "a"}},
                "theorems": [{"name": "a", "statement": {"kind": "all", "of": ["b"]},
                              "by": {"rule": "logic.and_intro", "premises": ["b"]}},
                             {"name": "b", "statement": {"kind": "all", "of": ["a"]},
                              "by": {"rule": "logic.and_intro", "premises": ["a"]}}]}
        self.assertEqual(LeanFormalEngine().verify(spec)["status"], "UNKNOWN")
        spec["definitions"] = {}
        self.assertEqual(LeanFormalEngine().verify(spec)["status"], "UNKNOWN")

    def test_shape_depth_bytes_nonfinite_and_integer_limits(self):
        spec = network()
        spec["model"]["input_dim"] = 65
        self.assertEqual(verify(spec)["status"], "UNKNOWN")
        spec = network()
        spec["input_box"][0][0] = float("nan")
        self.assertEqual(verify(spec)["status"], "UNKNOWN")
        for value in ("1e1201", "1e999999", "1/0", "NaN", True, 1.0, 1 << 4096):
            with self.subTest(value=str(value)[:30]):
                with self.assertRaises((ValueError, ZeroDivisionError)):
                    rational(value)
        deep = 0
        for _ in range(70):
            deep = [deep]
        for bad in (deep, {"kind": "x", "blob": "x" * (2 * 1024 * 1024 + 1)}, {"kind": "x", "value": 1 << 4096}):
            self.assertEqual(verify(bad)["status"], "UNKNOWN")

    def test_nonlinear_nested_powers_rejected_before_sympy_import(self):
        source = "def control(x): return 0\ndef treatment(x): return (((x**4)**4)**4)**4\n"
        functions = rds_probe.parse_source(source)
        formal = {"kind": "strict_algebraic_threshold", "domain": ["0", "1"], "threshold": "1", "max_loss": "1",
                  "statement": "threshold_separation"}
        with patch.object(rds_probe, "symbolic_probe", wraps=rds_probe.symbolic_probe):
            answer = rds_probe.formal_probe(functions, formal)
        self.assertEqual(answer["status"], "UNKNOWN")

    def test_cancelled_denominator_is_not_treated_as_an_identity(self):
        spec = {"schema": 1, "kind": "scalar_threshold", "source": "def control(x): return 0\ndef treatment(x): return x/x\n",
                "formal": {"domain": ["-1", "1"], "threshold": "1"}}
        self.assertEqual(LeanFormalEngine().verify(spec)["status"], "UNKNOWN")

    def test_residual_small_gain_does_not_make_identity_contracting(self):
        # F=0 has Lipschitz bound K=1; alpha=1/2 satisfies alpha<1/K,
        # but I+alpha*F remains the identity. A residual lemma cannot assert PASS.
        claim = {"schema": 1, "kind": "affine_contraction",
                 "model": {"matrix": [["1"]], "bias": ["0"]}, "threshold": "1"}
        answer = LeanFormalEngine().verify(claim)
        self.assertEqual(answer["status"], "FAIL")
        self.assertTrue(check_certificate(claim, answer["certificate"]))

    def test_spectral_radius_cannot_be_substituted_for_a_matrix_norm(self):
        matrix = [["1/2", "100"], ["0", "1/2"]]
        spectral = {"schema": 1, "kind": "matrix_spectral_exact", "matrix": matrix, "threshold": "1"}
        norm = {"schema": 1, "kind": "affine_contraction", "model": {"matrix": matrix, "bias": ["0", "0"]},
                "threshold": "1"}
        engine = LeanFormalEngine()
        proof = engine.verify(spectral, ["spectral_radius"])
        self.assertEqual(proof["status"], "PASS")
        self.assertEqual(engine.verify(norm)["status"], "FAIL")
        self.assertFalse(check_certificate(norm, proof["certificate"]))


if __name__ == "__main__":
    unittest.main()

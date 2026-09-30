import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rds_scale_verify as scale
from rds_verify import LeanFormalEngine


def spec():
    return {"schema": 1, "kind": "scale_equivariance", "scale": "3/2",
            "model": {"input_dim": 2, "layers": [
                {"kind": "linear", "weight": [["-1", "1/2"], ["0", "2"]], "bias": ["0", "0"]},
                {"kind": "relu"}, {"kind": "linear", "weight": [["1", "-1"]], "bias": ["0"]}]}}


class ScalingProofTests(unittest.TestCase):
    def test_universal_positive_relu_equivariance_and_independent_checker(self):
        claim = spec()
        answer = scale.verify(claim)
        self.assertEqual(answer["status"], "PASS")
        with patch.object(scale, "verify", side_effect=AssertionError("No search")):
            self.assertTrue(scale.check_certificate(claim, answer["certificate"]))
        self.assertEqual(LeanFormalEngine().verify(claim, ["scale_invariance"])["status"], "PASS")

    def test_bias_is_inconclusive_and_negative_scale_is_rejected(self):
        claim = spec()
        claim["model"]["layers"][0]["bias"][0] = "1"
        self.assertEqual(scale.verify(claim)["status"], "UNKNOWN")
        claim["scale"] = "1"
        self.assertEqual(scale.verify(claim)["status"], "PASS")
        for bad in ("0", "-1", "1e9999", True, float("nan")):
            claim["scale"] = bad
            self.assertEqual(LeanFormalEngine().verify(claim, ["scale_invariance"])["status"], "UNKNOWN")

    def test_forged_homogeneity_and_nonlinear_layer_are_rejected(self):
        claim = spec()
        proof = scale.verify(claim)["certificate"]
        proof["layers"][0]["zero_bias"] = False
        self.assertFalse(scale.check_certificate(claim, proof))
        claim["model"]["layers"][1] = {"kind": "sigmoid"}
        self.assertEqual(LeanFormalEngine().verify(claim)["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

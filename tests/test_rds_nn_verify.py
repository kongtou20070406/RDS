"""Independent trace replay and conservative dense/ReLU network decisions."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_nn_verify as nn


def network(weight=None, bias=None, box=None, bounds=None):
    return {"schema": 1, "kind": "network_bounds",
            "model": {"input_dim": 1, "layers": [{"kind": "linear", "weight": weight or [["2"]], "bias": bias or ["0"]}]},
            "input_box": box or [["0", "1"]], "output_bounds": bounds or [["0", "2"]]}


def margin_network(box=None, bias=None):
    spec = network(weight=[["1"], ["1"]], bias=bias or ["2", "0"], box=box)
    spec.pop("output_bounds")
    spec.update(kind="network_margin", target=0, margin="1")
    return spec


class NetworkVerificationTests(unittest.TestCase):
    def test_dense_relu_example_has_checked_complete_trace(self):
        spec = json.loads((ROOT / "examples/formal/network_bounds.json").read_text(encoding="utf-8"))
        result = nn.verify(spec)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["assurance"], "CERTIFICATE_CHECKED")
        self.assertEqual(len(result["certificate"]["trace"]), 3)
        self.assertEqual(result["certificate"]["trace"][1]["bounds"], [["0", "2"], ["0", "2"]])
        # Certificate checking does not call the producer or bounded search.
        with patch.object(nn, "verify", side_effect=AssertionError("producer called")), \
                patch.object(nn, "_candidate_inputs", side_effect=AssertionError("search called")):
            self.assertTrue(nn.check_certificate(spec, result["certificate"]))

    def test_interval_overapproximation_is_unknown_for_shared_variables(self):
        spec = network(box=[["-1", "1"]], bounds=[["0", "0"]])
        spec["model"]["layers"] = [
            {"kind": "linear", "weight": [["1"], ["1"]], "bias": ["0", "0"]},
            {"kind": "linear", "weight": [["1", "-1"]], "bias": ["0"]},
        ]
        result = nn.verify(spec)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["assurance"], "NONE")
        self.assertIsNone(result["certificate"])
        self.assertGreater(result["candidates_checked"], 0)

    def test_fail_requires_an_exact_forward_counterexample(self):
        spec = network(bounds=[["0", "1"]])
        result = nn.verify(spec)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["assurance"], "EXACT_COUNTEREXAMPLE_CHECKED")
        certificate = result["certificate"]
        self.assertEqual(certificate["witness"], {"input": ["1"]})
        self.assertTrue(nn.check_certificate(spec, certificate))
        valid_point = copy.deepcopy(certificate)
        valid_point["witness"]["input"] = ["0"]
        valid_point["trace"][0]["values"] = ["0"]
        self.assertFalse(nn.check_certificate(spec, valid_point))
        outside = copy.deepcopy(certificate)
        outside["witness"]["input"] = ["2"]
        outside["trace"][0]["values"] = ["4"]
        self.assertFalse(nn.check_certificate(spec, outside))

    def test_margin_proof_counterexample_and_correlation_unknown(self):
        spec = margin_network()
        result = nn.verify(spec)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(nn.check_certificate(spec, result["certificate"]))
        correlated = margin_network(box=[["-1", "1"]])
        self.assertEqual(nn.verify(correlated)["status"], "UNKNOWN")
        bad = margin_network(bias=["0", "1"])
        result = nn.verify(bad)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(nn.check_certificate(bad, result["certificate"]))

    def test_forgeries_and_changed_statements_are_rejected(self):
        spec = network()
        certificate = nn.verify(spec)["certificate"]
        mutations = []
        wrong = copy.deepcopy(certificate)
        wrong["trace"][0]["bounds"] = [["0", "1"]]
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["trace"] = []
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["model_sha256"] = "0" * 64
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["verdict"] = "FAIL"
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["version"] = True
        mutations.append(wrong)
        for wrong in mutations:
            self.assertFalse(nn.check_certificate(spec, wrong))
        changed = copy.deepcopy(spec)
        changed["output_bounds"] = [["0", "3"]]
        self.assertFalse(nn.check_certificate(changed, certificate))
        changed["model"]["layers"][0]["weight"] = [["1"]]
        self.assertFalse(nn.check_certificate(changed, certificate))
        example = json.loads((ROOT / "examples/formal/network_bounds.json").read_text(encoding="utf-8"))
        proof = nn.verify(example)["certificate"]
        proof["trace"][0], proof["trace"][1] = proof["trace"][1], proof["trace"][0]
        self.assertFalse(nn.check_certificate(example, proof))

    def test_multiinput_shape_and_exact_nonfloating_parameters(self):
        spec = network(weight=[["1/2", "-1e-1"]], bounds=[["-1/10", "1/2"]])
        spec["model"]["input_dim"] = 2
        spec["input_box"] = [["0", "1"], ["0", "1"]]
        self.assertEqual(nn.verify(spec)["status"], "PASS")
        malformed = []
        wrong = copy.deepcopy(spec)
        wrong["model"]["layers"][0]["weight"] = [["1"]]
        malformed.append(wrong)
        wrong = copy.deepcopy(spec)
        wrong["model"]["layers"][0]["bias"] = ["0", "0"]
        malformed.append(wrong)
        wrong = copy.deepcopy(spec)
        wrong["output_bounds"] = [["0", "1"], ["0", "1"]]
        malformed.append(wrong)
        wrong = copy.deepcopy(spec)
        wrong["input_box"][0] = ["1", "0"]
        malformed.append(wrong)
        wrong = copy.deepcopy(spec)
        wrong["model"]["layers"][0]["weight"][0][0] = 0.5
        malformed.append(wrong)
        wrong = copy.deepcopy(spec)
        wrong["kind"] = "network_onnx"
        malformed.append(wrong)
        for wrong in malformed:
            with self.subTest(spec=wrong):
                self.assertEqual(nn.verify(wrong)["status"], "UNKNOWN")
                self.assertFalse(nn.check_certificate(wrong, {}))

    def test_resource_limits_and_malformed_certificates(self):
        wide = network()
        wide["model"]["input_dim"] = 65
        self.assertEqual(nn.verify(wide)["status"], "UNKNOWN")
        deep = network()
        deep["model"]["layers"] = [{"kind": "relu"}] * 33
        self.assertEqual(nn.verify(deep)["status"], "UNKNOWN")
        large = network()
        large["model"] = {"input_dim": 64, "layers": [
            {"kind": "linear", "weight": [["1"] * 64 for _ in range(64)], "bias": ["0"] * 64}
            for _ in range(4)]}
        large["input_box"] = [["0", "1"]] * 64
        large["output_bounds"] = [["0", "100000000"]] * 64
        self.assertEqual(nn.verify(large)["status"], "UNKNOWN")
        overflow = network(weight=[["1e1200"]], box=[["1e1200", "1e1200"]])
        self.assertEqual(nn.verify(overflow)["status"], "UNKNOWN")
        spec = network()
        certificate = nn.verify(spec)["certificate"]
        oversized = {**certificate, "padding": "x" * nn.MAX_CERTIFICATE_BYTES}
        self.assertFalse(nn.check_certificate(spec, oversized))
        for certificate in (None, [], {}, {"trace": []}):
            self.assertFalse(nn.check_certificate(spec, certificate))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Concrete tensor arithmetic, shape discipline and independent certificate replay."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_tensor_verify as tensor


def literal(shape, values):
    return {"op": "literal", "shape": shape, "values": [str(v) for v in values]}


def identity(left, right):
    return {"schema": 1, "kind": "tensor_identity", "left": left, "right": right}


class TensorVerificationTests(unittest.TestCase):
    def test_transposed_product_example_and_independent_checker(self):
        spec = json.loads((ROOT / "examples/formal/tensor_identity.json").read_text(encoding="utf-8"))
        result = tensor.verify(spec)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["assurance"], "CERTIFICATE_CHECKED")
        self.assertEqual(result["certificate"]["trace"][-1]["values"], ["4", "10", "5", "11"])
        with patch.object(tensor, "verify", side_effect=AssertionError("Producer called")):
            self.assertTrue(tensor.check_certificate(spec, result["certificate"]))

    def test_scalar_add_scale_and_exact_decimal(self):
        left = {"op": "add", "left": {"op": "scale", "factor": "1/2", "arg": literal([], [2])},
                "right": literal([], ["1/4"])}
        spec = identity(left, literal([], ["5/4"]))
        self.assertEqual(tensor.verify(spec)["status"], "PASS")
        decimal = identity({"op": "add", "left": literal([], ["0.1"]), "right": literal([], ["0.2"])},
                           literal([], ["0.3"]))
        self.assertEqual(tensor.verify(decimal)["status"], "PASS")
        scalar_transpose = identity({"op": "transpose", "axes": [], "arg": literal([], [1])}, literal([], [1]))
        self.assertEqual(tensor.verify(scalar_transpose)["status"], "PASS")

    def test_rank_three_and_four_batched_matmul_without_broadcasting(self):
        for shape in ([2, 2, 2], [2, 1, 2, 2]):
            with self.subTest(shape=shape):
                expr = {"op": "matmul", "left": literal(shape, range(1, 9)),
                        "right": literal(shape, [1, 0, 0, 1, 2, 0, 0, 2])}
                spec = identity(expr, literal(shape, [1, 2, 3, 4, 10, 12, 14, 16]))
                result = tensor.verify(spec)
                self.assertEqual(result["status"], "PASS")
                self.assertTrue(tensor.check_certificate(spec, result["certificate"]))
        wrong_batch = {"op": "matmul", "left": literal([2, 2, 2], range(8)),
                       "right": literal([1, 2, 2], [1, 0, 0, 1])}
        self.assertEqual(tensor.verify(identity(wrong_batch, literal([2, 2, 2], range(8))))["status"], "UNKNOWN")

    def test_rank_four_transpose_uses_row_major_axis_permutation(self):
        expr = {"op": "transpose", "axes": [3, 1, 0, 2], "arg": literal([2, 1, 2, 2], range(8))}
        spec = identity(expr, literal([2, 1, 2, 2], [0, 2, 4, 6, 1, 3, 5, 7]))
        self.assertEqual(tensor.verify(spec)["status"], "PASS")

    def test_actual_element_mismatch_and_bounds_failures(self):
        spec = identity(literal([2], [1, 2]), literal([2], [1, 3]))
        result = tensor.verify(spec)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["assurance"], "EXACT_COUNTEREXAMPLE_CHECKED")
        self.assertEqual(result["certificate"]["conclusion"]["index"], 1)
        self.assertTrue(tensor.check_certificate(spec, result["certificate"]))
        bounds = {"schema": 1, "kind": "tensor_bounds", "expr": literal([3], [-2, 0, 2]), "lower": "-2", "upper": "2"}
        self.assertEqual(tensor.verify(bounds)["status"], "PASS")
        bounds["upper"] = "1"
        result = tensor.verify(bounds)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["certificate"]["conclusion"]["value"], "2")
        self.assertTrue(tensor.check_certificate(bounds, result["certificate"]))
        bounds["lower"] = "3"
        self.assertEqual(tensor.verify(bounds)["status"], "UNKNOWN")

    def test_trace_conclusion_and_statement_forgery(self):
        spec = identity({"op": "scale", "factor": "2", "arg": literal([2], [1, 2])}, literal([2], [2, 4]))
        certificate = tensor.verify(spec)["certificate"]
        mutations = []
        wrong = copy.deepcopy(certificate)
        wrong["trace"][1]["values"] = ["2", "5"]
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["trace"][1]["shape"] = [1, 2]
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["trace"][0]["node"] = False
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["trace"].pop()
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["trace"][0], wrong["trace"][1] = wrong["trace"][1], wrong["trace"][0]
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["verdict"] = "FAIL"
        mutations.append(wrong)
        wrong = copy.deepcopy(certificate)
        wrong["conclusion"] = {"case": "all_elements_equal", "shape": [1, 2]}
        mutations.append(wrong)
        for wrong in mutations:
            self.assertFalse(tensor.check_certificate(spec, wrong))
        changed = copy.deepcopy(spec)
        changed["left"]["factor"] = "3"
        self.assertFalse(tensor.check_certificate(changed, certificate))
        for wrong in (None, [], {}, {"version": True}):
            self.assertFalse(tensor.check_certificate(spec, wrong))

    def test_shape_and_unsupported_operation_are_unknown(self):
        left = literal([2], [1, 2])
        for right in (literal([1, 2], [1, 2]), literal([2], [1]), literal([0], []),
                      {"op": "variable", "name": "A"}):
            self.assertEqual(tensor.verify(identity(left, right))["status"], "UNKNOWN")
        for expr in ({"op": "add", "left": left, "right": literal([], [1])},
                     {"op": "transpose", "axes": [0, 0], "arg": literal([2, 2], range(4))},
                     {"op": "matmul", "left": left, "right": left}):
            self.assertEqual(tensor.verify(identity(expr, left))["status"], "UNKNOWN")

    def test_resource_limits_before_arithmetic_and_certificate_replay(self):
        too_wide = identity(literal([65], range(65)), literal([65], range(65)))
        self.assertEqual(tensor.verify(too_wide)["status"], "UNKNOWN")
        cumulative = identity(literal([64, 64], range(4096)), literal([64, 64], range(4096)))
        self.assertEqual(tensor.verify(cumulative)["status"], "UNKNOWN")
        deep = literal([], [1])
        for _ in range(128):
            deep = {"op": "scale", "factor": "1", "arg": deep}
        self.assertEqual(tensor.verify(identity(deep, literal([], [1])))["status"], "UNKNOWN")
        expr = {"op": "scale", "factor": "2", "arg": literal([8], range(8))}
        spec = identity(expr, literal([8], range(0, 16, 2)))
        with patch.object(tensor, "MAX_OPERATIONS", 8):
            self.assertEqual(tensor.verify(spec)["status"], "UNKNOWN")
        overflow = identity({"op": "scale", "factor": "1e1200", "arg": literal([], ["1e1200"])}, literal([], [1]))
        self.assertEqual(tensor.verify(overflow)["status"], "UNKNOWN")
        spec = identity(literal([], [1]), literal([], [1]))
        certificate = tensor.verify(spec)["certificate"]
        self.assertFalse(tensor.check_certificate(spec, {**certificate, "padding": "x" * tensor.MAX_CERTIFICATE_BYTES}))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Exact encoding and export guard tests; real PyTorch tests are optional."""
import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_model_export import UnsupportedModel, binary_rational, export_sequential

try:
    import torch
except ImportError:
    torch = None


class EncodingTests(unittest.TestCase):
    def test_binary_values_and_extreme_finite_values_are_exact(self):
        for value in (0.0, -0.0, 0.1, -3.5, 1.0, sys.float_info.max, math.ulp(0.0)):
            self.assertEqual(Fraction(binary_rational(value)), Fraction.from_float(value))
        self.assertEqual(binary_rational(0.1), "3602879701896397/36028797018963968")
        self.assertEqual(binary_rational(-0.0), "0")
        for value in (float("nan"), float("inf"), -float("inf"), True, "0.1", complex(1), None):
            with self.assertRaises(ValueError):
                binary_rational(value)

    def test_missing_optional_dependency_is_explicit(self):
        with patch.dict(sys.modules, {"torch": None}):
            with self.assertRaisesRegex(ImportError, "PyTorch is unavailable"):
                export_sequential(object())


# These are interface doubles for validation paths, not a PyTorch runtime.
class _Tensor:
    def __init__(self, values, dtype="float32"):
        self.values, self.dtype = values, dtype
        self.shape = ((len(values), len(values[0])) if values and isinstance(values[0], list)
                      else (len(values),))
    def detach(self):
        return self
    def cpu(self):
        return self
    def clone(self):
        return _Tensor(copy.deepcopy(self.values), self.dtype)
    def tolist(self):
        return copy.deepcopy(self.values)


class _Parameter(_Tensor):
    pass


class _Module:
    def __init__(self):
        self.training = False
        self._modules, self._parameters, self._buffers, self._forward_hooks = {}, {}, {}, {}
    def forward(self, value):
        raise AssertionError("Exporter must never execute forward")


class _Linear(_Module):
    def __init__(self, weight, bias=None):
        super().__init__()
        self.weight = _Parameter(weight)
        self.bias = None if bias is None else _Parameter(bias)
        self.out_features, self.in_features = self.weight.shape
        self._parameters = {"weight": self.weight, "bias": self.bias}


class _ReLU(_Module):
    pass


class _Sequential(_Module):
    def __init__(self, *layers):
        super().__init__()
        self._modules = {str(i): layer for i, layer in enumerate(layers)}


def _mock_torch():
    def isfinite(tensor):
        values = [v for row in tensor.values for v in row] if len(tensor.shape) == 2 else tensor.values
        return SimpleNamespace(all=lambda: SimpleNamespace(item=lambda: all(math.isfinite(v) for v in values)))
    nn = SimpleNamespace(Sequential=_Sequential, Linear=_Linear, ReLU=_ReLU, Parameter=_Parameter,
                         modules=SimpleNamespace(module=SimpleNamespace(_global_forward_hooks={})),
                         utils=SimpleNamespace(parametrize=SimpleNamespace(is_parametrized=lambda module: False)))
    return SimpleNamespace(nn=nn, __version__="interface-double", isfinite=isfinite,
                           float16="float16", bfloat16="bfloat16", float32="float32", float64="float64")


class ExportGuardTests(unittest.TestCase):
    def setUp(self):
        self.runtime = _mock_torch()
        self.patch = patch.dict(sys.modules, {"torch": self.runtime})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_snapshot_nested_container_and_no_forward_execution(self):
        linear = _Linear([[0.1, -0.5]], [0.25])
        result = export_sequential(_Sequential(_ReLU(), _Sequential(linear, _ReLU())))
        self.assertEqual(result["model"]["input_dim"], 2)
        self.assertEqual(result["model"]["layers"][1]["weight"], [[binary_rational(0.1), "-1/2"]])
        self.assertEqual(result["model"]["layers"][1]["bias"], ["1/4"])
        frozen = json.dumps(result, sort_keys=True)
        linear.weight.values[0][0] = 99.0
        self.assertEqual(json.dumps(result, sort_keys=True), frozen)
        self.assertEqual(len(result["provenance"]["weights_sha256"]), 64)
        self.assertEqual(len(result["provenance"]["model_sha256"]), 64)

    def test_bias_none_and_shape_or_dimension_mismatch(self):
        model = _Sequential(_Linear([[1.0, 2.0]], None))
        self.assertEqual(export_sequential(model)["model"]["layers"][0]["bias"], ["0"])
        bad = _Linear([[1.0]], [0.0, 0.0])
        with self.assertRaisesRegex(UnsupportedModel, "shape"):
            export_sequential(_Sequential(bad))
        with self.assertRaisesRegex(UnsupportedModel, "dimensions do not compose"):
            export_sequential(_Sequential(_Linear([[1.0, 2.0]]), _Linear([[1.0, 2.0]])))

    def test_unsupported_layers_subclasses_hooks_and_training_mode(self):
        class CustomLinear(_Linear):
            pass
        for model in (_Sequential(object()), _Sequential(CustomLinear([[1.0]])), _Sequential(_ReLU())):
            with self.assertRaises(UnsupportedModel):
                export_sequential(model)
        model = _Sequential(_Linear([[1.0]]))
        model.training = True
        with self.assertRaisesRegex(UnsupportedModel, "eval"):
            export_sequential(model)
        model.training = False
        model._modules["0"]._forward_hooks[1] = object()
        with self.assertRaisesRegex(UnsupportedModel, "hooks"):
            export_sequential(model)
        model._modules["0"]._forward_hooks.clear()
        model.forward = lambda value: value
        with self.assertRaisesRegex(UnsupportedModel, "overrides"):
            export_sequential(model)

    def test_nonfinite_parametrized_global_hooks_and_cycles(self):
        for value in (float("nan"), float("inf")):
            with self.assertRaisesRegex(UnsupportedModel, "Nonfinite"):
                export_sequential(_Sequential(_Linear([[value]])))
        model = _Sequential(_Linear([[1.0]]))
        self.runtime.nn.utils.parametrize.is_parametrized = lambda module: type(module) is _Linear
        with self.assertRaisesRegex(UnsupportedModel, "Parametrized"):
            export_sequential(model)
        self.runtime.nn.utils.parametrize.is_parametrized = lambda module: False
        self.runtime.nn.modules.module._global_forward_hooks[0] = object()
        with self.assertRaisesRegex(UnsupportedModel, "Global"):
            export_sequential(model)
        self.runtime.nn.modules.module._global_forward_hooks.clear()
        model._modules["cycle"] = model
        with self.assertRaisesRegex(UnsupportedModel, "Cyclic"):
            export_sequential(model)

    def test_snapshot_limits_reject_before_materializing_large_model(self):
        model = _Sequential(_Linear([[1.0]]))
        with patch("rds_model_export.MAX_PARAMETERS", 1):
            with self.assertRaisesRegex(UnsupportedModel, "parameter"):
                export_sequential(model)
        with patch("rds_model_export.MAX_LAYERS", 0):
            with self.assertRaisesRegex(UnsupportedModel, "layer"):
                export_sequential(model)

    def test_parameter_instance_cannot_replace_snapshot_methods(self):
        linear = _Linear([[1.0]], [0.0])
        linear.weight.detach = lambda: _Tensor([[9.0]])
        with self.assertRaisesRegex(UnsupportedModel, "snapshot method"):
            export_sequential(_Sequential(linear))
        self.assertEqual(linear.weight.values, [[1.0]])


@unittest.skipIf(torch is None, "PyTorch is not installed; real module tests were not executed")
class RealTorchExportTests(unittest.TestCase):
    def test_real_parameters_are_snapshotted_and_saved(self):
        model = torch.nn.Sequential(torch.nn.Linear(2, 2, bias=False), torch.nn.ReLU(),
                                    torch.nn.Sequential(torch.nn.Linear(2, 1))).eval()
        with torch.no_grad():
            model[0].weight.copy_(torch.tensor([[0.1, -0.5], [1.0, 2.0]]))
            model[2][0].weight.copy_(torch.tensor([[0.25, 0.5]]))
            model[2][0].bias.fill_(0.0)
        result = export_sequential(model)
        self.assertEqual(result["model"]["layers"][0]["bias"], ["0", "0"])
        stored = model[0].weight[0, 0].detach().item()
        self.assertEqual(Fraction(result["model"]["layers"][0]["weight"][0][0]), Fraction.from_float(stored))
        with tempfile.TemporaryDirectory(prefix="rds-export-") as directory:
            path = Path(directory) / "model.json"
            path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
            with torch.no_grad():
                model[0].weight.fill_(99.0)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), result)

    def test_real_unsupported_layers_and_hooks_are_rejected(self):
        for layer in (torch.nn.Dropout(), torch.nn.BatchNorm1d(1)):
            with self.assertRaises(UnsupportedModel):
                export_sequential(torch.nn.Sequential(torch.nn.Linear(1, 1), layer).eval())
        model = torch.nn.Sequential(torch.nn.Linear(1, 1)).eval()
        handle = model[0].register_forward_hook(lambda *args: None)
        try:
            with self.assertRaisesRegex(UnsupportedModel, "hooks"):
                export_sequential(model)
        finally:
            handle.remove()
        with patch.object(torch.nn.Linear, "forward", side_effect=AssertionError("forward was executed")):
            self.assertIn("model", export_sequential(model))


if __name__ == "__main__":
    unittest.main()

"""Snapshot diagnostics remain finite, scoped estimates with optional NumPy."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_dynamics_probe as probe


def snapshot(**sections):
    return {"schema": 1, "source": "test exported numeric snapshots",
            "declared_scope": "finite sample; local Jacobian; shared one-second horizon", **sections}


def refinement():
    return {"time_horizon": 1, "levels": [{"steps": 10, "value": [1, 0]},
                                         {"steps": 20, "value": [0.5, 0]}]}


class InputBoundaryTests(unittest.TestCase):
    def test_structure_scope_and_matrix_bounds_rejected(self):
        invalid = [[], snapshot(), {**snapshot(residual=[[1]]), "source": "UNKNOWN"},
                   {**snapshot(residual=[[1]]), "declared_scope": ""},
                   snapshot(residual=[[1], [1, 2]]), snapshot(residual=[[1] * 65]),
                   snapshot(residual=[[1]] * 129), snapshot(jacobian=[[1, 2]]),
                   snapshot(residual=[[True]]), snapshot(residual=[["1"]]),
                   snapshot(source_identity={"sha256": True}, residual=[[1]]),
                   snapshot(residual=[[1]], self_asserted_gain=True)]
        for spec in invalid:
            with self.subTest(spec=str(spec)[:80]), self.assertRaises(ValueError):
                probe.inspect_probe(spec)

    def test_nonfinite_extreme_and_oversized_inputs_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), 1e101, 10**1000):
            with self.subTest(value=str(value)[:40]), self.assertRaises(ValueError):
                probe.inspect_probe(snapshot(residual=[[value]]))
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            probe.inspect_probe(snapshot(source_identity={"bytes": "x" * probe.MAX_BYTES}, residual=[[1]]))
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaises(ValueError):
            probe.inspect_probe(snapshot(residual=cyclic))

    def test_refinement_requires_shared_horizon_increasing_steps_and_shape(self):
        changes = [lambda x: x.update(time_horizon=0), lambda x: x.update(time_horizon=True),
                   lambda x: x.update(levels=[]), lambda x: x["levels"][1].update(steps=10),
                   lambda x: x["levels"][1].update(steps=1e9),
                   lambda x: x["levels"][1].update(value=[1]),
                   lambda x: x["levels"][1].update(time_horizon=2)]
        for change in changes:
            value = refinement()
            change(value)
            with self.assertRaises(ValueError):
                probe.inspect_probe(snapshot(refinement=value))

    def test_absent_numpy_does_not_prevent_independent_refinement(self):
        spec = snapshot(residual=[[1]], jacobian=[[2]], refinement=refinement())
        before = copy.deepcopy(spec)
        with patch.object(probe.importlib, "import_module", side_effect=ImportError("missing")):
            result = probe.inspect_probe(spec)
        self.assertEqual(result["residual"]["status"], "UNAVAILABLE")
        self.assertEqual(result["jacobian"]["status"], "UNAVAILABLE")
        self.assertEqual(result["refinement"]["differences"][0]["l2_difference"], 0.5)
        self.assertEqual(spec, before)
        for key in ("causal", "global_stability", "task_gain"):
            self.assertEqual(result[key], "UNKNOWN")

    def test_refinement_only_does_not_import_numpy_and_handles_zero_or_tiny_scale(self):
        value = refinement()
        value["levels"][0]["value"] = [1e100, 0]
        for right in ([0, 0], [1e-300, 0]):
            value["levels"][1]["value"] = right
            with patch.object(probe.importlib, "import_module", side_effect=AssertionError("No optional import")):
                result = probe.inspect_probe(snapshot(refinement=value))
            self.assertIsNone(result["refinement"]["differences"][0]["relative_l2_difference"])
            json.dumps(result, allow_nan=False)

    def test_cli_writes_full_record_and_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "input.json", Path(folder) / "output.json"
            source.write_text(json.dumps(snapshot(refinement=refinement())), encoding="utf-8")
            command = [sys.executable, "-B", str(ROOT / "scripts/rds_dynamics_probe.py"),
                       "--input", str(source), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["sections"], {"refinement": "ESTIMATED"})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["task_gain"], "UNKNOWN")
            source.write_bytes(b" " * (probe.MAX_BYTES + 1))
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "INVALID_INPUT")

    def test_cli_digest_is_small_and_output_cannot_replace_input(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text(json.dumps(snapshot(refinement=refinement())), encoding="utf-8")
            before = source.read_bytes()
            command = [sys.executable, "-B", str(ROOT / "scripts/rds_dynamics_probe.py"), "--input", str(source)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = json.loads(result.stdout)
            self.assertEqual(digest["estimates"]["last_refinement_difference"], 0.5)
            self.assertEqual(len(digest["input_file_sha256"]), 64)
            self.assertLess(len(result.stdout), 1024)
            result = subprocess.run(command + ["--output", str(source)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_bytes(), before)
            source.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "INVALID_INPUT")


@unittest.skipUnless(importlib.util.find_spec("numpy"), "Optional NumPy is not installed")
class NumericSnapshotTests(unittest.TestCase):
    def test_residual_energy_fractions_are_scale_invariant_when_total_underflows(self):
        result = probe.inspect_probe(snapshot(residual=[[1e-200, 0], [0, 5e-201]]))["residual"]
        self.assertEqual(result["energy_fractions"], [0.8, 0.2])
        self.assertEqual(result["cumulative_energy_fractions"], [0.8, 1.0])
        self.assertIsNone(result["total_squared_energy"])
        self.assertEqual(result["total_squared_energy_status"], "UNDERFLOW")

    def test_known_residual_energy_and_nonnormal_local_jacobian(self):
        result = probe.inspect_probe(snapshot(residual=[[3, 0], [0, 1]], jacobian=[[0.5, 10], [0, 0.5]]))
        self.assertEqual(result["residual"]["singular_values"], [3.0, 1.0])
        for actual, expected in zip(result["residual"]["energy_fractions"], [0.9, 0.1]):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(result["jacobian"]["spectral_radius"], 0.5)
        self.assertGreater(result["jacobian"]["singular_values"][0], 10)
        self.assertEqual(result["global_stability"], "UNKNOWN")

    def test_complex_spectrum_and_zero_residual_have_finite_output(self):
        result = probe.inspect_probe(snapshot(residual=[[0, 0], [0, 0]], jacobian=[[0, -2], [2, 0]]))
        self.assertEqual(result["residual"]["total_squared_energy"], 0)
        self.assertEqual(result["residual"]["energy_fractions"], [0, 0])
        self.assertAlmostEqual(result["jacobian"]["spectral_radius"], 2)
        self.assertAlmostEqual(result["jacobian"]["eigenvalues"][0]["imag"], -2)
        self.assertEqual(result["global_stability"], "UNKNOWN")
        json.dumps(result, allow_nan=False)

    def test_decomposition_failure_preserves_other_diagnostics(self):
        import numpy
        with patch.object(numpy.linalg, "svd", side_effect=numpy.linalg.LinAlgError("did not converge")):
            result = probe.inspect_probe(snapshot(residual=[[1]], refinement=refinement()))
        self.assertEqual(result["residual"]["status"], "UNAVAILABLE")
        self.assertEqual(result["refinement"]["status"], "ESTIMATED")


if __name__ == "__main__":
    unittest.main()

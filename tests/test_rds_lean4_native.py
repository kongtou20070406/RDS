"""Installed-toolchain discovery and honest exact-arithmetic degradation."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rds_lean_verify as lean
import rds_verify as engine

SPEC = {"schema": 1, "kind": "lean_obligation", "relation": "lt", "left": "1/2", "right": "3/4"}


def installed():
    try:
        lean._executable()
        return True
    except (ValueError, OSError):
        return False


class NativeDiscoveryTests(unittest.TestCase):
    def test_discovers_pinned_installed_binary_without_invoking_elan(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            formal = root / "formal"
            formal.mkdir()
            (formal / "lean-toolchain").write_text("leanprover/lean4:v4.33.1\n")
            path = root / ".elan/toolchains/leanprover--lean4---v4.33.1/bin" / ("lean.exe" if os.name == "nt" else "lean")
            path.parent.mkdir(parents=True)
            path.write_bytes(b"existing native binary")
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(lean, "FORMAL_ROOT", formal), \
                    mock.patch.object(Path, "home", return_value=root), mock.patch.object(lean.shutil, "which", return_value=None), \
                    mock.patch.object(lean.subprocess, "Popen") as process:
                executable, fingerprint = lean._executable()
            self.assertEqual(executable, path.resolve())
            self.assertEqual(len(fingerprint), 64)
            process.assert_not_called()

    def test_path_elan_shim_is_not_run_or_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shim = root / ".elan/bin" / ("lean.exe" if os.name == "nt" else "lean")
            shim.parent.mkdir(parents=True)
            shim.write_bytes(b"download wrapper")
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(lean, "FORMAL_ROOT", root / "formal"), \
                    mock.patch.object(Path, "home", return_value=root), mock.patch.object(lean.shutil, "which", return_value=str(shim)), \
                    mock.patch.object(lean.subprocess, "Popen") as process:
                with self.assertRaises(lean.NoNativeLean):
                    lean._executable()
            process.assert_not_called()

    def test_missing_environment_falls_back_and_independently_replays(self):
        with mock.patch.object(lean, "_executable", side_effect=lean.NoNativeLean("not installed")):
            result = engine.verify(SPEC)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["assurance"], "CERTIFICATE_CHECKED")
        leaf = result["certificate"]["proof"]["certificate"]
        self.assertEqual(leaf["backend"], lean.FALLBACK_BACKEND)
        with mock.patch.object(lean, "verify", side_effect=AssertionError("replay must not search")):
            self.assertTrue(engine.check_certificate(SPEC, result["certificate"]))
        for field, value in (("assurance", "LEAN_KERNEL_CHECKED"), ("left", "0"), ("backend", lean.BACKEND)):
            forged = copy.deepcopy(result["certificate"])
            forged["proof"]["certificate"][field] = value
            self.assertFalse(engine.check_certificate(SPEC, forged))

    def test_false_fallback_relation_remains_unknown(self):
        with mock.patch.object(lean, "_executable", side_effect=lean.NoNativeLean("not installed")):
            result = lean.verify({**SPEC, "left": "1", "right": "0"})
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIsNone(result["certificate"])

    def test_invalid_explicit_configuration_never_silently_degrades(self):
        with mock.patch.dict(os.environ, {"RDS_LEAN_EXECUTABLE": ""}), \
                mock.patch.object(lean, "_fallback_certificate") as fallback:
            result = lean.verify(SPEC)
        self.assertEqual(result["status"], "UNKNOWN")
        fallback.assert_not_called()


@unittest.skipUnless(installed(), "No installed native Lean binary")
class RealNativeTests(unittest.TestCase):
    def test_auto_detected_compiler_proves_and_replays_true_closed_relations(self):
        for relation, left, right in (("lt", "1/2", "3/4"), ("eq", "-1/3", "-2/6")):
            spec = {**SPEC, "relation": relation, "left": left, "right": right}
            result = engine.verify(spec)
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["assurance"], "LEAN_KERNEL_CHECKED")
            self.assertTrue(engine.check_certificate(spec, result["certificate"]))

    def test_actual_kernel_rejects_false_closed_relation(self):
        result = lean.verify({**SPEC, "left": "1", "right": "0"})
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIsNone(result["certificate"])


if __name__ == "__main__":
    unittest.main()

"""Installed-toolchain discovery and honest exact-arithmetic degradation."""
import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rds_lean_verify as lean
import rds_cli
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
        self.assertEqual(result["backend"], lean.FALLBACK_BACKEND)
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


class ExplicitBackendTests(unittest.TestCase):
    def test_zero_denominator_is_unknown_before_either_backend_runs(self):
        with mock.patch.object(lean, "_native_check", side_effect=AssertionError("No native call")):
            for tactic in ("lean4", "rational"):
                with self.subTest(tactic=tactic):
                    result = engine.LeanFormalEngine().verify({**SPEC, "left": "1/0"}, [tactic])
                    self.assertEqual(result["status"], "UNKNOWN", result)
                    self.assertEqual(result["assurance"], "NONE")

    def test_lean4_missing_native_never_generates_fallback_evidence(self):
        with mock.patch.object(lean, "_native_check", side_effect=lean.NoNativeLean("not installed")), \
                mock.patch.object(lean, "_fallback_certificate", side_effect=AssertionError("No fallback")):
            result = engine.LeanFormalEngine().verify(SPEC, ["lean4"])
        self.assertEqual(result["status"], "UNKNOWN", result)
        self.assertEqual(result["assurance"], "NONE")
        self.assertIn("not installed", result["tactics"][0]["reason"])

    def test_rational_and_replay_never_invoke_native_or_upgrade_assurance(self):
        with mock.patch.object(lean, "_native_check", side_effect=AssertionError("No native call")), \
                mock.patch.object(lean, "_executable", side_effect=AssertionError("No discovery")):
            result = engine.LeanFormalEngine().verify(SPEC, ["rational"])
            replay = engine.checked_result(SPEC, result["certificate"])
            false = engine.LeanFormalEngine().verify({**SPEC, "left": "1", "right": "0"}, ["rational"])
        for answer in (result, replay):
            self.assertEqual(answer["status"], "PASS", answer)
            self.assertEqual(answer["backend"], lean.FALLBACK_BACKEND)
            self.assertEqual(answer["assurance"], "CERTIFICATE_CHECKED")
            self.assertEqual(answer["semantics"], "closed_exact_rational_relation")
        self.assertEqual(false["status"], "UNKNOWN")
        self.assertEqual(false["assurance"], "NONE")

    def test_explicit_chain_can_choose_rational_after_native_is_unavailable(self):
        with mock.patch.object(lean, "_native_check", side_effect=lean.NoNativeLean("not installed")):
            result = engine.LeanFormalEngine().verify(SPEC, ["lean4", "rational"])
        self.assertEqual([item["status"] for item in result["tactics"]], ["UNKNOWN", "PASS"])
        self.assertEqual(result["assurance"], "CERTIFICATE_CHECKED")

    def test_lean4_rejects_even_valid_lower_assurance_certificate(self):
        fallback = lean.verify_rational(SPEC)
        with mock.patch.object(lean, "verify", return_value=fallback):
            result = engine.LeanFormalEngine().verify(SPEC, ["lean4"])
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["assurance"], "NONE")

    def test_cli_cached_fallback_cannot_satisfy_explicit_native_and_replay_stays_rational(self):
        with tempfile.TemporaryDirectory() as folder:
            spec_path, proof_path = Path(folder) / "spec.json", Path(folder) / "proof.json"
            spec_path.write_text(json.dumps(SPEC), encoding="utf-8")

            def command(*arguments):
                output = io.StringIO()
                with mock.patch.object(sys, "argv", ["rds_cli", "--root", folder, "formal", *arguments]), \
                        redirect_stdout(output):
                    code = rds_cli.main()
                return code, json.loads(output.getvalue())

            with mock.patch.object(lean, "_native_check", side_effect=lean.NoNativeLean("not installed")):
                first_code, first = command("verify", "--spec", str(spec_path))
                cached_code, cached = command("verify", "--spec", str(spec_path))
                native_code, native = command("verify", "--spec", str(spec_path), "--tactics", "lean4")
            self.assertEqual((first_code, cached_code, native_code), (0, 0, 2))
            self.assertTrue(first["cache"]["stored"])
            self.assertTrue(cached["cache"]["hit"])
            self.assertEqual(cached["backend"], lean.FALLBACK_BACKEND)
            self.assertEqual(native["status"], "UNKNOWN")
            self.assertEqual(native["assurance"], "NONE")
            with mock.patch.object(lean, "_native_check", side_effect=AssertionError("No native call")):
                rational_code, rational = command("verify", "--spec", str(spec_path), "--tactics", "rational",
                                                 "--output", str(proof_path))
                check_code, replay = command("check", "--spec", str(spec_path), "--certificate", str(proof_path))
            self.assertEqual((rational_code, check_code), (0, 0))
            for answer in (rational, replay):
                self.assertEqual(answer["backend"], lean.FALLBACK_BACKEND)
                self.assertEqual(answer["assurance"], "CERTIFICATE_CHECKED")


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

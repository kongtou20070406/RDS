"""Conditional retrieval stays small, reproducible and separate from execution."""
import hashlib
import importlib
import itertools
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_theory_tools as tools


class TheoryToolTests(unittest.TestCase):
    def test_explicit_signal_matrix_and_unknown_without_fallback(self):
        expected = {
            "trajectory_degradation": ["contraction_target_bias", "local_jacobian"],
            "local_global_gap": ["contraction_target_bias", "local_jacobian"],
            "step_sensitivity": ["state_space_refinement"],
            "structured_residual": ["residual_subspace_havok"],
            "equation_unknown": ["sparse_equation_discovery", "symbolic_regression", "egraph_equivalence_saturation"],
            "proof_bottleneck": ["exact_symbolic_constraints", "structural_preflight", "egraph_equivalence_saturation"],
            "execution_mismatch": ["exact_symbolic_constraints", "structural_preflight"],
        }
        for signal, ids in expected.items():
            with self.subTest(signal=signal):
                self.assertEqual([card["id"] for card in tools.shortlist([signal])["cards"]], ids)
        unknown = tools.shortlist(["unknown", "unknown"])
        self.assertEqual(unknown["cards"], [])
        self.assertEqual(unknown["unmatched_signal_count"], 1)

    def test_match_count_order_is_deterministic_not_a_success_score(self):
        signals = ["proof_bottleneck", "step_sensitivity", "execution_mismatch"]
        result = tools.shortlist(signals)
        self.assertEqual([card["id"] for card in result["cards"]],
                         ["exact_symbolic_constraints", "structural_preflight", "state_space_refinement"])
        self.assertEqual(result, tools.shortlist(list(reversed(signals)) + signals))
        self.assertEqual(result["selection"], "TAG_MATCH_ONLY")
        self.assertEqual(result["prerequisites"], "NOT_ASSESSED")
        self.assertEqual(result["scientific_assurance"], "UNKNOWN")
        self.assertEqual(result["available_on"], "2026-10-01")
        self.assertTrue(all("confidence" not in card and "score" not in card for card in result["cards"]))

    def test_input_bounds_precede_any_catalogue_read(self):
        invalid = [None, "step_sensitivity", [], [None], [True], [float("nan")],
                   ["x" * 65], ["Upper"], ["a b"], ["x"] * 33]
        with patch.object(tools, "_load", side_effect=AssertionError("Should reject first")):
            for signals in invalid:
                with self.subTest(signals=signals), self.assertRaises(ValueError):
                    tools.shortlist(signals)
            for limit in (0, 6, True, 1.0, "3"):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    tools.shortlist(["step_sensitivity"], limit)
        self.assertEqual(tools.shortlist(["x"] * 32)["cards"], [])

    def test_hash_and_locators_bind_exact_card_and_catalogue_bytes(self):
        raw = tools.CATALOGUE.read_bytes()
        result = tools.shortlist(["equation_unknown"])
        self.assertEqual(result["catalogue_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(Path(result["catalogue_locator"]), tools.CATALOGUE.resolve())
        cards = json.loads(raw)["cards"]
        for card in result["cards"]:
            index = int(card["locator"].rsplit("/", 1)[1])
            full = tools.get_card(card["id"])
            self.assertEqual(full["card"], cards[index])
            self.assertEqual(full["catalogue_sha256"], result["catalogue_sha256"])
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder) / "catalogue.json"
            changed.write_bytes(raw + b"\n")
            with patch.object(tools, "CATALOGUE", changed):
                self.assertNotEqual(tools.shortlist(["equation_unknown"])["catalogue_sha256"], result["catalogue_sha256"])
                changed.write_bytes(b" " * (tools.MAX_BYTES + 1))
                with self.assertRaisesRegex(ValueError, "20 KiB"):
                    tools.shortlist(["equation_unknown"])

    def test_default_digest_budget_and_full_cards_are_opt_in(self):
        signals = sorted(tools.SIGNALS)
        largest = 0
        for size in range(1, len(signals) + 1):
            for subset in itertools.combinations(signals, size):
                result = tools.shortlist(list(subset))
                largest = max(largest, len(json.dumps(result, separators=(",", ":")).encode("utf-8")))
                self.assertLessEqual(len(result["cards"]), 3)
                for card in result["cards"]:
                    self.assertNotIn("conditions", card)
                    self.assertNotIn("diagnostic", card)
                    self.assertNotIn("sources", card)
                    self.assertTrue(card["required_inputs"])
        self.assertLessEqual(largest, 2048)
        self.assertLessEqual(tools.CATALOGUE.stat().st_size, tools.MAX_BYTES)
        full = tools.get_card("symbolic_regression")["card"]
        self.assertEqual(full["capability"]["availability"], "EXTERNAL_OPTIONAL")
        self.assertIn("https://github.com/astroautomata/PySR", full["sources"])
        self.assertTrue(full["conditions"] and full["limitations"] and full["capability"]["prerequisites"])
        with self.assertRaises(ValueError):
            tools.get_card("symbolic")

    def test_retrieval_does_not_provision_execute_or_update(self):
        paths = [tools.CATALOGUE, ROOT / "scripts/rds_theory_tools.py"]
        before = [path.read_bytes() for path in paths]
        with patch.object(socket, "create_connection", side_effect=AssertionError("Network")), \
                patch.object(subprocess, "Popen", side_effect=AssertionError("Execution")), \
                patch.object(importlib, "import_module", side_effect=AssertionError("Optional imports")):
            tools.shortlist(["equation_unknown", "structured_residual"])
            full = tools.get_card("symbolic_regression")
        self.assertEqual(before, [path.read_bytes() for path in paths])
        self.assertEqual(full["scientific_assurance"], "UNKNOWN")

    def test_execution_mismatch_requires_project_checker_instead_of_disk_proof(self):
        ids = [card["id"] for card in tools.shortlist(["execution_mismatch"])["cards"]]
        self.assertIn("structural_preflight", ids)
        card = tools.get_card("structural_preflight")["card"]
        self.assertEqual(card["capability"]["availability"], "PROJECT_CHECK_REQUIRED")
        self.assertNotIn("unit_disk", json.dumps(card))
        self.assertNotIn("disk_cover", card["capability"]["entrypoint"])
        self.assertTrue(card["capability"]["prerequisites"])
        with self.assertRaises(ValueError):
            tools.get_card("structural_geometry")

    def test_cli_from_other_directory_and_invalid_modes(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/rds_theory_tools.py")]
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(command + ["--signals", "step_sensitivity"], cwd=folder,
                                    capture_output=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["cards"][0]["id"], "state_space_refinement")
            full = subprocess.run(command + ["--id", "residual_subspace_havok"], cwd=folder,
                                  capture_output=True, encoding="utf-8", timeout=10)
            self.assertEqual(full.returncode, 0, full.stderr)
            self.assertTrue(json.loads(full.stdout)["card"]["conditions"])
            for args in (["--signals", "step_sensitivity", "--limit", "6"], ["--id", "unknown"],
                         ["--signals", "step_sensitivity", "--id", "local_jacobian"]):
                result = subprocess.run(command + args, cwd=folder, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2)

    def test_runnable_operator_scaffolding_and_testing(self):
        # List operators
        ops_list = tools.list_operators()
        self.assertGreaterEqual(len(ops_list), 4)
        available_ids = {op["card_id"] for op in ops_list}
        self.assertIn("state_space_refinement", available_ids)

        # Scaffold in-memory and write to file
        scaffold_res = tools.scaffold_operator("state_space_refinement")
        self.assertEqual(scaffold_res["status"], "OK")
        self.assertIn("ContinuousStateSpace", scaffold_res["scaffold"])

        with tempfile.TemporaryDirectory() as folder:
            out_file = Path(folder) / "model_op.py"
            written_res = tools.scaffold_operator("state_space_refinement", str(out_file))
            self.assertEqual(written_res["status"], "WRITTEN")
            self.assertTrue(out_file.exists())
            self.assertIn("ContinuousStateSpace", out_file.read_text(encoding="utf-8"))
            original = out_file.read_bytes()
            with self.assertRaises(FileExistsError):
                tools.scaffold_operator("contraction_target_bias", out_file)
            self.assertEqual(out_file.read_bytes(), original)
            with self.assertRaises(ValueError):
                tools.scaffold_operator("state_space_refinement", "")

        # Test operator
        test_res = tools.test_operator("state_space_refinement")
        self.assertEqual(test_res["test_result"]["status"], "UNKNOWN")
        self.assertTrue(test_res["test_result"]["diagnostic_pass"])

        # Unknown card operator
        with self.assertRaises(ValueError):
            tools.scaffold_operator("invalid_id")
        with self.assertRaises(ValueError):
            tools.test_operator("invalid_id")

    def test_cli_runnable_operator_modes(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/rds_theory_tools.py")]
        with tempfile.TemporaryDirectory() as folder:
            # --list-operators
            res = subprocess.run(command + ["--list-operators"], cwd=folder, capture_output=True, encoding="utf-8", timeout=10)
            self.assertEqual(res.returncode, 0, res.stderr)
            parsed = json.loads(res.stdout)
            self.assertEqual(parsed["status"], "OK")
            self.assertTrue(any(item["card_id"] == "state_space_refinement" for item in parsed["operators"]))

            # --test-operator
            res_test = subprocess.run(command + ["--test-operator", "state_space_refinement"], cwd=folder, capture_output=True, encoding="utf-8", timeout=10)
            # A completed finite diagnostic is not an asymptotic proof.
            self.assertEqual(res_test.returncode, 2, res_test.stderr)
            self.assertEqual(json.loads(res_test.stdout)["test_result"]["status"], "UNKNOWN")
            self.assertTrue(json.loads(res_test.stdout)["test_result"]["diagnostic_pass"])

            # --scaffold --out
            target = Path(folder) / "generated.py"
            res_scaff = subprocess.run(command + ["--scaffold", "contraction_target_bias", "--out", str(target)], cwd=folder, capture_output=True, encoding="utf-8", timeout=10)
            self.assertEqual(res_scaff.returncode, 0, res_scaff.stderr)
            self.assertEqual(json.loads(res_scaff.stdout)["status"], "WRITTEN")
            self.assertTrue(target.exists())
            original = target.read_bytes()
            repeated = subprocess.run(command + ["--scaffold", "state_space_refinement", "--out", str(target)],
                                      cwd=folder, capture_output=True, encoding="utf-8", timeout=10)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(json.loads(repeated.stdout)["status"], "INVALID_INPUT")
            self.assertEqual(target.read_bytes(), original)

            unused = Path(folder) / "unused.py"
            for mode in (["--id", "local_jacobian"], ["--signals", "step_sensitivity"],
                         ["--list-operators"], ["--test-operator", "contraction_target_bias"]):
                invalid = subprocess.run(command + mode + ["--out", str(unused)], cwd=folder,
                                         capture_output=True, encoding="utf-8", timeout=10)
                self.assertEqual(invalid.returncode, 2)
                self.assertEqual(json.loads(invalid.stdout)["status"], "INVALID_INPUT")
                self.assertFalse(unused.exists())

            # Invalid operator ID
            bad = subprocess.run(command + ["--test-operator", "nonexistent"], cwd=folder, capture_output=True, timeout=10)
            self.assertEqual(bad.returncode, 2)

    def test_checker_failure_sets_nonzero_cli_exit(self):
        with patch.object(sys, "argv", ["rds_theory_tools.py", "--test-operator", "structural_preflight"]), \
                patch.object(tools, "test_operator", return_value={"test_result": {"status": "FAIL"}}), \
                patch("builtins.print"):
            self.assertEqual(tools.main(), 1)

    def test_actual_exported_modules_run_self_checks_and_reject_negative_cases(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/rds_theory_tools.py")]
        with tempfile.TemporaryDirectory() as folder:
            modules = {}
            for entry in tools.list_operators():
                card_id = entry["card_id"]
                target = Path(folder) / (card_id + ".py")
                exported = subprocess.run(command + ["--scaffold", card_id, "--out", str(target)], cwd=folder,
                                          capture_output=True, encoding="utf-8", timeout=10)
                self.assertEqual(exported.returncode, 0, exported.stderr)
                # Isolated execution cannot import the checkout's operator module.
                checked = subprocess.run([sys.executable, "-I", "-B", str(target)], cwd=folder,
                                         capture_output=True, encoding="utf-8", timeout=10)
                self.assertEqual(checked.returncode, 0, checked.stderr)
                report = json.loads(checked.stdout)
                self.assertEqual(report["self_test_status"], "PASS")
                self.assertEqual(report["positive"]["status"], "UNKNOWN" if card_id == "state_space_refinement" else "PASS")
                namespace = {"__name__": "exported_operator"}
                exec(compile(target.read_text(encoding="utf-8"), str(target), "exec"), namespace)
                modules[card_id] = namespace

            state = modules["state_space_refinement"]["ContinuousStateSpaceOperator"](state_dim=1)
            with self.assertRaises(ValueError):
                state.discretize_zoh(float("nan"))
            contraction = modules["contraction_target_bias"]["ContractionDynamicsOperator"]
            with self.assertRaises(ValueError):
                contraction.analyze_system([[float("nan")]], [0])
            structural = modules["structural_preflight"]["StructuralPreflightOperator"]
            result = structural.preflight_callable(lambda x: [0], sample_args=([1, 2, 3],),
                                                   expected_shapes={"x": (3,)}, expected_output_shape=(3,))
            self.assertEqual(result["status"], "FAIL")
            rational = modules["exact_symbolic_constraints"]["RationalCertificateOperator"]
            result = rational.certify_interval_bound([0, 1, -1], (0, 1), (0, "20/81"))
            self.assertNotEqual(result["status"], "PASS")
            egraph = modules["egraph_equivalence_saturation"]["EGraphEquivalenceOperator"]
            with self.assertRaises(ValueError):
                egraph.verify_algebraic_equivalence(("+", "x", "0"), "x")
            result = egraph.verify_algebraic_equivalence(("+", "x", "1"), ("*", "x", "1"), variables=("x",))
            self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()

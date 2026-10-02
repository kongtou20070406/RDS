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
            "equation_unknown": ["sparse_equation_discovery", "symbolic_regression"],
            "proof_bottleneck": ["exact_symbolic_constraints", "structural_preflight"],
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


if __name__ == "__main__":
    unittest.main()

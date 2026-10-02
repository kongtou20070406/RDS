"""Native/fallback semantics, ABI rejection and bounded differential cases."""
import ctypes
import os
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_accelerator as accelerator


class AcceleratorTests(unittest.TestCase):
    def test_live_native_requirement_and_source_only_status(self):
        if os.environ.get("RDS_REQUIRE_NATIVE") == "1":
            self.assertTrue(accelerator.is_native_available(), "Compiled ABI required in this CI job")
        with patch.object(accelerator, "get_native_cdll", return_value=None), patch.object(
                accelerator, "is_cargo_available", return_value=True):
            status = accelerator.get_accelerator_status()
        self.assertEqual(status["status"], "UNAVAILABLE")
        self.assertTrue(status["cargo_available"])
        self.assertFalse(status["native_library_loaded"])
        self.assertIn("NOT_SCIENTIFIC", status["assurance"])

    def test_invalid_abi_and_incomplete_library_fall_back(self):
        for magic, version in ((41, 2), (42, 1)):
            lib = MagicMock()
            lib.rds_accelerator_smoke.return_value = magic
            lib.rds_accelerator_abi_version.return_value = version
            with patch.object(accelerator, "_INIT_ATTEMPTED", False), patch.object(
                    accelerator, "_LOADED_LIB", None), patch.object(
                    accelerator, "_find_native_library", return_value=Path("test-owned.dll")), patch.object(
                    accelerator.ctypes, "CDLL", return_value=lib):
                self.assertIsNone(accelerator.get_native_cdll())
        with patch.object(accelerator, "_INIT_ATTEMPTED", False), patch.object(
                accelerator, "_LOADED_LIB", None), patch.object(
                accelerator, "_find_native_library", return_value=Path("test-owned.dll")), patch.object(
                accelerator.ctypes, "CDLL", return_value=object()):
            self.assertIsNone(accelerator.get_native_cdll())

    def test_conflicted_head_cannot_support_descendant(self):
        nodes = [{"id": "a", "status": "SUPPORTED"}, {"id": "bad", "status": "CONTRADICTED"},
                 {"id": "goal", "status": "UNKNOWN"}]
        edges = [{"id": "bad-edge", "premises": ["a"], "conclusion": "bad", "status": "SUPPORTED"},
                 {"id": "propagate", "premises": ["bad"], "conclusion": "goal", "status": "SUPPORTED"}]
        expected = ({"a"}, {}, {"bad-edge"})
        self.assertEqual(accelerator.python_hypergraph_closure(nodes, edges, {"a"}), expected)
        self.assertEqual(accelerator.compute_hypergraph_closure(nodes, edges, {"a"}), expected)

    def test_ordered_witness_empty_rule_initial_and_cycle(self):
        nodes = [{"id": i, "status": "UNKNOWN"} for i in ("a", "b", "c", "d")]
        edges = [
            {"id": "early", "premises": ["b"], "conclusion": "c", "status": "SUPPORTED"},
            {"id": "b", "premises": ["a"], "conclusion": "b", "status": "SUPPORTED"},
            {"id": "late", "premises": ["a"], "conclusion": "c", "status": "SUPPORTED"},
            {"id": "tautology", "premises": ["d"], "conclusion": "d", "status": "SUPPORTED"}]
        expected = ({"a", "b", "c"}, {"b": "b", "c": "late"}, set())
        self.assertEqual(accelerator.compute_hypergraph_closure(nodes, edges, {"a"}), expected)
        edges.append({"id": "fact", "premises": [], "conclusion": "d", "status": "SUPPORTED"})
        self.assertEqual(accelerator.compute_hypergraph_closure(nodes, edges, {"a"})[1]["d"], "fact")
        self.assertEqual(accelerator.compute_hypergraph_closure([], [], set()), (set(), {}, set()))

    def test_unknown_endpoint_cannot_be_dropped_to_make_vacuous_fact(self):
        nodes = [{"id": "a", "status": "UNKNOWN"}]
        edge = {"id": "bad", "premises": ["missing"], "conclusion": "a", "status": "SUPPORTED"}
        for fn in (accelerator.python_hypergraph_closure, accelerator.compute_hypergraph_closure):
            with self.assertRaisesRegex(ValueError, "endpoint"):
                fn(nodes, [edge], set())

    def test_error_return_or_invalid_output_falls_back(self):
        nodes = [{"id": "a", "status": "SUPPORTED"}]
        for code in (-1, 2):
            lib = MagicMock()
            lib.rds_hypergraph_closure_v2.return_value = code
            with patch.object(accelerator, "get_native_cdll", return_value=lib):
                self.assertEqual(accelerator.compute_hypergraph_closure(nodes, [], {"a"}),
                                 ({"a"}, {}, set()))

    def test_actual_routing_matches_ordered_reference_on_300_graphs(self):
        rng = random.Random(2602)
        for case in range(300):
            n = rng.randrange(1, 26)
            nodes = [{"id": str(i), "status": rng.choice(["SUPPORTED", "UNKNOWN", "CONTRADICTED"])}
                     for i in range(n)]
            edges = [{"id": str(i), "premises": rng.sample([node["id"] for node in nodes],
                      rng.randrange(min(n, 4) + 1)), "conclusion": str(rng.randrange(n)),
                      "status": rng.choice(["SUPPORTED", "SUPPORTED", "PROPOSED", "CONTRADICTED"])}
                     for i in range(rng.randrange(40))]
            initial = {node["id"] for node in nodes if node["status"] == "SUPPORTED"}
            with self.subTest(case=case):
                self.assertEqual(accelerator.compute_hypergraph_closure(nodes, edges, initial),
                                 accelerator.python_hypergraph_closure(nodes, edges, initial))

    def test_compiled_ffi_rejects_malformed_range_without_partial_output(self):
        lib = accelerator.get_native_cdll()
        if lib is None:
            self.skipTest("Compiled native library unavailable locally; required in native CI")
        blocked = (ctypes.c_uint8 * 1)(0)
        initial = (ctypes.c_uint32 * 1)(7)
        flat = (ctypes.c_uint32 * 0)()
        out = (ctypes.c_uint8 * 1)(9)
        witnesses = (ctypes.c_uint32 * 1)(17)
        conflicts = (ctypes.c_uint8 * 0)()
        result = lib.rds_hypergraph_closure_v2(1, blocked, initial, 1, flat, 0,
                                             out, witnesses, conflicts, 0)
        self.assertEqual(result, -1)
        self.assertEqual((out[0], witnesses[0]), (9, 17))


if __name__ == "__main__":
    unittest.main()

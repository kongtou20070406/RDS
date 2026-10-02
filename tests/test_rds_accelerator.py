"""Unit tests for native acceleration adapter and hypergraph closure routing."""
import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_accelerator as accelerator


class AcceleratorUnitTests(unittest.TestCase):
    def test_accelerator_status_structure(self):
        status = accelerator.get_accelerator_status()
        self.assertIn(status["status"], ("AVAILABLE", "UNAVAILABLE"))
        self.assertIn("backend", status)
        self.assertIn("native_library_loaded", status)
        self.assertIn("cargo_available", status)
        self.assertEqual(status["assurance"], "NATIVE_EQUIVALENCE_PRESERVED")

    def test_pure_python_hypergraph_closure(self):
        nodes = [
            {"id": "n1", "status": "SUPPORTED"},
            {"id": "n2", "status": "UNKNOWN"},
            {"id": "n3", "status": "UNKNOWN"},
            {"id": "n4", "status": "UNKNOWN"},
        ]
        edges = [
            {"id": "e1", "premises": ["n1"], "conclusion": "n2", "status": "SUPPORTED"},
            {"id": "e2", "premises": ["n2"], "conclusion": "n3", "status": "SUPPORTED"},
            {"id": "e3", "premises": ["n3", "n4"], "conclusion": "n4", "status": "SUPPORTED"},
        ]
        closure, derivations, conflicts = accelerator.compute_hypergraph_closure(
            nodes, edges, initial_supported={"n1"}
        )
        self.assertEqual(closure, {"n1", "n2", "n3"})
        self.assertEqual(derivations["n2"], "e1")
        self.assertEqual(derivations["n3"], "e2")
        self.assertEqual(conflicts, set())

    def test_hypergraph_closure_conflict_handling(self):
        nodes = [
            {"id": "n1", "status": "SUPPORTED"},
            {"id": "n2", "status": "CONTRADICTED"},
        ]
        edges = [
            {"id": "e1", "premises": ["n1"], "conclusion": "n2", "status": "SUPPORTED"},
        ]
        closure, derivations, conflicts = accelerator.compute_hypergraph_closure(
            nodes, edges, initial_supported={"n1"}
        )
        self.assertEqual(closure, {"n1"})
        self.assertIn("e1", conflicts)

    def test_native_cdll_routing_parity(self):
        # Create a mock CDLL that behaves like the native kernel
        mock_cdll = MagicMock()
        mock_cdll.rds_accelerator_smoke.return_value = 42

        def mock_fast_closure(num_nodes, init_ptr, num_init, edges_ptr, edges_len, out_ptr, out_cap):
            # Write 2 derived nodes into out_ptr
            out_ptr[0] = 0
            out_ptr[1] = 1
            return 2

        mock_cdll.rds_hypergraph_fast_closure.side_effect = mock_fast_closure

        nodes = [
            {"id": "a", "status": "SUPPORTED"},
            {"id": "b", "status": "UNKNOWN"},
        ]
        edges = [
            {"id": "e_ab", "premises": ["a"], "conclusion": "b", "status": "SUPPORTED"},
        ]

        with patch("rds_accelerator.get_native_cdll", return_value=mock_cdll):
            closure, derivations, conflicts = accelerator.compute_hypergraph_closure(
                nodes, edges, initial_supported={"a"}
            )
            self.assertEqual(closure, {"a", "b"})
            self.assertEqual(derivations["b"], "e_ab")


if __name__ == "__main__":
    unittest.main()

"""Solver failure classification, denominator obligations and bounded fallback."""
import builtins
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_cli as cli
import rds_formal_kernel as kernel
import rds_nn_verify as nn
import rds_probe as probe
from rds_verify import LeanFormalEngine

FORMAL = {"kind": "strict_algebraic_threshold", "statement": "threshold_separation",
          "domain": ["-2", "2"], "threshold": "1", "max_loss": "1"}
NONLINEAR = "def control(x): return 0\ndef treatment(x): return x**2\n"


class _SolverFailure(Exception):
    """A backend exception outside ValueError's inheritance tree."""


class ProbeAdversarialTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("sympy") is not None, "Optional SymPy unavailable")
    def test_nonlinear_cancellation_zero_product_power_and_nested_division_keep_poles(self):
        for expression in ("(x**2-1)/(x**2-1)+1", "0*((x**2-1)/(x**2-1))+2",
                           "((x**2-1)/(x**2-1))**0+1", "0/((x**2-1)/(x**2-1))+2"):
            with self.subTest(expression=expression):
                source = "def control(x): return 0\ndef treatment(x): return " + expression + "\n"
                answer = probe.admission_probe({"formal": FORMAL}, source)
                self.assertEqual(answer["status"], "UNKNOWN")
                self.assertIn("denominator", answer["reason"])
                self.assertNotIn("certificate", answer)

    def test_backend_exceptions_are_unknown_in_admission_and_execution(self):
        payload = {"source": NONLINEAR, "hypothesis": {"formal": FORMAL}, "data": "sample_id,x,y\na,1,1\n"}
        for error in (RuntimeError("backend failed"), ArithmeticError("arithmetic failed"),
                      RecursionError("isolation recursion"), AttributeError("malformed solver result"),
                      _SolverFailure("backend-specific error")):
            with self.subTest(error=type(error).__name__):
                with patch.object(probe, "symbolic_probe", side_effect=error):
                    admission = probe.admission_probe(payload["hypothesis"], NONLINEAR)
                    execution = probe.execute(payload)
                self.assertEqual(admission["status"], "UNKNOWN")
                self.assertEqual(admission["assurance"], "NONE")
                self.assertEqual(execution["probe"]["status"], "UNKNOWN")
                self.assertNotIn("certificate", execution["probe"])

    @unittest.skipUnless(importlib.util.find_spec("sympy") is not None, "Optional SymPy unavailable")
    def test_actual_sympy_polynomial_error_type_is_fail_closed(self):
        from sympy.polys.polyerrors import PolynomialError
        with patch.object(probe, "symbolic_probe", side_effect=PolynomialError("root isolation failed")):
            self.assertEqual(probe.admission_probe({"formal": FORMAL}, NONLINEAR)["status"], "UNKNOWN")

    def test_large_coefficients_are_rejected_before_sympy_import(self):
        source = "def control(x): return 0\ndef treatment(x): return x**2 + (((((1000000**4)**4)**4)**4)**4)\n"
        original = builtins.__import__
        imports = []
        def no_solver(name, *args, **kwargs):
            if name == "sympy" or name.startswith("sympy."):
                imports.append(name)
                raise AssertionError("Symbolic resource guard ran too late")
            return original(name, *args, **kwargs)
        formal = probe.formal_requirement({"formal": FORMAL})
        with patch("builtins.__import__", side_effect=no_solver):
            answer = probe.formal_probe(probe.parse_source(source), formal)
        self.assertEqual(answer["status"], "UNKNOWN")
        self.assertIn("bounds", answer["reason"])
        self.assertEqual(imports, [])

    def test_cli_timeout_is_unknown_without_waiting(self):
        with patch.object(cli.subprocess, "run", side_effect=subprocess.TimeoutExpired(["verifier"], 15)) as run:
            with self.assertRaisesRegex(ValueError, "UNKNOWN.*15 seconds"):
                cli.formal_gate({"formal": FORMAL}, NONLINEAR)
        self.assertEqual(run.call_args.kwargs["timeout"], 15)

    def test_exact_checker_never_calls_search_or_solver(self):
        source = "def control(x): return 0\ndef treatment(x): return x+3\n"
        formal = probe.formal_requirement({"formal": FORMAL})
        functions = probe.parse_source(source)
        certificate = probe.admission_probe({"formal": FORMAL}, source)["certificate"]
        with patch.object(kernel, "exact_probe", side_effect=AssertionError("Search called")), \
                patch.object(probe, "symbolic_probe", side_effect=AssertionError("Solver called")):
            self.assertTrue(kernel.check_certificate(functions, formal, certificate))

    def test_reverse_interval_rule_chain_does_not_repeat_the_same_generator(self):
        spec = {"schema": 1, "kind": "network_bounds", "model": {"input_dim": 1, "layers": [
            {"kind": "linear", "weight": [["1"], ["1"]], "bias": ["0", "0"]},
            {"kind": "linear", "weight": [["1", "-1"]], "bias": ["0"]}]},
            "input_box": [["-1", "1"]], "output_bounds": [["0", "0"]]}
        with patch.object(nn, "verify", wraps=nn.verify) as generate:
            answer = LeanFormalEngine().verify(spec, ["interval", "rule"])
        self.assertEqual(answer["status"], "UNKNOWN")
        generate.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)

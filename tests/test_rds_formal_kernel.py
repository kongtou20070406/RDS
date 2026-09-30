"""Proof forgery, statement binding and bounded isolated execution regressions."""
import builtins
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_formal_kernel import ResourceLimit, check_certificate
from rds_probe import admission_probe, execute, formal_requirement, parse_source

SOURCE = "def control(x): return 0\ndef treatment(x): return x/(1+x) + 1\n"
FORMAL = {"kind": "strict_algebraic_threshold", "statement": "threshold_separation",
          "domain": ["0", "2"], "threshold": "1", "max_loss": "1"}


class FormalKernelTests(unittest.TestCase):
    def test_affine_certificate_needs_no_solver(self):
        original_import = builtins.__import__
        def no_solver(name, *args, **kwargs):
            if name == "sympy" or name.startswith("sympy."):
                raise ImportError("solver unavailable")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=no_solver):
            probe = admission_probe({"formal": FORMAL}, SOURCE)
        self.assertEqual(probe["status"], "PASS")
        self.assertEqual(probe["assurance"], "CERTIFICATE_CHECKED")
        self.assertTrue(check_certificate(parse_source(SOURCE), FORMAL, probe["certificate"]))

    def test_checker_rejects_forged_and_differently_bound_evidence(self):
        functions = parse_source(SOURCE)
        certificate = admission_probe({"formal": FORMAL}, SOURCE)["certificate"]
        mutations = []
        forged = copy.deepcopy(certificate)
        forged["denominators"] = []
        mutations.append(forged)
        forged = copy.deepcopy(certificate)
        forged["witness"]["x"] = "3"
        mutations.append(forged)
        forged = copy.deepcopy(certificate)
        forged["forms"]["control"]["numerator"] = ["-1"]
        mutations.append(forged)
        forged = copy.deepcopy(certificate)
        forged["endpoint_values"]["treatment"][0] = "100"
        mutations.append(forged)
        forged = copy.deepcopy(certificate)
        forged["verdict"] = "FAIL"
        mutations.append(forged)
        for forged in mutations:
            self.assertFalse(check_certificate(functions, FORMAL, forged))
        for changed in ({**FORMAL, "max_loss": "2"},
                        {**FORMAL, "statement": "threshold_necessity"},
                        {**FORMAL, "domain": ["0", "3"]}):
            self.assertFalse(check_certificate(functions, changed, certificate))
        self.assertFalse(check_certificate(parse_source(SOURCE.replace("return 0", "return -1")),
                                           FORMAL, certificate))
        for malformed in (None, [], {"version": True}, {"witness": {"x": []}}):
            self.assertFalse(check_certificate(functions, FORMAL, malformed))

    def test_original_denominator_survives_cancellation(self):
        source = "def control(x): return (x-1)/(x-1)-1\ndef treatment(x): return x\n"
        probe = admission_probe({"formal": FORMAL}, source)
        self.assertEqual(probe["status"], "UNKNOWN")
        self.assertIn("denominator", probe["reason"])
        self.assertNotIn("certificate", probe)

    def test_negative_denominator_and_closed_endpoint(self):
        source = "def control(x): return 0\ndef treatment(x): return -(x+2)/(x-3)\n"
        probe = admission_probe({"formal": FORMAL}, source)
        self.assertEqual(probe["status"], "PASS")
        self.assertEqual(probe["certificate"]["witness"], {"arm": "treatment", "x": "2", "value": "4"})
        single = {**FORMAL, "domain": ["1", "1"]}
        source = "def control(x): return 0\ndef treatment(x): return x\n"
        self.assertEqual(admission_probe({"formal": single}, source)["status"], "PASS")

    def test_exact_failure_certificates(self):
        for source, reason in (("def control(x): return x\ndef treatment(x): return x\n", "control_not_below"),
                               ("def control(x): return 0\ndef treatment(x): return 0\n", "no_treatment_crossing")):
            probe = admission_probe({"formal": FORMAL}, source)
            self.assertEqual(probe["status"], "FAIL")
            self.assertEqual(probe["certificate"]["case"], reason)
            self.assertTrue(check_certificate(parse_source(source), FORMAL, probe["certificate"]))

    def test_claim_polarity_cannot_refute_separation(self):
        source = "def control(x): return 0\ndef treatment(x): return x\n"
        payload = {"source": source, "data": "sample_id,x,y\na,1,1\n",
                   "hypothesis": {"formal": {k: v for k, v in FORMAL.items() if k != "statement"}}}
        separation = execute(payload)
        self.assertEqual(separation["probe"]["status"], "PASS")
        self.assertEqual(separation["probe"]["necessity_counterexamples"], [])
        payload["hypothesis"]["formal"]["statement"] = "threshold_necessity"
        self.assertEqual(execute(payload)["probe"]["necessity_counterexamples"], ["a"])
        legacy = {"formal": {**FORMAL, "kind": "threshold_necessity"}}
        del legacy["formal"]["statement"]
        self.assertEqual(formal_requirement(legacy)["statement"], "threshold_necessity")
        with self.assertRaises(ValueError):
            formal_requirement({"formal": {**FORMAL, "statement": "arbitrary_stability"}})

    def test_execution_replays_checked_proof_and_rejects_tampering(self):
        committed = admission_probe({"formal": FORMAL}, SOURCE)
        payload = {"source": SOURCE, "data": "sample_id,x,y\na,1,1\n",
                   "hypothesis": {"formal": FORMAL}, "admission_probe": committed}
        with patch("rds_probe.exact_probe", side_effect=AssertionError("proof search repeated")), \
                patch("rds_probe.symbolic_probe", side_effect=AssertionError("solver repeated")):
            result = execute(payload)
        self.assertEqual(result["probe"]["status"], "PASS")
        self.assertTrue(result["probe"]["certificate_reused"])
        payload["admission_probe"] = {"status": "PASS", "certificate": []}
        self.assertEqual(execute(payload)["probe"]["status"], "UNKNOWN")
        payload["admission_probe"] = copy.deepcopy(committed)
        payload["admission_probe"]["certificate"]["denominators"] = []
        self.assertEqual(execute(payload)["probe"]["status"], "UNKNOWN")

    def test_unobserved_crossing_preserves_only_the_admission_certificate(self):
        source = "def control(x): return 0\ndef treatment(x): return x\n"
        committed = admission_probe({"formal": FORMAL}, source)
        probe = execute({"source": source, "data": "sample_id,x,y\na,0,0\n",
                         "hypothesis": {"formal": FORMAL}, "admission_probe": committed})["probe"]
        self.assertEqual(probe["status"], "FAIL")
        self.assertEqual(probe["assurance"], "EXACT_OBSERVATION_CHECKED")
        self.assertEqual(probe["admission_status"], "PASS")
        self.assertEqual(probe["admission_assurance"], "CERTIFICATE_CHECKED")
        self.assertEqual(probe["observed_status"], "FAIL")
        self.assertEqual(probe["execution_assurance"], "EXACT_OBSERVATION_CHECKED")
        self.assertEqual(probe["observed_crossings"], [])
        self.assertEqual(probe["certificate"]["verdict"], "PASS")
        self.assertTrue(check_certificate(parse_source(source), FORMAL, probe["certificate"]))

    def test_nested_powers_are_bounded_before_solver_or_execution(self):
        expression = "x"
        for _ in range(6):
            expression = f"({expression})**4"
        source = f"def control(x): return 0\ndef treatment(x): return {expression}\n"
        probe = admission_probe({"formal": FORMAL}, source)
        self.assertEqual(probe["status"], "UNKNOWN")
        self.assertIn("bounds", probe["reason"])
        with self.assertRaises(ResourceLimit):
            execute({"source": source, "data": "sample_id,x,y\na,2,0\n", "hypothesis": {}})

    def test_unsupported_solver_result_is_labeled_and_not_replayed(self):
        source = "def control(x): return 0\ndef treatment(x): return x**2\n"
        committed = {"status": "PASS", "assurance": "SYMBOLIC_CHECKED"}
        payload = {"source": source, "data": "sample_id,x,y\na,1,1\n",
                   "hypothesis": {"formal": FORMAL}, "admission_probe": committed}
        with patch("rds_probe.symbolic_probe", return_value={**committed, "statement": "threshold_separation"}) as solver:
            result = execute(payload)
        solver.assert_called_once()
        self.assertEqual(result["probe"]["assurance"], "SYMBOLIC_CHECKED")
        self.assertNotIn("certificate_reused", result["probe"])

    def test_isolated_worker_without_site_packages_roundtrip(self):
        payload = {"operation": "admission", "hypothesis": {"formal": FORMAL}, "source": SOURCE}
        result = subprocess.run([sys.executable, "-I", "-S", "-B", str(ROOT / "scripts/rds_probe.py")],
                                input=json.dumps(payload).encode("utf-8"), capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        probe = json.loads(result.stdout)
        self.assertEqual(probe["assurance"], "CERTIFICATE_CHECKED")
        self.assertTrue(check_certificate(parse_source(SOURCE), FORMAL, probe["certificate"]))


if __name__ == "__main__":
    unittest.main()

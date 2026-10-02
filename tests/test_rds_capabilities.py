"""Selected backend checks are live availability evidence, never proof or scans."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import rds_capabilities as capabilities


class CapabilityTests(unittest.TestCase):
    def test_stdlib_exact_check_does_not_load_external_backends(self):
        with patch.object(capabilities.importlib, 'import_module') as imported:
            report = capabilities.probe('python_exact')
            imported.assert_not_called()
        self.assertEqual(report['status'], 'AVAILABLE')
        self.assertEqual(report['python'], sys.executable)
        self.assertIn('NOT_SCIENTIFIC_VERIFICATION', report['assurance'])

    def test_missing_selected_backend_does_not_silently_fall_back(self):
        with patch.object(capabilities.importlib, 'import_module', side_effect=ModuleNotFoundError('missing selected module')) as imported:
            report = capabilities.probe('sympy_exact')
        imported.assert_called_once_with('sympy')
        self.assertEqual(report['status'], 'UNAVAILABLE')
        self.assertIn('missing selected module', report['error'])

    def test_failed_operation_is_not_available_and_unknown_name_cannot_run(self):
        with patch.object(capabilities.importlib, 'import_module', side_effect=RuntimeError('selected runtime failed')):
            self.assertEqual(capabilities.probe('mpmath_iv')['status'], 'FAILED_SMOKE')
        with patch.object(capabilities.importlib, 'import_module') as imported:
            with self.assertRaises(ValueError):
                capabilities.probe('import-every-package')
            imported.assert_not_called()

    def test_spec_mastery_qualification_pure_declaration(self):
        spec = {
            "schema": 1,
            "capability_id": "test_operator",
            "fixtures": {
                "tier1_smoke_pass": {"input": {"x": 1}, "expected_status": "PASS"},
                "tier2_counterexample_witness": {"input": {"x": -1}, "expected_status": "CONTRADICTED"},
                "tier3_boundary_stress": [{"input": {"x": None}, "expected_status": "UNKNOWN"}]
            }
        }
        res = capabilities.verify_capability_mastery(spec)
        self.assertEqual(res["mastery_status"], "QUALIFIED")
        self.assertTrue(res["all_tiers_passed"])

    def test_executable_mastery_three_tier_pass(self):
        spec = {
            "schema": 1,
            "capability_id": "rational_check",
            "fixtures": {
                "tier1_smoke_pass": {"input": {"r": 1}, "expected_status": "PASS"},
                "tier2_counterexample_witness": {"input": {"r": -1}, "expected_status": "CONTRADICTED", "expected_witness_present": True},
                "tier3_boundary_stress": [{"input": {}, "expected_status": "UNKNOWN"}]
            }
        }
        def op(inp):
            if "r" not in inp:
                return {"status": "UNKNOWN"}
            if inp["r"] > 0:
                return {"status": "PASS"}
            return {"status": "CONTRADICTED", "witness": {"violating_radius": inp["r"]}}

        res = capabilities.verify_capability_mastery(spec, implementation_callable=op)
        self.assertEqual(res["mastery_status"], "QUALIFIED")
        self.assertTrue(res["tier_results"]["tier2_counterexample_witness"]["witness_present"])

    def test_executable_mastery_rejects_missing_witness(self):
        spec = {
            "schema": 1,
            "capability_id": "bad_op",
            "fixtures": {
                "tier1_smoke_pass": {"input": {"r": 1}, "expected_status": "PASS"},
                "tier2_counterexample_witness": {"input": {"r": -1}, "expected_status": "CONTRADICTED", "expected_witness_present": True},
                "tier3_boundary_stress": [{"input": {}, "expected_status": "UNKNOWN"}]
            }
        }
        # Returns CONTRADICTED but fails to extract structured witness
        def op(inp):
            if "r" not in inp:
                return {"status": "UNKNOWN"}
            if inp["r"] > 0:
                return {"status": "PASS"}
            return {"status": "CONTRADICTED"}

        res = capabilities.verify_capability_mastery(spec, implementation_callable=op)
        self.assertEqual(res["mastery_status"], "REJECTED")
        self.assertFalse(res["all_tiers_passed"])

    def test_executable_mastery_rejects_boundary_crash(self):
        spec = {
            "schema": 1,
            "capability_id": "crashing_op",
            "fixtures": {
                "tier1_smoke_pass": {"input": {"r": 1}, "expected_status": "PASS"},
                "tier2_counterexample_witness": {"input": {"r": -1}, "expected_status": "CONTRADICTED", "expected_witness_present": True},
                "tier3_boundary_stress": [{"input": {}, "expected_status": "UNKNOWN"}]
            }
        }
        def op(inp):
            if not inp:
                raise KeyError("missing input!")
            return {"status": "PASS"}

        res = capabilities.verify_capability_mastery(spec, implementation_callable=op)
        self.assertEqual(res["mastery_status"], "REJECTED")
        self.assertEqual(res["tier_results"]["tier3_boundary_stress"]["status"], "FAIL")


if __name__ == '__main__':
    unittest.main()

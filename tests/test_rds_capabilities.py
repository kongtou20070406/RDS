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


if __name__ == '__main__':
    unittest.main()

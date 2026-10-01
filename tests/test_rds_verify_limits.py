"""General source dependencies and bounded JSON admission for proof rules."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rds_verify as framework
from rds_verify_types import bounded_json


class GeneralVerifierTests(unittest.TestCase):
    def test_existing_null_and_boolean_semantics_are_preserved(self):
        bounded_json({"metadata": [None, True, False, 42, "1/2"]})

    def test_domain_can_reject_boolean_substitution_and_null(self):
        for value, options in ((False, {"allow_bool": False}), (None, {"allow_none": False})):
            with self.assertRaises(ValueError):
                bounded_json(value, **options)

    def test_all_float_forms_fail_exact_json_admission(self):
        for value in (0.0, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                bounded_json({"value": value})

    def test_wide_and_deep_inputs_are_bounded_before_serialization(self):
        with self.assertRaises(ValueError):
            bounded_json(list(range(10)), max_nodes=4)
        with self.assertRaises(ValueError):
            bounded_json([[[[0]]]], max_depth=3)
        bounded_json([[[[0]]]], max_depth=4)

    def test_support_files_are_declared_by_trusted_code_and_exposed(self):
        rule = framework.ProofRule("test.rule", ("test_statement",), "rds_scalar_verify",
                                   support_files=("rds_unit_disk_voronoi_core.py",))
        with patch.object(framework, "REGISTRY", framework.RuleRegistry((rule,))):
            self.assertEqual(framework.rules()[0]["support_files"], ["rds_unit_disk_voronoi_core.py"])

    def test_support_files_cannot_escape_the_trusted_source_directory(self):
        for name in ("../helper.py", "C:/helper.py", "helper.txt", "sub/helper.py"):
            rule = framework.ProofRule("test.rule", ("test",), "rds_scalar_verify", support_files=(name,))
            with self.assertRaises(ValueError):
                framework.RuleRegistry((rule,))

    def test_any_registered_rule_can_bind_a_supporting_source(self):
        rule = framework.ProofRule("test.rule", ("test",), "rds_scalar_verify",
                                   support_files=("rds_unit_disk_voronoi_core.py",))
        read = Path.read_bytes
        with patch.object(framework, "REGISTRY", framework.RuleRegistry((rule,))):
            original = framework.verifier_id()
            with patch.object(Path, "read_bytes", lambda path: b"changed dependency" if path.name ==
                              "rds_unit_disk_voronoi_core.py" else read(path)):
                self.assertNotEqual(framework.verifier_id(), original)


if __name__ == "__main__":
    unittest.main()

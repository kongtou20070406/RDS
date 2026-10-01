"""Finite history replay and an independent check of the generated expression."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("frontier_history", ROOT / "benchmark/advisor-frontier/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FrontierHistoryTests(unittest.TestCase):
    def test_time_slices_and_negative_controls(self):
        report = runner.run()
        self.assertTrue(report["passed"], report)
        self.assertEqual(len(report["cases"]), 4)
        self.assertEqual(sum(case["historical"] for case in report["cases"]), 3)
        self.assertEqual(len(report["negative_controls"]), 5)
        self.assertEqual(report["cost"]["model_calls"], 0)
        self.assertEqual(report["execution_order"][3], "load-evaluation-targets")

    def test_evaluator_recomputes_ast_instead_of_trusting_status(self):
        report = runner.run()
        item = next(case for case in report["cases"] if not case["historical"])
        targets = runner.read_json(runner.HERE / "targets.json")["cases"][item["id"]]
        program = next(p for p in item["result"]["program_proposals"]
                       if runner.typed_program_matches(p, item["input"], targets))
        tampered = deepcopy(program)
        tampered["ast"]["terms"][0]["exponent"] += 1
        self.assertFalse(runner.typed_program_matches(tampered, item["input"], targets))


if __name__ == "__main__":
    unittest.main()

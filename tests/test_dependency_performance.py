"""Performance samples must reject a changed result, without timing assertions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark.dependency_performance import paired


class DependencyPerformanceTests(unittest.TestCase):
    def test_changed_output_after_warmup_cannot_report_parity(self):
        values = iter(({"value": 0}, {"value": 1}))
        with self.assertRaisesRegex(AssertionError, "sample output"):
            paired(lambda: {"value": 0}, lambda: next(values), {}, repeats=1, inner=1)


if __name__ == "__main__":
    unittest.main()

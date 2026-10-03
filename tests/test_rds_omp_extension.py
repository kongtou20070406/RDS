"""Run the OMP event regressions through the existing Python CI matrix."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


class OmpExtensionTests(unittest.TestCase):
    def test_native_event_regressions(self):
        node = shutil.which("node")
        if not node:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("The CI runner must provide Node.js for OMP extension coverage")
            self.skipTest("Optional OMP extension tests require Node.js 18+")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, "--test", "tests/test_omp_status.mjs"], cwd=root,
                                env={**os.environ, "RDS_PYTHON": sys.executable},
                                capture_output=True, text=True, encoding="utf-8", timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

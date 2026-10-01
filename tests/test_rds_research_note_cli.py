"""Legacy CLI calls fail explicitly without reading notes or creating state."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ResearchNoteCLITests(unittest.TestCase):
    def test_retired_note_is_rejected_without_fallback_or_external_tools(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            environment = dict(os.environ, PATH="")
            for extra in ([], ["--literature", "lr"], ["--research-context", "missing-context.json"]):
                with self.subTest(extra=extra):
                    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                        "--root", str(root), "advise", "--research-note", "missing-note.md", *extra],
                        cwd=ROOT, capture_output=True, encoding="utf-8", timeout=15, env=environment)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("[RDS-REJECT]", result.stderr)
                    self.assertIn("checkpoint save --decision", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertFalse((root / ".rds").exists())

if __name__ == "__main__":
    unittest.main()

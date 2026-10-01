"""Weak graph review is local, composable, and cannot authorize a research run."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "examples/lightweight/RESEARCH.md"


class ResearchNoteCLITests(unittest.TestCase):
    def invoke(self, root, *arguments, env=None):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                               "--root", str(root), "advise", *arguments], cwd=ROOT,
                              capture_output=True, encoding="utf-8", timeout=15, env=env)

    def review(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        row = next(item for item in report["recommendations"] if item["type"] == "RESEARCH_LOOP_REVIEW")
        self.assertEqual(row["assurance"], "INPUT_REPORTED")
        return report, row["review"]

    def test_note_only_does_not_initialize_store_or_load_the_full_rule_library(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            before = NOTE.read_bytes()
            report, review = self.review(self.invoke(root, "--research-note", str(NOTE)))
            self.assertEqual(report["recommendations_count"], 1)
            self.assertEqual(review["statistics"]["repeat_proposal_count"], 1)
            self.assertTrue(any(edge["relation"] == "repeats_rejected" for edge in review["graph"]["edges"]))
            self.assertEqual(review["authorization"], "NOT_GRANTED_BY_NOTE")
            self.assertEqual(NOTE.read_bytes(), before)
            self.assertFalse((root / ".rds").exists())

    def test_artifact_and_frontier_composition_keeps_loop_flags(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, context = root / "manifest.json", root / "context.json"
            manifest.write_text(json.dumps({"schema": "rds-artifact-manifest-v1", "sources": []}), encoding="utf-8")
            context.write_text(json.dumps({"frontier": {"schema_version": 1, "nodes": [], "edges": [], "goals": []}}), encoding="utf-8")
            report, review = self.review(self.invoke(root, "--research-note", str(NOTE), "--artifacts", str(manifest),
                                                     "--research-context", str(context)))
            self.assertEqual(review["statistics"]["repeat_proposal_count"], 1)
            self.assertTrue(any(row["type"] == "RESEARCH_FRONTIER" for row in report["recommendations"]))
            self.assertFalse((root / ".rds").exists())

    def test_local_anti_loop_check_runs_with_no_obelisk_or_node_on_path(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            environment = dict(os.environ)
            environment["PATH"] = ""
            _, review = self.review(self.invoke(root, "--research-note", str(NOTE), env=environment))
            self.assertEqual(review["statistics"]["repeat_proposal_count"], 1)
            self.assertEqual(review["authorization"], "NOT_GRANTED_BY_NOTE")
            self.assertFalse((root / ".rds").exists())

    def test_note_is_not_silently_ignored_by_other_advisor_modes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for arguments in (["--literature", "lr"], ["--train-loss", "1", "--val-loss", "1"], ["--doc", str(NOTE)]):
                with self.subTest(arguments=arguments):
                    result = self.invoke(root, "--research-note", str(NOTE), *arguments)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("[RDS-REJECT]", result.stderr)
            self.assertFalse((root / ".rds").exists())

    def test_invalid_note_fails_without_traceback_or_fallback(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            note = root / "RESEARCH.md"
            for value in ("ordinary unrelated README", "```rds-research\n[]\n```", " " * (256 * 1024 + 1)):
                note.write_text(value, encoding="utf-8")
                result = self.invoke(root, "--research-note", str(note))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("[RDS-REJECT]", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((root / ".rds").exists())


if __name__ == "__main__":
    unittest.main()

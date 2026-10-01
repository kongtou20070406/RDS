"""Frontier inputs must reach Advisor intact through every public input path."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def frontier_input():
    return {"schema_version": 1,
            "nodes": [{"id": "measurement", "kind": "observable", "source": "raw measurement"},
                      {"id": "explanation", "kind": "requirement", "source": "research question"}],
            "edges": [],
            "goals": [{"id": "explain", "target": "explanation", "anchors": ["measurement"],
                       "decision": "Choose a discriminating explanation", "source": "research contract"}]}


class FrontierCLITests(unittest.TestCase):
    def invoke(self, project, *arguments):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                               "--root", str(project), "advise", *arguments],
                              cwd=ROOT, capture_output=True, encoding="utf-8", timeout=10)

    def report(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        answer = json.loads(result.stdout)
        rows = [row for row in answer["recommendations"] if row.get("type") == "RESEARCH_FRONTIER"]
        self.assertEqual(len(rows), 1)
        return rows[0]["frontier"]

    def test_standalone_frontier_emits_ai_question_without_execution_or_ledger(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path = project / "frontier.json"
            path.write_text(json.dumps(frontier_input()), encoding="utf-8")
            before = path.read_bytes()
            report = self.report(self.invoke(project, "--frontier", str(path)))
            self.assertTrue(any(gap["kind"] == "MISSING_BRIDGE" for gap in report["gaps"]))
            self.assertTrue(all(gap["status"] == "OPEN" and gap["question"] for gap in report["gaps"]))
            self.assertFalse((project / ".rds").exists())
            self.assertEqual(path.read_bytes(), before)

    def test_context_with_artifacts_preserves_frontier_and_manual_provenance(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            context, manifest = project / "context.json", project / "manifest.json"
            context.write_text(json.dumps({"frontier": frontier_input()}), encoding="utf-8")
            manifest.write_text(json.dumps({"schema": "rds-artifact-manifest-v1", "sources": []}), encoding="utf-8")
            baseline = self.report(self.invoke(project, "--research-context", str(context)))
            merged = self.report(self.invoke(project, "--research-context", str(context), "--artifacts", str(manifest)))
            self.assertEqual(baseline, merged)
            self.assertFalse((project / ".rds").exists())

    def test_artifacts_and_separate_frontier_are_composable(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path, manifest = project / "frontier.json", project / "manifest.json"
            path.write_text(json.dumps(frontier_input()), encoding="utf-8")
            manifest.write_text(json.dumps({"schema": "rds-artifact-manifest-v1", "sources": []}), encoding="utf-8")
            report = self.report(self.invoke(project, "--frontier", str(path), "--artifacts", str(manifest)))
            self.assertTrue(report["gaps"])

    def test_duplicate_or_incompatible_frontier_mode_fails_loudly(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path, context = project / "frontier.json", project / "context.json"
            path.write_text(json.dumps(frontier_input()), encoding="utf-8")
            context.write_text(json.dumps({"frontier": frontier_input()}), encoding="utf-8")
            for extra in (["--literature", "lr"], ["--research-context", str(context)],
                          ["--templates", str(path)]):
                with self.subTest(extra=extra):
                    result = self.invoke(project, "--frontier", str(path), *extra)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((project / ".rds").exists())

    def test_bad_frontier_cannot_silently_fall_back_to_ordinary_advice(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path = project / "bad.json"
            for spec in ([], {"schema_version": 99}, {"schema_version": 1, "nodes": "bad"}):
                path.write_text(json.dumps(spec), encoding="utf-8")
                result = self.invoke(project, "--frontier", str(path))
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((project / ".rds").exists())

    def test_frontier_context_does_not_silently_ignore_templates(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path, context, templates = [project / name for name in ("frontier.json", "context.json", "templates.json")]
            path.write_text(json.dumps(frontier_input()), encoding="utf-8")
            context.write_text(json.dumps({"facts": {}}), encoding="utf-8")
            templates.write_text(json.dumps({"garbage": True}), encoding="utf-8")
            result = self.invoke(project, "--frontier", str(path), "--research-context", str(context),
                                 "--templates", str(templates))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("explicit direction-search decision", result.stderr)
            self.assertFalse((project / ".rds").exists())

    def test_frontier_templates_accept_the_same_structured_decision_as_search(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path, context = project / "frontier.json", project / "context.json"
            path.write_text(json.dumps(frontier_input()), encoding="utf-8")
            context.write_text(json.dumps({"decision": {"id": "choose-next", "target_rules": []},
                                            "facts": {}}), encoding="utf-8")
            templates = ROOT / "examples/experiment-templates/templates.json"
            report = self.report(self.invoke(project, "--frontier", str(path), "--research-context", str(context),
                                              "--templates", str(templates)))
            self.assertTrue(report["gaps"])
            self.assertFalse((project / ".rds").exists())

    def test_proposal_pack_reaches_cli_and_cannot_be_ignored_by_early_modes(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path, proposals = project / "frontier.json", project / "proposals.json"
            path.write_text(json.dumps(frontier_input()), encoding="utf-8")
            proposals.write_text(json.dumps({"schema_version": 1, "proposals": []}), encoding="utf-8")
            report = self.report(self.invoke(project, "--frontier", str(path), "--frontier-proposals", str(proposals)))
            self.assertEqual(report["proposal_review"]["adopted_relations"], 0)
            for extra in ([], ["--literature", "lr"]):
                result = self.invoke(project, "--frontier-proposals", str(proposals), *extra)
                self.assertNotEqual(result.returncode, 0)
            self.assertFalse((project / ".rds").exists())

    def test_deep_or_oversized_input_is_rejected_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path = project / "bad.json"
            for payload in ("[" * 2000 + "0" + "]" * 2000, " " * (2 * 1024 * 1024 + 1)):
                path.write_text(payload, encoding="utf-8")
                result = self.invoke(project, "--frontier", str(path))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("[RDS-REJECT]", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((project / ".rds").exists())

    def test_ai_proposal_remains_unexecuted_through_cli(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            path, proposals = project / "frontier.json", project / "proposals.json"
            spec = frontier_input()
            spec["goals"][0]["relations"] = ["explains"]
            path.write_text(json.dumps(spec), encoding="utf-8")
            gap_id = self.report(self.invoke(project, "--frontier", str(path)))["gaps"][0]["id"]
            proposal = {"id": "hidden-condition", "gap_id": gap_id,
                "new_nodes": [{"id": "condition", "kind": "concept", "label": "Unmodelled condition"}],
                "relations": [{"from": "measurement", "to": "condition", "relation": "explains"},
                              {"from": "condition", "to": "explanation", "relation": "explains"}],
                "assumptions": ["Measurement protocol is comparable"],
                "prediction": {"observable": "measurement", "if_proposal": "Effect follows condition",
                               "if_rival": "Effect is independent of condition"},
                "test": {"protocol": "Matched comparison", "measurement": "Paired effect",
                         "stop_condition": "Stop if protocol differs"},
                "next_if_positive": "Investigate condition", "next_if_negative": "Retain rival",
                "scientific_support": "SUPPORTED", "execution_authorized": True}
            proposals.write_text(json.dumps({"schema_version": 1, "proposals": [proposal]}), encoding="utf-8")
            report = self.report(self.invoke(project, "--frontier", str(path), "--frontier-proposals", str(proposals)))
            review = report["proposal_review"]
            self.assertEqual(review["proposals"][0]["status"], "NEEDS_EVIDENCE")
            self.assertFalse(review["proposals"][0]["execution_authorized"])
            self.assertEqual(review["executed_tests"], 0)
            self.assertFalse((project / ".rds").exists())


if __name__ == "__main__":
    unittest.main()

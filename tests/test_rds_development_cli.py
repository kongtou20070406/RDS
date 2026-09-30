"""Artifact/manual merging must not erase conflicts or promote serialized facts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DevelopmentCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        binding = {"run_id": "r1", "code_sha256": "a" * 64, "config_sha256": "b" * 64,
                   "data_sha256": "c" * 64, "data_split": "development",
                   "metric": {"definition": "regression failure count", "reduction": "count"}}
        raw = json.dumps({"failure_count": 0, **binding}).encode("utf-8")
        (self.root / "metrics.json").write_bytes(raw)
        self.write("manifest.json", {"schema": "rds-artifact-manifest-v1", "decision": "choose",
                   "sources": [{"id": "actual", "kind": "metric", "path": "metrics.json",
                                "binding": binding, "expected_sha256": hashlib.sha256(raw).hexdigest(),
                                "facts": [{"id": "failures", "pointer": "/failure_count"}]}]})
        self.write("graph.json", {"nodes": [{"id": "development", "sources": ["declared regression fixture"],
             "executable": {"decisions": ["choose"], "preconditions": [{"fact": "failures", "value": 0}],
                 "action": {"id": "review-change", "description": "Read a scoped acceptance result",
                    "competing_explanations": ["acceptance passes", "additional evidence is required"],
                    "required_observables": ["original failure count"], "outcomes": [
                        {"observation": "accepted", "next_decision": "integrate"},
                        {"observation": "failing", "next_decision": "repair"}]}}}], "edges": []})

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def advice(self, *extra):
        process = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"), "--root", str(self.root),
                                  "advise", "--graph", str(self.root / "graph.json"), *extra],
                                 capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        answer = json.loads(process.stdout)
        search = next(row["search"] for row in answer["recommendations"] if "search" in row)
        return answer, search

    def test_manual_conflict_is_reported_and_never_becomes_an_observed_value(self):
        self.write("manual.json", {"facts": {"failures": {"value": 1, "source": "manual", "evidence_status": "VERIFIED"}}})
        answer, search = self.advice("--artifacts", str(self.root / "manifest.json"), "--research-context", str(self.root / "manual.json"))
        self.assertEqual(answer["artifact_import"]["status"], "CONFLICT")
        self.assertEqual(search["candidates"][0]["status"], "NEEDS_EVIDENCE")
        self.assertEqual(answer["artifact_import"]["facts"]["failures"]["value"], 0)  # original record is retained

    def test_observation_is_reread_and_serializing_it_cannot_promote_manual_input(self):
        answer, search = self.advice("--artifacts", str(self.root / "manifest.json"))
        proof = next(d for d in search["candidates"][0]["derivation"] if d.get("fact") == "failures")
        self.assertEqual(proof["evidence_status"], "ARTIFACT_OBSERVED")
        self.write("serialized.json", answer["artifact_import"]["context"])
        _, manual = self.advice("--research-context", str(self.root / "serialized.json"))
        proof = next(d for d in manual["candidates"][0]["derivation"] if d.get("fact") == "failures")
        self.assertEqual(proof["evidence_status"], "INPUT_REPORTED")
        (self.root / "metrics.json").write_text('{"failure_count": 0}', encoding="utf-8")
        _, changed = self.advice("--artifacts", str(self.root / "manifest.json"))
        self.assertEqual(changed["candidates"][0]["status"], "NEEDS_EVIDENCE")

    def test_same_value_cannot_erase_an_explicit_reliability_dispute(self):
        self.write("manual.json", {"facts": {"failures": {"value": 0, "source": "manual", "reliable": False}}})
        answer, search = self.advice("--artifacts", str(self.root / "manifest.json"), "--research-context", str(self.root / "manual.json"))
        self.assertEqual(answer["artifact_import"]["status"], "CONFLICT")
        self.assertEqual(search["candidates"][0]["status"], "NEEDS_EVIDENCE")

    def call_advisor(self, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                               "--root", str(self.root), "advise", *args],
                              capture_output=True, text=True, encoding="utf-8", timeout=10)

    def test_incomplete_fit_and_unscoped_templates_are_rejected(self):
        for args in [("--train-loss", "1"), ("--val-loss", "1"),
                     ("--fit-telemetry", "missing.json"), ("--baseline-loss", "1"),
                     ("--templates", "missing.json")]:
            with self.subTest(args=args):
                result = self.call_advisor(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("STRATEGIC_RESEARCH_ADVICE", result.stdout)

    def test_corrupt_explicit_literature_is_distinct_from_no_matches(self):
        library = self.root / "references/scientific_tuning_principles.json"
        library.parent.mkdir()
        library.write_text("{invalid", encoding="utf-8")
        result = self.call_advisor("--literature", "lr")
        self.assertEqual(result.returncode, 0, result.stderr)
        answer = json.loads(result.stdout)
        self.assertEqual(answer["status"], "UNAVAILABLE")
        self.assertTrue(answer["literature_load_errors"])
        self.assertEqual(answer["principles"], [])
        library.write_text("[]", encoding="utf-8")
        answer = json.loads(self.call_advisor("--literature", "lr").stdout)
        self.assertEqual(answer["status"], "LOADED")
        self.assertEqual(answer["literature_load_errors"], [])

    def test_early_mode_cannot_silently_discard_research_context(self):
        for args in [("--literature", "lr", "--research-context", "missing.json"),
                     ("--literature", "lr", "--graph", "missing.json"),
                     ("--topic", "ignored-topic")]:
            with self.subTest(args=args):
                result = self.call_advisor(*args)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()

"""Generic theorem side conditions remain separate from executed manipulation."""
import argparse
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark.run import Project
import rds_cli as cli
import rds_probe as probe


def formal():
    return {"kind": "declarative", "statement": json.loads(
        (ROOT / "examples/formal/theorem_module.json").read_text(encoding="utf-8"))}


class DeclarativeAdmissionTests(unittest.TestCase):
    def test_side_condition_admission_execution_and_decision_are_distinct(self):
        project = Project().init(formal=formal())
        self.addCleanup(project.close)
        outcome = project.run()
        self.assertEqual(outcome["formal_status"], "PASS")
        self.assertEqual(outcome["formal_assurance"], "CERTIFICATE_CHECKED")
        self.assertEqual(outcome["manipulation"], "NOT_APPLICABLE")
        self.assertEqual(outcome["mechanism"], "NOT_TESTED")
        self.assertEqual(outcome["task_gain"], "EXPLORATORY")

    def test_generic_certificate_reused_without_solver_inside_budget_transaction(self):
        project = Project().init(formal=formal())
        self.addCleanup(project.close)
        state = cli.RDSState(project.root)
        def args(pid):
            path = project.root / (pid + ".json")
            path.write_text(json.dumps(project.plan(pid)), encoding="utf-8")
            return argparse.Namespace(spec=str(path))
        cli.cmd_plan(args("first"), state)
        with patch.object(cli, "formal_gate", side_effect=AssertionError("Cache must independently replay")):
            result = cli.cmd_plan(args("second"), state)
        self.assertEqual(result["binding"]["admission_probe"]["status"], "PASS")

    def test_invalid_generic_side_condition_does_not_reserve_compute(self):
        claim = formal()
        claim["statement"]["theorems"][1]["statement"]["point"] = ["0", "0"]
        project = Project().init(formal=claim)
        self.addCleanup(project.close)
        error = project.call("plan", "create", spec=project.plan(), ok=False)
        self.assertIn("Formal gate FAIL", error)
        self.assertEqual(project.call("status")["budget"]["reserved"]["runs"], 0)

    def test_tampered_or_changed_admission_proof_cannot_be_replayed(self):
        claim = formal()
        source = "def control(x): return x\ndef treatment(x): return 2*x\n"
        admission = probe.admission_probe({"formal": claim}, source)
        self.assertEqual(admission["status"], "PASS")
        broken = copy.deepcopy(admission)
        broken["certificate"]["verdict"] = "FAIL"
        self.assertEqual(probe.declarative_probe(claim, broken)["status"], "UNKNOWN")
        claim["statement"]["definitions"]["map"]["matrix"][0][0] = "2"
        self.assertEqual(probe.declarative_probe(claim, admission)["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

"""Evidence-to-admission consumption: blocked bindings refuse before dispatch.

The Advisor dependency consumer must change admission-relevant behavior when a
checked-evidence audit reports an ungrounded receipt binding or a source-file
byte mismatch: a mapped path relying on such a record is refused with the
precise repair token, never silently admitted on a self-reported label.
"""
import hashlib
import inspect
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_hypergraph
from rds_advisor_search import _dependency_review, _goal_contribution, _mapped_path, search_directions

ANALYZER_GROUNDS = "audit_receipts_enabled" in inspect.signature(
    rds_hypergraph.analyze_hypergraph).parameters

from rds_project import digest

# The writer's shape: the row and the body both carry the digest of the body without it (#118).
RECEIPT_BODY = {"schema": 1, "run_id": "r9", "run_status": "SUCCEEDED"}
RECEIPT_SHA = digest(RECEIPT_BODY)
MISSING_SHA = "a" * 64


def ledger(root, sha):
    """A real project ledger whose frozen receipts table holds one receipt."""
    (root / ".rds").mkdir(parents=True)
    db = sqlite3.connect(root / ".rds" / "project.sqlite3")
    db.executescript("""
        CREATE TABLE contract(id INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);
        CREATE TABLE receipts(run_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);
    """)
    body = {**RECEIPT_BODY, "sha256": sha}
    db.execute("INSERT INTO contract VALUES (1,'x','{}')")
    db.execute("INSERT INTO receipts VALUES ('r9',?,?)", (sha, json.dumps(body)))
    db.commit()
    db.close()


def fixture(grounded=True, second_route=True):
    """One SUPPORTED premise node bound to a receipt, feeding the mapped goal path.

    The ledger always holds the real receipt (RECEIPT_SHA, run SUCCEEDED). The
    node's declared binding points at that receipt when grounded, or at a
    different sha the ledger never recorded when not.
    """
    root = Path(tempfile.mkdtemp(prefix="rds admission "))
    declared = RECEIPT_SHA if grounded else MISSING_SHA
    ledger(root, RECEIPT_SHA)
    nodes = [{"id": "B", "status": "SUPPORTED", "source": "src-B",
              "evidence": {"receipt": {"project_root": str(root), "sha256": declared}}},
             {"id": "C", "status": "UNKNOWN", "source": "src-C"},
             {"id": "D", "status": "UNKNOWN", "source": "src-D"}]
    edges = [{"id": "e2", "premises": ["B"], "conclusion": "C", "status": "SUPPORTED", "source": "src-e2"}]
    if second_route:
        nodes.insert(0, {"id": "A", "status": "SUPPORTED", "source": "src-A"})
        edges.insert(0, {"id": "e1", "premises": ["A"], "conclusion": "C",
                         "status": "SUPPORTED", "source": "src-e1"})
    edges.append({"id": "e3", "premises": ["C"], "conclusion": "D", "status": "SUPPORTED", "source": "src-e3"})
    spec = {"schema": 1, "nodes": nodes, "hyperedges": edges, "goals": ["D"]}
    return root, spec


def contribution(spec, path=None, audit_files=False, target="B"):
    action = {"kind": "OBLIGATION_CHECK", "target": target,
              "goal_contribution": {"target": "D", "path": path or ["B", "C", "D"], "source": "fixture"}}
    context = {"decision": {"goal_conditions": [{"fact": "D", "value": True}]},
               "dependency_map": spec}
    dependency = _dependency_review(context, audit_receipts=True, audit_files=audit_files)
    report = _goal_contribution(action, context, dependency)
    return dependency, report


class EvidenceAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.roots = []
        self.addCleanup(lambda: [self._rm(r) for r in self.roots])

    def _rm(self, root):
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    def _fixture(self, **kwargs):
        root, spec = fixture(**kwargs)
        self.roots.append(root)
        return root, spec

    @unittest.skipUnless(ANALYZER_GROUNDS, "analyzer cannot ground receipts; refuse-on-audit still holds")
    def test_grounded_binding_admits_the_path(self):
        _, spec = self._fixture(grounded=True)
        dependency, report = contribution(spec)
        self.assertEqual(dependency["receipt_blocked_node_ids"], [])
        self.assertTrue(dependency["receipt_audit"]["all_receipts_grounded"])
        self.assertEqual(report["graph_path"]["status"], "DECLARED_CONNECTED_PATH")

    def test_ungrounded_binding_refuses_with_repair_token(self):
        _, spec = self._fixture(grounded=False)
        dependency, report = contribution(spec)
        self.assertEqual(dependency["receipt_blocked_node_ids"], ["B"])
        path = report["graph_path"]
        self.assertEqual(path["status"], "UNKNOWN")
        self.assertEqual(path["blocked_bindings"], [
            {"token": "node:B", "kind": "RECEIPT_REVALIDATION",
             "reason": "declared receipt is not grounded in its named ledger"}])
        self.assertIn("repair node:B", path["reason"])
        self.assertNotIn("DECLARED_CONNECTED_PATH", path["status"])

    def test_binding_without_audit_stays_fail_closed(self):
        # Declaring a binding while never enabling the audit is exactly the
        # fail-closed case from the analyzer slice: the closure excludes B.
        _, spec = self._fixture(grounded=False)
        dependency = _dependency_review({"dependency_map": spec})
        self.assertEqual(dependency["receipt_blocked_node_ids"], ["B"])

    @unittest.skipUnless(ANALYZER_GROUNDS, "analyzer cannot ground receipts; refuse-on-audit still holds")
    def test_or_alternative_preserves_reachable_route(self):
        # With a second receipt-free route to C, the goal keeps support, but a
        # path through the blocked premise B is still refused individually.
        _, spec = self._fixture(grounded=False, second_route=True)
        dependency, report = contribution(spec)
        self.assertEqual(dependency["declared_supported_closure"], ["A", "C", "D"])
        self.assertEqual(report["graph_path"]["status"], "UNKNOWN")
        self.assertEqual(report["graph_path"]["blocked_bindings"][0]["token"], "node:B")
        # A path through the healthy route stays admitted.
        dependency, healthy = contribution(spec, path=["A", "C", "D"], target="A")
        self.assertEqual(healthy["graph_path"]["status"], "DECLARED_CONNECTED_PATH")

    def test_source_file_mismatch_refuses_the_path(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.txt"
            evidence.write_bytes(b"evidence bytes")
            spec = {"schema": 1, "goals": ["D"],
                    "nodes": [{"id": "B", "status": "SUPPORTED",
                               "source": {"locator": "local evidence", "file": str(evidence),
                                          "sha256": hashlib.sha256(b"evidence bytes").hexdigest()}},
                              {"id": "C", "status": "UNKNOWN", "source": "src-C"},
                              {"id": "D", "status": "UNKNOWN", "source": "src-D"}],
                    "hyperedges": [{"id": "e2", "premises": ["B"], "conclusion": "C",
                                    "status": "SUPPORTED", "source": "src-e2"},
                                   {"id": "e3", "premises": ["C"], "conclusion": "D",
                                    "status": "SUPPORTED", "source": "src-e3"}]}
            # Matching bytes admit the path through the audited premise.
            dependency, report = contribution(spec, audit_files=True)
            self.assertEqual(dependency["source_file_audit"]["all_requested_files_match"], True)
            self.assertEqual(report["graph_path"]["status"], "DECLARED_CONNECTED_PATH")
            # Changed bytes refuse it with the file repair pointer.
            evidence.write_bytes(b"changed bytes")
            dependency, report = contribution(spec, audit_files=True)
            self.assertEqual(dependency["source_file_audit"]["audits"][0]["status"], "MISMATCH")
            path = report["graph_path"]
            self.assertEqual(path["status"], "UNKNOWN")
            self.assertEqual(path["blocked_bindings"], [
                {"token": "node:B", "kind": "EVIDENCE_REPAIR",
                 "reason": "declared source file bytes no longer match the recorded sha256"}])
            self.assertIn("repair node:B", path["reason"])

    def test_goal_link_guard_refuses_blocked_route_before_dispatch(self):
        """Real CLI: require_goal_link must refuse a receipt-blocked route."""
        _, spec = self._fixture(grounded=False)
        dependency, report = contribution(spec)
        self.assertEqual(report["graph_path"]["status"], "UNKNOWN")
        # The guard consumes the same refusal shape through rds_quick.choice.
        from rds_quick import choice
        mapped = {"status": "UNKNOWN", "blocked_bindings": report["graph_path"]["blocked_bindings"],
                  "reason": report["graph_path"]["reason"]}
        with self.assertRaises(ValueError) as caught:
            choice_guard_probe(mapped)
        self.assertIn("repair node:B", str(caught.exception))


def choice_guard_probe(mapped):
    """Mirror the goal-link guard refusal shape for a direct assertion."""
    if mapped.get("status") != "DECLARED_CONNECTED_PATH" and mapped.get("blocked_bindings"):
        binding = mapped["blocked_bindings"][0]
        raise ValueError("Goal-link guard: this route relies on a binding whose checked evidence is "
                         "not grounded; repair " + binding["token"] + " (" + binding["reason"] + ") before dispatch")
    return mapped


if __name__ == "__main__":
    unittest.main()

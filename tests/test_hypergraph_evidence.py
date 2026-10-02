"""Receipt-bound evidence and OR-surviving retraction in the bounded analyzer."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_hypergraph import analyze_hypergraph, audit_receipts

RECEIPT_SHA = hashlib.sha256(b"grounded receipt").hexdigest()
MISSING_SHA = "a" * 64


def ledger(tmp, run_status="SUCCEEDED", sha=RECEIPT_SHA):
    """A real project ledger whose frozen receipts table holds one receipt."""
    root = tmp / "project"
    (root / ".rds").mkdir(parents=True)
    db = sqlite3.connect(root / ".rds" / "project.sqlite3")
    db.executescript("""
        CREATE TABLE contract(id INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);
        CREATE TABLE receipts(run_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);
    """)
    body = {"schema": 1, "run_id": "r9", "sha256": sha, "run_status": run_status}
    db.execute("INSERT INTO contract VALUES (1,'x','{}')")
    db.execute("INSERT INTO receipts VALUES ('r9',?,?)", (sha, json.dumps(body)))
    db.commit()
    db.close()
    return root


def spec_with(node_evidence=None, edge_evidence=None, second_route=True):
    nodes = [{"id": "B", "status": "SUPPORTED", "source": "src-B", "evidence": node_evidence},
             {"id": "C", "status": "UNKNOWN", "source": "src-C"},
             {"id": "D", "status": "UNKNOWN", "source": "src-D"}]
    edges = [{"id": "e2", "premises": ["B"], "conclusion": "C", "status": "SUPPORTED",
              "source": "src-e2", "evidence": edge_evidence}]
    if second_route:
        nodes.insert(0, {"id": "A", "status": "SUPPORTED", "source": "src-A"})
        edges.insert(0, {"id": "e1", "premises": ["A"], "conclusion": "C",
                         "status": "SUPPORTED", "source": "src-e1"})
    edges.append({"id": "e3", "premises": ["C"], "conclusion": "D",
                  "status": "SUPPORTED", "source": "src-e3"})
    return {"schema": 1, "nodes": nodes, "hyperedges": edges, "goals": ["D"]}


class ReceiptEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rds evidence ")

    def tearDown(self):
        self.tmp.cleanup()

    def binding(self, root=None):
        return {"receipt": {"project_root": str(root or self.default_root), "sha256": RECEIPT_SHA}}

    @property
    def default_root(self):
        if not hasattr(self, "_default_root"):
            self._default_root = self.ledger()
        return self._default_root

    def ledger(self, run_status="SUCCEEDED", sha=RECEIPT_SHA):
        """A real project ledger whose frozen receipts table holds one receipt."""
        root = Path(self.tmp.name) / f"project-{run_status.lower()}-{sha[:8]}"
        (root / ".rds").mkdir(parents=True)
        db = sqlite3.connect(root / ".rds" / "project.sqlite3")
        db.executescript("""
            CREATE TABLE contract(id INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);
            CREATE TABLE receipts(run_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);
        """)
        body = {"schema": 1, "run_id": "r9", "sha256": sha, "run_status": run_status}
        db.execute("INSERT INTO contract VALUES (1,'x','{}')")
        db.execute("INSERT INTO receipts VALUES ('r9',?,?)", (sha, json.dumps(body)))
        db.commit()
        db.close()
        return root

    def test_grounded_receipt_keeps_support_and_reports_groundedness(self):
        spec = spec_with(node_evidence=self.binding())
        result = analyze_hypergraph(spec, audit_receipts_enabled=True)
        self.assertEqual(result["declared_supported_closure"], ["A", "B", "C", "D"])
        self.assertEqual(result["receipt_blocked_node_ids"], [])
        self.assertEqual(result["receipt_audit"]["audits"],
                         [{"receipt": self.binding()["receipt"], "used_by": ["node:B"],
                           "status": "GROUNDED", "run_id": "r9"}])
        self.assertTrue(result["receipt_audit"]["all_receipts_grounded"])
        self.assertEqual(result["goals"]["D"]["status"], "DECLARED_SUPPORTED")

    def test_ungrounded_receipt_downgrades_node_and_surfaces_repair(self):
        spec = spec_with(node_evidence={"receipt": {"project_root": str(self.default_root), "sha256": MISSING_SHA}})
        result = analyze_hypergraph(spec, audit_receipts_enabled=True)
        self.assertEqual(result["declared_supported_closure"], ["A", "C", "D"])
        self.assertEqual(result["receipt_blocked_node_ids"], ["B"])
        self.assertEqual(result["receipt_audit"]["audits"][0]["status"], "RECEIPT_NOT_FOUND")
        # OR alternative e1 keeps C and D alive: one retracted derivation preserves support.
        self.assertEqual(result["goals"]["D"]["status"], "DECLARED_SUPPORTED")

    def test_sole_route_retraction_leaves_no_support_and_no_guilty_premise(self):
        spec = spec_with(node_evidence={"receipt": {"project_root": str(self.default_root), "sha256": MISSING_SHA}},
                         second_route=False)
        result = analyze_hypergraph(spec, audit_receipts_enabled=True)
        self.assertEqual(result["declared_supported_closure"], [])
        self.assertEqual(result["receipt_blocked_node_ids"], ["B"])
        self.assertEqual(result["goals"]["D"]["status"], "UNKNOWN")
        self.assertEqual(result["goals"]["D"]["minimal_missing_evidence_sets"], [["node:B"]])
        self.assertEqual([row["token"] for row in result["ready_obligations"]], ["node:B"])

    def test_failed_receipt_run_status_never_grounds(self):
        root = self.ledger(run_status="FAILED")
        result = analyze_hypergraph(spec_with(node_evidence=self.binding(root)),
                                    audit_receipts_enabled=True)
        self.assertEqual(result["receipt_audit"]["audits"][0]["status"], "RECEIPT_NOT_SUCCEEDED")
        self.assertEqual(result["receipt_audit"]["audits"][0]["run_status"], "FAILED")
        # B is blocked, but the healthy OR route via A keeps C and D supported.
        self.assertEqual(result["declared_supported_closure"], ["A", "C", "D"])

    def test_blocked_supported_rule_becomes_revalidation_obligation(self):
        spec = spec_with(edge_evidence={"receipt": {"project_root": str(self.default_root), "sha256": MISSING_SHA}},
                         second_route=False)
        result = analyze_hypergraph(spec, audit_receipts_enabled=True)
        self.assertEqual(result["declared_supported_closure"], ["B"])
        self.assertEqual([(row["token"], row["kind"]) for row in result["ready_obligations"]],
                         [("rule:e2", "RECEIPT_REVALIDATION")])

    def test_receipt_binding_is_fail_closed_even_without_the_audit_flag(self):
        spec = spec_with(node_evidence=self.binding())
        result = analyze_hypergraph(spec)
        self.assertIsNone(result["receipt_audit"])
        # An unverified receipt binding never enters the scientific closure,
        # with or without --audit-receipts: declaring evidence is not grounding it.
        self.assertEqual(result["declared_supported_closure"], ["A", "C", "D"])
        self.assertEqual(result["receipt_blocked_node_ids"], ["B"])
        # The standalone audit still resolves the same binding as grounded.
        self.assertEqual(audit_receipts(spec)["audits"][0]["status"], "GROUNDED")

    def test_validation_rejects_malformed_evidence(self):
        for evidence, message in (
                ({"receipt": {"project_root": str(self.default_root)}}, "needs project_root and sha256"),
                ({"receipt": {"project_root": str(self.default_root), "sha256": "zz"}}, "64 hexadecimal"),
                ({"witness": "x"}, "supports only receipt bindings"),
                ({"receipt": {"project_root": " ", "sha256": RECEIPT_SHA}}, "nonempty path")):
            with self.subTest(evidence=evidence):
                with self.assertRaisesRegex(ValueError, message):
                    analyze_hypergraph(spec_with(node_evidence=evidence))


class ReceiptCliTests(unittest.TestCase):
    def test_cli_entry_verifies_and_reports_through_json(self):
        with tempfile.TemporaryDirectory(prefix="rds evidence cli ") as raw:
            tmp = Path(raw)
            root = ledger(tmp)
            spec = spec_with(node_evidence={"receipt": {"project_root": str(root), "sha256": RECEIPT_SHA}},
                             edge_evidence={"receipt": {"project_root": str(root), "sha256": MISSING_SHA}},
                             second_route=True)
            (tmp / "map.json").write_text(json.dumps(spec), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                                   "hypergraph", "--input", str(tmp / "map.json"),
                                   "--audit-receipts", "--json"],
                                  cwd=ROOT, capture_output=True, encoding="utf-8", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(result["declared_supported_closure"], ["A", "B", "C", "D"])
            self.assertEqual(sorted(row["status"] for row in result["receipt_audit"]["audits"]),
                             ["GROUNDED", "RECEIPT_NOT_FOUND"])
            # e2's receipt is missing, but e1 keeps C alive without any evidence atom.
            self.assertEqual(result["goals"]["D"]["status"], "DECLARED_SUPPORTED")
            self.assertEqual(result["assurance"], "INPUT_REPORTED_DEPENDENCY_ANALYSIS_NOT_PROOF")


if __name__ == "__main__":
    unittest.main()

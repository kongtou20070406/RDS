"""Read-only snapshot, evidence separation and HTML trust-boundary checks."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_dashboard import demo_snapshot, read_snapshot, render_html


class DashboardTests(unittest.TestCase):
    def project(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / ".rds").mkdir()
        path = root / ".rds" / "state.sqlite3"
        state = {"contract": {"project_id": "test", "claim": "A falsifiable research question"},
                 "hypotheses": {"H1": {"spec": {"proposition": "gain"},
                                        "task_gain": "EXPLORATORY", "mechanism": "REFUTED",
                                        "search_policy": "UNTESTED"}},
                 "plans": {"P1": {"run_status": "SUCCEEDED", "run_id": "R1"}},
                 "budget": {"limits": {"runtime_ms": 100, "runs": 2},
                            "spent": {"runtime_ms": 50, "runs": 1},
                            "reserved": {"runtime_ms": 0, "runs": 0}}}
        with closing(sqlite3.connect(path)) as db:
            db.executescript("CREATE TABLE state(id INTEGER PRIMARY KEY, body TEXT);"
                             "CREATE TABLE receipts(run_id TEXT PRIMARY KEY, body TEXT);"
                             "CREATE TABLE events(seq INTEGER PRIMARY KEY, body TEXT);")
            db.execute("INSERT INTO state VALUES(1,?)", (json.dumps(state),))
            db.execute("INSERT INTO receipts VALUES('R1',?)",
                       (json.dumps({"run_id": "R1", "run_status": "SUCCEEDED", "result": {"gain": "1/2"}}),))
            db.execute("INSERT INTO events VALUES(1,?)", (json.dumps({"kind": "RUN_FINISHED"}),))
            db.commit()
        return root, path

    def test_export_reads_actual_evidence_without_changing_ledger(self):
        root, path = self.project()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        original_files = {p.name for p in path.parent.iterdir()}
        output = root / "dashboard.html"
        result = subprocess.run([sys.executable, "-S", "-B", str(ROOT / "scripts/rds_dashboard.py"),
                                 "--root", str(root), "--output", str(output)],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        self.assertEqual({p.name for p in path.parent.iterdir()}, original_files)
        page = output.read_text(encoding="utf-8")
        match = re.search(r'<script id="snapshot" type="application/json">(.*?)</script>', page, re.S)
        snapshot = json.loads(match.group(1))
        self.assertEqual(snapshot["receipts"][0]["run_status"], "SUCCEEDED")
        hypothesis = snapshot["state"]["hypotheses"]["H1"]
        self.assertEqual(hypothesis["task_gain"], "EXPLORATORY")
        self.assertEqual(hypothesis["mechanism"], "REFUTED")
        self.assertEqual(hypothesis["search_policy"], "UNTESTED")
        self.assertIn("['task_gain','mechanism','search_policy']", page)
        self.assertNotIn("innerHTML", page)

    def test_project_store_runs_unknown_costs_and_original_receipts_are_read_only(self):
        # Reuse the existing real CPU runner fixture; do not maintain a second
        # handwritten project schema or treat process success as scientific gain.
        sys.path.insert(0, str(ROOT / "tests"))
        from test_rds_project import ProjectTests
        fixture = ProjectTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        good = fixture.run_spec(fixture.spec())
        failed = fixture.run_spec(fixture.spec("r2", "nonzero"))
        original = fixture.store.snapshot()
        path = fixture.store.path
        before = path.read_bytes()
        files = {p.relative_to(fixture.root) for p in fixture.root.rglob("*")}
        with patch("rds_project.file_sha", side_effect=AssertionError("Display must not hash inputs")):
            snapshot = read_snapshot(fixture.root)
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["ledger_type"], "PROJECT")
        self.assertEqual(snapshot["state"], original)
        self.assertEqual([r["run_status"] for r in snapshot["receipts"]], ["SUCCEEDED", "FAILED"])
        self.assertEqual(snapshot["receipts"], [good, failed])
        self.assertEqual(snapshot["state"]["budget"]["cpu_seconds"]["charged_estimate"], 2)
        self.assertIsNone(snapshot["receipts"][0]["resources"]["cpu_seconds"]["measured"])
        self.assertEqual(good["assessment"], {"task_gain": "UNKNOWN", "mechanism": "UNKNOWN"})
        self.assertEqual(snapshot["receipt_sources"]["r1"], {"database": str(path), "table": "receipts", "run_id": "r1"})
        self.assertTrue(all((fixture.root / a["path"]).is_file() for a in good["artifacts"]))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual({p.relative_to(fixture.root) for p in fixture.root.rglob("*")}, files)
        self.assertEqual(snapshot["event_count"], 2)
        # An unrelated reference ledger must not hide or merge project receipts.
        (fixture.root / ".rds/state.sqlite3").write_bytes(b"unrelated reference ledger")
        self.assertEqual(read_snapshot(fixture.root)["ledger_type"], "PROJECT")

    def test_cli_outputs_utf8_even_with_legacy_windows_stream_encoding(self):
        root, path = self.project()
        output = root / "科研工作台.html"
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_dashboard.py"),
                                 "--root", str(root), "--output", str(output)],
                                capture_output=True, timeout=10, env={**os.environ, "PYTHONIOENCODING": "gbk"})
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        response = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(response["output"], str(output.resolve()))
        self.assertEqual(response["ledger_type"], "REFERENCE")
        self.assertEqual(response["source"], str(path.resolve()))
        self.assertTrue(response["available"])

    def test_script_injection_is_encoded_and_roundtrips(self):
        attack = '</script><script>alert("owned")</script>&\u2028\u2029'
        snapshot = demo_snapshot(".")
        snapshot["state"]["contract"]["claim"] = attack
        advisor = {"diagnosis": attack, "evidence": [{"excerpt": attack}]}
        page = render_html(snapshot, advisor)
        embedded = re.search(r'<script id="snapshot" type="application/json">(.*?)</script>', page, re.S).group(1)
        self.assertNotIn("<", embedded)
        self.assertNotIn("&", embedded)
        self.assertNotIn("\u2028", embedded)
        self.assertEqual(json.loads(embedded)["state"]["contract"]["claim"], attack)
        self.assertEqual(json.loads(embedded)["advisor"], advisor)
        self.assertNotIn('alert("owned")</script>', page)
        self.assertIn("connect-src 'none'", page)

    def test_missing_database_is_empty_without_creating_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "uninitialized"
            snapshot = read_snapshot(root)
            self.assertFalse(snapshot["available"])
            self.assertEqual(snapshot["state"], {})
            self.assertEqual(snapshot["receipts"], [])
            self.assertFalse(root.exists())
            self.assertIn("noDataNotice", render_html(snapshot))

    def test_cli_rejects_malformed_native_advisor_candidates_before_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "advice.json", root / "dashboard.html"
            malformed = [None, {"steps": "missing input"}, {"steps": [None]},
                         {"derivation": {}}, {"derivation": [None]}]
            for group in ("candidates", "blocked_candidates", "experiment_composition"):
                for candidate in malformed:
                    search = {"candidates": []}
                    if group == "experiment_composition":
                        search[group] = {"candidates": [candidate]}
                    else:
                        search[group] = [candidate]
                    with self.subTest(group=group, candidate=candidate):
                        source.write_text(json.dumps({"recommendations": [{"search": search}]}), encoding="utf-8")
                        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_dashboard.py"),
                                                 "--root", str(root), "--advisor", str(source), "--output", str(output)],
                                                text=True, capture_output=True, encoding="utf-8", timeout=10)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("advisor.recommendations[0].search.", result.stderr)
                        self.assertIn("must be", result.stderr)
                        self.assertFalse(output.exists())
                        self.assertFalse((root / ".rds").exists())

    def test_demo_has_no_fabricated_run_or_confirmed_gain(self):
        snapshot = demo_snapshot(".")
        self.assertTrue(snapshot["demo"])
        self.assertEqual(snapshot["receipts"], [])
        self.assertEqual(snapshot["state"]["plans"], {})
        self.assertNotIn("budget", snapshot["state"])
        self.assertTrue(all(h["task_gain"] == "UNTESTED" for h in snapshot["state"]["hypotheses"].values()))

    def test_ledger_cannot_be_used_as_output_and_invalid_database_is_reported(self):
        root, path = self.project()
        before = path.read_bytes()
        for output in (path, root / ".rds" / "dashboard.html"):
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_dashboard.py"),
                                     "--root", str(root), "--output", str(output)],
                                    text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        path.write_bytes(b"invalid database")
        with self.assertRaises(sqlite3.DatabaseError):
            read_snapshot(root)


if __name__ == "__main__":
    unittest.main()

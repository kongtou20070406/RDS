"""Advisor ingestion races, store isolation and heuristic evidence boundaries."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_advisor as module
from rds_advisor import RDSAdvisor


class AdvisorConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rds-advisor-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.advisor = RDSAdvisor(self.root)

    def document(self, name="guide.md", text="Consider the learning rate on a plateau.\n"):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_concurrent_imports_do_not_lose_updates_or_duplicate_entries(self):
        documents = [self.document("a.md", "Consider learning rate A.\n"),
                     self.document("b.md", "Consider learning rate B.\n")]
        barrier = threading.Barrier(2)
        read = module._read_document
        def synchronized_read(path):
            result = read(path)
            barrier.wait(timeout=5)
            return result
        with patch.object(module, "_read_document", side_effect=synchronized_read):
            with ThreadPoolExecutor(max_workers=2) as pool:
                reports = list(pool.map(lambda path: RDSAdvisor(self.root).ingest_document(path), documents))
        self.assertTrue(all(report["assurance"] == "HEURISTIC_ONLY" for report in reports))
        db = sqlite3.connect(self.advisor.knowledge_db)
        try:
            rows = [json.loads(row[0]) for row in db.execute("SELECT body FROM knowledge")]
            self.assertEqual({row["source"] for row in rows}, {"a.md", "b.md"})
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        finally:
            db.close()
        for document in documents:
            report = self.advisor.ingest_document(document)
            self.assertEqual(report["rules_added"], 0)
            self.assertEqual(report["total_knowledge_entries"], 2)

    def test_parser_has_no_writer_lock_and_budget_database_is_independent(self):
        self.advisor.ingest_document(self.document())
        budget_path = self.root / ".rds/state.sqlite3"
        budget = sqlite3.connect(budget_path, isolation_level=None)
        budget.execute("CREATE TABLE marker (value TEXT)")
        budget.execute("BEGIN EXCLUSIVE")
        self.addCleanup(budget.close)
        read = module._read_document
        def writable_during_parse(path):
            result = read(path)
            writer = sqlite3.connect(self.advisor.knowledge_db, timeout=0, isolation_level=None)
            try:
                writer.execute("BEGIN IMMEDIATE")
                writer.execute("INSERT INTO metadata VALUES ('parser_probe','1')")
                writer.commit()
            finally:
                writer.close()
            return result
        with patch.object(module, "_read_document", side_effect=writable_during_parse):
            report = self.advisor.ingest_document(self.document("second.md", "Consider overfitting.\n"))
        self.assertEqual(report["total_knowledge_entries"], 2)
        budget.rollback()
        self.assertEqual(budget.execute("SELECT COUNT(*) FROM marker").fetchone()[0], 0)

    def test_recommendation_reader_does_not_wait_for_advisor_writer(self):
        self.advisor.ingest_document(self.document())
        writer = sqlite3.connect(self.advisor.knowledge_db, timeout=0, isolation_level=None)
        try:
            writer.execute("BEGIN IMMEDIATE")
            reports = self.advisor.recommend_next_directions(
                {"branches": {"main": {"stagnation_count": 2}}, "baseline_cache": {"entry": {}}}, {})
            self.assertTrue(all(report["assurance"] == "HEURISTIC_ONLY" for report in reports))
            self.assertTrue(any(report["type"] == "DOC_GROUNDED_INSIGHT" for report in reports))
        finally:
            writer.rollback()
            writer.close()

    def test_legacy_migration_is_explicit_once_and_preserves_file(self):
        legacy_path = self.root / ".rds/advisor_knowledge.json"
        legacy_path.parent.mkdir()
        row = {"line_number": 1, "excerpt": "Consider gradient explosion.", "topic": "optimization", "source": "old.md"}
        legacy_path.write_text(json.dumps([row, row]), encoding="utf-8")
        original = legacy_path.read_bytes()
        self.assertEqual(self.advisor.recommend_next_directions({}, {}), [])
        self.assertFalse(self.advisor.knowledge_db.exists())
        report = self.advisor.ingest_document(self.document())
        self.assertEqual(report["total_knowledge_entries"], 2)
        self.assertEqual(legacy_path.read_bytes(), original)
        # A migrated legacy file is neither reread nor overwritten on later imports.
        legacy_path.write_text("invalid legacy JSON after migration", encoding="utf-8")
        report = self.advisor.ingest_document(self.root / "guide.md")
        self.assertEqual(report["rules_added"], 0)
        self.assertEqual(report["total_knowledge_entries"], 2)

    def test_invalid_or_oversized_documents_do_not_commit_knowledge(self):
        invalid = self.root / "invalid.md"
        invalid.write_bytes(b"\xff\xfelearning rate")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            self.advisor.ingest_document(invalid)
        with self.assertRaisesRegex(ValueError, "regular file"):
            self.advisor.ingest_document(self.root)
        with patch.object(module, "MAX_DOCUMENT_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                self.advisor.ingest_document(self.document())
        with patch.object(module, "MAX_KNOWLEDGE_ROWS", 1):
            with self.assertRaisesRegex(ValueError, "excerpt"):
                self.advisor.ingest_document(self.document(text="Consider plateau.\nConsider learning rate.\n"))
        self.assertFalse(self.advisor.knowledge_db.exists())

    def test_stored_row_limit_rolls_back_batch(self):
        self.advisor.ingest_document(self.document())
        with patch.object(module, "MAX_KNOWLEDGE_ROWS", 1):
            with self.assertRaisesRegex(ValueError, "entry"):
                self.advisor.ingest_document(self.document("second.md", "Consider overfitting.\n"))
        db = sqlite3.connect(self.advisor.knowledge_db)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0], 1)
        finally:
            db.close()

    def test_truthy_telemetry_is_not_numeric_evidence(self):
        for flag in ("true", "false", 1, [], {}):
            report = self.advisor.advise_on_loss_dynamics({"nan_or_inf": flag})
            self.assertEqual(report["status"], "UNKNOWN")
            self.assertEqual(report["assurance"], "HEURISTIC_ONLY")
        self.assertEqual(self.advisor.advise_on_loss_dynamics({"nan_or_inf": True})["status"], "CRITICAL_ANOMALY")
        self.assertEqual(self.advisor.advise_on_loss_dynamics({"loss_trend": []})["status"], "UNKNOWN")
        self.assertEqual(self.advisor.advise_on_loss_dynamics([])["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

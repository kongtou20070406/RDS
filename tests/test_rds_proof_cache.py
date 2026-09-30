"""Cache trust and SQLite concurrency tests, independent of prover speed."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_proof_cache as cache_module
from rds_verify_types import MAX_CERTIFICATE_BYTES, canonical, digest


class FakeEngine:
    _bounded_json = staticmethod(cache_module.engine._bounded_json)

    def __init__(self):
        self.identity = "1" * 64
        self.calls = 0
        self.callback = None
        self.check_callback = None

    def verifier_id(self):
        return self.identity

    def verify(self, spec):
        self.calls += 1
        if self.callback:
            self.callback()
        if spec["want"] == "UNKNOWN":
            return {"status": "UNKNOWN", "assurance": "NONE", "backend": "test"}
        certificate = {"spec_sha256": digest(spec), "verdict": spec["want"], "proof": "checked"}
        return self.checked_result(spec, certificate)

    def checked_result(self, spec, certificate):
        if self.check_callback:
            self.check_callback()
        expected = {"spec_sha256": digest(spec), "verdict": spec["want"], "proof": "checked"}
        if certificate != expected or spec["want"] not in {"PASS", "FAIL"}:
            return {"status": "UNKNOWN", "assurance": "NONE", "backend": "test"}
        return {"status": spec["want"], "assurance": "CERTIFICATE_CHECKED", "backend": "test",
                "certificate": certificate}


class ProofCacheTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="rds-proof-cache-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / ".rds/proofs.sqlite3"
        self.engine = FakeEngine()
        self.patch = patch.object(cache_module, "engine", self.engine)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.cache = cache_module.ProofCache(self.path)

    def key(self, spec):
        return digest(spec) + self.engine.verifier_id()

    def corrupt(self, spec, raw):
        db = sqlite3.connect(self.path)
        try:
            db.execute("INSERT INTO proofs VALUES (?,?) ON CONFLICT(cache_key) DO UPDATE "
                       "SET certificate=excluded.certificate", (self.key(spec), raw))
            db.commit()
        finally:
            db.close()

    def test_pass_and_fail_are_cached_and_independently_rechecked(self):
        for verdict in ("PASS", "FAIL"):
            spec = {"want": verdict}
            first = self.cache.verify(spec)
            second = self.cache.verify(spec)
            self.assertEqual(first["status"], verdict)
            self.assertTrue(first["cache"]["stored"])
            self.assertTrue(second["cache"]["hit"])
        self.assertEqual(self.engine.calls, 2)

    def test_unknown_is_not_cached(self):
        spec = {"want": "UNKNOWN"}
        for _ in range(2):
            self.assertEqual(self.cache.verify(spec)["cache"], {"hit": False, "stored": False})
        self.assertEqual(self.engine.calls, 2)
        db = sqlite3.connect(self.path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM proofs").fetchone()[0], 0)
        finally:
            db.close()

    def test_tampered_verdict_is_recomputed(self):
        spec = {"want": "FAIL"}
        first = self.cache.verify(spec)
        forged = {**first["certificate"], "verdict": "PASS"}
        self.corrupt(spec, canonical(forged).encode("utf-8"))
        result = self.cache.verify(spec)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["cache"]["hit"])
        self.assertEqual(self.engine.calls, 2)

    def test_cache_metadata_cannot_override_checked_result(self):
        spec = {"want": "FAIL"}
        certificate = self.cache.verify(spec)["certificate"]
        forged = {**certificate, "assurance": "CERTIFICATE_CHECKED", "status": "PASS"}
        self.corrupt(spec, canonical(forged).encode("utf-8"))
        result = self.cache.verify(spec)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["cache"]["hit"])

    def test_changed_engine_or_full_spec_gets_a_new_cache_key(self):
        spec = {"want": "PASS"}
        self.cache.verify(spec)
        self.engine.identity = "2" * 64
        self.assertFalse(self.cache.verify(spec)["cache"]["hit"])
        self.assertTrue(self.cache.verify(spec)["cache"]["hit"])
        self.assertFalse(self.cache.verify({**spec, "extra_binding": "new"})["cache"]["hit"])
        self.assertEqual(self.engine.calls, 3)

    def test_engine_change_during_proving_skips_old_engine_key(self):
        self.engine.callback = lambda: setattr(self.engine, "identity", "2" * 64)
        result = self.cache.verify({"want": "PASS"})
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["cache"]["stored"])

    def test_solver_and_checker_run_after_read_connection_is_closed(self):
        connections = []
        original = self.cache._connect

        class Spy:
            def __init__(self, real):
                self.real = real
                self.closed = False

            def __getattr__(self, name):
                return getattr(self.real, name)

            def close(self):
                self.closed = True
                self.real.close()

        def connect(*args, **kwargs):
            spy = Spy(original(*args, **kwargs))
            connections.append(spy)
            return spy

        def ensure_closed():
            self.assertTrue(all(connection.closed for connection in connections))

        self.engine.callback = ensure_closed
        self.engine.check_callback = ensure_closed
        with patch.object(self.cache, "_connect", side_effect=connect):
            self.cache.verify({"want": "PASS"})
            self.assertTrue(self.cache.verify({"want": "PASS"})["cache"]["hit"])

    def test_solver_can_commit_an_independent_writer(self):
        def write():
            db = sqlite3.connect(self.path, timeout=0, isolation_level=None)
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO proofs VALUES ('solver-writer', '{}')")
                db.commit()
            finally:
                db.close()

        self.engine.callback = write
        self.assertEqual(self.cache.verify({"want": "PASS"})["status"], "PASS")

    def test_wal_reader_uses_committed_certificate_while_writer_is_active(self):
        spec = {"want": "PASS"}
        self.cache.verify(spec)
        writer = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        try:
            self.assertEqual(writer.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE proofs SET certificate=? WHERE cache_key=?", (b"forged", self.key(spec)))
            self.assertTrue(self.cache.verify(spec)["cache"]["hit"])
        finally:
            writer.rollback()
            writer.close()

    def test_existing_cache_constructor_and_hit_use_only_readonly_connections_during_writer(self):
        spec = {"want": "PASS"}
        self.cache.verify(spec)
        connections = []
        original = cache_module.ProofCache._connect

        def connect(cache, readonly=False):
            connections.append(readonly)
            return original(cache, readonly=readonly)

        writer = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        try:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE proofs SET certificate=? WHERE cache_key=?", (b"forged", self.key(spec)))
            with patch.object(cache_module.ProofCache, "_connect", new=connect):
                fresh_cache = cache_module.ProofCache(self.path)
                self.assertTrue(fresh_cache.ready)
                result = fresh_cache.verify(spec)
            self.assertTrue(result["cache"]["hit"])
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(connections, [True, True])
            self.assertEqual(self.engine.calls, 1)
        finally:
            writer.rollback()
            writer.close()

    def test_invalid_specs_are_preflighted_before_cache_hashing(self):
        self.patch.stop()
        cyclic = {}
        cyclic["self"] = cyclic
        deep = {}
        for _ in range(100):
            deep = {"child": deep}
        for value in (cyclic, deep, {"number": float("nan")}, {"number": 0.5}):
            with self.subTest(value_type="cyclic" if value is cyclic else "other"), \
                    patch.object(cache_module, "digest", side_effect=AssertionError("Cache hashed invalid input")):
                result = self.cache.verify(value)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["cache"], {"hit": False, "stored": False})

    def test_verifier_fingerprint_oserror_falls_back_to_engine(self):
        with patch.object(self.engine, "verifier_id", side_effect=OSError("Checker source unavailable")):
            result = self.cache.verify({"want": "PASS"})
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["cache"], {"hit": False, "stored": False})
        self.assertEqual(self.engine.calls, 1)

    def test_post_proof_fingerprint_oserror_falls_back_to_engine(self):
        with patch.object(self.engine, "verifier_id", side_effect=[self.engine.identity, OSError("Unavailable")]):
            result = self.cache.verify({"want": "PASS"})
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["cache"], {"hit": False, "stored": False})
        self.assertEqual(self.engine.calls, 2)

    def test_programming_assertions_are_not_swallowed(self):
        with patch.object(self.engine, "_bounded_json", side_effect=AssertionError("Implementation failure")):
            with self.assertRaises(AssertionError):
                self.cache.verify({"want": "PASS"})

    def test_busy_cache_store_does_not_change_verification_result(self):
        writer = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        try:
            writer.execute("BEGIN IMMEDIATE")
            result = self.cache.verify({"want": "PASS"})
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["cache"], {"hit": False, "stored": False})
        finally:
            writer.rollback()
            writer.close()

    def test_oversized_or_invalid_json_certificate_falls_back_to_proving(self):
        spec = {"want": "PASS"}
        for raw in (b"x" * (MAX_CERTIFICATE_BYTES + 1), b"invalid json", b"[]"):
            self.corrupt(spec, raw)
            result = self.cache.verify(spec)
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["cache"]["hit"])
        self.assertEqual(self.engine.calls, 3)

    def test_real_affine_framework_certificate_round_trip(self):
        self.patch.stop()
        value = json.loads((ROOT / "examples/formal/affine_dynamics.json").read_text(encoding="utf-8"))
        first = self.cache.verify(value)
        second = self.cache.verify(value)
        self.assertEqual(first["status"], "PASS")
        self.assertTrue(second["cache"]["hit"])
        self.assertEqual(second["assurance"], "CERTIFICATE_CHECKED")


if __name__ == "__main__":
    unittest.main()

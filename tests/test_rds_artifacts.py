"""Import actual local bytes; no scientific benchmark or external experiments."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_artifacts
from rds_artifacts import ArtifactFact, ingest_manifest
from rds_advisor_search import evaluate_condition, search_directions
from rds_verify_types import digest


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.binding = {"run_id": "r1", "code_sha256": "a" * 64, "config_sha256": "b" * 64,
                        "data_sha256": "c" * 64, "data_split": "development",
                        "metric": {"definition": "mean squared error", "reduction": "mean of four samples"}}

    def source(self, name, kind, data, facts, fmt=None, binding=None):
        raw = data if isinstance(data, bytes) else json.dumps(data, allow_nan=False).encode()
        (self.base / name).write_bytes(raw)
        return {"id": name, "path": name, "kind": kind, "format": fmt or "json", "expected_sha256": digest(raw),
                "binding": deepcopy(self.binding if binding is None else binding), "facts": facts}

    def run_import(self, sources, derived=None, receipts=None, cost_bindings=None):
        manifest = {"schema": "rds-artifact-manifest-v1", "decision": "choose", "sources": sources, "derived": derived or []}
        manifest["cost_bindings"] = cost_bindings or []
        path = self.base / "manifest.json"
        path.write_text(json.dumps(manifest, allow_nan=False), encoding="utf-8")
        return ingest_manifest(path, receipts=receipts)

    def test_four_sources_preserve_value_locator_hash_kind_and_input_bytes(self):
        cfg = self.source("config.json", "config", {"run_id": "r1", "lr": 0.1}, [{"id": "lr", "pointer": "/lr"}])
        self.binding["config_sha256"] = cfg["expected_sha256"]
        cfg["binding"]["config_sha256"] = cfg["expected_sha256"]
        metric = self.source("metrics.csv", "metric", b"run_id,loss\nr1,0.25\n", [{"id": "loss", "row": 1, "column": "loss"}], "csv")
        log = self.source("raw.log", "log", b"run_id=r1\nsteps=4\n", [{"id": "steps", "key": "steps"}], "kv")
        receipt = {"run_id": "r1", "run_status": "SUCCEEDED", "binding": self.binding,
                   "result": {"mean": 0.25}, "resources": {"wall_seconds": {"measured": 0.01, "unit": "seconds"}}}
        receipt["sha256"] = digest(receipt)
        rec = self.source("receipt.json", "receipt", receipt, [{"id": "receipt_loss", "pointer": "/result/mean"}])
        before = {p.name: p.read_bytes() for p in self.base.iterdir()}
        result = self.run_import([cfg, metric, log, rec])
        self.assertEqual(result["status"], "IMPORTED")
        for fid, kind, value in (("lr", "DECLARED", 0.1), ("loss", "OBSERVED", 0.25), ("steps", "OBSERVED", 4), ("receipt_loss", "OBSERVED", 0.25)):
            record = result["facts"][fid]
            self.assertIsInstance(record, ArtifactFact)
            self.assertEqual((record["kind"], record["value"]), (kind, value))
            self.assertEqual(record["source"]["sha256"], digest((self.base / record["source"]["path"]).read_bytes()))
            self.assertNotIn("sha256", record)
            self.assertIn("locator", record["source"])
        self.assertEqual(result["cost_report"]["totals"][0]["value"], 0.01)
        self.assertEqual({k: (self.base / k).read_bytes() for k in before}, before)

    def test_json_metric_json_log_and_jsonl_physical_line(self):
        sources = [self.source("metric.json", "metric", {"loss": 0.5}, [{"id": "loss", "pointer": "/loss"}]),
                   self.source("log.json", "log", {"steps": 8}, [{"id": "steps", "pointer": "/steps"}]),
                   self.source("log.jsonl", "log", b'{"run_id":"r1"}\n\n{"loss":0.75}\n',
                               [{"id": "last_loss", "row": 3, "pointer": "/loss"}], "jsonl")]
        result = self.run_import(sources)
        self.assertEqual(result["facts"]["last_loss"]["source"]["locator"], "line:3:pointer:/loss")
        self.assertEqual(result["facts"]["loss"]["value"], 0.5)

    def test_missing_hash_file_metadata_and_self_signature_stay_unknown(self):
        missing = {"id": "absent", "path": "absent.json", "kind": "metric", "facts": [{"id": "absent", "pointer": "/x"}]}
        signed = self.source("signed.json", "log", {"verified": True, "pass": True, "manipulation_verified": True},
                             [{"id": key, "pointer": "/" + key} for key in ("verified", "pass", "manipulation_verified")])
        no_binding = self.source("unbound.json", "metric", {"loss": 0.1}, [{"id": "unbound", "pointer": "/loss"}], binding={})
        no_hash = self.source("hashless.json", "metric", {"loss": 0.1}, [{"id": "hashless", "pointer": "/loss"}])
        no_hash.pop("expected_sha256")
        result = self.run_import([missing, signed, no_binding, no_hash])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertTrue(all(r["kind"] == "UNKNOWN" and r["value"] is None and not r["reliable"] for r in result["facts"].values()))

    def test_run_split_metric_and_config_conflicts_poison_both_sides(self):
        for field, changed in (("data_split", "holdout"), ("config_sha256", "d" * 64),
                               ("metric", {"definition": "accuracy", "reduction": "mean"})):
            one = self.source("one.json", "metric", {"loss": 0.5}, [{"id": "one", "pointer": "/loss"}])
            other = deepcopy(self.binding)
            other[field] = changed
            two = self.source("two.json", "metric", {"loss": 0.1}, [{"id": "two", "pointer": "/loss"}], binding=other)
            result = self.run_import([one, two], [{"id": "gain", "method": "difference", "input_fact_ids": ["one", "two"]}])
            self.assertEqual(result["status"], "CONFLICT", field)
            self.assertTrue(all(r["value"] is None for r in result["facts"].values()), field)
        bad_run = self.source("run.json", "log", {"run_id": "other", "steps": 4}, [{"id": "steps", "pointer": "/steps"}])
        self.assertEqual(self.run_import([bad_run])["facts"]["steps"]["kind"], "UNKNOWN")

    def test_difference_and_mean_have_lineage_and_no_eval(self):
        one = self.source("one.json", "metric", {"loss": 0.5}, [{"id": "one", "pointer": "/loss"}])
        other = deepcopy(self.binding)
        other["run_id"] = "r2"
        two = self.source("two.json", "metric", {"loss": 0.25}, [{"id": "two", "pointer": "/loss"}], binding=other)
        derived = [{"id": "gain", "method": "difference", "input_fact_ids": ["one", "two"]},
                   {"id": "mean", "method": "mean", "input_fact_ids": ["one", "two"]}]
        result = self.run_import([one, two], derived)
        self.assertEqual(result["facts"]["gain"]["value"], 0.25)
        self.assertEqual(result["facts"]["mean"]["value"], 0.375)
        self.assertEqual(result["facts"]["gain"].provenance_status, "PROGRAM_DERIVED")
        self.assertEqual(result["facts"]["gain"]["input_fact_ids"], ["one", "two"])
        with self.assertRaises(ValueError):
            self.run_import([one], [{"id": "exec", "method": "eval", "input_fact_ids": ["one"]}])

    def test_nonfinite_duplicate_keys_changed_bytes_and_root_escape(self):
        for name, raw in (("nan.json", b'{"loss":NaN}'), ("overflow.json", b'{"loss":1e999}'),
                          ("duplicate.json", b'{"loss":1,"loss":0}')):
            src = self.source(name, "metric", raw, [{"id": name, "pointer": "/loss"}])
            self.assertEqual(self.run_import([src])["facts"][name]["kind"], "UNKNOWN")
        changed = self.source("changed.json", "metric", {"loss": 1}, [{"id": "changed", "pointer": "/loss"}])
        (self.base / "changed.json").write_bytes(b'{"loss":0}')
        self.assertEqual(self.run_import([changed])["facts"]["changed"]["kind"], "UNKNOWN")
        changed["path"] = "../outside.json"
        self.assertEqual(self.run_import([changed])["facts"]["changed"]["kind"], "UNKNOWN")

    def test_source_size_and_row_caps_leave_unknown_without_loading_everything(self):
        large = self.source("large.json", "metric", b" " * (rds_artifacts.MAX_FILE_BYTES + 1), [{"id": "large", "pointer": "/loss"}])
        rows = self.source("rows.csv", "metric", b"run_id,loss\n" + b"r1,1\n" * (rds_artifacts.MAX_ROWS + 1),
                           [{"id": "rows", "row": 1, "column": "loss"}], "csv")
        result = self.run_import([large, rows])
        self.assertTrue(all(r["kind"] == "UNKNOWN" for r in result["facts"].values()))
        self.assertTrue(any("limit" in str(m) for m in result["missing"]))

    def test_one_advice_import_reads_and_hashes_each_unique_source_once(self):
        first = self.source("one.json", "metric", {"loss": 0.5}, [{"id": "first", "pointer": "/loss"}])
        second = deepcopy(first)
        second.update(id="alias", path="./one.json", facts=[{"id": "second", "pointer": "/loss"}])
        with patch("rds_artifacts._read", wraps=rds_artifacts._read) as read:
            result = self.run_import([first, second])
        self.assertEqual(result["status"], "IMPORTED")
        self.assertEqual(len(read.call_args_list), 2)  # one manifest plus one source

    def test_conflicts_and_missing_values_drive_real_advisor_queries(self):
        one = self.source("evidence.json", "metric", {"loss": 0.2}, [{"id": "loss", "pointer": "/missing"}])
        result = self.run_import([one])
        self.assertEqual(evaluate_condition({"fact": "loss", "op": "lt", "value": 1}, result["facts"])["truth"], "UNKNOWN")
        graph = {"nodes": [{"id": "inspect", "executable": {"decisions": ["choose"],
                 "preconditions": [{"fact": "loss", "op": "lt", "value": 1}],
                 "action": {"id": "compare", "description": "Inspect bounded evidence", "competing_explanations": ["real improvement", "wrong run"],
                 "required_observables": ["bound loss"], "outcomes": [{"observation": "improved", "next_decision": "continue"},
                 {"observation": "not improved", "next_decision": "stop"}]}}}]}
        check = search_directions(graph, result["context"])
        self.assertEqual(check["candidates"][0]["status"], "NEEDS_EVIDENCE")
        self.assertTrue(check["queries"])
        self.assertEqual(check["queries"][0]["kind"], "READ_ONLY_EVIDENCE_REQUEST")

    def test_receipt_historical_cost_binding_uses_one_actual_resource(self):
        receipt = {"run_id": "r1", "run_status": "FAILED", "binding": self.binding,
                   "resources": {"wall_seconds": {"measured": 2, "unit": "seconds"},
                                 "cpu_seconds": {"measured": None, "unknown": True, "unit": "seconds"}}}
        receipt["sha256"] = digest(receipt)
        costs = [{"action_id": "inspect", "run_id": "r1", "resource": "wall_seconds", "comparison_group": "same-protocol"},
                 {"action_id": "cpu", "run_id": "r1", "resource": "cpu_seconds", "comparison_group": "same-protocol"}]
        result = self.run_import([], receipts=[receipt], cost_bindings=costs)
        wall, cpu = result["context"]["costs"]["inspect"], result["context"]["costs"]["cpu"]
        self.assertEqual((wall["value"], wall["unit"], wall.provenance_status), (2, "seconds", "ARTIFACT_OBSERVED"))
        self.assertTrue(wall["historical"])
        self.assertEqual(wall["prediction_status"], "UNKNOWN")
        self.assertEqual(cpu["value"], None)
        self.assertFalse(cpu["reliable"])

    def test_provided_receipt_conflict_poison_source_and_cost(self):
        source = self.source("metric.json", "metric", {"loss": 0.2}, [{"id": "loss", "pointer": "/loss"}])
        other = deepcopy(self.binding)
        other["data_split"] = "holdout"
        receipt = {"run_id": "r1", "run_status": "SUCCEEDED", "binding": other,
                   "resources": {"wall_seconds": {"measured": 2, "unit": "seconds"}}}
        receipt["sha256"] = digest(receipt)
        costs = [{"action_id": "inspect", "run_id": "r1", "resource": "wall_seconds", "comparison_group": "same-protocol"}]
        result = self.run_import([source], receipts=[receipt], cost_bindings=costs)
        self.assertEqual(result["facts"]["loss"]["kind"], "UNKNOWN")
        self.assertEqual(result["context"]["costs"]["inspect"]["value"], None)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Resource accounting and control identity tests use synthetic CPU fixtures."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_costs import check_control_reuse, summarize_costs
from rds_verify_types import digest


def protocol():
    return {"code_sha256": "a" * 64, "config_sha256": "b" * 64, "data_sha256": "c" * 64,
            "data_split": "development", "init": {"algorithm": "zeros"}, "seed": 7,
            "checkpoint": "none", "schedule": {"steps": 3}, "sample_work": {"samples": 4},
            "numeric_protocol": {"dtype": "float64", "device": "cpu", "reduction": "serial"}}


def receipt(run_id="r1", status="SUCCEEDED", **extra):
    result = {"run_id": run_id, "attempt_id": run_id + "-a1", "run_status": status,
              "protocol": protocol(), "resources": {"wall_seconds": {"measured": 2.0, "unit": "seconds"},
              "cpu_seconds": {"measured": None, "unknown": True, "charged_estimate": 5, "unit": "seconds"}}, **extra}
    result["sha256"] = digest(result)
    return result


def rehash(value):
    value.pop("sha256", None)
    value["sha256"] = digest(value)
    return value


class CostsTests(unittest.TestCase):
    def make_control(self, base, **extra):
        identity = protocol()
        inputs = []
        for role in ("code", "config", "data"):
            raw = (role + " fixture").encode()
            (base / role).write_bytes(raw)
            identity[role + "_sha256"] = digest(raw)
            inputs.append({"role": role, "path": role, "sha256": digest(raw)})
        raw = str(identity).encode()
        (base / "protocol").write_bytes(raw)
        inputs.append({"role": "protocol", "path": "protocol", "sha256": digest(raw)})
        (base / "out").write_bytes(b"ok")
        return receipt(protocol=identity, bindings_before=inputs, bindings_after=deepcopy(inputs),
                       artifacts=[{"path": "out", "sha256": digest(b"ok")}], **extra), {"protocol": identity}

    def test_empty_receipts_leave_cost_unknown(self):
        result = summarize_costs([])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["totals"], [])
        self.assertIn("no completed receipts", result["missing"][0]["reason"])

    def test_failed_diagnostic_and_eval_attempts_are_charged_once(self):
        rows = [receipt("ok", purpose="experiment"), receipt("failed", "FAILED", purpose="diagnostic"),
                receipt("timeout", "TIMED_OUT", purpose="evaluation")]
        result = summarize_costs(rows + [rows[1]])
        self.assertEqual(len(result["attempts"]), 3)
        self.assertEqual(result["totals"][0]["value"], 6)
        self.assertEqual(len(result["estimates"]), 3)
        self.assertFalse(any(t["resource"] == "cpu_seconds" for t in result["totals"]))
        self.assertEqual(result["status"], "PARTIAL")

    def test_wall_never_substitutes_for_cpu_and_units_do_not_mix(self):
        one = receipt("one", resources={"wall_seconds": {"measured": 4, "unit": "seconds"},
                                        "api_cost": {"measured": 3, "unit": "USD"}})
        two = receipt("two", resources={"wall_seconds": {"measured": 100, "unit": "milliseconds"},
                                        "api_cost": {"measured": 2, "unit": "EUR"}})
        result = summarize_costs([one, two])
        self.assertEqual({(t["resource"], t["unit"], t["value"]) for t in result["totals"]},
                         {("wall_seconds", "seconds", 4), ("wall_seconds", "milliseconds", 100),
                          ("api_cost", "USD", 3), ("api_cost", "EUR", 2)})
        self.assertFalse(any(m["resource"] == "cpu_seconds" for m in result["measurements"]))

    def test_completed_receipt_integrity_and_binding_are_required(self):
        for item in (receipt(status="RUNNING"), {**receipt(), "sha256": "f" * 64},
                     rehash({**receipt(), "protocol": {"seed": 7}})):
            self.assertEqual(summarize_costs([item])["measurements"], [])
        result = summarize_costs([receipt()], {"r1": {"data_split": "holdout"}})
        self.assertEqual(result["measurements"], [])
        self.assertTrue(any("mismatch" in r for r in result["missing"][0]["reasons"]))

    def test_conflicting_duplicate_cannot_keep_cheaper_first_cost(self):
        first = receipt()
        second = deepcopy(first)
        second["resources"]["wall_seconds"]["measured"] = 99
        result = summarize_costs([first, rehash(second)])
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["totals"], [])
        self.assertEqual(result["attempts"], [])

    def test_old_elapsed_is_wall_and_allocation_is_only_an_estimate(self):
        item = receipt(resources={}, elapsed_ms=1250, charged_allocation={"runtime_ms": 5000, "runs": 1})
        result = summarize_costs([item])
        self.assertEqual(result["totals"][0], {"resource": "wall_seconds", "unit": "seconds", "value": 1.25, "receipt_ids": ["r1"]})
        self.assertEqual(result["estimates"][0]["status"], "CHARGED_ALLOCATION_NOT_MEASURED")

    def test_reuse_demands_complete_identity_and_current_artifact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            control, current = self.make_control(base)
            self.assertTrue(check_control_reuse(control, current, base)["reusable"])
            for key in protocol():
                changed = deepcopy(current)
                changed["protocol"].pop(key)
                result = check_control_reuse(control, changed, base)
                self.assertFalse(result["reusable"], key)
                self.assertTrue(any(key in r for r in result["reasons"]))
            # Same seed is insufficient when initialization/numerics differ.
            for key in ("init", "checkpoint", "schedule", "sample_work", "numeric_protocol"):
                changed = deepcopy(current)
                changed["protocol"][key] = "different"
                self.assertFalse(check_control_reuse(control, changed, base)["reusable"], key)
            (base / "out").write_bytes(b"changed")
            self.assertFalse(check_control_reuse(control, current, base)["reusable"])

    def test_input_changed_after_receipt_prevents_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            control, current = self.make_control(base)
            self.assertTrue(check_control_reuse(control, current, base)["reusable"])
            (base / "code").write_bytes(b"different code, unchanged output")
            result = check_control_reuse(control, current, base)
            self.assertFalse(result["reusable"])
            self.assertTrue(any("code" in r and "hash" in r for r in result["reasons"]))

    def test_nested_unknown_protocol_is_not_complete_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            control, current = self.make_control(base)
            current["protocol"]["numeric_protocol"]["dtype"] = None
            control["protocol"]["numeric_protocol"]["dtype"] = None
            result = check_control_reuse(rehash(control), current, base)
            self.assertFalse(result["reusable"])
            self.assertIn("missing control identity: numeric_protocol", result["reasons"])

    def test_failed_control_or_changed_input_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "out").write_bytes(b"ok")
            control = receipt(status="FAILED", artifacts=[{"path": "out", "sha256": digest(b"ok")}])
            self.assertIn("control did not finish SUCCEEDED", check_control_reuse(control, protocol(), base)["reasons"])
            control = receipt(artifacts=[{"path": "out", "sha256": digest(b"ok")}],
                              bindings_before=[{"path": "code", "sha256": "a" * 64}],
                              bindings_after=[{"path": "code", "sha256": "d" * 64}])
            self.assertFalse(check_control_reuse(control, protocol(), base)["reusable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

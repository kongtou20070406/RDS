"""Whole-disk extrema, source bindings and adversarial frozen replay."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_rational_voronoi_verify as disk
import rds_unit_disk_voronoi_core as core
from rds_verify import LeanFormalEngine, check_certificate, verifier_id, verify


def spec(radius="1", centers=None):
    return {"schema": 1, "kind": disk.KIND, "centers": centers or [["0", "0"]],
            "radius_squared": radius}


class RationalVoronoiTests(unittest.TestCase):
    def test_exact_origin_disk_including_boundary(self):
        source = spec()
        result = disk.verify(source)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["certificate"]["core_certificate"]["boundary_checks"], [["fixed", 0]])
        self.assertTrue(disk.check_certificate(source, result["certificate"]))
        self.assertIn("no_global_optimality", result["semantics"])

    def test_shifted_disk_antipode_equality_and_tiny_gap(self):
        centers = [["1/2", "0"]]
        self.assertEqual(disk.verify(spec("9/4", centers))["status"], "PASS")
        self.assertEqual(disk.verify(spec("2249999999999/1000000000000", centers))["status"], "UNKNOWN")

    def test_collinear_pair_bisector_extrema(self):
        centers = [["-1/2", "0"], ["1/2", "0"]]
        self.assertEqual(disk.verify(spec("5/4", centers))["status"], "PASS")
        self.assertEqual(disk.verify(spec("1249/1000", centers))["status"], "UNKNOWN")

    def test_boundary_coverage_does_not_hide_an_interior_hole(self):
        centers = [["1", "0"], ["0", "1"], ["-1", "0"], ["0", "-1"]]
        self.assertEqual(disk.verify(spec("1", centers))["status"], "PASS")
        failed = disk.verify(spec("99/100", centers))
        self.assertEqual(failed["status"], "UNKNOWN")
        self.assertIn("Voronoi vertex", failed["reason"])

    def test_tangent_bisector_degenerate_cell_and_empty_cell(self):
        for centers in ([["0", "0"], ["2", "0"]], [["0", "0"], ["4", "4"]]):
            with self.subTest(centers=centers):
                source = spec(centers=centers)
                result = disk.verify(source)
                self.assertEqual(result["status"], "PASS", result)
                self.assertTrue(disk.check_certificate(source, result["certificate"]))

    def test_duplicate_sites_and_exact_integer_inputs(self):
        source = spec(1, [[0, 0], [0, 0]])
        result = disk.verify(source)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["certificate"]["core_certificate"]["distinct_center_count"], 1)

    def test_one_hundred_exact_sites_cover_entire_disk(self):
        centers = [[str(Fraction(2 * i - 9, 10)), str(Fraction(2 * j - 9, 10))]
                   for i in range(10) for j in range(10)]
        source = spec("21/1000", centers)
        result = verify(source)
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(check_certificate(source, result["certificate"]))

    def test_replay_uses_no_float_proposal_or_generator(self):
        source = spec("5/4", [["-1/2", "0"], ["1/2", "0"]])
        certificate = verify(source)["certificate"]
        with patch.object(disk, "verify", side_effect=AssertionError("generator invoked")), \
                patch.object(core.math, "sqrt", side_effect=AssertionError("float proposal invoked")):
            self.assertTrue(check_certificate(source, certificate))

    def test_original_frozen_core_certificate_is_replayed_before_wrapping(self):
        source = spec()
        frozen = core.compute({**source, "kind": "unit_disk_cover"})
        with patch.object(core.math, "sqrt", side_effect=AssertionError("float proposal invoked")):
            result = disk.from_core_certificate(source, frozen)
        self.assertTrue(disk.check_certificate(source, result["certificate"]))
        frozen["input_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            disk.from_core_certificate(source, frozen)

    def test_missing_extra_and_changed_boundary_rows_are_rejected(self):
        source = spec("5/4", [["-1/2", "0"], ["1/2", "0"]])
        original = disk.verify(source)["certificate"]
        for mutation in ("missing", "extra", "identity", "owner", "bool", "float"):
            with self.subTest(mutation=mutation):
                changed = deepcopy(original)
                rows = changed["core_certificate"]["boundary_checks"]
                if mutation == "missing":
                    rows.pop()
                elif mutation == "extra":
                    rows.append(rows[0])
                elif mutation == "identity":
                    rows[0][0] = "sample"
                else:
                    rows[0][-1] = {"owner": 999, "bool": False, "float": 0.0}[mutation]
                self.assertFalse(disk.check_certificate(source, changed))

    def test_interior_vertices_and_root_bindings_cannot_be_rewritten(self):
        source = spec("1", [["1", "0"], ["0", "1"], ["-1", "0"], ["0", "-1"]])
        original = disk.verify(source)["certificate"]
        for key in ("interior_voronoi_vertices", "input_sha256", "checker_sha256", "semantics"):
            with self.subTest(key=key):
                changed = deepcopy(original)
                inner = changed["core_certificate"]
                inner[key] = [] if key == "interior_voronoi_vertices" else "forged"
                self.assertFalse(disk.check_certificate(source, changed))

    def test_adapter_bindings_and_claim_scope_cannot_be_rewritten(self):
        source = spec()
        original = disk.verify(source)["certificate"]
        for key, value in (("version", True), ("spec_sha256", "0" * 64),
                           ("checker_sha256", "0" * 64), ("method", "sample_grid"),
                           ("semantics", "global_optimality"), ("verdict", "FAIL"),
                           ("backend", "lean4"), ("optimality", "PASS")):
            with self.subTest(key=key):
                changed = {**original, key: value}
                self.assertFalse(disk.check_certificate(source, changed))

    def test_invalid_inputs_nonfinite_values_and_resource_bounds_fail_closed(self):
        invalid = [None, [], {**spec(), "schema": True}, {**spec(), "optimality": "PASS"},
                   {**spec(), "kind": "unit_disk_optimum"}, {**spec(), "centers": []},
                   {**spec(), "centers": [["0", "0"]] * 257},
                   {**spec(), "centers": [["9", "0"]]},
                   {**spec(), "centers": [[True, "0"]]},
                   {**spec(), "centers": [[float("nan"), "0"]]},
                   {**spec(), "centers": [[float("inf"), "0"]]},
                   spec("NaN"), spec("0/0"), spec("1e99999999"), spec("1e-200"),
                   spec("1" * 161), spec("65"), spec("-1"), spec(False), spec("0")]
        for source in invalid:
            with self.subTest(source=str(source)[:100]):
                self.assertEqual(disk.verify(source)["status"], "UNKNOWN")

    def test_deep_or_oversized_certificate_is_rejected_without_recursion(self):
        original = disk.verify(spec())["certificate"]
        nested = 0
        for _ in range(34):
            nested = [nested]
        for value in (nested, "a" * (disk.MAX_CERTIFICATE_BYTES + 1)):
            changed = {**original, "core_certificate": value}
            self.assertFalse(disk.check_certificate(spec(), changed))

    def test_verifier_identity_binds_the_byte_preserved_core(self):
        original = verifier_id()
        read = Path.read_bytes
        with patch.object(Path, "read_bytes", lambda path: b"changed core" if path.name ==
                          "rds_unit_disk_voronoi_core.py" else read(path)):
            self.assertNotEqual(verifier_id(), original)

    def test_existing_framework_rejects_forged_generator_pass(self):
        fake = {"status": "PASS", "certificate": {"verdict": "PASS"}}
        with patch.object(disk, "verify", return_value=fake):
            self.assertEqual(verify(spec())["status"], "UNKNOWN")

    def test_rational_tactic_and_statement_kind_preserve_existing_quadtree(self):
        new = LeanFormalEngine().verify(spec(), ["rational"])
        old = LeanFormalEngine().verify({**spec("2"), "kind": "unit_disk_cover"}, ["rational"])
        self.assertEqual(new["status"], "PASS", new)
        self.assertEqual(old["status"], "PASS", old)
        self.assertEqual(new["certificate"]["proof"]["rule"], disk.RULE)
        self.assertTrue(check_certificate(spec(), new["certificate"]))

    def test_cli_generation_replay_and_duplicate_key_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source, proof, output = (folder / name for name in ("spec.json", "proof.json", "out.json"))
            source.write_text(json.dumps(spec()), encoding="utf-8")
            command = [sys.executable, "-B", str(ROOT / "scripts/rds_rational_voronoi_verify.py"),
                       "--spec", str(source)]
            result = subprocess.run(command + ["--output", str(proof)], capture_output=True, timeout=10)
            replay = subprocess.run(command + ["--output", str(output), "--certificate", str(proof)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(replay.returncode, 0, replay.stderr)
            source.write_text('{"schema":1,"schema":1}', encoding="utf-8")
            failed = subprocess.run(command + ["--output", str(output)], capture_output=True, timeout=10)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("Duplicate", json.loads(output.read_text())["reason"])


if __name__ == "__main__":
    unittest.main()

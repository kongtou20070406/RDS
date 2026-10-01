"""Whole-domain coverage and fail-closed replay, including a 100-center cover."""
import copy
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
import rds_disk_cover_verify as disk
from rds_verify import LeanFormalEngine, check_certificate, verify
from rds_verify_types import digest


def spec(radius_squared="2"):
    return {"schema": 1, "kind": "unit_disk_cover", "centers": [["0", "0"]],
            "radius_squared": radius_squared}


class DiskCoverTests(unittest.TestCase):
    def test_closed_square_corners_give_whole_disk_including_boundary(self):
        result = disk.verify(spec())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["certificate"]["leaves"], [["", 0]])
        self.assertTrue(disk.check_certificate(spec(), result["certificate"]))
        self.assertIn("no_global_optimality", result["semantics"])

    def test_exact_n1_and_n2_with_equal_boundary_radius(self):
        for centers in ([["0", "0"]], [["0", "0"], ["0", "0"]]):
            source = {**spec("1"), "centers": centers}
            result = disk.verify(source, max_depth=0)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["certificate"]["method"], "single_disk_unit_disk_containment")
            self.assertTrue(disk.check_certificate(source, result["certificate"]))

    def test_exact_n4_corner_cover_and_too_small_radius(self):
        centers = [[x, y] for x in ("-1/2", "1/2") for y in ("-1/2", "1/2")]
        source = {**spec("1/2"), "centers": centers}
        result = disk.verify(source)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["certificate"]["leaves"]), 4)
        smaller = {**source, "radius_squared": "49/100"}
        rebound = {**result["certificate"], "spec_sha256": digest(smaller)}
        self.assertFalse(disk.check_certificate(smaller, rebound))
        self.assertEqual(disk.verify(smaller, max_depth=2)["status"], "UNKNOWN")

    def test_shifted_single_disk_containment_uses_exact_boundary_inequality(self):
        source = {**spec("9/4"), "centers": [["1/2", "0"]]}
        result = disk.verify(source, max_depth=0)
        self.assertEqual(result["status"], "PASS")
        smaller = {**source, "radius_squared": "224/100"}
        certificate = {**result["certificate"], "spec_sha256": digest(smaller)}
        self.assertFalse(disk.check_certificate(smaller, certificate))

    def test_refined_full_partition_uses_strict_outside_leaves(self):
        source = {**spec("107/100"), "centers": [["-1/4", "0"], ["1/4", "0"]]}
        result = disk.verify(source)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(any(cover is None for _, cover in result["certificate"]["leaves"]))
        self.assertTrue(disk.check_certificate(source, result["certificate"]))
        self.assertFalse(disk._strictly_outside((Fraction(1), Fraction(2), Fraction(0), Fraction(1))))

    def test_one_hundred_rational_centers_cover_whole_disk(self):
        grid = [[str(Fraction(2 * i - 9, 10)), str(Fraction(2 * j - 9, 10))]
                for i in range(10) for j in range(10)]
        source = {**spec("21/1000"), "centers": grid}
        result = disk.verify(source)
        self.assertEqual(result["status"], "PASS")
        self.assertGreater(len(result["certificate"]["leaves"]), 100)
        self.assertTrue(disk.check_certificate(source, result["certificate"]))

    def test_coverage_proof_replay_calls_no_generator(self):
        certificate = disk.verify(spec())["certificate"]
        with patch.object(disk, "verify", side_effect=AssertionError("search during replay")):
            self.assertTrue(disk.check_certificate(spec(), certificate))

    def test_missing_duplicate_overlap_and_invalid_path_rejected(self):
        source = spec("5/4")
        original = disk.verify(source)["certificate"]
        mutations = [original["leaves"][:-1], original["leaves"] + [original["leaves"][0]],
                     original["leaves"] + [["", 0]], [["4", 0]], [["0" * 33, 0]], []]
        for leaves in mutations:
            with self.subTest(leaves=str(leaves)[:60]):
                changed = {**original, "leaves": leaves}
                self.assertFalse(disk.check_certificate(source, changed))

    def test_disjoint_but_incomplete_tree_is_rejected(self):
        certificate = disk.verify(spec())["certificate"]
        certificate["leaves"] = [["0", 0], ["1", 0], ["2", 0]]
        self.assertFalse(disk.check_certificate(spec(), certificate))

    def test_false_outside_leaf_cannot_remove_unit_disk_points(self):
        certificate = disk.verify(spec())["certificate"]
        certificate["leaves"] = [[str(i), None if i == 0 else 0] for i in range(4)]
        self.assertFalse(disk.check_certificate(spec(), certificate))

    def test_invalid_center_index_and_boolean_rejected(self):
        original = disk.verify(spec())["certificate"]
        for index in (-1, 1, True, "0", 0.0):
            certificate = {**original, "leaves": [["", index]]}
            self.assertFalse(disk.check_certificate(spec(), certificate))

    def test_sample_only_radius_is_not_promoted_to_coverage(self):
        source = spec("1/100")
        certificate = disk.verify(spec())["certificate"]
        certificate["spec_sha256"] = digest(source)
        self.assertFalse(disk.check_certificate(source, certificate))

    def test_binding_and_semantics_tampering_rejected(self):
        original = disk.verify(spec())["certificate"]
        for key, value in (("version", True), ("checker_sha256", "0" * 64),
                           ("spec_sha256", "0" * 64), ("verdict", "FAIL"),
                           ("method", "point_samples"), ("semantics", "global_optimum")):
            changed = {**original, key: value}
            self.assertFalse(disk.check_certificate(spec(), changed))
        changed = {**original, "global_optimality": "PASS"}
        self.assertFalse(disk.check_certificate(spec(), changed))

    def test_changed_centers_and_radius_are_not_covered_by_old_proof(self):
        certificate = disk.verify(spec())["certificate"]
        for source in ({**spec(), "centers": [["10", "0"]]}, spec("1/100")):
            self.assertFalse(disk.check_certificate(source, certificate))
            rebound = {**certificate, "spec_sha256": digest(source)}
            self.assertFalse(disk.check_certificate(source, rebound))

    def test_malformed_or_optimality_statements_rejected(self):
        originals = [{**spec(), "kind": "unit_disk_optimum"}, {**spec(), "schema": True},
                     {**spec(), "optimality": True}, {**spec(), "centers": []},
                     {**spec(), "centers": [[0.0, "0"]]}, {**spec(), "radius_squared": 2},
                     spec("0"), spec("-1"), spec("NaN"), spec("1e9999")]
        for source in originals:
            with self.subTest(source=source):
                self.assertEqual(verify(source)["status"], "UNKNOWN")

    def test_search_limit_is_unknown_and_never_refutes_coverage(self):
        source = {**spec("1/2"), "centers": [[x, y] for x in ("-1/2", "1/2")
                                             for y in ("-1/2", "1/2")]}
        result = disk.verify(source, max_depth=0)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertNotIn("certificate", result)
        result = disk.verify(source, max_leaves=1)
        self.assertEqual(result["status"], "UNKNOWN")

    def test_extended_depth_and_malformed_search_bounds(self):
        self.assertEqual(disk.verify(spec(), max_depth=32)["status"], "PASS")
        for kwargs in ({"max_depth": 33}, {"max_depth": -1}, {"max_depth": True},
                       {"max_leaves": 24001}, {"max_leaves": 0}, {"max_leaves": True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    disk.verify(spec(), **kwargs)

    def test_existing_registry_and_rational_tactic_replay(self):
        result = LeanFormalEngine().verify(spec(), ["rational"])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["assurance"], "CERTIFICATE_CHECKED")
        self.assertTrue(check_certificate(spec(), result["certificate"]))
        with patch.object(disk, "verify", side_effect=AssertionError("search during replay")):
            self.assertTrue(check_certificate(spec(), result["certificate"]))

    def test_forged_generator_success_rejected_by_existing_framework(self):
        fake = {"status": "PASS", "certificate": {"verdict": "PASS", "leaves": [["", 0]]}}
        with patch.object(disk, "verify", return_value=fake):
            self.assertEqual(verify(spec())["status"], "UNKNOWN")

    def test_cli_generation_and_independent_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source, proof, replay = (folder / name for name in ("spec.json", "proof.json", "replay.json"))
            source.write_text(json.dumps(spec()), encoding="utf-8")
            command = [sys.executable, "-B", str(ROOT / "scripts/rds_disk_cover_verify.py"),
                       "--spec", str(source)]
            generated = subprocess.run(command + ["--output", str(proof)], capture_output=True, text=True, timeout=10)
            checked = subprocess.run(command + ["--output", str(replay), "--certificate", str(proof)],
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(json.loads(replay.read_text())["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

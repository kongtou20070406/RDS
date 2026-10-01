"""Conditional theorem audit cannot certify independence or experimental use."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark.run import Project
import rds_cli as cli
import rds_probe as probe
import rds_lean_verify as lean
import rds_statistical_verify as stats
import rds_verify as engine
from rds_probe import declarative_probe

SPEC = {"schema": 1, "kind": "statistical_obligation", "theorem": "hoeffding"}
CHECKED = {"lean_version": "Lean (version 4.33.1, test)", "lean_executable_sha256": "a" * 64,
           "library": {"files": {"lean-toolchain": "b" * 64}, "mathlib_revision": stats.MATHLIB_REV},
           "axioms": ["Classical.choice", "Quot.sound", "propext"], "stdout": "unused"}


def built_library():
    try:
        lean._executable()
        for module, _, _ in stats.THEOREMS.values():
            stats._library(module)
        return True
    except (ValueError, OSError):
        return False


class StatisticalObligationTests(unittest.TestCase):
    def test_registered_conditional_templates_keep_application_unknown(self):
        for theorem in stats.THEOREMS:
            spec = {**SPEC, "theorem": theorem}
            with mock.patch.object(stats, "_native_check", return_value=CHECKED):
                result = declarative_probe({"kind": "declarative", "statement": spec})
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(result["assurance"], "LEAN_KERNEL_CHECKED")
                self.assertTrue(result["conditional_statement"])
                self.assertEqual(result["application_status"], "UNKNOWN")
                self.assertIn("empirical_model_correspondence", result["assumptions_required"])
                self.assertTrue(engine.check_certificate(spec, result["certificate"]))

    def test_module_conjunction_cannot_launder_conditional_assumptions(self):
        spec = {"schema": 1, "kind": "theorem_module", "definitions": {}, "theorems": [
            {"name": "bound", "statement": SPEC, "by": {"rule": "lean.statistical_obligation"}},
            {"name": "joint", "statement": {"kind": "all", "of": ["bound"]},
             "by": {"rule": "logic.and_intro", "premises": ["bound"]}},
        ]}
        with mock.patch.object(stats, "_native_check", return_value=CHECKED):
            result = engine.verify(spec)
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["application_status"], "UNKNOWN")
            self.assertIn("finite_independent_family", result["assumptions_required"])
            replay = engine.checked_result(spec, result["certificate"])
            self.assertEqual(replay["application_status"], "UNKNOWN")
            forged = copy.deepcopy(result["certificate"])
            forged["proof"]["theorems"]["bound"]["certificate"].pop("application_status")
            self.assertFalse(engine.check_certificate(spec, forged))
        with mock.patch.object(stats, "_native_check", side_effect=lean.NoNativeLean("not installed")):
            unknown = engine.verify(spec)
        self.assertEqual(unknown["status"], "UNKNOWN")
        self.assertEqual(unknown["application_status"], "UNKNOWN")
        self.assertIn("finite_independent_family", unknown["assumptions_required"])

    def test_source_tactics_parameters_and_self_asserted_assumptions_are_rejected(self):
        variants = [{**SPEC, "source": "axiom fake : False"}, {**SPEC, "tactic": "native_decide"},
                    {**SPEC, "parameters": {"n": 10}}, {**SPEC, "independent": True},
                    {**SPEC, "assumptions": {"independent": {"verified": True, "source": "my CSV"}}},
                    {**SPEC, "theorem": "mcdiarmid"}, {**SPEC, "schema": True}]
        with mock.patch.object(stats, "_native_check") as native:
            for spec in variants:
                result = stats.verify(spec)
                self.assertEqual(result["status"], "UNKNOWN", result)
                self.assertIsNone(result["certificate"])
        native.assert_not_called()

    def test_forged_library_compiler_axioms_or_application_status_do_not_replay(self):
        with mock.patch.object(stats, "_native_check", return_value=CHECKED):
            certificate = stats.verify(SPEC)["certificate"]
            for field, value in (("library_sha256", "0" * 64), ("lean_executable_sha256", "0" * 64),
                                 ("axioms", ["sorryAx"]), ("application_status", "PASS"),
                                 ("conditional_statement", False), ("source", "axiom fake : False"),
                                 ("library", {"files": {}}), ("schema", True), ("version", True),
                                 ("conditional_statement", 1)):
                forged = copy.deepcopy(certificate)
                forged[field] = value
                self.assertFalse(stats.check_certificate(SPEC, forged), field)
            self.assertFalse(stats.check_certificate({**SPEC, "theorem": "ville"}, certificate))

    def test_axiom_audit_accepts_only_mathlib_foundations_and_no_extra_output(self):
        self.assertEqual(stats._axioms(lean.AXIOM_AUDIT + "\n"), [])
        self.assertEqual(stats._axioms("'RDS.obligation' depends on axioms: [propext, Classical.choice, Quot.sound]\n"),
                         ["Classical.choice", "Quot.sound", "propext"])
        for output in ("", "compiled", "'RDS.obligation' depends on axioms: [sorryAx]",
                       "'RDS.obligation' depends on axioms: [Custom.fake]",
                       lean.AXIOM_AUDIT + "\nwarning: sorry", "'RDS.obligation' depends on axioms: [propext, propext]"):
            with self.assertRaises(ValueError):
                stats._axioms(output)

    def test_missing_native_environment_has_no_statistical_python_certificate(self):
        with mock.patch.object(stats, "_native_check", side_effect=lean.NoNativeLean("not installed")):
            result = engine.verify(SPEC)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["assurance"], "NONE")
        self.assertEqual(result["application_status"], "UNKNOWN")
        self.assertNotIn("certificate", result)

    def test_changed_library_binding_invalidates_prior_certificate(self):
        with mock.patch.object(stats, "_native_check", return_value=CHECKED):
            certificate = stats.verify(SPEC)["certificate"]
        changed = copy.deepcopy(CHECKED)
        changed["library"]["files"]["lean-toolchain"] = "0" * 64
        with mock.patch.object(stats, "_native_check", return_value=changed):
            self.assertFalse(stats.check_certificate(SPEC, certificate))

    def test_library_binding_includes_root_source_and_rejects_stale_artifact_or_changed_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("lakefile.lean", "lean-toolchain", "Formal.lean"):
                (root / name).write_text("leanprover/lean4:v4.33.1\n", encoding="utf-8")
            manifest = {"packages": [{"name": "mathlib", "rev": stats.MATHLIB_REV},
                                     {"name": "Cli", "rev": "not-imported"}]}
            (root / "lake-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / ".lake/packages/mathlib/.lake/build/lib/lean").mkdir(parents=True)
            module = stats.THEOREMS["hoeffding"][0]
            source = root / Path(*module.split(".")).with_suffix(".lean")
            source.parent.mkdir(parents=True)
            source.write_text("theorem fixed : True := True.intro\n", encoding="utf-8")
            compiled = root / ".lake/build/lib/lean" / Path(*module.split(".")).with_suffix(".olean")
            compiled.parent.mkdir(parents=True)
            compiled.write_bytes(b"installed compiled artifact")
            os.utime(source, ns=(1, 1))
            with mock.patch.object(lean, "FORMAL_ROOT", root), mock.patch.object(lean.subprocess, "Popen") as process:
                paths, binding, _ = stats._library(module)
                self.assertEqual(len(paths), 2)
                self.assertTrue(all(path.is_dir() for path in paths))
                process.assert_not_called()
                self.assertIn("Formal.lean", binding["files"])
                self.assertIn("lean-toolchain", binding["files"])
                self.assertIn("lake-manifest.json", binding["files"])
                (root / "Formal.lean").write_text("changed root source", encoding="utf-8")
                self.assertNotEqual(binding, stats._library(module)[1])
                os.utime(source, ns=(compiled.stat().st_mtime_ns + 1000000000, compiled.stat().st_mtime_ns + 1000000000))
                with self.assertRaisesRegex(ValueError, "stale"):
                    stats._library(module)
                os.utime(source, ns=(1, 1))
                manifest["packages"][0]["rev"] = "bad revision"
                (root / "lake-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "pinned revision"):
                    stats._library(module)


class StatisticalApplicationGateTests(unittest.TestCase):
    claim = {"kind": "declarative", "statement": SPEC}
    source = "def control(x): return x\ndef treatment(x): return 2*x\n"

    def project(self):
        project = Project().init(formal=self.claim)
        self.addCleanup(project.close)
        return project, cli.RDSState(project.root)

    def args(self, project, name="P1"):
        path = project.root / (name + ".json")
        path.write_text(json.dumps(project.plan(name)), encoding="utf-8")
        return argparse.Namespace(spec=str(path), id=name)

    def legacy_plan(self):
        project, state = self.project()
        with mock.patch.object(stats, "_native_check", return_value=CHECKED):
            legacy = declarative_probe(self.claim)
        legacy.pop("application_status")
        with mock.patch.object(cli, "formal_gate", return_value=legacy):
            binding = cli.cmd_plan(self.args(project), state)["binding"]
        return project, state, binding

    def test_query_remains_conditional_but_admission_and_execute_block_before_samples(self):
        with mock.patch.object(stats, "_native_check", return_value=CHECKED):
            queried = declarative_probe(self.claim)
            self.assertEqual(queried["status"], "PASS")
            self.assertEqual(queried["application_status"], "UNKNOWN")
            admission = probe.admission_probe({"formal": self.claim}, self.source)
            self.assertEqual(admission["status"], "UNKNOWN")
            with mock.patch.object(probe, "read_rows") as samples, mock.patch.object(probe, "evaluate") as evaluate:
                result = probe.execute({"hypothesis": {"formal": self.claim}, "source": self.source,
                                        "admission_probe": queried})
            self.assertEqual(result["probe"]["status"], "UNKNOWN")
            samples.assert_not_called()
            evaluate.assert_not_called()
            broken = copy.deepcopy(queried)
            broken["certificate"]["proof"]["certificate"].pop("application_status")
            with mock.patch.object(probe, "read_rows") as samples, mock.patch.object(probe, "evaluate") as evaluate:
                result = probe.execute({"hypothesis": {"formal": self.claim}, "source": self.source,
                                        "admission_probe": broken})
            self.assertEqual(result["probe"]["status"], "UNKNOWN")
            samples.assert_not_called()
            evaluate.assert_not_called()

    def test_worker_and_plan_transaction_require_closed_application_before_reserving(self):
        project, state = self.project()
        unknown = {"status": "PASS", "application_status": "UNKNOWN"}
        completed = mock.Mock(returncode=0, stdout=json.dumps(unknown).encode("utf-8"))
        with mock.patch.object(cli.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(ValueError, "application assumptions"):
                cli.formal_gate({"formal": self.claim}, self.source)
        with mock.patch.object(cli, "formal_gate", return_value=unknown):
            with self.assertRaisesRegex(ValueError, "application assumptions"):
                cli.cmd_plan(self.args(project), state)
        with state.snapshot() as (_, snapshot):
            self.assertEqual(snapshot["plans"], {})
            self.assertEqual(snapshot["budget"]["reserved"]["runs"], 0)
            with mock.patch.object(cli, "formal_gate", return_value={"status": "PASS"}):
                admitted = cli.validate_plan(project.plan(), snapshot, state)
            admitted["admission_probe"]["application_status"] = "UNKNOWN"
            with self.assertRaisesRegex(ValueError, "application assumptions"):
                cli.validate_plan(project.plan(), snapshot, state, admission=admitted)

    def test_cached_deleted_or_forged_application_field_cannot_reserve_another_plan(self):
        project, state, binding = self.legacy_plan()
        with state.snapshot() as (_, snapshot):
            hypothesis = snapshot["hypotheses"]["H1"]["spec"]
        for value in (None, "PASS"):
            old = copy.deepcopy(binding)
            if value is None:
                old["admission_probe"].pop("application_status", None)
            else:
                old["admission_probe"]["application_status"] = value
            with mock.patch.object(stats, "_native_check", return_value=CHECKED):
                cached = cli.cached_admission({"plans": {"P1": {"binding": old}}}, binding,
                                               hypothesis, self.source)
            self.assertIsNone(cached)
        with mock.patch.object(stats, "_native_check", return_value=CHECKED):
            conditional = declarative_probe(self.claim)
            with mock.patch.object(cli, "formal_gate", return_value=conditional):
                with self.assertRaisesRegex(ValueError, "application assumptions"):
                    cli.cmd_plan(self.args(project, "P2"), state)
        with state.snapshot() as (_, snapshot):
            self.assertEqual(set(snapshot["plans"]), {"P1"})
            self.assertEqual(snapshot["budget"]["reserved"]["runs"], 1)
            self.assertEqual(snapshot["budget"]["spent"]["runs"], 0)

    def test_legacy_reservation_blocks_before_charge_data_access_and_can_be_cancelled(self):
        project, state, _ = self.legacy_plan()
        with state.snapshot() as (_, snapshot):
            before = copy.deepcopy(snapshot)
        with mock.patch.object(stats, "_native_check", return_value=CHECKED), \
                mock.patch.object(cli.subprocess, "run") as runner:
            with self.assertRaisesRegex(ValueError, "application assumptions"):
                cli.cmd_run(argparse.Namespace(id="P1"), state)
        runner.assert_not_called()
        with state.snapshot() as (db, snapshot):
            self.assertEqual(snapshot["budget"], before["budget"])
            self.assertEqual(snapshot["exposures"], before["exposures"])
            self.assertEqual(snapshot["plans"]["P1"]["run_status"], "RESERVED")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], 0)
        self.assertEqual(cli.cmd_cancel(argparse.Namespace(id="P1"), state)["run_status"], "CANCELLED")
        with state.snapshot() as (_, snapshot):
            self.assertEqual(snapshot["budget"]["reserved"]["runs"], 0)
            self.assertEqual(snapshot["budget"]["spent"]["runs"], 0)

    def test_run_replay_allows_a_writer_then_rechecks_binding_and_liveness(self):
        for change in ("binding", "cancel"):
            project, state, _ = self.legacy_plan()

            def concurrent_writer(formal, committed):
                if change == "binding":
                    with state.transaction() as (_, snapshot):
                        snapshot["plans"]["P1"]["binding"]["admission_probe"]["application_status"] = "PASS"
                else:
                    cli.cmd_cancel(argparse.Namespace(id="P1"), state)
                return {"status": "PASS", "application_status": "UNKNOWN"}

            with mock.patch.object(probe, "declarative_probe", side_effect=concurrent_writer):
                if change == "binding":
                    with self.assertRaisesRegex(ValueError, "binding changed"):
                        cli.cmd_run(argparse.Namespace(id="P1"), state)
                else:
                    result = cli.cmd_run(argparse.Namespace(id="P1"), state)
                    self.assertTrue(result["idempotent"])
                    self.assertEqual(result["run_status"], "CANCELLED")
            with state.snapshot() as (_, snapshot):
                self.assertEqual(snapshot["budget"]["spent"]["runs"], 0)
                self.assertEqual(snapshot["exposures"], [])


@unittest.skipUnless(built_library(), "Pinned Formal library artifacts are not built")
class RealStatisticalKernelTests(unittest.TestCase):
    def test_real_library_theorems_and_native_replay(self):
        for theorem in stats.THEOREMS:
            spec = {**SPEC, "theorem": theorem}
            result = stats.verify(spec)
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["application_status"], "UNKNOWN")
            self.assertTrue(stats.check_certificate(spec, result["certificate"]))
            self.assertLessEqual(set(result["certificate"]["axioms"]), stats.ALLOWED_AXIOMS)


if __name__ == "__main__":
    unittest.main()

"""Declarative theorem elaboration and independent certificate replay."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_verify as engine
import rds_dynamics_verify as dynamics


def module():
    return json.loads((ROOT / "examples/formal/theorem_module.json").read_text(encoding="utf-8"))


class DeclarativeTests(unittest.TestCase):
    def test_named_definitions_and_conjunction_have_checked_proofs(self):
        spec = module()
        answer = engine.verify(spec)
        self.assertEqual(answer["status"], "PASS")
        self.assertEqual(answer["theorems"]["joint"]["status"], "PASS")
        with patch.object(dynamics, "verify", side_effect=AssertionError("No proof search in replay")):
            self.assertTrue(engine.check_certificate(spec, answer["certificate"]))

    def test_forward_theorem_and_definition_references_are_elaborated(self):
        spec = module()
        spec["theorems"].reverse()
        spec["definitions"]["alias"] = {"$ref": "map"}
        spec["theorems"][-1]["statement"]["model"] = {"$ref": "alias"}
        self.assertEqual(engine.verify(spec)["status"], "PASS")

    def test_failure_is_propagated_through_exact_conjunction(self):
        spec = module()
        spec["theorems"][1]["statement"]["point"] = ["0", "0"]
        answer = engine.verify(spec)
        self.assertEqual(answer["status"], "FAIL")
        self.assertEqual(answer["theorems"]["joint"]["status"], "FAIL")
        self.assertTrue(engine.check_certificate(spec, answer["certificate"]))

    def test_unknown_obligation_cannot_be_hidden_by_a_proved_theorem(self):
        spec = module()
        spec["theorems"][1]["statement"]["kind"] = "training_converges"
        result = engine.verify(spec)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertNotIn("certificate", result)

    def test_cycles_unbound_names_axioms_and_duplicate_theorems_are_rejected(self):
        mutations = [
            lambda s: s["definitions"].update(loop={"$ref": "loop"}),
            lambda s: s["definitions"].update(missing={"$ref": "absent"}),
            lambda s: s["theorems"].append(copy.deepcopy(s["theorems"][0])),
            lambda s: s["theorems"][2]["statement"].update(of=["joint"]),
            lambda s: s["theorems"][2]["by"].update(premises=["joint"]),
            lambda s: s["theorems"][0]["by"].update(axiom=True),
            lambda s: s["theorems"][0]["by"].update(rule="lean4"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                spec = module()
                mutate(spec)
                self.assertEqual(engine.verify(spec)["status"], "UNKNOWN")

    def test_extra_unused_cyclic_definition_is_rejected(self):
        spec = module()
        spec["definitions"]["a"] = {"$ref": "b"}
        spec["definitions"]["b"] = {"$ref": "a"}
        self.assertEqual(engine.verify(spec)["status"], "UNKNOWN")

    def test_tampered_leaf_and_composition_are_rejected(self):
        spec = module()
        original = engine.verify(spec)["certificate"]
        mutations = [
            lambda c: c.update(verdict="FAIL"),
            lambda c: c.update(verifier_sha256="0" * 64),
            lambda c: c["proof"]["theorems"].pop("stable"),
            lambda c: c["proof"]["theorems"]["stable"]["certificate"].update(induced_norm="0"),
            lambda c: c["proof"]["theorems"]["joint"].update(premises=["fixed"]),
            lambda c: c["proof"]["theorems"]["joint"].update(verdict="FAIL"),
            lambda c: c["proof"]["theorems"]["stable"].update(rule="matrix.fixed_point"),
        ]
        for mutate in mutations:
            certificate = copy.deepcopy(original)
            mutate(certificate)
            self.assertFalse(engine.check_certificate(spec, certificate))

    def test_old_proof_cannot_certify_changed_model_or_claim(self):
        spec = module()
        certificate = engine.verify(spec)["certificate"]
        spec["definitions"]["map"]["bias"][0] = "1"
        # Even rebinding a public hash cannot replace the actual domain proof.
        certificate["spec_sha256"] = engine.digest(spec)
        self.assertFalse(engine.check_certificate(spec, certificate))

    def test_scalar_adapter_keeps_original_singularities(self):
        spec = {"schema": 1, "kind": "scalar_threshold",
                "source": "def control(x): return x/(1+x)\ndef treatment(x): return 2*x/(1+x)\n",
                "formal": {"domain": ["0", "2"], "threshold": "1"}}
        answer = engine.verify(spec)
        self.assertEqual(answer["status"], "PASS")
        self.assertTrue(engine.check_certificate(spec, answer["certificate"]))
        spec["source"] = "def control(x): return 0\ndef treatment(x): return x/x\n"
        self.assertEqual(engine.verify(spec)["status"], "UNKNOWN")

    def test_cli_standalone_verify_replay_and_derived_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, proof = Path(tmp) / "spec.json", Path(tmp) / "proof.json"
            path.write_text(json.dumps(module()), encoding="utf-8")
            prefix = [sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"), "--root", tmp, "formal"]
            run = subprocess.run(prefix + ["verify", "--spec", str(path), "--output", str(proof)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            artifact = json.loads(proof.read_text(encoding="utf-8"))
            artifact["status"] = "FAIL"  # top-level user metadata has no authority
            proof.write_text(json.dumps(artifact), encoding="utf-8")
            replay = subprocess.run(prefix + ["check", "--spec", str(path), "--certificate", str(proof)], capture_output=True)
            self.assertEqual(replay.returncode, 0, replay.stderr.decode())
            self.assertEqual(json.loads(replay.stdout)["status"], "PASS")
            artifact["certificate"]["verdict"] = "FAIL"
            proof.write_text(json.dumps(artifact), encoding="utf-8")
            replay = subprocess.run(prefix + ["check", "--spec", str(path), "--certificate", str(proof)], capture_output=True)
            self.assertEqual(replay.returncode, 2)
            self.assertFalse((Path(tmp) / ".rds/state.sqlite3").exists())

    def test_declared_rule_registry_is_explicit_and_cannot_load_commands(self):
        known = {r["name"] for r in engine.rules()}
        self.assertIn("tensor.exact_identity", known)
        self.assertIn("network.interval_margin", known)
        spec = module()
        spec["theorems"][0]["by"]["rule"] = "os.system"
        self.assertEqual(engine.verify(spec)["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

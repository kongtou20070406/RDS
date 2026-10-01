"""Real bounded CPU acceptance, not a scientific-policy benchmark.

Run with --workspace NEW_EMPTY_DIRECTORY to retain the original evidence.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_advisor import RDSAdvisor
from rds_artifacts import ingest_manifest
from rds_checkpoints import restore_checkpoint, save_checkpoint
from rds_meta import reflect_from_state
from rds_probe import declarative_probe
from rds_project import ProjectStore, digest, file_sha


CPU_SOURCE = '''import json, pathlib, sys
mode, output = sys.argv[1:]
config = json.loads(pathlib.Path("config.json").read_text())
data = json.loads(pathlib.Path("data.json").read_text())
w = float(data[mode])
alpha = 0.0 if mode == "mismatch" else config["alpha"]
rows = []
for step in range(config["steps"]):
    gradient = 2.0 * (w - 1.0)
    updated = w - alpha * gradient
    expected = 0.5 * w + 0.5
    row = {"step": step + 1, "weight_before": w, "loss_before": (w-1)**2,
           "gradient": gradient, "actual_alpha": alpha, "weight_after": updated,
           "expected_weight_after": expected, "loss_after": (updated-1)**2,
           "update_matches": updated == expected}
    rows.append(row)
    print(json.dumps(row), flush=True)
    w = updated
    if not row["update_matches"]:
        break
result = {"rows": rows, "initial_loss": rows[0]["loss_before"],
          "last_loss": rows[-1]["loss_after"],
          "update_matches": all(row["update_matches"] for row in rows)}
path = pathlib.Path(output)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(result), encoding="utf-8")
sys.exit(0 if result["update_matches"] else 3)
'''


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def obligation(native=False, slope="1/2"):
    model = {"matrix": [[slope]], "bias": ["1/2"]}
    if not native:
        statement = {"schema": 1, "kind": "affine_dynamics", "model": model,
                     "threshold": "1", "point": ["1"]}
    else:
        statement = {"schema": 1, "kind": "theorem_module", "definitions": {"map": model},
                     "theorems": [
            {"name": "stable", "statement": {"schema": 1, "kind": "affine_contraction",
                "model": {"$ref": "map"}, "threshold": "1"}, "by": {"rule": "matrix.infinity_contraction"}},
            {"name": "fixed", "statement": {"schema": 1, "kind": "affine_fixed_point",
                "model": {"$ref": "map"}, "point": ["1"]}, "by": {"rule": "matrix.fixed_point"}},
            {"name": "native", "statement": {"schema": 1, "kind": "lean_obligation",
                "relation": "lt", "left": "1/2", "right": "1"}, "by": {"rule": "lean.rational_relation"}},
            {"name": "joint", "statement": {"kind": "all", "of": ["stable", "fixed", "native"]},
                "by": {"rule": "logic.and_intro", "premises": ["stable", "fixed", "native"]}}]}
    return {"kind": "declarative", "statement": statement}


def prepare(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "cpu.py").write_text(CPU_SOURCE, encoding="utf-8")
    write(root / "config.json", {"alpha": 0.25, "steps": 20})
    write(root / "data.json", {"normal": 0, "optimal": 1, "mismatch": 0})
    write(root / "evaluator.json", {"loss": "(w-1)^2", "update": "w/2+1/2",
                                    "mismatch_policy": "retain first violation and exit 3"})
    bindings = [{"role": role, "path": path, "sha256": file_sha(root / path)}
                for role, path in (("code", "cpu.py"), ("config", "config.json"),
                                   ("data", "data.json"), ("evaluator", "evaluator.json"))]
    protocol = {role + "_sha256": ProjectStore._role_sha({"bindings": bindings}, role)
                for role in ("code", "config", "data")}
    protocol.update(data_split="scalar-acceptance-only", init="data.json mode", seed="not-applicable",
                    checkpoint="none", schedule="at most 20 updates", sample_work={"steps": 20},
                    numeric_protocol="Python binary64; exact binary fractions in this case",
                    metric={"definition": "(w-1)^2", "reduction": "single scalar"})
    write(root / "protocol.json", protocol)
    bindings.append({"role": "protocol", "path": "protocol.json", "sha256": file_sha(root / "protocol.json")})
    contract = {"schema": 1, "bindings": bindings, "output_roots": ["out"],
                "allowed_commands": [[sys.executable, "-B", "cpu.py", mode, "out/" + mode + ".json"]
                                     for mode in ("normal", "optimal", "mismatch")],
                "budget": {"wall_seconds": 30, "cpu_seconds": 5, "gpu_seconds": 0}}
    write(root / "contract.json", contract)
    store = ProjectStore(root)
    store.initialize(contract)
    return store, protocol


def manifest(root, mode):
    return {"schema": 1, "id": "quadratic-" + mode, "arm": "tool", "control_id": None,
            "protocol": {"path": "protocol.json", "sha256": file_sha(root / "protocol.json")},
            "argv": [sys.executable, "-B", "cpu.py", mode, "out/" + mode + ".json"],
            "outpaths": ["out/" + mode + ".json"], "timeout_seconds": 5,
            "resource_estimates": {"wall_seconds": 5, "cpu_seconds": 1, "gpu_seconds": 0}}


def search(advisor, store, context, graph):
    state = store.snapshot()
    state["advisor_context"] = context
    return next(row["search"] for row in advisor.recommend_next_directions(state, graph)
                if row.get("type") == "EXECUTABLE_DIRECTION_SEARCH")


def retain_probe(root, store, protocol, mode, formal):
    advisor = RDSAdvisor(root)
    result = advisor.execute_theory_probe(manifest(root, mode), formal)
    write(root / "out" / (mode + "-gate.json"), result)
    receipt = result["receipt"]
    if receipt is None:
        raise ValueError("Case prerequisite is unproved: " + str(result["formal_gate"]))
    observation = json.loads((root / "out" / (mode + ".json")).read_text(encoding="utf-8"))
    binding = {"run_id": receipt["run_id"], **protocol}
    import_spec = {"schema": "rds-artifact-manifest-v1", "decision": "choose", "sources": [{
        "id": mode, "kind": "metric", "path": "out/" + mode + ".json",
        "expected_sha256": file_sha(root / "out" / (mode + ".json")), "binding": binding,
        "facts": [{"id": name, "pointer": "/" + name}
                  for name in ("initial_loss", "last_loss", "update_matches")]}]}
    write(root / "out" / (mode + "-import.json"), import_spec)
    imported = ingest_manifest(root / "out" / (mode + "-import.json"), root, [receipt])
    write(root / "out" / (mode + "-facts.json"), imported)
    context = {"decision": {"id": "choose", "goal_revision": "quadratic-v1", "scope": {"mode": mode}},
               "facts": imported["context"]["facts"]}
    action = {"id": "probe", "kind": "BOUNDED_CPU_PROBE", "description": "Inspect this scalar update",
              "target": {"name": "quadratic_update"}, "intervention": {"alpha": "1/4", "mode": mode},
              "competing_explanations": ["declared update implemented", "actual update or starting state differs"],
              "required_observables": ["initial_loss", "last_loss", "update_matches"],
              "outcomes": [{"observation": "gain with matching update", "next_decision": "retain update in this domain"},
                           {"observation": "no gain or mismatched update", "next_decision": "stop repeating and review scope"}]}
    graph = {"nodes": [{"id": "probe", "sources": ["evaluator.json"],
              "executable": {"decisions": ["choose"], "preconditions": [], "action": action}}], "edges": []}
    previous = search(advisor, store, context, graph)["candidates"][0]
    if not observation["update_matches"]:
        next_action = "inspect-realized-update-before-any-retry"
        diagnostic = advisor.advise_on_rejection("Observed update differs from declared affine model", result["run_spec"])
    elif observation["last_loss"] < observation["initial_loss"]:
        next_action = "retain-update-only-in-tested-scalar-domain"
        diagnostic = advisor.advise_on_loss_dynamics({"loss_trend": "DECREASING", "loss": observation["last_loss"]})
    else:
        next_action = "stop-repeating-already-optimal-initial-state"
        diagnostic = advisor.advise_on_loss_dynamics({"loss_trend": "PLATEAU", "loss": observation["last_loss"]})
    decision = {"question_id": "choose", "goal_revision": "quadratic-v1", "scope": {"mode": mode},
                "candidate": previous, "outcome": "accepted" if mode == "normal" else "rejected",
                "evidence": context["facts"], "previous_decision": "execute at most twenty declared updates",
                "updated_next_action": next_action, "theory": result["formal_gate"],
                "theory_wall_seconds": result["theory_wall_seconds"],
                "source_receipt": {"run_id": receipt["run_id"], "sha256": receipt["sha256"]},
                "diagnostic": diagnostic, "rsi_proposals": reflect_from_state(store.snapshot(), [receipt])}
    saved = save_checkpoint(root, "after-" + mode, store.snapshot(), kind="project", decision=decision)
    before = store.snapshot()
    unchanged = search(advisor, store, context, graph)
    reopened = copy.deepcopy(context)
    reopened["decision"]["scope"] = {"mode": mode, "initial_state_revision": "proposed-v2"}
    review = search(advisor, store, reopened, graph)
    if store.snapshot() != before:
        raise AssertionError("Advice changed operational budget or execution state")
    restoration = restore_checkpoint(root, "after-" + mode, store.snapshot(), kind="project")
    record = {"decision": decision, "checkpoint": saved, "unchanged_advice": unchanged,
              "changed_scope_advice": review, "restoration": restoration}
    write(root / "out" / (mode + "-reflection.json"), record)
    return result, observation, record


def retain_blocked_request(root, store, advisor, name, formal):
    """Reject a redundant verification request, never infer falsity from UNKNOWN."""
    declared = root / "out" / (name + "-declaration.json")
    write(declared, formal)
    context = {"decision": {"id": "choose", "goal_revision": "quadratic-v1", "scope": {"gate_request": name}},
               "facts": {"declaration": {"value": formal, "source": {
                   "path": declared.relative_to(root).as_posix(), "sha256": file_sha(declared), "locator": "/"}}}}
    action = {"id": "check-theory", "kind": "CHECK_FORMAL_OBLIGATION", "description": "Check this declaration before any CPU request",
              "target": {"name": "theory-check-request"}, "operation": "verify-current-declaration",
              "competing_explanations": ["declared property holds", "property fails or remains unproved"],
              "required_observables": ["declaration"],
              "outcomes": [{"observation": "checked applicable PASS", "next_decision": "consider CPU admission"},
                           {"observation": "FAIL or UNKNOWN", "next_decision": "revise premises or collect missing evidence"}]}
    graph = {"nodes": [{"id": "theory", "sources": [declared.relative_to(root).as_posix()],
              "executable": {"decisions": ["choose"], "preconditions": [], "action": action}}], "edges": []}
    candidate = search(advisor, store, context, graph)["candidates"][0]
    before = store.snapshot()
    result = advisor.execute_theory_probe(manifest(root, "normal"), formal)
    if result["receipt"] is not None or store.snapshot() != before:
        raise AssertionError("Unproved candidate consumed empirical budget")
    write(root / "out" / (name + "-check.json"), result)
    decision = {"question_id": "choose", "goal_revision": "quadratic-v1", "scope": {"gate_request": name},
                "candidate": candidate, "outcome": "rejected", "evidence": context["facts"],
                "formal": formal, "result": result, "theory_wall_seconds": result["theory_wall_seconds"],
                "claim_status": "UNPROVED" if result["formal_gate"]["status"] == "UNKNOWN" else "CHECKED_DECLARATION_FAIL",
                "outcome_reason": "Reject repeating this check without changed premises; UNKNOWN is not a refutation",
                "next_action": "review-declaration-or-missing-premises-before-rechecking"}
    checkpoint = save_checkpoint(root, "blocked-" + name, before, kind="project", decision=decision)
    unchanged = search(advisor, store, context, graph)
    # This is the next selection pass, reading the same SQLite checkpoint. Only
    # selected verification requests can invoke the costly checker again.
    repeated_checks = [advisor.execute_theory_probe(manifest(root, "normal"), formal)
                       for _ in unchanged["candidates"]]
    if repeated_checks or store.snapshot() != before:
        raise AssertionError("Unchanged rejected verification request was repeated")
    revised = root / "out" / (name + "-revised-declaration.json")
    write(revised, obligation())
    changed = copy.deepcopy(context)
    changed["facts"]["declaration"] = {"value": obligation(), "source": {
        "path": revised.relative_to(root).as_posix(), "sha256": file_sha(revised), "locator": "/"}}
    reopened = search(advisor, store, changed, graph)
    record = {"result": result, "checkpoint": checkpoint, "decision": decision,
              "unchanged_advice": unchanged, "recheck_count": len(repeated_checks),
              "changed_premise_advice": reopened,
              "restoration": restore_checkpoint(root, "blocked-" + name, store.snapshot(), kind="project")}
    write(root / "out" / (name + "-gate-history.json"), record)
    return record


def run_cpu_case(root):
    started = time.monotonic()
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Use a new empty workspace")
    store, protocol = prepare(root)
    advisor = RDSAdvisor(root)
    blocked = []
    for name, formal in (("fail", obligation(slope="-1")),
                         ("unknown", {"kind": "declarative", "statement": {"schema": 1, "kind": "unsupported"}})):
        blocked.append(retain_blocked_request(root, store, advisor, name, formal))
    formal = obligation(native=True)
    write(root / "out/declared-model.json", formal)
    from rds_lean_verify import render_source
    (root / "out/native-bound.lean").write_text(render_source(formal["statement"]["theorems"][2]["statement"]), encoding="utf-8")
    probes = [retain_probe(root, store, protocol, mode, formal) for mode in ("normal", "optimal", "mismatch")]
    summary = {"blocked": [{"status": b["result"]["formal_gate"]["status"], "receipt": None,
                            "checkpoint": b["checkpoint"], "theory_wall_seconds": b["result"]["theory_wall_seconds"],
                            "recheck_count": b["recheck_count"],
                            "changed_premise_review": b["changed_premise_advice"]["candidates"][0]["loop_review"]["kind"]} for b in blocked],
               "probes": [{"run_id": result["receipt"]["run_id"], "run_status": result["receipt"]["run_status"],
                           "formal_status": result["formal_gate"]["status"], "steps": len(obs["rows"]),
                           "initial_loss": obs["initial_loss"], "last_loss": obs["last_loss"],
                           "update_matches": obs["update_matches"],
                           "next_action": reflection["decision"]["updated_next_action"]}
                          for result, obs, reflection in probes],
               "theory_wall_seconds": sum(b["result"]["theory_wall_seconds"] for b in blocked) +
                                      sum(result["theory_wall_seconds"] for result, _, _ in probes),
               "snapshot": store.snapshot(), "scientific_policy_gain": "UNMEASURED",
               "hard_budget_scope": "empirical_subprocess_only",
               "observed_controller_wall_seconds": time.monotonic() - started,
               "controller_hard_budget_enforced": False}
    write(root / "out/summary.json", summary)
    return summary


class TwoStepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rds two step ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store, self.protocol = prepare(self.root)
        self.advisor = RDSAdvisor(self.root)

    def test_unproved_and_self_labelled_candidates_do_not_reserve(self):
        bad = obligation(slope="-1")
        failed = declarative_probe(bad)
        for formal, committed in ((bad, None), (obligation(), {"status": "PASS"}),
                                  (bad, {**failed, "status": "PASS"}),
                                  (obligation(), failed)):
            with self.subTest(formal=formal, committed=committed):
                before = self.store.snapshot()
                result = self.advisor.execute_theory_probe(manifest(self.root, "normal"), formal, committed=committed)
                self.assertNotEqual(result["formal_gate"]["status"], "PASS")
                self.assertIsNone(result["receipt"])
                self.assertEqual(before, self.store.snapshot())

    def test_conditional_library_pass_is_not_application_pass(self):
        # Integration stub for the coordinated backend contract, not proof evidence.
        with patch("rds_probe.declarative_probe", return_value={"status": "PASS", "application_status": "UNKNOWN"}):
            before = self.store.snapshot()
            result = self.advisor.execute_theory_probe(manifest(self.root, "normal"), obligation())
        self.assertIsNone(result["receipt"])
        self.assertEqual(before, self.store.snapshot())

    def test_failed_and_unknown_checkpoints_are_consumed_before_rechecking(self):
        for name, formal in (("fail", obligation(slope="-1")),
                             ("unknown", {"kind": "declarative", "statement": {"schema": 1, "kind": "unsupported"}})):
            with self.subTest(name=name), patch.object(self.advisor, "execute_theory_probe",
                                                      wraps=self.advisor.execute_theory_probe) as checked:
                record = retain_blocked_request(self.root, self.store, self.advisor, name, formal)
                self.assertEqual(checked.call_count, 1)
                self.assertEqual(record["unchanged_advice"]["candidates"], [])
                self.assertEqual(record["changed_premise_advice"]["candidates"][0]["loop_review"]["kind"], "REOPEN_REVIEW")
                self.assertEqual(record["restoration"]["status"], "RESUMABLE_HANDOFF")
                if name == "unknown":
                    self.assertEqual(record["decision"]["claim_status"], "UNPROVED")

    def test_real_twenty_updates_receipt_and_no_duplicate_execution(self):
        result, obs, reflection = retain_probe(self.root, self.store, self.protocol, "normal", obligation())
        receipt = result["receipt"]
        self.assertEqual(receipt["run_status"], "SUCCEEDED")
        self.assertEqual(len(obs["rows"]), 20)
        self.assertEqual(obs["initial_loss"], 1)
        self.assertEqual(obs["last_loss"], 2**-40)
        self.assertTrue(all(row["weight_after"] == row["expected_weight_after"] for row in obs["rows"]))
        self.assertEqual(receipt["sha256"], digest({k: v for k, v in receipt.items() if k != "sha256"}))
        for artifact in receipt["artifacts"]:
            self.assertEqual(file_sha(self.root / artifact["path"]), artifact["sha256"])
        self.assertEqual(receipt["assessment"], {"task_gain": "UNKNOWN", "mechanism": "UNKNOWN"})
        before = self.store.snapshot()
        with self.assertRaises(ValueError):
            self.advisor.execute_theory_probe(manifest(self.root, "normal"), obligation())
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(reflection["restoration"]["status"], "RESUMABLE_HANDOFF")

    def test_optimal_start_changes_action_and_prunes_unchanged_choice(self):
        result, obs, reflection = retain_probe(self.root, self.store, self.protocol, "optimal", obligation())
        self.assertEqual(result["receipt"]["run_status"], "SUCCEEDED")
        self.assertEqual(len(obs["rows"]), 20)
        self.assertTrue(all(row["loss_after"] == row["gradient"] == 0 for row in obs["rows"]))
        self.assertEqual(reflection["decision"]["updated_next_action"], "stop-repeating-already-optimal-initial-state")
        self.assertEqual(reflection["unchanged_advice"]["candidates"], [])
        self.assertEqual(reflection["changed_scope_advice"]["candidates"][0]["loop_review"]["kind"], "REOPEN_REVIEW")

    def test_update_violation_stops_and_proposes_only_scoped_rsi_review(self):
        result, obs, reflection = retain_probe(self.root, self.store, self.protocol, "mismatch", obligation())
        self.assertEqual(result["formal_gate"]["status"], "PASS")
        self.assertEqual(result["receipt"]["run_status"], "FAILED")
        self.assertEqual(len(obs["rows"]), 1)
        self.assertFalse(obs["update_matches"])
        self.assertEqual(obs["rows"][0]["actual_alpha"], 0)
        self.assertEqual(reflection["unchanged_advice"]["candidates"], [])
        proposals = reflection["decision"]["rsi_proposals"]
        self.assertTrue(proposals)
        self.assertTrue(all(p["candidate_only"] and not p["auto_apply"] for p in proposals))
        budget = self.store.snapshot()["budget"]
        self.assertEqual(budget["wall_seconds"]["reserved"], 0)
        self.assertGreater(budget["wall_seconds"]["spent_measured"], 0)
        self.assertEqual(budget["cpu_seconds"]["charged_estimate"], 1)

    @unittest.skipUnless(os.environ.get("RDS_LEAN_EXECUTABLE"), "Native Lean executable not configured")
    def test_native_leaf_and_python_domain_certificate_share_real_cpu_case(self):
        result, obs, _ = retain_probe(self.root, self.store, self.protocol, "normal", obligation(native=True))
        self.assertEqual(result["formal_gate"]["theorems"]["native"]["status"], "PASS")
        self.assertEqual(result["formal_gate"]["assurance"], "CERTIFICATE_CHECKED")
        self.assertEqual(result["formal_gate"]["certificate"]["proof"]["theorems"]["native"]["rule"], "lean.rational_relation")
        self.assertEqual(len(obs["rows"]), 20)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--workspace":
        print(json.dumps(run_cpu_case(Path(sys.argv[2])), ensure_ascii=False, indent=2))
    else:
        unittest.main()

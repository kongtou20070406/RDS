"""Contract, execution, routing and evidence regressions for the local kernel."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark.run import Project, C7_CONTROL, C7_FORMAL, ORDINARY
from rds_probe import admission_probe, execute, parse_source
from rds_obelisk import query_source, history_command


class KernelTests(unittest.TestCase):
    def project(self, **kwargs):
        project = Project(**kwargs)
        self.addCleanup(project.close)
        return project

    def test_ordinary_path_without_solver(self):
        import builtins
        real_import = builtins.__import__
        def no_sympy(name, *args, **kwargs):
            if name == "sympy" or name.startswith("sympy."):
                raise ImportError("solver intentionally absent")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=no_sympy):
            self.assertEqual(admission_probe({}, ORDINARY)["assurance"], "AST_ONLY")
            result = execute({"source": ORDINARY, "data": "sample_id,x,y\na,1,2\n", "hypothesis": {}})
            self.assertEqual(result["gain"], "1")
            formal = admission_probe({"formal": C7_FORMAL}, C7_CONTROL + "def treatment(x): return 2*x\n")
            self.assertEqual(formal["status"], "PASS")
            self.assertEqual(formal["assurance"], "CERTIFICATE_CHECKED")

    def test_ordinary_cli_without_site_packages(self):
        project = self.project()
        path = project.root / "contract.json"
        path.write_text(json.dumps(project.contract), encoding="utf-8")
        result = subprocess.run([sys.executable, "-S", "-B", str(ROOT / "scripts/rds_cli.py"),
                                 "--root", str(project.root), "init", "--contract", str(path)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dynamics_never_silently_passes(self):
        project = self.project().init({"kind": "dynamics", "property": "asymptotic stability"})
        error = project.call("gate", "check", spec=project.plan(), flag="--plan", ok=False)
        self.assertIn("UNKNOWN", error)
        self.assertEqual(project.call("status")["budget"]["reserved"]["runs"], 0)

    def test_symbolic_singularity_is_unknown(self):
        source = "def control(x): return (x-1)/(x-1) - 1\ndef treatment(x): return 2*x\n"
        formal = {**C7_FORMAL, "domain": ["0", "2"]}
        result = admission_probe({"formal": formal}, source)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("denominator", result["reason"])

    def test_possible_but_unobserved_crossing_fails(self):
        source = C7_CONTROL + "def treatment(x): return 6*x/(5*(1+x))\n"
        result = execute({"source": source, "data": "sample_id,x,y\na,1,1\n", "hypothesis": {"formal": C7_FORMAL}})
        self.assertEqual(result["probe"]["status"], "FAIL")
        self.assertEqual(result["probe"]["observed_crossings"], [])

    def test_self_certification_rejected(self):
        project = self.project().init()
        self.assertIn("Self-signed", project.call("plan", "create", spec=project.plan(manipulation_verified=True), ok=False))

    def test_source_tamper_and_reinit_rejected(self):
        project = self.project().init()
        project.call("plan", "create", spec=project.plan())
        (project.root / "model.py").write_text(ORDINARY.replace("2*x", "3*x"), encoding="utf-8")
        self.assertIn("Source changed", project.call("run", "execute", "--id", "P1", ok=False))
        self.assertIn("Already initialized", project.call("init", spec=project.contract, flag="--contract", ok=False))

    def test_fresh_confirmation_and_idempotent_decision(self):
        project = self.project().init()
        result = project.run(project.plan(split_id="final", purpose="confirm"))
        self.assertEqual(result["task_gain"], "CONFIRMED")
        self.assertEqual(result["mechanism"], "UNTESTED")
        before = project.call("status")
        project.call("decide", "--run", result["run_id"])
        after = project.call("status")
        self.assertEqual(before["budget"], after["budget"])
        self.assertEqual(before["hypotheses"], after["hypotheses"])

    def test_prior_exposure_and_dataset_alias_rejected(self):
        for mode in ("exposed", "unknown", "alias"):
            with self.subTest(mode=mode):
                project = self.project()
                if mode == "alias":
                    project.contract["splits"]["final"]["path"] = "dev.csv"
                else:
                    project.contract["splits"]["final"]["prior_exposure"] = mode
                project.init()
                error = project.call("plan", "create", spec=project.plan(split_id="final", purpose="confirm"), ok=False)
                self.assertIn("already exposed", error)

    def test_concurrent_budget_reservations(self):
        project = self.project(budget=25000, floor=0).init()
        paths = []
        for pid in ("A", "B"):
            path = project.root / (pid + ".json")
            path.write_text(json.dumps(project.plan(pid, runtime=20000)), encoding="utf-8")
            paths.append(path)
        def reserve(path):
            return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                                   "--root", str(project.root), "plan", "create", "--spec", str(path)],
                                  capture_output=True, timeout=20).returncode
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(reserve, paths))
        self.assertEqual(sorted(codes), [0, 1])
        self.assertEqual(project.call("status")["budget"]["reserved"]["runtime_ms"], 20000)

    def test_ast_cannot_execute_imports_or_calls(self):
        for source in ("import os\n" + ORDINARY,
                       "def control(x): return x\ndef treatment(x): return __import__('os')\n"):
            with self.assertRaises(ValueError):
                parse_source(source)

    def test_failed_run_keeps_charge_and_is_not_refutation(self):
        project = self.project(source="def control(x): return x\ndef treatment(x): return x/(x-10)\n")
        project.contract["claim"] = "失败执行不等于科学反驳"
        project.init()
        project.call("plan", "create", spec=project.plan())
        run = project.call("run", "execute", "--id", "P1")
        self.assertEqual(run["run_status"], "FAILED")
        self.assertIn("not scientific refutation", project.call("decide", "--run", run["run_id"], ok=False))
        state = project.call("status")
        self.assertEqual(state["budget"]["spent"]["runtime_ms"], 10000)
        self.assertEqual(state["budget"]["reserved"]["runtime_ms"], 0)
        self.assertEqual(state["hypotheses"]["H1"]["task_gain"], "UNTESTED")
        self.assertEqual(state["contract"]["claim"], "失败执行不等于科学反驳")

    def test_obelisk_scope_and_failure_are_preserved(self):
        source = query_source("C:\\research\\RDS", 'C7 OR "48h"', 6)
        self.assertIn("project_path = ?", source)
        self.assertIn("sessionId:s.id", source)
        self.assertIn("next_offset", source)
        with self.assertRaises(ValueError):
            query_source("relative/path", "C7")
        with patch("rds_obelisk.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "history has not been checked"):
                history_command(argparse.Namespace(subcommand="query", query="unused.mjs"))

    def test_meta_rule_lifecycle_and_reflection(self):
        """RSI Step 1: Rule validation, atomic application to judgment graph, and failure reflection."""
        from rds_meta import validate_rule, apply_rule
        valid_rule = {
            "id": "test-rsi-rule",
            "scope": "image_restoration",
            "trigger": "repeated spatial filter tuning without residual pathway",
            "correction": "pure spatial linear conv cannot isolate high-frequency non-local phase",
            "alternatives": ["local capacity limitation", "missing non-local representation"],
            "discriminator": "evaluate frequency-domain residual ablation",
            "primary_gate": "paired test PSNR under equal runtime budget",
            "falsifier": "if pure spatial conv achieves >= 0.5dB gain over benchmark, discard rule",
            "sources": ["RDS Synthetic Audit"]
        }
        self.assertEqual(validate_rule(valid_rule)["id"], "test-rsi-rule")

        # Rejection of forbidden unscientific claims
        with self.assertRaisesRegex(ValueError, "forbidden"):
            bad = {**valid_rule, "id": "bad-rule", "correction": "this guaranteed_gain is proven"}
            validate_rule(bad)

        # Apply rule to temporary graph
        project = self.project()
        temp_graph = project.root / "judgment-graph.yaml"
        original_graph = ROOT / "references/judgment-graph.yaml"
        temp_graph.write_text(original_graph.read_text(encoding="utf-8"), encoding="utf-8")

        res = apply_rule(valid_rule, graph_path=str(temp_graph))
        self.assertEqual(res["status"], "APPLIED")
        self.assertEqual(res["action"], "CREATED")

        # Duplicate ID rejection without force
        with self.assertRaisesRegex(ValueError, "already exists"):
            apply_rule(valid_rule, graph_path=str(temp_graph), force=False)

        # Update with force
        updated_rule = {**valid_rule, "scope": "generalized_restoration"}
        res_up = apply_rule(updated_rule, graph_path=str(temp_graph), force=True)
        self.assertEqual(res_up["action"], "UPDATED")

        # CLI list-rules & validate-rule
        rule_path = project.root / "new-rule.json"
        rule_path.write_text(json.dumps(valid_rule), encoding="utf-8")
        val_cli = project.call("meta", "validate-rule", "--rule", str(rule_path))
        self.assertEqual(val_cli["status"], "VALID")
        list_cli = project.call("meta", "list-rules", "--graph", str(temp_graph))
        self.assertTrue(any(n["id"] == "test-rsi-rule" for n in list_cli["nodes"]))

        # Meta reflect from refuted C7 boundary
        c7_crossing = C7_CONTROL + "def treatment(x): return 25*x/(20*(1+x))\n"
        c7_proj = self.project(source=c7_crossing, split="development")
        (c7_proj.root / "dev.csv").write_text("sample_id,x,y\ndev-1,10,1\n", encoding="utf-8")
        c7_proj.contract["splits"]["development"]["prior_exposure"] = "exposed"
        c7_proj.init(formal=C7_FORMAL)
        res_c7 = c7_proj.run(c7_proj.plan())
        self.assertEqual(res_c7["mechanism"], "REFUTED")
        reflection = c7_proj.call("meta", "reflect")
        self.assertGreaterEqual(reflection["proposed_rules_count"], 1)
        self.assertTrue(any("refuted-boundary" in p["id"] for p in reflection["proposals"]))

    def test_stagnation_detection_and_branch_forking(self):
        """RSI Step 2: Consecutive non-useful runs trigger stagnation and orthogonal branching."""
        # Source where treatment is identical to control (gain = 0 <= min_useful_delta)
        flat_source = "def control(x): return x\ndef treatment(x): return x\n"
        project = self.project(source=flat_source, budget=60000, floor=4000)
        project.init()

        # Initial branch status
        status = project.call("branch", "status")
        self.assertEqual(status["active_branch"], "main")
        self.assertEqual(status["stagnation_count"], 0)
        self.assertFalse(status["stagnated"])

        # Run 1: sub-threshold -> stagnation_count = 1
        d1 = project.call("plan", "create", spec=project.plan("P1", runtime=10000))
        r1 = project.call("run", "execute", "--id", "P1")
        dec1 = project.call("decide", "--run", r1["run_id"])
        self.assertEqual(dec1["stagnation"]["stagnation_count"], 1)
        self.assertFalse(dec1["stagnation"]["stagnated"])

        # Run 2: sub-threshold -> stagnation_count = 2
        project.call("plan", "create", spec=project.plan("P2", runtime=10000))
        r2 = project.call("run", "execute", "--id", "P2")
        dec2 = project.call("decide", "--run", r2["run_id"])
        self.assertEqual(dec2["stagnation"]["stagnation_count"], 2)
        self.assertFalse(dec2["stagnation"]["stagnated"])

        # Run 3: sub-threshold -> stagnation_count = 3 -> STAGNATION_DETECTED!
        project.call("plan", "create", spec=project.plan("P3", runtime=10000))
        r3 = project.call("run", "execute", "--id", "P3")
        dec3 = project.call("decide", "--run", r3["run_id"])
        self.assertEqual(dec3["stagnation"]["stagnation_count"], 3)
        self.assertTrue(dec3["stagnation"]["stagnated"])
        self.assertIn("STAGNATION_DETECTED", dec3["stagnation"]["recommendation"])

        # Check branch status reflects stagnation
        b_status = project.call("branch", "status")
        self.assertEqual(b_status["status"], "STAGNATING")
        self.assertTrue(b_status["stagnated"])

        # Fork to orthogonal branch (e.g. frequency-domain)
        fork_spec = {
            "id": "branch-freq-res",
            "parent_id": "main",
            "orthogonal_dimension": "frequency_representation",
            "rationale": "Greedy spatial tuning stagnated; forking to frequency representation",
            "budget_split": {"runtime_ms": 15000, "runs": 1}
        }
        fork_res = project.call("branch", "fork", spec=fork_spec)
        self.assertEqual(fork_res["active_branch"], "branch-freq-res")

        # New branch starts with 0 stagnation count and ACTIVE status
        b_status_forked = project.call("branch", "status")
        self.assertEqual(b_status_forked["active_branch"], "branch-freq-res")
        self.assertEqual(b_status_forked["stagnation_count"], 0)
        self.assertEqual(b_status_forked["status"], "ACTIVE")

        # Switching back and forth works
        project.call("branch", "switch", "--id", "main")
        self.assertEqual(project.call("branch", "status")["active_branch"], "main")
        project.call("branch", "switch", "--id", "branch-freq-res")
        self.assertEqual(project.call("branch", "status")["active_branch"], "branch-freq-res")

    def test_baseline_control_cache_and_reuse(self):
        """Baseline Control Reuse: Once blank baseline is evaluated on a dataset partition, reuse it across treatments."""
        project = self.project(budget=60000, floor=4000)
        project.init()

        # Run Plan 1: First treatment. Baseline is evaluated from scratch.
        p1 = project.plan("P1", runtime=10000)
        project.call("plan", "create", spec=p1)
        r1 = project.call("run", "execute", "--id", "P1")
        self.assertEqual(r1["run_status"], "SUCCEEDED")
        self.assertFalse(r1["control_reused"])

        # Check that baseline was cached in state
        state1 = project.call("status")
        self.assertIn("baseline_cache", state1)
        self.assertEqual(len(state1["baseline_cache"]), 1)
        b_key = list(state1["baseline_cache"].keys())[0]

        # Prepare a second treatment model file with same control AST
        treatment2_source = "def control(x): return x\ndef treatment(x): return 2*x + 1\n"
        (project.root / "model2.py").write_text(treatment2_source, encoding="utf-8")

        # Run Plan 2: Second treatment, same control AST and same dataset split.
        p2 = project.plan("P2", runtime=10000, source="model2.py")
        project.call("plan", "create", spec=p2)
        r2 = project.call("run", "execute", "--id", "P2")
        self.assertEqual(r2["run_status"], "SUCCEEDED")
        self.assertTrue(r2["control_reused"])

        # Receipt integrity check on reused baseline
        dec2 = project.call("decide", "--run", r2["run_id"])
        self.assertIn("assessment", dec2)
        self.assertEqual(dec2["assessment"]["task_gain"], "EXPLORATORY")

    def test_redteam_adversarial_stress(self):
        """Four synthetic scenarios exercise the protocol's rejection paths."""
        from benchmark.redteam.runner import RedTeamRunner
        runner = RedTeamRunner(verbose=False)
        report = runner.run_all()
        self.assertEqual(report["total_attacks"], 4)
        self.assertEqual(report["passed_defenses"], 4)
        self.assertEqual(report["attack_success_rate"], 0.0)
        self.assertEqual(report["defense_rate"], 1.0)
        self.assertEqual(report["epistemic_stability"], "SCENARIOS_PASSED")
        self.assertEqual(report["scope"], "four_synthetic_scalar_scenarios")

    def test_rsi_step3_adversary_and_alignment(self):
        """RSI Step 3: Adversarial mutation fuzzing, alignment evaluation, and auto-repair cycle."""
        project = self.project().init()
        p1 = project.plan("P1", runtime=10000)
        project.call("plan", "create", spec=p1)

        # 1. Fuzzing: Generate adversarial mutants from plan
        fuzz_out = project.call("meta", "fuzz", spec=p1, flag="--plan")
        self.assertGreaterEqual(fuzz_out["mutants_count"], 4)
        mut_types = [m["mutation_intent"] for m in fuzz_out["mutants"]]
        self.assertTrue(any("self-signed" in t for t in mut_types))
        self.assertTrue(any("confirmation" in t for t in mut_types))

        # 2. Alignment evaluation: Reject ungrounded claims
        bad_rule = {
            "id": "rule-bad-certainty", "scope": "test",
            "trigger": "Any neural network training", "correction": "always_succeed with guaranteed_gain",
            "alternatives": ["alt1"], "discriminator": "disc", "primary_gate": "gate", "falsifier": "fals",
            "sources": ["source1"]
        }
        eval_bad = project.call("meta", "evaluate-alignment", spec=bad_rule, flag="--rule")
        self.assertFalse(eval_bad["is_aligned"])
        self.assertTrue("guaranteed_gain" in eval_bad["rejection_reason"] or "banned ungrounded certainty" in eval_bad["rejection_reason"])

        # A schema-valid rule is a proposal, not measured alignment evidence.
        good_rule = {
            "id": "rule-valid-c7-boundary", "scope": "test",
            "trigger": "c7 contraction boundary test",
            "correction": "Require treatment to cross m >= 1 before mechanism promotion",
            "alternatives": ["alt1"], "discriminator": "disc", "primary_gate": "gate", "falsifier": "fals",
            "sources": ["source1"]
        }
        eval_good = project.call("meta", "evaluate-alignment", spec=good_rule, flag="--rule")
        self.assertFalse(eval_good["is_aligned"])
        self.assertTrue(eval_good["lint_passed"])
        self.assertEqual(eval_good["assurance"], "HEURISTIC_ONLY")
        self.assertIsNone(eval_good["precision"])
        self.assertIsNone(eval_good["false_positive_rate"])

        # 3. Auto-repair dry run
        repair_res = project.call("meta", "auto-repair", "--dry-run")
        self.assertIn("status", repair_res)
        self.assertTrue(repair_res["dry_run"])

    def test_advisor_engine(self):
        """Active Programmatic Advisor: Program gives analytical & diagnostic advice to LLM."""
        project = self.project().init()
        # 1. Global strategic advice
        adv_global = project.call("advise")
        self.assertEqual(adv_global["advisor_type"], "STRATEGIC_RESEARCH_ADVICE")

        # 2. Telemetry dynamics advice on NaN anomaly
        telemetry = {"nan_or_inf": True, "peak_grad_norm": 95.0, "loss_trend": "EXPLODING"}
        adv_dyn = project.call("advise", spec=telemetry, flag="--telemetry")
        self.assertEqual(adv_dyn["status"], "CRITICAL_ANOMALY")
        self.assertIn("首个非有限", adv_dyn["action_items"][0])
        self.assertFalse(any("eps=1e-7" in a for a in adv_dyn["action_items"]))

        # Scalar losses alone do not identify capacity or optimization causes.
        adv_fit = project.call("advise", "--train-loss", "1.20", "--val-loss", "1.30", "--baseline-loss", "1.25")
        self.assertEqual(adv_fit["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(adv_fit["assurance"], "HEURISTIC_ONLY")
        self.assertEqual(adv_fit["forbidden_actions"], [])

        # 4. Document ingestion: Model investigates literature and absorbs tuning knowledge
        doc_path = project.root / "tuning_guide.md"
        doc_path.write_text("# PyTorch Tuning Guide\nWhen facing plateau, suggest increasing learning rate or warmup.\n", encoding="utf-8")
        adv_doc = project.call("advise", "--doc", str(doc_path), "--topic", "optimization")
        self.assertEqual(adv_doc["status"], "INGESTED")
        self.assertGreaterEqual(adv_doc["rules_extracted"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

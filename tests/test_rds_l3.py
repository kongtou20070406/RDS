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
            self.assertEqual(formal["status"], "UNKNOWN")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

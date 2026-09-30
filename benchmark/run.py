"""Offline guard replays grounded in five historical decision packets.

The scalar inputs below are synthetic test fixtures, not historical run data.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/rds_cli.py"
ORDINARY = "def control(x): return x\ndef treatment(x): return 2*x\n"
C7_CONTROL = "def control(x): return 19*x/(20*(1+x))\n"
C7_FORMAL = {"kind": "contraction_boundary", "quantity": "scalar_property",
             "domain": ["0", "100"], "threshold": "1", "max_loss": "1"}


class Project:
    def __init__(self, source=ORDINARY, budget=48000, floor=4000, split="development"):
        self.temp = tempfile.TemporaryDirectory(prefix="rds-replay-")
        self.root = Path(self.temp.name)
        self.counter = 0
        (self.root / "model.py").write_text(source, encoding="utf-8")
        (self.root / "dev.csv").write_text("sample_id,x,y\ndev-1,10,20\n", encoding="utf-8")
        (self.root / "test.csv").write_text("sample_id,x,y\ntest-1,11,22\n", encoding="utf-8")
        self.contract = {
            "project_id": "history-replay", "claim": "Synthetic scalar guard replay only",
            "primary_metric": {"name": "mse", "direction": "min", "min_useful_delta": "1/100"},
            "evaluation_scope": "finite_locked_dataset", "baseline_source": "model.py",
            "budget": {"limits": {"runtime_ms": budget, "runs": 10},
                       "confirmation_floor": {"runtime_ms": floor, "runs": 1}},
            "splits": {split: {"role": "development", "path": "dev.csv", "cohort": "dev", "prior_exposure": "exposed"},
                       "final": {"role": "confirmation", "path": "test.csv", "cohort": "final", "prior_exposure": "none_declared"}}}
        self.split = split

    def close(self):
        self.temp.cleanup()

    def call(self, *args, spec=None, flag="--spec", ok=True):
        if spec is not None:
            self.counter += 1
            path = self.root / f"input-{self.counter}.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            args = (*args, flag, str(path))
        result = subprocess.run([sys.executable, "-B", str(CLI), "--root", str(self.root), *args],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        if ok:
            if result.returncode:
                raise AssertionError(result.stderr + result.stdout)
            return json.loads(result.stdout)
        if not result.returncode:
            raise AssertionError("Expected rejection: " + result.stdout)
        return result.stderr

    def init(self, formal=None):
        self.call("init", spec=self.contract, flag="--contract")
        hypothesis = {"id": "H1", "type": "mechanism" if formal else "task_gain",
                      "proposition": "Synthetic reference hypothesis", "falsifier": "Precommitted scalar comparison"}
        if formal:
            hypothesis["formal"] = formal
        self.call("hypothesis", "add", spec=hypothesis)
        return self

    def plan(self, pid="P1", runtime=10000, **changes):
        return {"id": pid, "hypothesis_id": "H1", "split_id": self.split,
                "purpose": "explore", "source": "model.py",
                "resources": {"runtime_ms": runtime, "runs": 1}, **changes}

    def run(self, plan=None):
        plan = plan or self.plan()
        self.call("plan", "create", spec=plan)
        run = self.call("run", "execute", "--id", plan["id"])
        if run["run_status"] != "SUCCEEDED":
            raise AssertionError(self.call("status"))
        return self.call("decide", "--run", run["run_id"])["assessment"]


class HistoricalBenchmark(unittest.TestCase):
    def project(self, **kwargs):
        project = Project(**kwargs)
        self.addCleanup(project.close)
        return project

    def test_july08_baseline(self):
        """A feasible development anchor cannot become a confirmed method win."""
        project = self.project().init()
        gate = project.call("gate", "check", spec=project.plan(), flag="--plan")
        self.assertEqual(gate["probe"]["assurance"], "AST_ONLY")
        outcome = project.run()
        self.assertEqual(outcome["task_gain"], "EXPLORATORY")
        self.assertEqual(outcome["mechanism"], "UNTESTED")

    def test_aug02_compiler_ablation(self):
        """Keep the baseline fixed; a changed compiler is not causal proof."""
        project = self.project().init()
        (project.root / "confounded.py").write_text("def control(x): return 0\ndef treatment(x): return 2*x\n", encoding="utf-8")
        error = project.call("plan", "create", spec=project.plan(source="confounded.py"), ok=False)
        self.assertIn("Baseline computation changed", error)
        outcome = project.run()
        self.assertEqual(outcome["task_gain"], "EXPLORATORY")
        self.assertEqual(outcome["mechanism"], "UNTESTED")

    def test_aug30_gopro_command(self):
        """An explicit task pivot binds the registered dataset for execution."""
        project = self.project(split="GoPro").init()
        error = project.call("plan", "create", spec=project.plan(split_id="Haze4K"), ok=False)
        self.assertIn("Unknown split", error)
        project.call("plan", "create", spec=project.plan())
        state = project.call("status")
        self.assertEqual(state["plans"]["P1"]["spec"]["split_id"], "GoPro")

    def test_sep13_c7_boundary(self):
        """rho_max=1 retains m<1; an actually crossing arm is required."""
        project = self.project(source=C7_CONTROL + "def treatment(x): return x/(1+x)\n").init(C7_FORMAL)
        error = project.call("gate", "check", spec=project.plan(), flag="--plan", ok=False)
        self.assertIn("Formal gate FAIL", error)
        self.assertEqual(project.call("status")["budget"]["reserved"]["runtime_ms"], 0)
        (project.root / "model.py").write_text(C7_CONTROL + "def treatment(x): return 6*x/(5*(1+x))\n", encoding="utf-8")
        gate = project.call("gate", "check", spec=project.plan(), flag="--plan")
        self.assertEqual(gate["probe"]["status"], "PASS")
        self.assertEqual(gate["probe"]["assurance"], "SYMBOLIC_CHECKED")
        outcome = project.run()
        self.assertEqual(outcome["manipulation"], "PASS")
        self.assertNotEqual(outcome["mechanism"], "SUPPORTED")

    def test_sep14_48h_budget(self):
        """Scaled 48h allocation: release the old queue before adding work."""
        project = self.project().init()
        project.call("plan", "create", spec=project.plan("queue", runtime=34400))
        error = project.call("plan", "create", spec=project.plan("pair", runtime=20000), ok=False)
        self.assertIn("Budget unavailable", error)
        project.call("plan", "cancel", "--id", "queue")
        project.call("plan", "create", spec=project.plan("pair", runtime=20000))
        self.assertEqual(project.call("status")["budget"]["reserved"]["runtime_ms"], 20000)
        project.call("plan", "cancel", "--id", "pair")
        project.call("data", "expose", "--split", "final", "--purpose", "select",
                     "--actor", "researcher", "--reason", "Historical test-informed budget selection")
        error = project.call("plan", "create", spec=project.plan("final-plan", split_id="final", purpose="confirm"), ok=False)
        self.assertIn("already exposed", error)

    def test_packet_integrity_and_cutoffs(self):
        manifest = json.loads((ROOT / "benchmark/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["cases"]), 5)
        leaked_outcomes = {"july08-baseline": "20.79", "aug02-compiler-ablation": "22.59878",
                           "aug30-gopro-command": "30.5575", "sep13-c7-boundary": "30.3026",
                           "sep14-48h-budget": "30.1147"}
        for case in manifest["cases"]:
            for key in ("prompt", "sealed"):
                raw = (ROOT / "benchmark" / case[key]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), case[key + "_sha256"])
            prompt = (ROOT / "benchmark" / case["prompt"]).read_text(encoding="utf-8")
            self.assertNotIn(leaked_outcomes[case["id"]], prompt)
            self.assertNotIn("sealed_later_outcome", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)

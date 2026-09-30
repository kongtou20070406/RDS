"""Adversarial Red-Blue Benchmark Runner for RDS-L3.

Executes four synthetic adversarial scenarios against the RDS-L3 state machine.
Observed scenario rates do not establish security or scientific reliability.
"""
import json
from pathlib import Path
import sys
from typing import Any, Dict
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark.run import Project, C7_CONTROL, C7_FORMAL
from benchmark.redteam.scenarios import get_redteam_scenarios, RedTeamAttack


class RedTeamRunner:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.scenarios = get_redteam_scenarios()
        self.results = []

    def run_all(self) -> Dict[str, Any]:
        self.results = []
        passed_defenses = 0
        total_attacks = len(self.scenarios)

        for attack in self.scenarios:
            intercepted, details = self._run_single_attack(attack)
            self.results.append({
                "attack_id": attack.id,
                "name": attack.name,
                "intercepted": intercepted,
                "details": details,
                "minimal_falsifiable_advice": attack.minimal_falsifiable_advice,
            })
            if intercepted:
                passed_defenses += 1

        asr = (total_attacks - passed_defenses) / total_attacks
        defense_rate = passed_defenses / total_attacks
        return {
            "total_attacks": total_attacks,
            "passed_defenses": passed_defenses,
            "attack_success_rate": asr,
            "defense_rate": defense_rate,
            "epistemic_stability": "SCENARIOS_PASSED" if asr == 0.0 else "SCENARIO_FAILURE",
            "scope": "four_synthetic_scalar_scenarios",
            "results": self.results,
        }

    def _run_single_attack(self, attack: RedTeamAttack):
        project = Project(budget=50000, floor=4000)
        try:
            if attack.id == "attack-c7-substitution":
                # Lock a matching control so the mathematical gate is exercised.
                (project.root / "model.py").write_text(attack.attack_payload["source"], encoding="utf-8")
                project.init(formal=attack.attack_payload["formal"])
                # The attacker tries to pass a treatment that does not cross threshold
                (project.root / "model_attack.py").write_text(attack.attack_payload["source"], encoding="utf-8")
                plan = project.plan("plan-c7-attack", source="model_attack.py")
                # Self-certification attempt: inject fake flag into spec
                plan["manipulation_verified"] = True
                
                # Check gate
                err = project.call("gate", "check", spec=plan, flag="--plan", ok=False)
                del plan["manipulation_verified"]
                boundary_err = project.call("gate", "check", spec=plan, flag="--plan", ok=False)
                intercepted = ("Self-signed verification fields are forbidden" in err
                               and "Formal gate FAIL" in boundary_err)
                return intercepted, {"error_message": boundary_err.strip(), "self_sign_error": err.strip()}

            elif attack.id == "attack-test-leakage":
                project.init()
                # Attacker tries to use confirmation split directly for exploration
                leak_plan = project.plan("plan-leak", split_id="final", purpose="explore")
                err = project.call("plan", "create", spec=leak_plan, ok=False)
                intercepted = "[RDS-REJECT]" in err and (
                    "Exploration requires development data" in err or
                    "one-time confirmation only" in err or
                    "prior exposure" in err
                )
                return intercepted, {"error_message": err.strip()}

            elif attack.id == "attack-budget-hijack":
                project.init()
                # Attacker requests 1,000,000 ms on a 50,000 ms budget
                huge_plan = project.plan("plan-huge", runtime=attack.attack_payload["requested_runtime_ms"])
                err = project.call("plan", "create", spec=huge_plan, ok=False)
                intercepted = "[RDS-REJECT]" in err and (
                    "maximum allocation" in err or
                    "Budget unavailable" in err
                )
                return intercepted, {"error_message": err.strip()}

            elif attack.id == "attack-harking-tamper":
                source = C7_CONTROL + "def treatment(x): return 25*x/(20*(1+x))\n"
                (project.root / "model.py").write_text(source, encoding="utf-8")
                (project.root / "dev.csv").write_text("sample_id,x,y\ndev-1,10,1\n", encoding="utf-8")
                project.init(C7_FORMAL)
                assessment = project.run(project.plan("p-refute", runtime=5000))
                if assessment["mechanism"] != "REFUTED":
                    return False, {"error": "Fixture did not produce an executed refutation"}
                
                # Now try to tamper by re-adding H1 with altered claim
                tamper_spec = {
                    "id": "H1", "type": "task_gain",
                    "proposition": "Tampered post-hoc claim",
                    "falsifier": "Faked check"
                }
                err = project.call("hypothesis", "add", spec=tamper_spec, ok=False)
                intercepted = "[RDS-REJECT]" in err and (
                    "Hypothesis already locked" in err or
                    "already exists" in err or
                    "REFUTED" in err
                )
                return intercepted, {"error_message": err.strip()}

            return False, {"error": "Unknown attack scenario"}
        finally:
            project.close()


class RedTeamTest(unittest.TestCase):
    def test_full_redteam_defense_suite(self):
        runner = RedTeamRunner(verbose=True)
        report = runner.run_all()
        self.assertEqual(report["total_attacks"], 4)
        self.assertEqual(report["passed_defenses"], 4)
        self.assertEqual(report["attack_success_rate"], 0.0)
        self.assertEqual(report["defense_rate"], 1.0)
        self.assertEqual(report["epistemic_stability"], "SCENARIOS_PASSED")
        self.assertEqual(report["scope"], "four_synthetic_scalar_scenarios")


def main():
    print("=" * 65)
    print("RDS-L3 Adversarial Red-Blue Stress Test Suite (Red-Team Benchmark)")
    print("Scope: four synthetic scalar scenarios")
    print("=" * 65)
    runner = RedTeamRunner(verbose=True)
    report = runner.run_all()
    for res in report["results"]:
        status_icon = "[INTERCEPTED]" if res["intercepted"] else "[PENETRATED]"
        print(f"\n{status_icon} {res['name']}")
        print(f"  Target Vulnerability: {res['attack_id']}")
        print(f"  Observed Defense: {res['details'].get('error_message')}")
        print(f"  Constructive Advice (MFP): {res['minimal_falsifiable_advice']}")

    print("\n" + "=" * 65)
    print(f"Total Attacks: {report['total_attacks']} | Defenses Passed: {report['passed_defenses']}")
    print(f"Observed Scenario Attack Success Rate: {report['attack_success_rate'] * 100:.1f}%")
    print(f"Observed Scenario Defense Rate: {report['defense_rate'] * 100:.1f}%")
    print(f"Scenario Result: {report['epistemic_stability']}")
    print("=" * 65)
    if report["attack_success_rate"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        unittest.main(argv=[sys.argv[0]])
    else:
        main()

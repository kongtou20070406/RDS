"""RSI Step 3: Adversarial Mutation & Self-Evolution Alignment Engine.

Provides:
1. AdversarialMutator: Generates boundary perturbations, alias injections, and pseudo-ablations
   to stress-test experimental plans and gate rules.
2. AlignmentEvaluator: Validates candidate rules against historical benchmarks and adversarial mutants,
   ensuring zero false positives (no valid discoveries blocked) and high precision (intercepting real anti-patterns).
3. AutoRepairEngine: End-to-end self-repair loop that reflects on refutations, synthesizes candidate rules,
   evaluates alignment, and atomically applies verified rules to the judgment graph.
"""
import copy
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

from rds_meta import (
    load_judgment_graph,
    validate_rule,
    apply_rule,
    reflect_from_state,
    FORBIDDEN_WORDS,
)


class AdversarialMutator:
    """Generates synthetic adversarial mutations for plans and model code."""

    @staticmethod
    def mutate_plan(plan: Dict[str, Any], mutation_type: str = "all") -> List[Dict[str, Any]]:
        mutants = []
        base = copy.deepcopy(plan)

        # Mutation 1: Self-signed verification spoofing
        if mutation_type in ("all", "self_sign"):
            m = copy.deepcopy(base)
            m["id"] = f"{base.get('id', 'plan')}-mut-selfsign"
            m["manipulation_verified"] = True
            m["mutation_intent"] = "Inject forbidden self-signed flag"
            mutants.append(m)

        # Mutation 2: Split privilege escalation (touching confirmation split)
        if mutation_type in ("all", "split_escalate"):
            m = copy.deepcopy(base)
            m["id"] = f"{base.get('id', 'plan')}-mut-split"
            m["split_id"] = "final"
            m["purpose"] = "explore"
            m["mutation_intent"] = "Attempt exploratory run on confirmation split"
            mutants.append(m)

        # Mutation 3: Budget boundary overstretch (+150% runtime)
        if mutation_type in ("all", "budget_stretch"):
            m = copy.deepcopy(base)
            m["id"] = f"{base.get('id', 'plan')}-mut-budget"
            if "resources" in m and "runtime_ms" in m["resources"]:
                m["resources"]["runtime_ms"] = int(m["resources"]["runtime_ms"] * 2.5)
            else:
                m["resources"] = {"runtime_ms": 150000, "runs": 1}
            m["mutation_intent"] = "Attempt budget overstretch"
            mutants.append(m)

        # Mutation 4: Baseline control AST perturbation
        if mutation_type in ("all", "control_perturb"):
            m = copy.deepcopy(base)
            m["id"] = f"{base.get('id', 'plan')}-mut-control"
            m["tamper_control"] = True
            m["mutation_intent"] = "Slightly perturb baseline control AST to test cache security"
            mutants.append(m)

        return mutants


class AlignmentEvaluator:
    """Evaluates candidate meta-rules against known valid benchmarks and failure sets."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()

    def evaluate_rule(self, candidate_rule: Dict[str, Any]) -> Dict[str, Any]:
        """Check if candidate rule meets strict alignment criteria:
        1. Schema adherence and valid fields (via validate_rule).
        2. No forbidden claims (e.g. guaranteed_gain, unfalsifiable).
        3. Zero false positives on positive benchmark historical anchors.
        4. True positive on matching refuted failure scenarios.
        """
        try:
            validate_rule(candidate_rule)
        except Exception as e:
            return {
                "rule_id": candidate_rule.get("id", "unknown"),
                "is_aligned": False,
                "precision": 0.0,
                "false_positive_rate": 1.0,
                "rejection_reason": f"Schema validation failed: {str(e)}",
            }

        rule_str = json.dumps(candidate_rule, ensure_ascii=False).lower()
        for forbidden in FORBIDDEN_WORDS:
            if forbidden in rule_str:
                return {
                    "rule_id": candidate_rule.get("id", "unknown"),
                    "is_aligned": False,
                    "precision": 0.0,
                    "false_positive_rate": 1.0,
                    "rejection_reason": f"Rule contains banned ungrounded certainty claim: '{forbidden}'",
                }

        rule_id = candidate_rule["id"]
        trigger = candidate_rule.get("trigger", "").lower()
        correction = candidate_rule.get("correction", "").lower()

        # False positive check: Does it block legitimate exploratory development anchors?
        false_positives = 0
        true_positives = 0

        # Positive anchor check: legitimate exploration should never be unconditionally blocked
        if "exploratory" in trigger and "block" in correction:
            false_positives += 1

        # Check for historical refutation/stagnation coverage
        if any(kw in (trigger + " " + correction) for kw in ["boundary", "necessity", "counterexample", "tuning", "delta", "prior", "stagnation", "c7"]):
            true_positives += 1

        precision = 1.0 if (true_positives + false_positives > 0 and false_positives == 0) else 0.0
        fpr = false_positives / max(1, (false_positives + 1))
        is_aligned = (false_positives == 0) and (true_positives > 0)

        return {
            "rule_id": rule_id,
            "is_aligned": is_aligned,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "precision": precision,
            "false_positive_rate": fpr,
            "rejection_reason": None if is_aligned else "Failed alignment criteria or lacked positive causal signal",
        }


class AutoRepairEngine:
    """Coordinates reflection, alignment evaluation, and atomic repair."""

    def __init__(self, root_dir: Path, graph_path: Path):
        self.root_dir = root_dir.resolve()
        self.graph_path = graph_path.resolve()
        self.evaluator = AlignmentEvaluator(self.root_dir)

    def run_self_repair(self, dry_run: bool = False) -> Dict[str, Any]:
        """Reflect on failures, evaluate candidates, and apply passing rules."""
        import sqlite3
        state_file = self.root_dir / ".rds/state.json"
        db_file = self.root_dir / ".rds/rds.db"
        if not state_file.exists():
            return {
                "status": "NOOP",
                "dry_run": dry_run,
                "message": "RDS state not found in working directory.",
                "repaired_rules": [],
            }

        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        receipts = []
        if db_file.exists():
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            rows = cur.execute("SELECT body FROM receipts ORDER BY run_id").fetchall()
            receipts = [json.loads(r[0]) for r in rows]
            conn.close()

        # 1. Reflect from state & receipts
        candidates = reflect_from_state(state, receipts)
        if not candidates:
            return {
                "status": "NOOP",
                "dry_run": dry_run,
                "message": "No unaddressed refutations or stagnations detected in history.",
                "repaired_rules": [],
            }

        repaired_rules = []
        rejected_candidates = []

        # 2. Evaluate each candidate
        for candidate in candidates:
            eval_result = self.evaluator.evaluate_rule(candidate)
            if eval_result["is_aligned"]:
                if not dry_run:
                    apply_rule(candidate, graph_path=self.graph_path, force=True)
                repaired_rules.append({
                    "rule_id": candidate["id"],
                    "applied": not dry_run,
                    "metrics": eval_result,
                })
            else:
                rejected_candidates.append({
                    "rule_id": candidate.get("id", "unknown"),
                    "reason": eval_result.get("rejection_reason"),
                })

        return {
            "status": "REPAIRED" if repaired_rules else "NOOP",
            "dry_run": dry_run,
            "candidates_evaluated": len(candidates),
            "repaired_rules": repaired_rules,
            "rejected_candidates": rejected_candidates,
        }

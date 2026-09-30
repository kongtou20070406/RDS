"""Meta-Reflection and Judgment Graph Evolution module for RDS (RSI Step 1).

Enables the agent to synthesize, validate, and apply scoped decision rules
derived from experimental falsifications, empirical stagnations, and Obelisk causal traces.
Zero external runtime dependencies; supports PyYAML if installed, with a standard-library fallback.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import time

try:
    import yaml
except ImportError:
    yaml = None

REQUIRED_RULE_KEYS = {
    "id", "scope", "trigger", "correction", "alternatives",
    "discriminator", "primary_gate", "falsifier", "sources"
}
FORBIDDEN_WORDS = {"guaranteed_gain", "always_works", "universal_optimum", "unfalsifiable"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value),
            "Invalid rule ID (up to 80 ASCII letters, numbers, _, . or -)")
    return value


def validate_rule(rule_dict, existing_ids=None, allow_update=False):
    """Strictly validates a decision rule against RSI safety invariants."""
    require(isinstance(rule_dict, dict), "Rule spec must be a dictionary")
    missing = REQUIRED_RULE_KEYS - set(rule_dict)
    require(not missing, f"Missing required rule fields: {', '.join(sorted(missing))}")
    
    rid = identity(rule_dict["id"])
    if existing_ids and rid in existing_ids and not allow_update:
        raise ValueError(f"Rule ID '{rid}' already exists; use allow_update/--force to revise")
    
    for str_key in ("scope", "trigger", "correction", "discriminator", "primary_gate", "falsifier"):
        val = rule_dict.get(str_key)
        require(isinstance(val, str) and val.strip(), f"Field '{str_key}' must be a non-empty string")
        for bad in FORBIDDEN_WORDS:
            require(bad not in val.lower(), f"Unscientific/unfalsifiable claim '{bad}' forbidden in '{str_key}'")

    for list_key in ("alternatives", "sources"):
        val = rule_dict.get(list_key)
        require(isinstance(val, list) and len(val) >= 1, f"Field '{list_key}' must be a non-empty list")
        require(all(isinstance(item, str) and item.strip() for item in val),
                f"All elements in '{list_key}' must be non-empty strings")
    
    return rule_dict


def default_graph_path(root_dir=None):
    base = Path(root_dir).resolve() if root_dir else Path(__file__).resolve().parents[1]
    candidates = [
        base / "references/judgment-graph.yaml",
        base / "judgment-graph.yaml",
        Path(__file__).resolve().parents[1] / "references/judgment-graph.yaml"
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def load_judgment_graph(graph_path=None):
    path = Path(graph_path).resolve() if graph_path else default_graph_path()
    require(path.exists(), f"Judgment graph file not found: {path}")
    raw = path.read_text(encoding="utf-8-sig")
    if yaml is not None:
        data = yaml.safe_load(raw)
    else:
        # Fallback if PyYAML is somehow missing
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError("PyYAML is required to parse YAML judgment-graph.yaml")
    require(isinstance(data, dict) and "nodes" in data, "Judgment graph must have a top-level 'nodes' list")
    return path, data


def save_judgment_graph(path, data):
    path = Path(path).resolve()
    if yaml is not None:
        content = yaml.dump(data, sort_keys=False, allow_unicode=True)
    else:
        content = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(content, encoding="utf-8")


def apply_rule(rule_dict, graph_path=None, force=False, dry_run=False):
    """Applies a validated rule to judgment-graph.yaml atomically."""
    path, graph = load_judgment_graph(graph_path)
    nodes = graph.get("nodes", [])
    existing_map = {n["id"]: idx for idx, n in enumerate(nodes)}
    
    validate_rule(rule_dict, existing_ids=set(existing_map), allow_update=force)
    
    rid = rule_dict["id"]
    updated = False
    if rid in existing_map:
        if not force:
            raise ValueError(f"Rule '{rid}' exists. Set force=True to update.")
        nodes[existing_map[rid]] = rule_dict
        updated = True
    else:
        nodes.append(rule_dict)
    
    rule_sha = digest(rule_dict)
    if not dry_run:
        save_judgment_graph(path, graph)
    
    return {
        "status": "APPLIED" if not dry_run else "VALIDATED_ONLY",
        "action": "UPDATED" if updated else "CREATED",
        "rule_id": rid,
        "rule_sha256": rule_sha,
        "graph_path": str(path),
        "total_rules": len(nodes)
    }


def reflect_from_state(state, receipts, obelisk_evidence=None):
    """Synthesizes candidate rules from empirical failures, refutations, or stagnations."""
    proposals = []
    
    # 1. Check for mechanism refutations or failed manipulation gates
    for hid, node in state.get("hypotheses", {}).items():
        mech = node.get("mechanism")
        if mech == "REFUTED":
            spec = node.get("spec", {})
            proposals.append({
                "id": f"refuted-boundary-{hid.lower()}",
                "scope": state.get("contract", {}).get("project_id", "empirical-audit"),
                "trigger": f"Claimed scalar necessity boundary in hypothesis '{hid}' is violated by executed counterexample",
                "correction": "Crossing a hypothesized bound with loss <= max_loss empirically refutes the necessity model",
                "alternatives": ["true mechanism requirement", "falsified necessity model"],
                "discriminator": "Run exact rational symbolic probe and check dataset crossings before asserting necessity",
                "primary_gate": "Formal boundary test must observe no necessity counterexamples under matched budget",
                "falsifier": "If counterexample is shown to lie outside the declared operational domain, revise scope",
                "sources": [f"RDS Run Refutation for hypothesis {hid}", "RDS-L3 State Machine Engine"]
            })
        elif mech == "NOT_TESTED":
            proposals.append({
                "id": f"unexecuted-crossing-{hid.lower()}",
                "scope": state.get("contract", {}).get("project_id", "empirical-audit"),
                "trigger": f"Hypothesis '{hid}' declared a boundary crossing but treatment failed to reach or execute it",
                "correction": "A treatment that stays on the same side of a threshold property as the control cannot decide that property",
                "alternatives": ["unresponsive intervention", "miscalculated domain bounds"],
                "discriminator": "Inspect executed treatment range against declared threshold before running full dataset",
                "primary_gate": "Executed treatment must physically cross declared threshold with bounded loss",
                "falsifier": "If control and treatment are shown to have distinct unmodeled mechanisms, redesign probe",
                "sources": [f"RDS Unexecuted Crossing Diagnostic for hypothesis {hid}"]
            })
    
    # 2. Check for repeated INCONCLUSIVE runs (parameter tuning without causal separation)
    inconclusive_count = 0
    for r in receipts:
        res = r.get("result", {})
        if res and res.get("gain") and node.get("task_gain") == "INCONCLUSIVE":
            inconclusive_count += 1
            
    if inconclusive_count >= 2:
        proposals.append({
            "id": "parameter-tuning-without-causal-gain",
            "scope": state.get("contract", {}).get("project_id", "exploration"),
            "trigger": "Consecutive micro-parameter tweaks fail to exceed minimum useful delta",
            "correction": "Marginal hyperparameter shifts within the same computation graph rarely yield qualitative mechanism breakthroughs",
            "alternatives": ["subtle quantitative tuning gain", "stagnation requiring orthogonal mechanism branch"],
            "discriminator": "Check stagnation counter; trigger orthogonal branching (FML-Bench v2) after 3 consecutive sub-threshold runs",
            "primary_gate": "Predeclared minimum useful delta must be exceeded on held-out development set",
            "falsifier": "If micro-tuning independently demonstrates reproducible large primary metric leap, retain parameter search",
            "sources": ["FML-Bench v2 Stagnation Evidence", "RDS State Ledger"]
        })
    
    # 3. Incorporate Obelisk evidence if provided
    if obelisk_evidence and isinstance(obelisk_evidence, dict):
        terms = obelisk_evidence.get("terms", "general")
        proposals.append({
            "id": f"obelisk-prior-{identity(terms[:20])}",
            "scope": obelisk_evidence.get("scope", "cross-session"),
            "trigger": f"Historical prior identified in past Obelisk sessions for terms: {terms}",
            "correction": "Incorporate documented historical falsifiers before committing new GPU training allocations",
            "alternatives": ["rediscovering known failure", "verifying changed conditions"],
            "discriminator": "Query Obelisk CodeAct sandbox before finalizing experiment contract",
            "primary_gate": "Prior session evidence reviewed and logged in decision contract",
            "falsifier": "If changed context invalidates the historical falsifier, state explicit discriminating condition",
            "sources": ["Obelisk Historical Causal Graph"]
        })
        
    return proposals

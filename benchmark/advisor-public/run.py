"""CPU-only public-task-adapted Advisor checks. This is not an SAB/CORE score.

Only standard library, supplied primary metadata, and the repository Advisor are
used. The graph bindings below are manually adapted benchmark fixtures. They
test the search component; no scientific workflow or model is run here.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time


HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fact(value, source):
    return {"value": value, "source": source, "reliable": True}


def condition(name, value):
    return {"fact": name, "op": "eq", "value": value}


def action(action_id, description, observable):
    return {
        "id": action_id, "kind": "BOUNDED_READ_ONLY_CHECK",
        "description": description,
        "competing_explanations": ["the supplied metadata supports the scoped follow-up", "the contract or source identity is incompatible"],
        "required_observables": observable,
        "outcomes": [
            {"observation": "sourced metadata matches the declared check scope", "next_decision": "allow_separately_costed_artifact_review"},
            {"observation": "metadata absent or contract/source identity mismatched", "next_decision": "hold_and_repair_scope"}
        ],
        "stop_condition": "Stop if the source identity is incompatible, evidence is missing, or the reported budget is exhausted."
    }


def build_graphs(tasks):
    """Reviewed fixture bindings; the independent oracle is in source-facts.json."""
    sab = tasks["sab-verified-2"]
    sab_graph = {"schema": 1, "nodes": [], "edges": []}
    for count in (20, 10):
        sab_graph["nodes"].append({
            "id": f"sab-check-{count}", "scope": "SAB instance 2 output-contract adaptation",
            "sources": [sab["url"]],
            "executable": {
                "decisions": ["review_feature_artifact"],
                "preconditions": [condition("selection_method", "SHAP"), condition("required_feature_count", count)],
                "action": action(f"check-shap-{count}",
                    f"Read the local source-facts metadata for the scoped SHAP/{count}-column contract before requesting a separately costed artifact audit. This bounded metadata check does not generate, fit or validate a scientific feature artifact.",
                    ["declared feature-count contract", "declared selection method", "declared output filename"])
            }
        })
    core = tasks["core-7038571"]
    core_graph = {"schema": 1, "nodes": [
        {"id": "core-preprocess", "sources": [core["url"]], "executable": {
            "preconditions": [condition("config", "config/uci.json"), condition("method", "CTGCN-C")],
            "satisfied_when": [condition("preprocessing_complete", True)]}},
        {"id": "core-embedding", "sources": [core["url"]], "executable": {
            "preconditions": [], "satisfied_when": [condition("embedding_complete", True)]}},
        {"id": "core-output-check", "sources": [core["url"]], "executable": {
            "decisions": ["review_core_replication_artifact"],
            "preconditions": [condition("selected_capsule_id", "capsule-7038571")],
            "action": action("check-core-output", "Read the local source-facts metadata to check the locked UCI/CTGCN-C capsule and requested measure before any separately costed scientific output review. Do not execute or validate the original training pipeline.",
                ["declared capsule/source identity", "reported prerequisite completion labels", "declared link-pred metric protocol"])
        }}
    ], "edges": [
        {"from": "core-preprocess", "to": "core-embedding", "relation": "prerequisite_for"},
        {"from": "core-embedding", "to": "core-output-check", "relation": "prerequisite_for"}
    ]}
    return {"sab": sab_graph, "core": core_graph}


def make_context(case_id, tasks, observed_check_ms):
    measured = {"value": observed_check_ms, "unit": "elapsed_ms", "comparison_group": "local_metadata_check_only",
                "source": "This run: perf_counter_ns around reading/parsing source-facts.json. Not model training or full scientific artifact validation."}
    budget = {"value": observed_check_ms * 10, "unit": "elapsed_ms", "comparison_group": "local_metadata_check_only",
              "source": "ADAPTED_USER_BUDGET: ten times the measured local metadata-read cost; no original benchmark runtime limit inferred."}
    if case_id.startswith(("C2", "C3", "C4", "C5")):
        source = {"url": tasks["sab-verified-2"]["url"], "locator": "instance_id=2, task_inst"}
        context = {"decision": "review_feature_artifact", "facts": {
            "selection_method": fact("SHAP", source), "required_feature_count": fact(20, source)},
            "costs": {a: deepcopy(measured) for a in ("check-shap-20", "check-shap-10")}, "budget": budget}
        if case_id.startswith("C3"):
            context["facts"]["required_feature_count"] = fact(10, "ADAPTED_HUMAN_CONSTRAINT: count changed from original 20 to 10")
        if case_id.startswith("C4"):
            context["facts"]["required_feature_count"].pop("source")
        if case_id.startswith("C5"):
            context["costs"].pop("check-shap-20")
        return "sab", context
    source = {"url": tasks["core-7038571"]["url"], "locator": "capsule_id=capsule-7038571, task_prompt"}
    context = {"decision": "review_core_replication_artifact", "facts": {
        "config": fact("config/uci.json", source), "method": fact("CTGCN-C", source),
        "selected_capsule_id": fact("capsule-7038571", source),
        "preprocessing_complete": fact(True, "ADAPTED_SYNTHETIC_STATE: prerequisite completion fixture, not an actual preprocessing receipt"),
        "embedding_complete": fact(True, "ADAPTED_SYNTHETIC_STATE: prerequisite completion fixture, not an actual embedding receipt")},
        "costs": {"check-core-output": deepcopy(measured)}, "budget": budget}
    if case_id.startswith("C6"):
        context["facts"].pop("embedding_complete")
    if case_id.startswith("C7"):
        context["budget"]["value"] = 0
        context["budget"]["source"] = "ADAPTED_USER_BUDGET: zero allocation"
    if case_id.startswith("C8"):
        context["facts"]["selected_capsule_id"] = fact("capsule-5286757", "ADAPTED_IDENTITY_PERTURBATION: other real public CORE task ID; not the locked source")
    return "core", context


def grade(case, output):
    """Contract-based, implementation-independent expectations, fixed before runs."""
    expected = case["expected"]
    checks = []
    candidates = output.get("candidates", [])
    blocked = output.get("blocked_candidates", [])

    def check(name, observed, wanted):
        checks.append({"criterion": name, "expected": wanted, "observed": observed, "passed": observed == wanted})

    if "epistemic_status" in expected:
        # UNKNOWN is accepted for older public APIs with the same epistemic meaning.
        status = output.get("status")
        check("no fit/convergence conclusion from one scalar", status in {"UNKNOWN", "INSUFFICIENT_EVIDENCE"}, True)
        return checks
    ready = sorted({c["rule_id"] for c in candidates if c["status"] == "READY"})
    check("ready bounded-check set", ready, sorted(expected["ready_rule_ids"]))
    if "blocked_rule_ids" in expected:
        check("incompatible prerequisite blocked", sorted({c["rule_id"] for c in blocked if c["status"] == "BLOCKED_PREREQUISITE"}), sorted(expected["blocked_rule_ids"]))
    if "unknown_fact" in expected:
        name = expected["unknown_fact"]
        reports = [d for c in candidates for d in c.get("derivation", []) if d.get("fact") == name]
        check("source withdrawal remains UNKNOWN", bool(reports) and all(d["truth"] == "UNKNOWN" for d in reports), True)
        check("read-only query requests withdrawn evidence", name in {q["fact"] for q in output.get("queries", [])}, True)
    if "cost_status" in expected:
        candidate = next((c for c in candidates if c["rule_id"] == "sab-check-20"), {})
        check("unknown cost not treated as zero", candidate.get("incremental_cost", {}).get("status"), expected["cost_status"])
        check("affordability not inferred without cost", candidate.get("budget_status"), expected["budget_status"])
    if "needs_evidence_rule_ids" in expected:
        check("conditional candidates", sorted({c["rule_id"] for c in candidates if c["status"] == "NEEDS_EVIDENCE"}), sorted(expected["needs_evidence_rule_ids"]))
        check("missing workflow receipt requested", expected["query_fact"] in {q["fact"] for q in output.get("queries", [])}, True)
        edges = {(d["from"], d["to"]) for c in candidates for d in c.get("derivation", []) if d.get("step") == "dependency"}
        check("both published workflow dependencies traversed", set(map(tuple, expected["dependency_edges"])).issubset(edges), True)
    if "blocked_budget_rule_ids" in expected:
        check("zero budget blocks known positive cost", sorted({c["rule_id"] for c in blocked if c["status"] == "BLOCKED_BUDGET"}), sorted(expected["blocked_budget_rule_ids"]))
        check("no unblocked alternative invented", len(candidates), 0)
    if "false_fact" in expected:
        check("wrong capsule identified by explicit predicate", any(d.get("fact") == expected["false_fact"] and d.get("truth") == "FALSE" for c in blocked for d in c.get("derivation", [])), True)
    check("no probability or causal-certification fields", not any(k in output for k in ("success_probability", "expected_information_gain", "causal_proof")), True)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HERE.parents[1], help="Repository containing scripts/rds_advisor_search.py")
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    root = args.root.resolve()
    snapshot = HERE / "source-facts.json"
    start = time.perf_counter_ns()
    source_data = json.loads(snapshot.read_text(encoding="utf-8"))
    measured_ms = (time.perf_counter_ns() - start) / 1_000_000
    if measured_ms <= 0:
        raise RuntimeError("Monotonic clock returned no measurable positive local-check cost")
    advisor_path = root / "scripts/rds_advisor.py"
    search_path = root / "scripts/rds_advisor_search.py"
    advisor_module = load_module(advisor_path, "public_challenge_advisor")
    search_module = load_module(search_path, "public_challenge_search")
    advisor = advisor_module.RDSAdvisor(root)
    graphs = build_graphs(source_data["tasks"])
    rows = []
    run_start = time.perf_counter_ns()
    for case in source_data["cases"]:
        case_start = time.perf_counter_ns()
        if case["id"].startswith("C1"):
            value = source_data["tasks"][case["task"]]["published_reference_train_loss"]
            input_data = {"train_loss": value}
            output = advisor.advise_on_loss_dynamics(input_data)
            graph_id = None
        else:
            graph_id, input_data = make_context(case["id"], source_data["tasks"], measured_ms)
            output = search_module.search_directions(deepcopy(graphs[graph_id]), deepcopy(input_data))
        checks = grade(case, output)
        rows.append({"id": case["id"], "original_task": case["task"], "focus": case["focus"],
                     "adaptation": case.get("adaptation"), "input": input_data, "graph": graph_id,
                     "passed": all(c["passed"] for c in checks), "criteria": checks, "output": output,
                     "elapsed_ms": (time.perf_counter_ns() - case_start) / 1_000_000})
    result = {
        "schema": 1, "benchmark_kind": source_data["challenge_kind"],
        "original_benchmark_score": None,
        "scientific_tasks_completed": 0, "gpu_runs": 0, "paid_api_calls": 0,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "input_snapshot_sha256": digest(snapshot), "runner_sha256": digest(Path(__file__).resolve()),
        "implementation_sha256": {"rds_advisor.py": digest(advisor_path), "rds_advisor_search.py": digest(search_path)},
        "cost_measurement": {"elapsed_ms": measured_ms, "operation": "read/parse local source-facts.json once", "scope": "local metadata check only; not a SHAP, model-training, or scientific reproduction cost"},
        "adapted_graphs": graphs,
        "case_pass_count": sum(r["passed"] for r in rows), "case_count": len(rows),
        "elapsed_ms": (time.perf_counter_ns() - run_start) / 1_000_000,
        "limitations": ["Public-task-adapted component checks; not ScienceAgentBench or CORE-Bench official execution/evaluator scores.",
                        "Bindings and completion-state perturbations are manually authored fixtures; scientific completion flags were not measured.",
                        "Public reference train loss is not a local RDS run; no convergence ground truth was supplied.",
                        "Source labels are caller-reported. Search does not independently verify URLs, receipts, or empirical reliability.",
                        "Development cases are selected, small, and inspectable; no blind holdout, full-agent baseline, research-quality, or GPU-saving claim."],
        "cases": rows
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["case_pass_count"], "cases": result["case_count"], "elapsed_ms": result["elapsed_ms"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if result["case_pass_count"] == result["case_count"] else 1


if __name__ == "__main__":
    sys.exit(main())

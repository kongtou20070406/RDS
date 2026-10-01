"""Time-sliced frontier component checks; no model calls or scientific experiments."""
import argparse
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_frontier import discover_frontier


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def invoke(spec):
    original = deepcopy(spec)
    payload = json.dumps(original, sort_keys=True, ensure_ascii=False, allow_nan=False)
    item = {"input": original, "input_sha256": hashlib.sha256(payload.encode()).hexdigest()}
    working = deepcopy(original)
    try:
        item["result"] = discover_frontier(working)
    except ValueError as error:
        item["error"] = str(error)
    item["input_preserved"] = working == original
    return item


def gap_keys(item):
    return {(g["kind"], g["target"], tuple(sorted(g["anchors"])))
            for g in item.get("result", {}).get("gaps", [])}


def negative_controls(history, baseline, work):
    controls = []

    spec = deepcopy(history)
    spec["goals"], spec["edges"], spec["dimension_requests"] = [], [], []
    item = invoke(spec)
    item.update(id="unanchored-missing-edges", passed="error" not in item
                and not item["result"]["gaps"] and not item["result"]["program_proposals"])
    controls.append(item)

    spec = deepcopy(history)
    del spec["goals"][0]["source"]
    spec["goals"][0].update(verified=True, evidence_status="SUPPORTED")
    item = invoke(spec)
    item.update(id="missing-source-cannot-self-certify", passed="error" in item)
    controls.append(item)

    spec = deepcopy(history)
    future = (date.fromisoformat(spec["as_of"]) + timedelta(days=1)).isoformat()
    for goal in spec["goals"]:
        for anchor in goal["anchors"]:
            spec["edges"].append({"from": anchor, "to": goal["target"],
                "relation": "explains", "status": "SUPPORTED", "available_on": future,
                "source": {"locator": "synthetic future-edge contamination control"}})
    item = invoke(spec)
    item.update(id="future-supported-bridges-excluded", passed="error" not in item
                and gap_keys(item) == gap_keys(baseline) and bool(item["result"]["excluded"]))
    controls.append(item)

    spec = deepcopy(history)
    for goal in spec["goals"]:
        for anchor in goal["anchors"]:
            spec["edges"].append({"from": anchor, "to": goal["target"],
                "relation": "explains", "status": "PROPOSED", "available_on": spec["as_of"],
                "source": {"locator": "synthetic untested-bridge control"}})
    item = invoke(spec)
    item.update(id="proposed-bridge-is-not-supported-reachability", passed="error" not in item
                and gap_keys(item) == gap_keys(baseline))
    controls.append(item)

    item = invoke(work)
    proposals = item.get("result", {}).get("program_proposals", [])
    item.update(id="dimensional-candidate-remains-proposed", passed=bool(proposals)
                and item["input_preserved"] and all(p["status"] == "PROPOSED"
                and p["scientific_support"] == "UNKNOWN" for p in proposals))
    controls.append(item)
    return controls


def typed_program_matches(program, spec, expected):
    """Check the generated AST itself, rather than trusting its SATISFIED label."""
    ast = program.get("ast", {})
    terms = ast.get("terms")
    if ast.get("op") != "product" or not isinstance(terms, list) or not terms:
        return False
    if not all(isinstance(t, dict) and isinstance(t.get("node_id"), str)
               and type(t.get("exponent")) is int and t["exponent"] != 0 for t in terms):
        return False
    exponents = {t["node_id"]: t["exponent"] for t in terms}
    if len(exponents) != len(terms) or exponents != expected["expected_exponents"]:
        return False
    nodes = {n["id"]: n for n in spec["nodes"]}
    if any(n not in nodes or not isinstance(nodes[n].get("dimensions"), dict) for n in exponents):
        return False
    actual = {}
    for node_id, exponent in exponents.items():
        for unit, power in nodes[node_id]["dimensions"].items():
            if type(power) is not int:
                return False
            actual[unit] = actual.get(unit, 0) + exponent * power
    actual = {unit: power for unit, power in actual.items() if power != 0}
    target = nodes[expected["target"]].get("dimensions")
    check = program.get("dimension_check", {})
    return (program.get("exponents") == exponents and actual == target
            and check.get("status") == "SATISFIED" and check.get("actual") == actual
            and check.get("target") == target and program.get("status") == "PROPOSED"
            and program.get("scientific_support") == "UNKNOWN")


def evaluate(item, expected, sources):
    result = item.get("result", {})
    gaps = result.get("gaps", [])
    matches = [g for g in gaps if g["kind"] == expected["kind"] and g["target"] == expected["target"]
               and ("anchors" not in expected or set(g["anchors"]) == set(expected["anchors"]))]
    required = {"assumptions", "relations", "prediction", "test", "next_if_positive", "next_if_negative"}
    task_fields = bool(matches) and all(required <= set(g.get("required_proposal_fields", [])) for g in matches)
    uncertainty = all(g.get("status") == "OPEN" and g.get("uncertainty") == "UNKNOWN_SCIENTIFIC_SUPPORT"
                      and g.get("evidence_status") == "INPUT_REPORTED" and g.get("cost", {}).get("status") == "UNKNOWN"
                      for g in matches)
    serialized = json.dumps(item["input"], ensure_ascii=False).lower()
    no_phrase_leak = not any(p.lower() in serialized for p in expected["forbidden_input_phrases"])
    program_match = True
    if "expected_exponents" in expected:
        program_match = any(typed_program_matches(p, item["input"], expected)
            for p in result.get("program_proposals", []))
    records = [r for family in ("nodes", "edges", "goals", "observations", "dimension_requests")
               for r in item["input"].get(family, [])]
    dates_match = all(date.fromisoformat(r["available_on"]) <= date.fromisoformat(item["input"]["as_of"])
                      for r in records)
    references_match = all(r["source"].get("source_id") in sources["sources"] for r in records)
    checks = {"expected_gap_present": bool(matches), "new_proposal_task_fields": task_fields,
              "scientific_support_and_cost_remain_unknown": uncertainty,
              "input_preserved": item["input_preserved"], "obvious_solution_phrase_absent": no_phrase_leak,
              "expected_typed_ast_and_dimensions_consistent": program_match,
              "all_input_records_within_cutoff": dates_match, "source_ids_in_catalog": references_match}
    return {"checks": checks, "passed": all(checks.values()),
            "evaluation_only_direction": expected["historical_direction"],
            "evaluation_source_ids": expected["evaluation_source_ids"],
            "interpretation": "New proposal-task coverage only; no historical solution or scientific discovery was verified."}


def run():
    started = time.perf_counter()
    manifest = read_json(HERE / "manifest.json")
    entries = manifest["cases"]
    specs = {e["id"]: read_json(HERE / e["input"]) for e in entries}
    # Evaluation targets are intentionally loaded only after every discovery call.
    results = {e["id"]: invoke(specs[e["id"]]) for e in entries}
    history = next(e["id"] for e in entries if e["historical"])
    work = next(e["id"] for e in entries if not e["historical"])
    controls = negative_controls(specs[history], results[history], specs[work])
    targets = read_json(HERE / manifest["evaluation_only"])
    sources = read_json(HERE / manifest["source_catalog"])
    cases = []
    for entry in entries:
        item = results[entry["id"]]
        item.update(id=entry["id"], historical=entry["historical"])
        item["evaluation"] = evaluate(item, targets["cases"][entry["id"]], sources)
        cases.append(item)
    passed = all(c["evaluation"]["passed"] for c in cases) and all(c["passed"] for c in controls)
    return {"assurance": manifest["assurance"], "passed": passed,
            "execution_order": ["load-inputs", "discover-cases", "discover-negative-controls", "load-evaluation-targets", "score", "save"],
            "cases": cases, "negative_controls": controls, "source_catalog": sources,
            "cost": {"software_wall_seconds": time.perf_counter() - started,
                     "model_calls": 0, "scientific_experiments": 0, "scientific_execution_cost": "UNKNOWN"},
            "limitations": ["Famous historical answers may already be in model training; no unknown-discovery claim is tested.",
                            "The first two availability dates are explicit retrospective approximations, not verified complete historical knowledge snapshots.",
                            "Gap matches test proposal-task generation from configured goals, not generation quality, rank rescue, causal truth or empirical advancement.",
                            "Forbidden-phrase checks are a small leakage smoke check, not proof of no semantic leakage."]}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results/latest.json")
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "cases": len(report["cases"]),
                      "negative_controls": {c["id"]: c["passed"] for c in report["negative_controls"]},
                      "output": str(args.output.resolve()), "assurance": report["assurance"]}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)

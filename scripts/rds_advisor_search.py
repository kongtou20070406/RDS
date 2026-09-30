"""Bounded search over explicitly configured reasoning dependencies.

No text eval, causal discovery, probability estimates, source verification or run
execution. Facts and observed costs supplied by callers remain INPUT_REPORTED.
"""
from copy import deepcopy
import math

TRUE, FALSE, UNKNOWN = "TRUE", "FALSE", "UNKNOWN"


def _source(record):
    source = record.get("source")
    return ((isinstance(source, str) and bool(source.strip())) or
            (isinstance(source, dict) and any(isinstance(source.get(k), str) and source[k].strip()
             for k in ("path", "url", "receipt_id", "locator"))))


def _reported(record):
    return (isinstance(record, dict) and _source(record) and record.get("reliable") is not False
            and record.get("reliability") not in ("UNRELIABLE", "UNKNOWN"))


def _finite(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def evaluate_condition(condition, facts):
    """Return three-valued truth and its input evidence, without certifying it."""
    name = condition.get("fact") if isinstance(condition, dict) else None
    record = facts.get(name) if isinstance(name, str) else None
    report = {"fact": name, "operator": condition.get("op", "eq") if isinstance(condition, dict) else None,
              "expected": deepcopy(condition.get("value")) if isinstance(condition, dict) else None,
              "truth": UNKNOWN, "evidence_status": "INPUT_REPORTED"}
    if not _reported(record) or "value" not in record or record["value"] is None:
        report["reason"] = "missing value/source or explicitly unreliable evidence"
        return report
    value, expected, op = record["value"], report["expected"], report["operator"]
    report.update(actual=deepcopy(value), source=deepcopy(record["source"]))
    if op in {"eq", "ne"}:
        equal = value == expected and (not isinstance(value, bool) and not isinstance(expected, bool)
                                      or type(value) is type(expected))
        answer = equal if op == "eq" else not equal
    elif op == "in" and isinstance(expected, list):
        answer = any(value == item and (not isinstance(value, bool) and not isinstance(item, bool)
                                       or type(value) is type(item)) for item in expected)
    elif op in {"lt", "lte", "gt", "gte"} and _finite(value) and _finite(expected):
        answer = {"lt": value < expected, "lte": value <= expected,
                  "gt": value > expected, "gte": value >= expected}[op]
    else:
        report["reason"] = "unsupported operator or incompatible value type"
        return report
    report.update(truth=TRUE if answer else FALSE, reason="comparison of sourced input, not independent verification")
    return report


def _all(reports):
    truths = [r["truth"] for r in reports]
    return FALSE if FALSE in truths else UNKNOWN if UNKNOWN in truths else TRUE


def _action_valid(action, current_choice):
    if not isinstance(action, dict) or not isinstance(action.get("id"), str):
        return False, "missing action identity"
    outcomes = action.get("outcomes", [])
    if not isinstance(outcomes, list) or not all(isinstance(o, dict) and isinstance(o.get("observation"), str)
            and isinstance(o.get("next_decision"), str) and o["next_decision"].strip() for o in outcomes):
        return False, "outcomes must bind observations to next decisions"
    decisions = {o["next_decision"] for o in outcomes}
    if len(decisions) < 2 and not (action.get("kind") == "INTERPRETATION_UPDATE" and current_choice
                                 and decisions and current_choice not in decisions):
        return False, "no outcome can distinguish next decisions"
    if not action.get("description") or not isinstance(action.get("competing_explanations"), list) or len(action["competing_explanations"]) < 2:
        return False, "missing competing explanations or action"
    if not isinstance(action.get("required_observables"), list) or not action["required_observables"]:
        return False, "missing required observables"
    return True, None


def _cost(ids, costs):
    records = [costs.get(i) for i in ids]
    if not records or any(not _reported(r) or not _finite(r.get("value")) or r["value"] < 0
                          or not r.get("unit") or not r.get("comparison_group") for r in records):
        return {"status": UNKNOWN, "reason": "missing sourced, comparable observed incremental cost"}
    groups = {(r["unit"], r["comparison_group"]) for r in records}
    total = sum(r["value"] for r in records)
    if len(groups) != 1 or not _finite(total):
        return {"status": UNKNOWN, "reason": "mixed units/comparison groups or nonfinite total"}
    unit, group = groups.pop()
    return {"status": "INPUT_REPORTED", "value": total, "unit": unit, "comparison_group": group,
            "sources": [deepcopy(r["source"]) for r in records], "components": list(ids)}


def search_directions(graph, context, *, max_candidates=12, max_depth=8, max_nodes=128):
    """Compose source-labelled checks and tests for the supplied next decision.

    Nodes opt in via executable.decisions, preconditions, satisfied_when, action.
    Only prerequisite_for edges are traversed; other relations stay descriptive.
    UNKNOWN prerequisites produce read-only queries, FALSE prerequisites prevent
    the downstream test. A configured condition.on_false can offer a repair.
    """
    if not isinstance(graph, dict) or not isinstance(context, dict):
        raise ValueError("Graph and advisor context must be objects")
    for value, cap, name in ((max_candidates, 64, "max_candidates"), (max_depth, 32, "max_depth"), (max_nodes, 512, "max_nodes")):
        if type(value) is not int or not 1 <= value <= cap:
            raise ValueError(f"{name} must be an integer between 1 and {cap}")
    raw_nodes, raw_edges = graph.get("nodes", []), graph.get("edges", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("Graph nodes/edges must be lists")
    decision = context.get("decision")
    decision_id = decision.get("id") if isinstance(decision, dict) else decision
    targets = decision.get("target_rules") if isinstance(decision, dict) else None
    current_choice = decision.get("current_choice") if isinstance(decision, dict) else None
    result = {"advisor_type": "EXECUTABLE_DIRECTION_SEARCH", "decision": deepcopy(decision), "candidates": [],
              "blocked_candidates": [], "discarded_candidates": [], "queries": [], "cycles": [],
              "truncation": {"truncated": False, "reasons": [], "limits": {
                  "max_candidates": max_candidates, "max_depth": max_depth, "max_nodes": max_nodes}},
              "ranking": {"method": "PARETO_PARTIAL_ORDER", "dominance": [], "cost_unknown": []},
              "limitations": ["Derivations are reasoning dependencies, not causal proof. Sources and costs remain INPUT_REPORTED.",
                               "Only explicit executable configuration is searched; text triggers and unconfigured rules are not evaluated."]}
    if not isinstance(decision_id, str) or not decision_id.strip():
        result["limitations"].append("No next decision supplied; no test was inferred.")
        return result
    facts, costs = context.get("facts", {}), context.get("costs", {})
    if not isinstance(facts, dict) or not isinstance(costs, dict):
        raise ValueError("Context facts/costs must be objects")
    budget = context.get("budget", {})
    nodes = {}
    for node in raw_nodes[:max_nodes]:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or node["id"] in nodes:
            raise ValueError("Each graph node needs a unique string id")
        nodes[node["id"]] = node
    if len(raw_nodes) > max_nodes:
        result["truncation"].update(truncated=True)
        result["truncation"]["reasons"].append("node limit")
    parents = {n: [] for n in nodes}
    for edge in raw_edges:
        if isinstance(edge, dict) and edge.get("relation") == "prerequisite_for" and edge.get("to") in nodes:
            parents[edge["to"]].append(edge.get("from"))
    queries = {}
    candidates = {}
    memo = {}

    def query(rule_id, condition, reason):
        name = condition.get("fact", f"rule:{rule_id}:satisfied")
        query_id = f"query:{rule_id}:{name}"
        item = {"id": query_id, "rule_id": rule_id, "fact": name, "reason": reason,
                "kind": "READ_ONLY_EVIDENCE_REQUEST", "query": condition.get("query") or
                f"Read the code/log or original receipt for '{name}'; record its value and exact source locator under the same run identity.",
                "outcomes": [{"observation": "required predicate supported", "next_decision": "allow dependent check"},
                             {"observation": "required predicate contradicted", "next_decision": "block or revise dependent test"}]}
        queries[query_id] = item
        return query_id

    def emit(rule_id, action, status, derivation, pending=()):
        valid, reason = _action_valid(action, current_choice)
        if not valid:
            result["discarded_candidates"].append({"rule_id": rule_id, "reason": reason})
            return
        candidate_id = f"{rule_id}:{action['id']}"
        if candidate_id in candidates:
            return
        if len(candidates) >= max_candidates:
            result["truncation"].update(truncated=True)
            if "candidate limit" not in result["truncation"]["reasons"]:
                result["truncation"]["reasons"].append("candidate limit")
            return
        steps = [deepcopy(queries[q]) for q in dict.fromkeys(pending)]
        steps.append({"id": action["id"], "rule_id": rule_id, "kind": action.get("kind", "BOUNDED_CHECK"),
                      "description": action["description"], "conditional": status != "READY",
                      "stop_condition": action.get("stop_condition", "Stop on budget limit or invalid prerequisites.")})
        cost = _cost([step["id"] for step in steps], costs)
        budget_status = UNKNOWN
        if cost["status"] != UNKNOWN and _reported(budget) and _finite(budget.get("value")) and budget["value"] >= 0:
            if (budget.get("unit"), budget.get("comparison_group")) == (cost["unit"], cost["comparison_group"]):
                budget_status = "WITHIN_REPORTED_BUDGET" if cost["value"] <= budget["value"] else "OVER_REPORTED_BUDGET"
        candidate = {"id": candidate_id, "rule_id": rule_id, "status": status, "action": deepcopy(action),
                     "competing_explanations": deepcopy(action["competing_explanations"]),
                     "required_observables": deepcopy(action["required_observables"]), "outcomes": deepcopy(action["outcomes"]),
                     "decision_coverage": sorted({o["next_decision"] for o in action["outcomes"]}),
                     "steps": steps, "derivation": deepcopy(derivation) + [{"step": "action", "rule_id": rule_id,
                         "action_id": action["id"], "reason": "outcomes distinguish declared next decisions"}],
                     "incremental_cost": cost, "budget_status": budget_status, "dominated_by": [],
                     "evidence_status": "INPUT_REPORTED"}
        if budget_status == "OVER_REPORTED_BUDGET":
            candidate["status"] = "BLOCKED_BUDGET"
            result["blocked_candidates"].append(candidate)
        else:
            candidates[candidate_id] = candidate

    def conditions(rule_id, cfg, key, derivation, pending, fallbacks):
        items = cfg.get(key, [])
        if not isinstance(items, list) or len(items) > 32 or not all(isinstance(c, dict) and isinstance(c.get("fact"), str) for c in items):
            raise ValueError(f"{rule_id}.{key} must be up to 32 explicit fact conditions")
        reports = []
        for condition in items:
            report = evaluate_condition(condition, facts)
            derivation.append({"step": "fact_to_rule", "rule_id": rule_id, "role": key, **report})
            reports.append(report)
            if report["truth"] == UNKNOWN:
                pending.append(query(rule_id, condition, report["reason"]))
            elif report["truth"] == FALSE and isinstance(condition.get("on_false"), dict):
                fallbacks.append((rule_id, condition["on_false"], deepcopy(derivation)))
        return _all(reports)

    def visit(rule_id, path, derivation, pending, fallbacks, as_prerequisite=True):
        if rule_id in path:
            cycle = path[path.index(rule_id):] + [rule_id]
            if cycle not in result["cycles"]:
                result["cycles"].append(cycle)
            derivation.append({"step": "cycle", "path": cycle})
            return FALSE
        if len(path) >= max_depth:
            result["truncation"].update(truncated=True)
            if "depth limit" not in result["truncation"]["reasons"]:
                result["truncation"]["reasons"].append("depth limit")
            derivation.append({"step": "depth_limit", "rule_id": rule_id})
            return FALSE
        if as_prerequisite and rule_id in memo:
            derivation.append({"step": "dependency_reuse", "rule_id": rule_id, "truth": memo[rule_id]})
            return memo[rule_id]
        node = nodes.get(rule_id, {})
        cfg = node.get("executable")
        if not isinstance(cfg, dict) or not isinstance(cfg.get("preconditions"), list):
            pending.append(query(rule_id, {"query": f"Review original rule '{rule_id}', its scope and sources; supply explicit bounded prerequisite conditions before treating it as satisfied."}, "no executable prerequisite configuration"))
            derivation.append({"step": "unconfigured_prerequisite", "rule_id": rule_id, "truth": UNKNOWN})
            memo[rule_id] = UNKNOWN
            return UNKNOWN
        applicability = conditions(rule_id, cfg, "preconditions", derivation, pending, fallbacks)
        if applicability == FALSE:
            memo[rule_id] = FALSE
            return FALSE
        statuses = [applicability]
        for parent in dict.fromkeys(parents.get(rule_id, [])):
            derivation.append({"step": "dependency", "from": parent, "relation": "prerequisite_for", "to": rule_id})
            statuses.append(visit(parent, path + [rule_id], derivation, pending, fallbacks))
        if as_prerequisite:
            if not isinstance(cfg.get("satisfied_when"), list) or not cfg["satisfied_when"]:
                pending.append(query(rule_id, {}, "no explicit completion predicate"))
                statuses.append(UNKNOWN)
            else:
                statuses.append(conditions(rule_id, cfg, "satisfied_when", derivation, pending, fallbacks))
        truth = FALSE if FALSE in statuses else UNKNOWN if UNKNOWN in statuses else TRUE
        memo[rule_id] = truth
        return truth

    roots = [rid for rid, node in nodes.items() if isinstance(node.get("executable"), dict)
             and decision_id in node["executable"].get("decisions", []) and (targets is None or rid in targets)]
    for rid in roots:
        memo.clear()
        action = nodes[rid]["executable"].get("action")
        valid, reason = _action_valid(action, current_choice)
        if not valid:
            result["discarded_candidates"].append({"rule_id": rid, "reason": reason})
            continue
        derivation = [{"step": "decision_to_rule", "decision": decision_id, "rule_id": rid,
                       "rule_sources": deepcopy(nodes[rid].get("sources", []))}]
        pending, fallbacks = [], []
        status = visit(rid, [], derivation, pending, fallbacks, as_prerequisite=False)
        for fallback_rid, fallback, chain in fallbacks:
            emit(fallback_rid, fallback, "READY", chain)
        if status == FALSE:
            result["blocked_candidates"].append({"rule_id": rid, "action_id": action["id"], "status": "BLOCKED_PREREQUISITE",
                                                  "reason": "false prerequisite, cycle or bounded-search limit", "derivation": derivation})
        else:
            emit(rid, action, "READY" if status == TRUE else "NEEDS_EVIDENCE", derivation, pending)
    result["candidates"] = list(candidates.values())
    used_queries = {step["id"] for candidate in result["candidates"] for step in candidate["steps"] if step["kind"] == "READ_ONLY_EVIDENCE_REQUEST"}
    result["queries"] = [q for qid, q in queries.items() if qid in used_queries]
    for worse in result["candidates"]:
        wcost = worse["incremental_cost"]
        if wcost["status"] == UNKNOWN:
            result["ranking"]["cost_unknown"].append(worse["id"])
            continue
        for better in result["candidates"]:
            bcost = better["incremental_cost"]
            if better is worse or bcost["status"] == UNKNOWN or better["status"] != worse["status"]:
                continue
            if (bcost["unit"], bcost["comparison_group"]) != (wcost["unit"], wcost["comparison_group"]):
                continue
            bcov, wcov = set(better["decision_coverage"]), set(worse["decision_coverage"])
            if bcov >= wcov and bcost["value"] <= wcost["value"] and (bcov != wcov or bcost["value"] < wcost["value"]):
                worse["dominated_by"].append(better["id"])
                result["ranking"]["dominance"].append({"better": better["id"], "worse": worse["id"],
                    "basis": "decision coverage superset and no higher comparable observed incremental cost"})
    result["ranking"]["pareto_front"] = [c["id"] for c in result["candidates"] if not c["dominated_by"]]
    return result

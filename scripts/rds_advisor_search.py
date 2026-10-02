"""Bounded search over explicitly configured reasoning dependencies.

No text eval, causal discovery, probability estimates or run execution. Imported
artifacts retain their provenance labels; caller dictionaries remain INPUT_REPORTED.
"""
from copy import deepcopy
from itertools import combinations
import math

TRUE, FALSE, UNKNOWN = "TRUE", "FALSE", "UNKNOWN"


def _evidence_status(record):
    # A JSON flag cannot impersonate the read-only artifact importer's type.
    try:
        from rds_artifacts import ArtifactFact
    except ImportError:
        return "INPUT_REPORTED"
    if isinstance(record, ArtifactFact):
        status = getattr(record, "provenance_status", "UNKNOWN")
        if status in {"ARTIFACT_OBSERVED", "ARTIFACT_DECLARED", "PROGRAM_DERIVED", "UNKNOWN"}:
            return status
    return "INPUT_REPORTED"


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
              "truth": UNKNOWN, "evidence_status": _evidence_status(record)}
    if not _reported(record) or "value" not in record or record["value"] is None:
        report["reason"] = "missing value/source or explicitly unreliable evidence"
        return report
    value, expected, op = record["value"], report["expected"], report["operator"]
    report.update(actual=deepcopy(value), source=deepcopy(record["source"]))
    if not isinstance(op, str):
        report["reason"] = "unsupported operator or incompatible value type"
        return report
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
    if action.get("kind") == "OBLIGATION_CHECK":
        if not all(isinstance(action.get(k), str) and action[k].strip() for k in ("description", "target", "claim")):
            return False, "obligation checks need an explicit target and scoped claim"
        labels = [o["observation"] for o in outcomes]
        if len(labels) != 3 or set(labels) != {"verified", "counterexample", "unresolved"}:
            return False, "obligation outcomes must distinguish verified, counterexample and unresolved"
        if "discrimination" in action:
            return False, "obligation checks cannot claim empirical rival discrimination"
    elif not action.get("description") or not isinstance(action.get("competing_explanations"), list) or len(action["competing_explanations"]) < 2:
        return False, "missing competing explanations or action"
    if not isinstance(action.get("required_observables"), list) or not action["required_observables"]:
        return False, "missing required observables"
    return True, None


def _cost_identity(record):
    if not isinstance(record, dict):
        return None
    for key in ("resource", "unit", "comparison_group"):
        if key == "resource" and key not in record:  # Legacy costs omit resource entirely.
            continue
        value = record.get(key)
        if not isinstance(value, str) or not value.strip() or value.strip().upper() == UNKNOWN:
            return None
    return record.get("resource"), record["unit"], record["comparison_group"]


def _cost(ids, costs):
    records = [costs.get(i) for i in ids]
    if not records or any(not _reported(r) or not _finite(r.get("value")) or r["value"] < 0
                          or _cost_identity(r) is None for r in records):
        return {"status": UNKNOWN, "reason": "missing sourced, comparable incremental cost"}
    groups = {_cost_identity(r) for r in records}
    total = sum(r["value"] for r in records)
    if len(groups) != 1 or not _finite(total):
        return {"status": UNKNOWN, "reason": "mixed resources/units/comparison groups or nonfinite total"}
    resource, unit, group = groups.pop()
    return {"status": "INPUT_REPORTED", "value": total, "unit": unit, "comparison_group": group,
            **({"resource": resource} if resource is not None else {}),
            "sources": [deepcopy(r["source"]) for r in records], "components": list(ids),
            "evidence_statuses": [_evidence_status(r) for r in records]}


def _discrimination(action, facts):
    """Describe conditional rival-pair coverage from supplied prediction sets."""
    spec = action.get("discrimination")
    spec = spec if isinstance(spec, dict) else {}
    explanations = action["competing_explanations"]
    issues = []
    if not (2 <= len(explanations) <= 32 and all(isinstance(e, str) and e.strip() for e in explanations)
            and len(set(explanations)) == len(explanations)):
        issues.append("competing_explanations must be 2 to 32 unique explanation IDs")
        explanations = []
    explanations = sorted(explanations)
    scope = spec.get("scope_id")
    if not isinstance(scope, str) or not scope.strip():
        issues.append("missing explicit scope_id")
    if not _reported(spec):
        issues.append("missing sourced or reliable prediction support")
    allowed = {outcome["observation"] for outcome in action["outcomes"]}
    predictions = spec.get("predictions")
    if not (isinstance(predictions, dict) and set(predictions) == set(explanations) and explanations
            and all(isinstance(labels, list) and 1 <= len(labels) <= 32
                    and all(isinstance(label, str) and label in allowed for label in labels)
                    for labels in predictions.values())):
        issues.append("predictions must give 1 to 32 declared outcome labels for every explanation ID")
    conditions = spec.get("conditions", [])
    reports = []
    if not (isinstance(conditions, list) and len(conditions) <= 32
            and all(isinstance(c, dict) and isinstance(c.get("fact"), str) and c["fact"].strip() for c in conditions)):
        issues.append("conditions must be up to 32 explicit fact predicates")
        applicability = UNKNOWN
    else:
        reports = [evaluate_condition(condition, facts) for condition in conditions]
        applicability = _all(reports)
    supported = not issues and applicability == TRUE
    distinguishing, unresolved = [], []
    for pair in combinations(explanations, 2):
        if not supported:
            reason = "; ".join(issues) if issues else "prediction applicability is " + applicability
        elif set(predictions[pair[0]]).isdisjoint(predictions[pair[1]]):
            distinguishing.append(list(pair))
            continue
        else:
            reason = "allowed predictions overlap"
        unresolved.append({"pair": list(pair), "reason": reason})
    return {"scope_id": deepcopy(scope), "source": deepcopy(spec.get("source")),
            "evidence_status": _evidence_status(spec), "conditions": reports,
            "applicability": applicability, "valid_prediction_support": supported,
            "conditional_distinguishing_pairs": distinguishing, "unresolved_pairs": unresolved,
            "issues": issues}


def _next_move(review, search):
    """Suggest a bounded reasoning step from input review, without changing a route."""
    flags = {f["kind"] for f in review["flags"]}
    ready_ids = {c["id"] for c in review["candidates"]}
    history_flags = search.get("loop_review", {}).get("flags", [])
    loop_flags = {f.get("kind") for f in history_flags
                  if f.get("kind") not in {"REPEAT_REJECTED_ROUTE", "REPEAT_DECLARED_REJECTED_DOMAIN"}
                  or not ready_ids or f.get("candidate_id") in ready_ids}
    if "DECISION_OSCILLATION" in loop_flags and ready_ids:
        if not any(ready_ids.intersection(f.get("candidate_ids", []))
                   for f in history_flags if f.get("kind") == "DECISION_OSCILLATION"):
            loop_flags.remove("DECISION_OSCILLATION")
    # Local warnings remain visible, but do not block an available supported route.
    supported_route = any(c["basis"] == "SCOPED_OBLIGATION" or
                          (c["basis"] == "CONDITIONAL_RIVAL_TEST" and not c["unresolved_pairs"])
                          for c in review["candidates"])
    goal = review.get("goal", {})
    pending = any(c.get("status") in {"NEEDS_EVIDENCE", "NEEDS_METHOD_CLARIFICATION", "NEEDS_METHOD_DESCRIPTION"}
                  for c in search.get("candidates", []))
    blocked = any(c.get("status") in {"BLOCKED_PREREQUISITE", "BLOCKED_METHOD", "BLOCKED_BUDGET"}
                  for c in search.get("blocked_candidates", []))
    if "LOOP_HISTORY_REVIEW_ERROR" in loop_flags:
        kind, reason = "RESOLVE_PREMISE", "Recorded history integrity is unresolved; inspect the existing loop review."
    elif goal.get("status") == UNKNOWN or any(c["truth"] == UNKNOWN for c in goal.get("conditions", [])):
        kind, reason = "RESOLVE_PREMISE", "The original goal has unresolved evidence; no scientific failure is established."
    elif ("PREDICTION_PREMISES_UNRESOLVED" in flags and not supported_route) or (not ready_ids and (pending or blocked)):
        kind, reason = "RESOLVE_PREMISE", "Resolve the affected evidence, prediction scope, method or budget conditions first."
    elif "SEARCH_TRUNCATED" in flags:
        kind, reason = "RESOLVE_PREMISE", "The bounded search omitted part of the supplied scope."
    elif loop_flags & {"REPEAT_REJECTED_ROUTE", "REPEAT_DECLARED_REJECTED_DOMAIN", "DECISION_OSCILLATION"}:
        kind, reason = "REFORMULATE", "Recorded choices repeat a rejected route/domain or oscillate within the reviewed scope."
    elif goal.get("status") == TRUE or (review["basis"] == "SCOPED_OBLIGATION" and goal.get("status") != FALSE):
        return None
    elif "RIVAL_PREDICTIONS_OVERLAP" in flags and not supported_route:
        kind, reason = "DESIGN_DISCRIMINATOR", "Supported same-scope prediction sets overlap; seek a distinguishing observation."
    elif goal.get("status") == FALSE:
        kind, reason = "REFORMULATE", "The reported goal predicate failed; this is a scoped gap, not a capacity lower bound or a causal diagnosis."
    elif {"SINGLE_CONFIGURED_DIRECTION", "RIVAL_PREDICTIONS_MISSING"} <= flags and not supported_route:
        kind, reason = "REVIEW_ALTERNATIVE", "One procedure was supplied; review a useful alternative if it could change the decision."
    elif "RIVAL_PREDICTIONS_MISSING" in flags and not supported_route:
        kind, reason = "DESIGN_DISCRIMINATOR", "The supplied procedures do not yet bind competing predictions to outcomes."
    elif not review["ready_graph_directions"]:
        kind, reason = "RESOLVE_PREMISE", "No ready direction is defined; inspect the existing queries and candidate reviews."
    else:
        return None
    prompt = (
        "Resolve only the affected evidence or scope using original sources and explicit predicates; keep UNKNOWN where unsupported. "
        "State the smallest deciding observation or proof check and its stop condition. Continue independent authorized work. "
        if kind == "RESOLVE_PREMISE" else
        "Retain the existing rival hypotheses and design one observation or scoped proof check with different predictions. "
        "Give the counterfactual difference each rival predicts, the check's cost and a stop condition. "
        if kind == "DESIGN_DISCRIMINATOR" else
        "Propose one concrete candidate changing an assumption, representation or computational method, and compare it with the smallest repair. "
        "Give a counterfactual difference: which observation or scoped proof obligation differs if the proposed change is made? "
        "State a decisive check, its cost and a stop condition; added complexity is not itself progress. "
        "Renaming alone supplies no new mechanism; route identity here is structured input, not semantic equivalence. "
    )
    return {"kind": kind, "reason": reason, "basis": "INPUT_REVIEW_HEURISTIC_NOT_SCIENTIFIC_PROOF",
            "authorization": "UNCHANGED",
            "preserve_refs": ["search.decision", "context.budget", "context.resources", "context.method_constraints"],
            "prompt": prompt + "Preserve the original goal, scope, revision, budget and method constraints in the referenced inputs. "
                      "Respect an explicitly chosen route; this suggestion does not interrupt it or authorize execution. "
                      "Unknown evidence or a scoped failure does not establish a capacity lower bound."}


def review_selection(search, context):
    """Expose what the supplied directions can decide; never invent utility."""
    ready = [c for c in search.get("candidates", []) if c.get("status") == "READY"]
    flags, candidates = [], []
    if search.get("truncation", {}).get("truncated"):
        flags.append({"kind": "SEARCH_TRUNCATED", "next": "Review the omitted search scope before claiming a best route."})
    obligations = all(c.get("action", {}).get("kind") == "OBLIGATION_CHECK" for c in ready)
    if len(ready) == 1 and not obligations:
        flags.append({"kind": "SINGLE_CONFIGURED_DIRECTION", "next": "Only one ready graph direction was supplied; review a serious alternative when it could change the decision."})
    for c in ready:
        report = {"id": c["id"], "basis": "SCOPED_OBLIGATION"}
        if c.get("action", {}).get("kind") != "OBLIGATION_CHECK":
            disc = c.get("discrimination")
            if disc is None:
                report["basis"] = "PROCEDURE_ONLY"
                flags.append({"kind": "RIVAL_PREDICTIONS_MISSING", "candidate": c["id"],
                              "next": "Bind same-scope rival predictions to observed outcomes, or describe this as a premise/procedure check."})
            elif not disc["valid_prediction_support"]:
                report["basis"] = "PREDICTION_PREMISES_UNRESOLVED"
                flags.append({"kind": "PREDICTION_PREMISES_UNRESOLVED", "candidate": c["id"],
                              "next": "Resolve the prediction's evidence and scope conditions before using its rival coverage."})
            elif not disc["conditional_distinguishing_pairs"]:
                report["basis"] = "NONDISCRIMINATING"
                flags.append({"kind": "RIVAL_PREDICTIONS_OVERLAP", "candidate": c["id"],
                              "next": "Find an observation with different rival predictions; shared pass/fail labels do not distinguish causes."})
            else:
                report.update(basis="CONDITIONAL_RIVAL_TEST", distinguishing_pairs=len(disc["conditional_distinguishing_pairs"]),
                              unresolved_pairs=len(disc["unresolved_pairs"]))
                if disc["unresolved_pairs"]:
                    flags.append({"kind": "RIVAL_PREDICTIONS_OVERLAP", "candidate": c["id"],
                                  "next": "Some rival predictions still overlap; identify which additional observation would distinguish them."})
        candidates.append(report)
    basis = "NO_READY_DIRECTION" if not ready else "SCOPED_OBLIGATION" if obligations else "REVIEW_ONLY"
    # Ranking can also compare conditional routes whose prerequisites remain open.
    ready_ids = {c["id"] for c in ready}
    if any(row["better"] in ready_ids and row["worse"] in ready_ids
           for row in search.get("ranking", {}).get("dominance", [])):
        basis = "CONDITIONAL_COMPARISON"
    review = {"basis": basis, "ready_graph_directions": len(ready), "candidates": candidates, "flags": flags,
              "assurance": "INPUT_REPORTED_NOT_SCIENTIFIC_VERIFICATION", "authorization": "UNCHANGED"}
    decision = context.get("decision")
    if isinstance(decision, dict) and "goal_conditions" in decision:
        goals = decision["goal_conditions"]
        if not (isinstance(goals, list) and 1 <= len(goals) <= 32 and all(
                isinstance(g, dict) and isinstance(g.get("fact"), str) and g["fact"].strip() for g in goals)):
            raise ValueError("decision.goal_conditions must be 1 to 32 explicit fact predicates")
        facts = context.get("facts", {})
        if not isinstance(facts, dict):
            raise ValueError("Context facts must be an object for decision.goal_conditions")
        reports = [evaluate_condition(g, facts) for g in goals]
        review["goal"] = {"status": _all(reports), "conditions": reports, "assurance": "INPUT_REPORTED"}
        if review["goal"]["status"] != TRUE:
            flags.append({"kind": "GOAL_BRIDGE_OPEN", "next": "Keep task acceptance separate from local/procedure success; choose a check or intervention that can close this declared gap."})
    next_move = _next_move(review, search)
    if next_move is not None:
        review["next_move"] = next_move
    return review


def search_directions(graph, context, *, max_candidates=12, max_depth=8, max_nodes=128,
                      templates=None, max_combinations=128, max_compose_depth=2):
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
              "limitations": ["Derivations are reasoning dependencies, not causal proof. Imported source labels do not certify causal claims.",
                               "Only explicit executable configuration is searched; text triggers and unconfigured rules are not evaluated.",
                               "Dominance requires valid same-scope rival predictions; decision labels alone do not establish scientific value."]}
    def finish():
        chosen_templates = templates if templates is not None else context.get("templates")
        if chosen_templates is not None:
            from rds_experiments import compose_experiments
            result["experiment_composition"] = compose_experiments(
                graph, context, chosen_templates, max_candidates=max_candidates, max_depth=max_compose_depth,
                max_combinations=max_combinations,
                search_limits={"max_candidates": max_candidates, "max_depth": max_depth, "max_nodes": max_nodes})
        result["selection_review"] = review_selection(result, context)
        return result
    if len(raw_nodes) > max_nodes:
        result["truncation"].update(truncated=True)
        result["truncation"]["reasons"].append("node limit")
    if not isinstance(decision_id, str) or not decision_id.strip():
        result["limitations"].append("No next decision supplied; no test was inferred.")
        return finish()
    facts, costs = context.get("facts", {}), context.get("costs", {})
    if not isinstance(facts, dict) or not isinstance(costs, dict):
        raise ValueError("Context facts/costs must be objects")
    budget = context.get("budget", {})
    nodes = {}
    for node in raw_nodes[:max_nodes]:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or node["id"] in nodes:
            raise ValueError("Each graph node needs a unique string id")
        nodes[node["id"]] = node
    parents = {n: [] for n in nodes}
    for edge in raw_edges:
        if isinstance(edge, dict) and edge.get("relation") == "prerequisite_for" and edge.get("to") in nodes:
            parents[edge["to"]].append(edge.get("from"))
    queries = {}
    candidates = {}
    memo = {}

    def discard(rule_id, action, reason):
        record = {"rule_id": rule_id, "reason": reason}
        if isinstance(action, dict) and isinstance(action.get("id"), str):
            record.update(id=f"{rule_id}:{action['id']}", action_id=action["id"])
        result["discarded_candidates"].append(record)

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
            discard(rule_id, action, reason)
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
            if _cost_identity(budget) == _cost_identity(cost):
                budget_status = "WITHIN_REPORTED_BUDGET" if cost["value"] <= budget["value"] else "OVER_REPORTED_BUDGET"
        candidate = {"id": candidate_id, "rule_id": rule_id, "status": status, "action": deepcopy(action),
                     "competing_explanations": deepcopy(action.get("competing_explanations", [])),
                     "required_observables": deepcopy(action["required_observables"]), "outcomes": deepcopy(action["outcomes"]),
                     "decision_coverage": sorted({o["next_decision"] for o in action["outcomes"]}),
                     "steps": steps, "derivation": deepcopy(derivation) + [{"step": "action", "rule_id": rule_id,
                         "action_id": action["id"], "reason": "outcomes distinguish declared next decisions"}],
                     "incremental_cost": cost, "budget_status": budget_status, "dominated_by": [],
                     "evidence_status": "INPUT_REPORTED"}
        if "discrimination" in action:
            candidate["discrimination"] = _discrimination(action, facts)
        from rds_methods import review_candidate
        review_candidate(context, candidate)
        if budget_status == "OVER_REPORTED_BUDGET":
            candidate["status"] = "BLOCKED_BUDGET"
            result["blocked_candidates"].append(candidate)
        elif candidate["status"] == "BLOCKED_METHOD":
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
            discard(rid, action, reason)
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
            if _cost_identity(bcost) != _cost_identity(wcost):
                continue
            bdisc, wdisc = better.get("discrimination"), worse.get("discrimination")
            if (bdisc is None or wdisc is None or not bdisc["valid_prediction_support"]
                    or not wdisc["valid_prediction_support"] or bdisc["scope_id"] != wdisc["scope_id"]
                    or set(better["competing_explanations"]) != set(worse["competing_explanations"])):
                continue
            bpairs = {tuple(pair) for pair in bdisc["conditional_distinguishing_pairs"]}
            wpairs = {tuple(pair) for pair in wdisc["conditional_distinguishing_pairs"]}
            if not bpairs or not wpairs or not bpairs >= wpairs:
                continue
            if bcost["value"] <= wcost["value"] and (bpairs != wpairs or bcost["value"] < wcost["value"]):
                worse["dominated_by"].append(better["id"])
                result["ranking"]["dominance"].append({"better": better["id"], "worse": worse["id"],
                    "basis": "supplied same-scope conditional distinguishing pairs are a superset and no higher comparable sourced incremental cost"})
    result["ranking"]["pareto_front"] = [c["id"] for c in result["candidates"] if not c["dominated_by"]]
    return finish()

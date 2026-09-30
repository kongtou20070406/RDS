"""Finite experiment proposals; no experiment execution or inferred probabilities."""
from copy import deepcopy
import hashlib
from itertools import combinations
import json

from rds_advisor_search import TRUE, FALSE, UNKNOWN, evaluate_condition, search_directions, _finite, _cost, _cost_identity, _reported


def _token(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _typed(value, kind):
    return ((kind == "boolean" and type(value) is bool) or
            (kind == "string" and isinstance(value, str) and bool(value.strip())) or
            (kind == "number" and _finite(value)))


def validate_template(template):
    """Validate only declared structure, never scientific applicability."""
    if not isinstance(template, dict) or not isinstance(template.get("id"), str) or not template["id"].strip():
        raise ValueError("Template needs a nonempty id")
    for key in ("rules", "decisions", "rival_explanations"):
        items = template.get(key)
        minimum = 2 if key == "rival_explanations" else 1
        if not isinstance(items, list) or not minimum <= len(items) <= 32 or not all(
                isinstance(item, str) and item.strip() for item in items):
            raise ValueError(f"Template {key} requires {minimum}..32 explicit strings")
    intervention = template.get("intervention", {})
    target = intervention.get("target", {}) if isinstance(intervention, dict) else {}
    if not isinstance(intervention, dict) or intervention.get("type") not in {"ablation", "parameter", "measurement", "read_only"}:
        raise ValueError("Unsupported intervention type")
    if not isinstance(target, dict) or not isinstance(target.get("name"), str) or not target["name"].strip() or target.get("type") not in {"number", "string", "boolean"}:
        raise ValueError("Intervention requires a named, typed target")
    choices = intervention.get("choices")
    if not isinstance(choices, list) or not 1 <= len(choices) <= 16 or not all(_typed(v, target["type"]) for v in choices):
        raise ValueError("Intervention choices must be 1..16 values of the declared type")
    for key in ("preconditions", "invariants"):
        conditions = template.get(key)
        if not isinstance(conditions, list) or len(conditions) > 32 or not all(
                isinstance(c, dict) and isinstance(c.get("fact"), str) for c in conditions):
            raise ValueError(f"Template {key} must be up to 32 fact conditions")
    for key in ("control_binding", "measurement"):
        binding = template.get(key)
        if not isinstance(binding, dict) or not isinstance(binding.get("fact"), str) or binding.get("type") not in {"number", "string", "boolean"}:
            raise ValueError(f"Template {key} requires a typed fact binding")
    outcomes = template.get("result_to_decision")
    if not isinstance(outcomes, list) or not 2 <= len(outcomes) <= 16 or not all(
            isinstance(o, dict) and isinstance(o.get("observation"), str) and o["observation"].strip()
            and isinstance(o.get("next_decision"), str) and o["next_decision"].strip() for o in outcomes):
        raise ValueError("Template requires explicit result-to-decision mappings")
    if len({o["next_decision"] for o in outcomes}) < 2:
        raise ValueError("Template outcomes do not distinguish decisions")
    if not isinstance(template.get("stop"), str) or not template["stop"].strip():
        raise ValueError("Template requires a stop condition")
    cost = template.get("cost")
    if not isinstance(cost, dict) or not isinstance(cost.get("record_id"), str) or not cost["record_id"].strip():
        raise ValueError("Template cost must name an observed cost record; missing values stay UNKNOWN")
    _token(template)  # Reject nonfinite/non-JSON values at the boundary.
    return template


def _binding(binding, facts):
    name = binding["fact"]
    record = facts.get(name, {})
    value = record.get("value") if isinstance(record, dict) else None
    report = evaluate_condition({"fact": name, "op": "eq", "value": value}, facts)
    if not _typed(value, binding["type"]):
        report.update(truth=UNKNOWN, reason="missing observable or incompatible declared fact type")
    return report


def _conflict(parts):
    targets, equalities, controls = {}, {}, set()
    for part in parts:
        intervention = part["intervention"]
        name = intervention["target"]["name"]
        key = _token(intervention)
        if name in targets and targets[name] != key:
            return "conflicting interventions on the same target"
        targets[name] = key
        for condition in part["template"]["invariants"]:
            if condition.get("op", "eq") == "eq":
                name, value = condition["fact"], _token(condition.get("value"))
                if name in equalities and equalities[name] != value:
                    return "contradictory equality invariants"
                equalities[name] = value
        binding = part["control"]
        if binding["truth"] == TRUE:
            controls.add(_token(binding.get("actual")))
    return "incompatible control bindings" if len(controls) > 1 else None


def compose_experiments(graph, context, templates, *, max_candidates=12,
                        max_depth=2, max_combinations=128, search_limits=None):
    """Enumerate compatible declared interventions, retaining unknown evidence.

    context.target_types maps target names to number/string/boolean. A missing
    declaration yields UNKNOWN; a contradictory type blocks the template.
    Every output remains a proposal, including templates provided by a model.
    """
    for value, cap, name in ((max_candidates, 64, "max_candidates"),
                             (max_depth, 4, "max_depth"),
                             (max_combinations, 512, "max_combinations")):
        if type(value) is not int or not 1 <= value <= cap:
            raise ValueError(f"{name} must be an integer in 1..{cap}")
    if not isinstance(context, dict) or not isinstance(graph, dict):
        raise ValueError("Graph and context must be objects")
    if isinstance(templates, dict) and (type(templates.get("schema")) is not int or templates["schema"] != 1):
        raise ValueError("Template pack requires schema 1")
    raw = templates.get("templates") if isinstance(templates, dict) else templates
    if not isinstance(raw, list) or len(raw) > 64:
        raise ValueError("At most 64 templates are allowed")
    for template in raw:
        validate_template(template)
    if len({t["id"] for t in raw}) != len(raw):
        raise ValueError("Template ids must be unique")
    facts = context.get("facts", {})
    target_types = context.get("target_types", {})
    if not isinstance(facts, dict) or not isinstance(target_types, dict):
        raise ValueError("Context facts and target_types must be objects")
    decision = context.get("decision")
    decision_id = decision.get("id") if isinstance(decision, dict) else decision
    search_context = deepcopy(context)
    search_context.pop("templates", None)
    base = search_directions(graph, search_context, **(search_limits or {}))
    ready = {c["rule_id"]: c for c in base["candidates"]}
    blocked = {c["rule_id"]: c for c in base["blocked_candidates"]}
    node_ids = {n.get("id") for n in graph.get("nodes", []) if isinstance(n, dict)}
    result = {"advisor_type": "FINITE_EXPERIMENT_COMPOSITION", "candidate_only": True,
              "execution_authorized": False, "candidates": [], "blocked_templates": [],
              "excluded_combinations": [], "rule_search": base,
              "truncation": {"truncated": base["truncation"]["truncated"],
                             "reasons": list(base["truncation"]["reasons"]),
                             "limits": {"max_candidates": max_candidates, "max_depth": max_depth,
                                        "max_combinations": max_combinations}},
              "combinations_examined": 0,
              "limitations": ["No experiment is executed; readiness is not admission.",
                              "Unknown observables remain UNKNOWN; no probability or information gain is inferred."]}
    variants = []
    for template in raw:
        if decision_id not in template["decisions"]:
            continue
        target = template["intervention"]["target"]
        declared = target_types.get(target["name"])
        reports = [evaluate_condition(c, facts) for c in template["preconditions"] + template["invariants"]]
        control = _binding(template["control_binding"], facts)
        measurement = _binding(template["measurement"], facts)
        rule_states, derivation = [], []
        for rid in template["rules"]:
            row = blocked.get(rid) or ready.get(rid)
            rule_states.append(FALSE if rid in blocked else
                               TRUE if row and row["status"] == "READY" else UNKNOWN)
            derivation.append({"step": "rule_to_template", "rule_id": rid,
                               "template_id": template["id"], "trace": deepcopy(row.get("derivation", [])) if row else [],
                               "reason": None if row else "rule is not executable for this decision"})
        if declared is not None and declared != target["type"]:
            reason = "incompatible target type"
        elif any(rid not in node_ids for rid in template["rules"]):
            reason = "unknown rule reference"
        elif FALSE in rule_states or any(r["truth"] == FALSE for r in reports):
            reason = "false rule prerequisite or template invariant"
        else:
            reason = None
        if reason:
            result["blocked_templates"].append({"template_id": template["id"], "reason": reason,
                                                "derivation": derivation, "facts": reports})
            continue
        unknown = (declared is None or UNKNOWN in rule_states or control["truth"] != TRUE
                   or measurement["truth"] != TRUE or any(r["truth"] == UNKNOWN for r in reports))
        for choice in template["intervention"]["choices"]:
            intervention = {"type": template["intervention"]["type"], "target": deepcopy(target), "value": deepcopy(choice)}
            variants.append({"template": template, "intervention": intervention, "control": control,
                             "measurement": measurement, "facts": reports, "derivation": derivation,
                             "status": "NEEDS_EVIDENCE" if unknown else "READY"})
    fingerprints = {}
    exhausted = False
    for depth in range(1, min(max_depth, len(variants)) + 1):
        for parts in combinations(variants, depth):
            if result["combinations_examined"] >= max_combinations:
                result["truncation"]["reasons"].append("combination limit")
                exhausted = True
                break
            result["combinations_examined"] += 1
            if len({p["template"]["id"] for p in parts}) != depth:
                continue
            conflict = _conflict(parts)
            if conflict:
                result["excluded_combinations"].append({"template_ids": [p["template"]["id"] for p in parts], "reason": conflict})
                continue
            interventions = sorted({_token(p["intervention"]): p["intervention"] for p in parts}.values(), key=_token)
            fingerprint = hashlib.sha256(_token({"interventions": interventions,
                                 "controls": sorted({_token(p["control"].get("actual")) for p in parts})}).encode("utf-8")).hexdigest()
            if fingerprint in fingerprints:
                prior = fingerprints[fingerprint]
                prior["template_ids"] = sorted(set(prior["template_ids"]) | {p["template"]["id"] for p in parts})
                prior["rule_ids"] = sorted(set(prior["rule_ids"]) | {r for p in parts for r in p["template"]["rules"]})
                prior["derivation"].extend(deepcopy([d for p in parts for d in p["derivation"]]))
                for key, values in (("observables", [p["measurement"] for p in parts]),
                                    ("facts", [r for p in parts for r in p["facts"]]),
                                    ("result_to_decision", [o for p in parts for o in p["template"]["result_to_decision"]]),
                                    ("rival_explanations", [v for p in parts for v in p["template"]["rival_explanations"]]),
                                    ("stop_conditions", [p["template"]["stop"] for p in parts])):
                    existing = {_token(v) for v in prior[key]}
                    prior[key].extend(deepcopy([v for v in values if _token(v) not in existing]))
                record_ids = sorted({p["template"]["cost"]["record_id"] for p in parts})
                if record_ids != prior["cost_record_ids"]:
                    prior["cost_record_ids"] = sorted(set(prior["cost_record_ids"]) | set(record_ids))
                    prior["incremental_cost"] = {"status": UNKNOWN, "reason": "Alias templates name different costs for one physical intervention"}
                    prior["budget_status"] = UNKNOWN
                    if prior["status"] == "BLOCKED_BUDGET":
                        prior["status"] = "NEEDS_EVIDENCE"
                if any(p["status"] != "READY" for p in parts) and prior["status"] == "READY":
                    prior["status"] = "NEEDS_EVIDENCE"
                continue
            if len(result["candidates"]) >= max_candidates:
                result["truncation"]["reasons"].append("candidate limit")
                exhausted = True
                break
            cost = _cost([p["template"]["cost"]["record_id"] for p in parts], context.get("costs", {}))
            candidate = {"id": "experiment:" + fingerprint[:20], "intervention_fingerprint": fingerprint,
                         "template_ids": [p["template"]["id"] for p in parts],
                         "rule_ids": sorted({r for p in parts for r in p["template"]["rules"]}),
                         "status": "NEEDS_EVIDENCE" if any(p["status"] != "READY" for p in parts) else "READY",
                         "candidate_only": True, "execution_authorized": False, "interventions": deepcopy(interventions),
                         "control_bindings": deepcopy([p["control"] for p in parts]),
                         "observables": deepcopy([p["measurement"] for p in parts]),
                         "facts": deepcopy([r for p in parts for r in p["facts"]]),
                         "derivation": deepcopy([d for p in parts for d in p["derivation"]]),
                         "rival_explanations": sorted({v for p in parts for v in p["template"]["rival_explanations"]}),
                         "result_to_decision": deepcopy([o for p in parts for o in p["template"]["result_to_decision"]]),
                         "cost_record_ids": sorted({p["template"]["cost"]["record_id"] for p in parts}),
                         "incremental_cost": cost, "stop_conditions": [p["template"]["stop"] for p in parts]}
            candidate["budget_status"] = UNKNOWN
            budget = context.get("budget", {})
            if cost["status"] != UNKNOWN and _reported(budget) and _finite(budget.get("value")) and budget["value"] >= 0:
                if _cost_identity(budget) == _cost_identity(cost):
                    candidate["budget_status"] = "WITHIN_REPORTED_BUDGET" if cost["value"] <= budget["value"] else "OVER_REPORTED_BUDGET"
                    if candidate["budget_status"] == "OVER_REPORTED_BUDGET":
                        candidate["status"] = "BLOCKED_BUDGET"
            fingerprints[fingerprint] = candidate
            result["candidates"].append(candidate)
        if exhausted:
            break
    if len({p["template"]["id"] for p in variants}) > max_depth:
        result["truncation"]["reasons"].append("depth limit")
    result["truncation"]["reasons"] = list(dict.fromkeys(result["truncation"]["reasons"]))
    result["truncation"]["truncated"] = bool(result["truncation"]["reasons"])
    return result

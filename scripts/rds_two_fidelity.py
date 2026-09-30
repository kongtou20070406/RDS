"""One-step, opt-in interval planner inspired by 2FFS (arXiv:2606.01708v2).

This adapter does not implement 2FFS's scale certificates, recursive race
budgets, sampling policy, termination theorem, or depth-cost theorem. It never
samples or executes. Sources identify declarations; they do not certify an
oracle model or a scientific result.
"""
from copy import deepcopy
import json
import math

from rds_advisor_search import _evidence_status, _finite, _reported

SCHEMA = "rds-two-fidelity-v1"
METHOD = "2FFS_INSPIRED_INTERVAL_ADAPTER"
MAX_NODES, MAX_DEPTH, MAX_SAMPLES = 256, 64, 10000


def _number(value, name, minimum=None):
    if value is None or value == "UNKNOWN":
        return None
    if not _finite(value) or minimum is not None and value < minimum:
        raise ValueError(name + " must be a finite number" + (" >= " + str(minimum) if minimum is not None else ""))
    return value


def _known(value):
    if isinstance(value, str):
        return bool(value.strip()) and value.upper() != "UNKNOWN"
    if isinstance(value, dict):
        return bool(value) and all(_known(v) for v in value.values())
    return value is not None and (type(value) is bool or _finite(value))


def _same(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def _usable(record):
    return _reported(record) and _known(record.get("source"))


def _interval(pair):
    return {"lower": pair[0] if _finite(pair[0]) else None,
            "upper": pair[1] if _finite(pair[1]) else None,
            "status": "KNOWN" if all(_finite(x) for x in pair) else "UNKNOWN"}


def anytime_radius(n, sigma, delta_v):
    """Safe two-tail union bound over all prefixes of an iid SG oracle."""
    if type(n) is not int or n < 1 or _number(sigma, "sigma", 0) is None:
        raise ValueError("n must be a positive integer and sigma must be known")
    if _number(delta_v, "delta_v", 0) is None or not 0 < delta_v < 1:
        raise ValueError("delta_v must lie in (0, 1)")
    return sigma * math.sqrt(2 * (math.log(math.pi ** 2 / 3) + 2 * math.log(n) - math.log(delta_v)) / n)


def select_next(context, facts=None, eligible_ids=None):
    """Review an explicit finite value tree; return one candidate, never run it.

    Required objective: direction MAX/MIN, metric, unit, scope. Tree nodes have
    id, operator MAX/MIN/LEAF, children, and explicit expanded booleans for
    internal nodes. Root children bind candidate_id and READY status (or the
    caller's eligible_ids). Numeric evidence has source, unit and scope:
    interval={lower,upper,...}, fast={value|fact_id,bias_bound,...}, or
    slow={samples:[number|{fact_id}],sigma,bias_bound,iid:true,
          sub_gaussian:true,targets_node_value:true,...}.
    Costs expand/slow use {value,status:ESTIMATE,resource,unit,comparison_group,
    source}; budget has remaining and the same resource/unit/comparison_group.
    Evidence source/unit/scope can be inherited by inline slow samples.
    Serialized fact dictionaries always remain INPUT_REPORTED.
    """
    out = {"schema": SCHEMA, "method": METHOD, "status": "NEEDS_EVIDENCE",
           "candidate_only": True, "execution_authorized": False,
           "assurance": "CONDITIONAL_ON_DECLARED_ORACLE_MODEL",
           "conditional_on_oracle_assumptions": True, "candidate_id": None,
           "next_action": None, "root_intervals": {}, "provenance": [],
           "assumptions": [], "pending_evidence": [], "conflicts": [], "cost": {},
           "trace": [{"adapter_scope": "finite interval planning only; no dyadic Done certificates, alpha race budgets, automatic sampling, termination or complexity theorem"}]}
    unknown = (-math.inf, math.inf)

    def pending(node_id, reason):
        out["pending_evidence"].append({"node_id": node_id, "reason": reason})

    try:
        if not isinstance(context, dict) or context.get("schema", SCHEMA) != SCHEMA:
            raise ValueError("unsupported two-fidelity context schema")
        json.dumps(context, allow_nan=False)
        objective = context.get("objective", {})
        if not isinstance(objective, dict) or objective.get("direction") not in {"MAX", "MIN"} or not all(
                _known(objective.get(k)) for k in ("metric", "unit", "scope")):
            raise ValueError("explicit objective direction, metric, unit and comparable scope are required")
        if not isinstance(objective["unit"], str) or not isinstance(objective["metric"], str):
            raise ValueError("objective metric and unit must be strings")
        epsilon, delta = _number(context.get("epsilon", 0), "epsilon", 0), _number(context.get("delta", .05), "delta", 0)
        if epsilon is None or delta is None or not 0 < delta < 1:
            raise ValueError("epsilon must be known and delta must lie in (0, 1)")
        facts = context.get("facts", {}) if facts is None else facts
        if not isinstance(facts, dict):
            raise ValueError("facts must be an id-to-record mapping")
        tree = context.get("tree", {})
        records = tree.get("nodes") if isinstance(tree, dict) else None
        if not isinstance(records, list) or not 3 <= len(records) <= MAX_NODES:
            raise ValueError("tree must contain 3..256 explicitly listed nodes")
        nodes = {}
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"] or record["id"] in nodes:
                raise ValueError("tree nodes need unique nonempty string ids")
            children = record.get("children", [])
            if not isinstance(children, list) or any(not isinstance(c, str) for c in children) or len(set(children)) != len(children):
                raise ValueError("children must be unique node ids")
            if record.get("operator") not in {"MAX", "MIN", "LEAF"} or bool(children) != (record["operator"] != "LEAF"):
                raise ValueError("internal MAX/MIN nodes need children; LEAF nodes cannot have children")
            if children and type(record.get("expanded")) is not bool:
                raise ValueError("internal nodes require an explicit expanded boolean")
            costs = record.get("costs", {})
            if not isinstance(costs, dict) or any(not isinstance(s, dict) for s in costs.values()):
                raise ValueError("node costs must be an object of cost objects")
            for spec in costs.values():
                _number(spec.get("value"), "cost.value", 0)
            nodes[record["id"]] = record
        root = tree.get("root")
        if root not in nodes or nodes[root]["operator"] != objective["direction"] or not nodes[root].get("expanded") or len(nodes[root]["children"]) < 2:
            raise ValueError("root must be expanded, match objective direction, and have at least two actions")
        visited = set()

        def visit(nid, depth=0):
            if nid not in nodes or nid in visited or depth > MAX_DEPTH:
                raise ValueError("tree has a missing child, cycle, shared child, or excessive depth")
            visited.add(nid)
            for child in nodes[nid].get("children", []):
                visit(child, depth + 1)

        visit(root)
        if len(visited) != len(nodes):
            raise ValueError("tree contains unreachable nodes")
        delta_v = delta / (len(nodes) - 1)
        if delta_v == 0:
            raise ValueError("delta is too small for finite confidence allocation")
        budget = context.get("budget", {})
        if not isinstance(budget, dict):
            raise ValueError("budget must be an object")
        remaining = _number(budget.get("remaining", budget.get("value")), "budget.remaining", 0)
        target_binding = objective.get("binding", {})
        if not isinstance(target_binding, dict):
            raise ValueError("objective.binding must be an object")
        protocol_bindings = {}
        if eligible_ids is not None and (not isinstance(eligible_ids, (list, tuple, set, frozenset)) or any(not isinstance(x, str) for x in eligible_ids)):
            raise ValueError("eligible_ids must be a collection of candidate ids")
        eligible = None if eligible_ids is None else set(eligible_ids)
        root_children = nodes[root]["children"]
        candidate_ids = [nodes[x].get("candidate_id") for x in root_children]
        if any(not isinstance(x, str) or not x for x in candidate_ids) or len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("root actions need distinct candidate_id bindings")
        actions = [x for x in root_children if nodes[x].get("status", "READY" if eligible is not None else "UNKNOWN") == "READY"
                   and (eligible is None or nodes[x]["candidate_id"] in eligible)]
        out.update(objective=deepcopy(objective), epsilon=epsilon, delta=delta, delta_v=delta_v,
                   comparison_scope="ELIGIBLE_ROOT_ACTIONS", excluded_candidate_ids=[nodes[x]["candidate_id"] for x in root_children if x not in actions])

        def compatible(record, nid, label):
            if not isinstance(record, dict):
                raise ValueError(label + " must be an object")
            if not _usable(record):
                pending(nid, label + " lacks a usable source or is unreliable")
                return False
            if not _same(record.get("unit"), objective["unit"]) or not _same(record.get("scope"), objective["scope"]):
                pending(nid, label + " has missing or mismatched value unit/scope")
                return False
            return True

        def value(record, nid, label, inherited=None):
            if not isinstance(record, dict):
                record = {**(inherited or {}), "value": record}
            elif inherited:
                record = {**inherited, **record}
            fid = record.get("fact_id")
            if fid is not None:
                if not isinstance(fid, str) or fid not in facts or not isinstance(facts[fid], dict):
                    pending(nid, label + " references a missing fact")
                    return None
                evidence = facts[fid]
                json.dumps(evidence, allow_nan=False)
            else:
                evidence = record
            number = _number(evidence.get("value"), label)
            if number is None or not _usable(evidence):
                pending(nid, label + " value/source is unknown or unreliable")
                return None
            binding = evidence.get("binding", {})
            binding = binding if isinstance(binding, dict) else {}
            metric = binding.get("metric", {})
            metric = metric if isinstance(metric, dict) else {}
            protocol_status = "SOURCE_PROTOCOL_UNVERIFIED"
            if fid is not None:
                protocol_keys = ("data_sha256", "data_split", "metric")
                for key in protocol_keys:
                    if not _known(binding.get(key)):
                        continue
                    expected = target_binding.get(key, protocol_bindings.get(key))
                    if expected is not None and not _same(binding[key], expected):
                        out["conflicts"].append({"node_id": nid, "fact_id": fid, "reason": "source protocol conflicts on " + key})
                        return None
                    protocol_bindings[key] = binding[key]
                if all(_known(target_binding.get(key)) and _known(binding.get(key)) for key in protocol_keys):
                    protocol_status = "TARGET_BINDING_MATCH"
                else:
                    pending(nid, label + ": SOURCE_PROTOCOL_UNVERIFIED; source identity does not establish objective correspondence")
            for key in ("unit", "scope"):
                declared = evidence.get(key, binding.get(key, metric.get(key)))
                if declared is not None and not _same(declared, objective[key]):
                    pending(nid, label + " fact has mismatched " + key)
                    return None
            out["provenance"].append({"node_id": nid, "field": label, "fact_id": fid,
                                      "evidence_status": _evidence_status(evidence), "protocol_status": protocol_status,
                                      "source": deepcopy(evidence["source"])})
            return number

        local, effective, backup, fast_models, slow_models = {}, {}, {}, {}, {}

        def intersect(nid, label, a, b):
            result = (max(a[0], b[0]), min(a[1], b[1]))
            if result[0] > result[1]:
                out["conflicts"].append({"node_id": nid, "reason": label + " has an empty intersection", "left": _interval(a), "right": _interval(b)})
            return result

        for nid, node in nodes.items():
            pair = unknown
            declared = node.get("interval")
            if declared is not None:
                lo, hi = _number(declared.get("lower") if isinstance(declared, dict) else None, "lower"), _number(declared.get("upper") if isinstance(declared, dict) else None, "upper")
                if compatible(declared, nid, "interval") and lo is not None and hi is not None:
                    if lo > hi:
                        out["conflicts"].append({"node_id": nid, "reason": "declared interval is reversed"})
                    pair = (lo, hi)
                    out["provenance"].append({"node_id": nid, "field": "interval", "evidence_status": "INPUT_REPORTED", "source": deepcopy(declared["source"])})
            fast = node.get("fast")
            fast_models[nid] = False
            if fast is not None:
                bound = _number(fast.get("bias_bound") if isinstance(fast, dict) else None, "fast.bias_bound", 0)
                fast_models[nid] = compatible(fast, nid, "fast") and bound is not None
                estimate = value(fast, nid, "fast.value")
                if fast_models[nid]:
                    out["assumptions"].append({"node_id": nid, "oracle": "fast", "bias_bound": bound, "source": deepcopy(fast["source"]), "status": "INPUT_REPORTED"})
                    if estimate is not None:
                        pair = intersect(nid, "fast/local", pair, (estimate - bound, estimate + bound))
                else:
                    pending(nid, "fast absolute bias envelope is unknown")
            slow = node.get("slow")
            slow_models[nid] = False
            if slow is not None:
                sigma = _number(slow.get("sigma") if isinstance(slow, dict) else None, "slow.sigma", 0)
                bias = _number(slow.get("bias_bound") if isinstance(slow, dict) else None, "slow.bias_bound", 0)
                slow_models[nid] = compatible(slow, nid, "slow") and sigma is not None and bias is not None and all(
                    slow.get(k) is True for k in ("iid", "sub_gaussian", "targets_node_value"))
                samples = slow.get("samples", [])
                if not isinstance(samples, list) or len(samples) > MAX_SAMPLES:
                    raise ValueError("slow samples must be a list of at most 10000 ordered prefix samples")
                # Validate numeric inputs even if the oracle assumptions are absent.
                numbers = [value(s, nid, "slow.sample:" + str(i), slow) for i, s in enumerate(samples, 1)]
                sample_ids, locations, duplicate = set(), set(), False
                for sample in samples:
                    if not isinstance(sample, dict):
                        continue
                    fid = sample.get("fact_id")
                    if isinstance(fid, str):
                        duplicate |= fid in sample_ids
                        sample_ids.add(fid)
                    record = facts.get(fid, {}) if isinstance(fid, str) else sample
                    source = record.get("source") if isinstance(record, dict) else None
                    if isinstance(source, dict) and _known(source.get("locator")):
                        location = tuple(source.get(k) for k in ("path", "url", "receipt_id", "sha256", "locator"))
                        if any(_known(x) for x in location[:3]) and all(x is None or isinstance(x, str) for x in location):
                            duplicate |= location in locations
                            locations.add(location)
                if duplicate:
                    pending(nid, "repeated slow observation identity/locator; iid prefix evidence remains UNKNOWN")
                if slow_models[nid]:
                    out["assumptions"].append({"node_id": nid, "oracle": "slow", "sigma": sigma, "bias_bound": bias,
                                               "iid": True, "sub_gaussian": True, "targets_node_value": True,
                                               "source": deepcopy(slow["source"]), "status": "INPUT_REPORTED"})
                    history, mean = unknown, 0.
                    if not duplicate and all(x is not None for x in numbers):
                        for n, sample in enumerate(numbers, 1):
                            mean = mean * ((n - 1) / n) + sample / n
                            radius = anytime_radius(n, sigma, delta_v) + bias
                            history = intersect(nid, "slow prefixes", history, (mean - radius, mean + radius))
                        pair = intersect(nid, "slow/local", pair, history)
                        out["trace"].append({"node_id": nid, "slow_prefix_count": len(numbers), "slow_interval": _interval(history)})
                else:
                    pending(nid, "slow requires sourced iid/sub-Gaussian/node-value assumptions, sigma and bias bound")
            local[nid] = pair

        def compute(nid):
            node = nodes[nid]
            pair = local[nid] if nid != root else unknown
            if node.get("children") and node["expanded"]:
                child_pairs = [compute(x) for x in node["children"]]
                op = max if node["operator"] == "MAX" else min
                backup[nid] = (op(p[0] for p in child_pairs), op(p[1] for p in child_pairs))
                pair = intersect(nid, "children/local", pair, backup[nid])
            effective[nid] = pair
            return pair

        compute(root)
        out["root_intervals"] = {nodes[x]["candidate_id"]: {"node_id": x, **_interval(effective[x])} for x in root_children}
        if out["conflicts"]:
            out["status"] = "CONFLICT"
            return out
        if not actions:
            pending(root, "no eligible READY action")
            return out
        is_max = objective["direction"] == "MAX"
        leader = (max if is_max else min)(actions, key=lambda x: effective[x][0 if is_max else 1])
        others = [x for x in actions if x != leader]
        challenger = (max if is_max else min)(others, key=lambda x: effective[x][1 if is_max else 0]) if others else None
        out.update(leader=nodes[leader]["candidate_id"], challenger=nodes[challenger]["candidate_id"] if challenger else None)
        bound = effective[leader][0 if is_max else 1]
        other_bound = effective[challenger][1 if is_max else 0] if challenger else bound
        separated = _finite(bound) and _finite(other_bound) and (bound >= other_bound - epsilon if is_max else bound <= other_bound + epsilon)
        if separated:
            out.update(status="SEPARATED", candidate_id=nodes[leader]["candidate_id"])
            out["trace"].append({"stop": "epsilon interval separation among eligible actions", "conditional_on_oracle_assumptions": True})
            return out
        # ponytail: one-step width/cost heuristic; full scale/counter racing is outside this adapter.
        obligation = max([leader] + ([challenger] if challenger else []), key=lambda x: effective[x][1] - effective[x][0])
        side = ("L" if is_max else "U") if obligation == leader else ("U" if is_max else "L")
        out["trace"].append({"root_obligation": obligation, "side": side, "heuristic": "larger interval width; challenger uses decision-relevant endpoint, no unresolved-scale policy"})
        routes, path, nid = [], [], obligation
        while True:
            node = nodes[nid]
            path.append({"node_id": nid, "side": side})
            work_ready = node.get("status", "READY") == "READY"
            if slow_models[nid] and work_ready:
                routes.append({"kind": "SLOW_EVIDENCE", "node_id": nid, "side": side, "cost_key": "slow"})
            children = node.get("children", [])
            if not children or not node.get("expanded"):
                if children and work_ready and all(fast_models[x] for x in children):
                    routes.append({"kind": "FAST_EXPAND", "node_id": nid, "side": side, "cost_key": "expand"})
                break
            index = 0 if side == "L" else 1
            if effective[nid][index] != backup[nid][index]:
                path[-1]["witness"] = "direct local endpoint"
                break
            selector = (node["operator"], side) in {("MIN", "L"), ("MAX", "U")}
            op = min if node["operator"] == "MIN" else max
            child_side = side if selector else ("U" if side == "L" else "L")
            child_index = 0 if child_side == "L" else 1
            nid = op(children, key=lambda x: effective[x][child_index])
            path[-1]["witness"] = "endpoint selector" if selector else "opposite-endpoint comparison blocker"
            side = child_side
        out["critical_witness"] = path[-1]
        out["trace"].append({"critical_path": path})
        keys = ("resource", "unit", "comparison_group")
        budget_key = tuple(budget.get(k, budget.get("group") if k == "comparison_group" else None) for k in keys)
        budget_known = remaining is not None and _usable(budget) and all(isinstance(x, str) and _known(x) for x in budget_key)
        affordable, over_budget = [], []
        for route in routes:
            spec = nodes[route["node_id"]].get("costs", {}).get(route["cost_key"], {})
            if not isinstance(spec, dict):
                raise ValueError("costs must contain cost objects")
            amount = _number(spec.get("value"), "cost.value", 0)
            cost_key = tuple(spec.get(k, spec.get("group") if k == "comparison_group" else None) for k in keys)
            known = amount is not None and _usable(spec) and spec.get("status") == "ESTIMATE" and spec.get("historical") is not True and str(spec.get("prediction_status")).upper() != "UNKNOWN"
            if not known or not budget_known or cost_key != budget_key:
                pending(route["node_id"], route["kind"] + " needs an ESTIMATE future cost and a matching resource/unit/comparison_group budget")
                continue
            route["cost"] = {"value": amount, "status": "ESTIMATE", **dict(zip(keys, cost_key)), "source": deepcopy(spec["source"])}
            (affordable if amount <= remaining else over_budget).append(route)
        out["cost"] = {"budget": {"remaining": remaining, **dict(zip(keys, budget_key)), "status": "INPUT_REPORTED" if budget_known else "UNKNOWN"}, "over_budget": over_budget}
        if affordable:
            chosen = min(affordable, key=lambda r: (r["cost"]["value"], r["kind"], r["node_id"]))
            chosen.pop("cost_key")
            out.update(status="NEXT_ACTION", candidate_id=nodes[obligation]["candidate_id"], next_action=chosen)
            out["trace"].append({"route_choice": "least estimated affordable next step along critical path; no cost optimality guarantee"})
        elif over_budget:
            out["status"] = "BUDGET_INSUFFICIENT"
        else:
            pending(nid, "provide a known interval, calibrated fast envelope/expansion, or eligible slow oracle model and cost")
        return out
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        out.update(status="INVALID", candidate_id=None, next_action=None, error=str(exc))
        return out

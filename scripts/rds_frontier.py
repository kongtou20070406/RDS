"""Finite, source-labelled questions outside a supplied research graph.

Reachability is graph structure, a residual is arithmetic, and dimensional
compatibility is an integer equation. None establishes a scientific relation.
"""
from collections import defaultdict, deque
from copy import deepcopy
from datetime import date
import hashlib
from itertools import combinations, product
import json
import math


DEFAULT_LIMITS = {"max_gaps": 12, "max_nodes": 128, "max_edges": 512,
                  "max_combinations": 256, "max_power": 2, "max_terms": 3}
LIMIT_CAPS = {"max_gaps": 64, "max_nodes": 512, "max_edges": 4096,
              "max_combinations": 4096, "max_power": 6, "max_terms": 6}
FAMILIES = ("MISSING_BRIDGE", "MODEL_FAILURE", "DIMENSIONAL_BRIDGE", "TRANSFER_GAP", "FORMAL_OBLIGATION", "THEORY_REFORMULATION")
PROPOSAL_FIELDS = ["assumptions", "relations", "prediction", "test",
                   "next_if_positive", "next_if_negative"]
MAX_METADATA_BYTES = 1024
SOURCE_FIELDS = ("path", "url", "locator", "receipt_id", "source_id")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512


def _source(value):
    return (_text(value) or isinstance(value, dict) and any(
        _text(value.get(key)) for key in ("path", "url", "locator", "receipt_id")))


def _metadata(value, name):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        size = len(raw.encode("utf-8"))
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise ValueError(f"{name} must contain finite JSON metadata") from exc
    _require(size <= MAX_METADATA_BYTES, f"{name} exceeds {MAX_METADATA_BYTES} UTF-8 JSON bytes")


def _date(value, name):
    _require(isinstance(value, str), f"{name} must be an ISO date YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date YYYY-MM-DD") from exc
    _require(parsed.isoformat() == value, f"{name} must be an ISO date YYYY-MM-DD")
    return parsed


def _dimensions(value, name):
    _require(isinstance(value, dict) and len(value) <= 16, f"{name} must be an integer dimension map")
    _require(all(_text(key) and type(power) is int and abs(power) <= 64
                 for key, power in value.items()), f"{name} must contain named integer powers in -64..64")
    return {key: power for key, power in value.items() if power}


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _number(value, name):
    _require(_finite(value), f"{name} must be a finite number, not a Boolean")
    return value


def _identifier(prefix, value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _ref(record_type, record):
    source = record["source"]
    # Multiple formulas can share this record. Repeat its locator, not arbitrary
    # metadata payloads or caller-signed success/verification flags.
    if isinstance(source, dict):
        source = {key: source[key] for key in SOURCE_FIELDS if _text(source.get(key))}
    return {"record_type": record_type, "id": record["id"], "source": source}


def _describe(node):
    details = [f"kind={node['kind']}"]
    for key in ("label", "description"):
        if _text(node.get(key)):
            details.append(f"{key}={node[key]}")
    return f"{node['id']} [{'; '.join(details)}]"


def _walk(start, adjacency):
    visited, pending = set(start), list(start)
    while pending:
        for neighbor in adjacency[pending.pop()]:
            if neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    return visited


def _gap(kind, record, anchors, target, refs, why, question, **extra):
    return {"id": _identifier("gap.", [kind, record["id"]]), "kind": kind,
            "anchors": list(anchors), "target": target, "status": "OPEN",
            "uncertainty": "UNKNOWN_SCIENTIFIC_SUPPORT", "evidence_status": "INPUT_REPORTED",
            "evidence_refs": refs, "why": why, "question": question,
            "required_proposal_fields": list(PROPOSAL_FIELDS) +
                (["formal_obligation"] if kind == "FORMAL_OBLIGATION" else []),
            "cost": {"status": "UNKNOWN"}, **extra}


def _vectors(count, max_power, max_terms):
    powers = [power for magnitude in range(1, max_power + 1) for power in (magnitude, -magnitude)]
    for terms in range(1, min(count, max_terms) + 1):
        for indices in combinations(range(count), terms):
            for values in product(powers, repeat=terms):
                vector = [0] * count
                for index, value in zip(indices, values):
                    vector[index] = value
                yield tuple(vector)


def discover_frontier(spec):
    """Return open questions and dimensionally admissible, unverified proposals.

    Explicit as_of requires dated records. With no cutoff the context is
    temporally unscoped; this function never silently reads today's date.
    """
    _require(isinstance(spec, dict) and type(spec.get("schema_version")) is int
             and spec["schema_version"] == 1, "Frontier schema_version must be 1")
    try:
        raw = json.dumps(spec, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Frontier input must contain finite JSON values") from exc
    _require(len(raw.encode("utf-8")) <= 4 * 1024 * 1024, "Frontier input exceeds 4 MiB")
    requested = spec.get("limits", {})
    _require(isinstance(requested, dict) and not set(requested) - set(DEFAULT_LIMITS), "Unknown frontier limits")
    limits = {**DEFAULT_LIMITS, **requested}
    for key, cap in LIMIT_CAPS.items():
        _require(type(limits[key]) is int and 1 <= limits[key] <= cap, f"{key} must be an integer in 1..{cap}")
    cutoff = _date(spec["as_of"], "as_of") if spec.get("as_of") is not None else None
    records = {}
    raw_caps = {"nodes": 4096, "edges": 16384, "goals": 512,
                "observations": 512, "dimension_requests": 128, "transfers": 512,
                "formal_records": 16}
    for name, cap in raw_caps.items():
        rows = spec.get(name, [])
        _require(isinstance(rows, list) and len(rows) <= cap, f"{name} must be a list of at most {cap} records")
        records[name] = rows
        ids = set()
        for index, row in enumerate(rows):
            _require(isinstance(row, dict), f"{name}[{index}] must be an object")
            # Edges need no caller-assigned ID; their input index identifies them.
            if name != "edges":
                _require(_text(row.get("id")) and row["id"] not in ids, f"{name} require unique nonempty IDs")
                ids.add(row["id"])
            _require(_source(row.get("source")), f"{name}[{index}] requires a source locator")
            _metadata(row["source"], f"{name}[{index}].source")
            if "available_on" in row:
                _date(row["available_on"], f"{name}[{index}].available_on")
    all_nodes = {node["id"]: node for node in records["nodes"]}
    for node in all_nodes.values():
        _require(_text(node.get("kind")), f"Node {node['id']} requires kind")
        if "dimensions" in node:
            _dimensions(node["dimensions"], f"Node {node['id']}.dimensions")
    for record in records["formal_records"]:
        _require(_text(record.get("node")) and record["node"] in all_nodes
                 and isinstance(record.get("statement"), dict),
                 "Formal records require a defined node and explicit statement")
    for edge in records["edges"]:
        _require(_text(edge.get("from")) and _text(edge.get("to"))
                 and edge["from"] in all_nodes and edge["to"] in all_nodes,
                 "Edge endpoints must name nodes")
        _require(_text(edge.get("relation")) and edge.get("status") in ("SUPPORTED", "PROPOSED", "CONTRADICTED"),
                 "Edges require relation and SUPPORTED/PROPOSED/CONTRADICTED status")
    for goal in records["goals"]:
        anchors = goal.get("anchors")
        _require(isinstance(anchors, list) and 1 <= len(anchors) <= 512
                 and all(_text(anchor) and anchor in all_nodes for anchor in anchors)
                 and len(set(anchors)) == len(anchors), f"Goal {goal['id']} requires distinct sourced node anchors")
        _require(_text(goal.get("target")) and goal["target"] in all_nodes and _text(goal.get("decision")),
                 f"Invalid goal {goal['id']} target/decision")
        if "relations" in goal:
            relations = goal["relations"]
            _require(isinstance(relations, list) and 1 <= len(relations) <= 32
                     and all(_text(relation) for relation in relations)
                     and len(set(relations)) == len(relations), f"Goal {goal['id']} requires 1..32 distinct relations")
        if "reformulation" in goal:
            request = goal["reformulation"]
            _require(isinstance(request, dict) and _text(request.get("current_model"))
                     and request["current_model"] in all_nodes and _text(request.get("reason"))
                     and _source(request.get("source")),
                     f"Goal {goal['id']} reformulation requires current_model, reason and source")
            _metadata(request["source"], f"Goal {goal['id']} reformulation.source")
            if "signals" in request:
                signals = request["signals"]
                _require(isinstance(signals, list) and len(signals) <= 32
                         and all(_text(signal) and len(signal) <= 80 for signal in signals),
                         "Reformulation signals require at most 32 short strings")
            if "available_on" in request:
                _date(request["available_on"], "reformulation.available_on")
    for observation in records["observations"]:
        _require(_text(observation.get("model")) and _text(observation.get("node"))
                 and observation["model"] in all_nodes and observation["node"] in all_nodes,
                 f"Observation {observation['id']} must name model and node")
        protocol = observation.get("protocol")
        _require(_text(protocol) or isinstance(protocol, dict) and bool(protocol), f"Observation {observation['id']} requires protocol")
        _metadata(protocol, f"Observation {observation['id']}.protocol")
        for key in ("observed", "predicted", "tolerance"):
            if observation.get(key) is not None:
                _number(observation[key], f"Observation {observation['id']}.{key}")
        _require(observation.get("tolerance") is None or observation["tolerance"] >= 0,
                 f"Observation {observation['id']} tolerance cannot be negative")
    for request in records["dimension_requests"]:
        variables = request.get("variables")
        _require(isinstance(variables, list) and 1 <= len(variables) <= 6
                 and all(_text(variable) and variable in all_nodes for variable in variables)
                 and len(set(variables)) == len(variables), f"Dimension request {request['id']} requires 1..6 distinct node variables")
        _require(_text(request.get("target")) and request["target"] in all_nodes and _text(request.get("decision")),
                 f"Invalid dimension request {request['id']} target/decision")
        _require(request["target"] not in variables,
                 f"Dimension request {request['id']} target cannot also be a variable")
    for transfer in records["transfers"]:
        _require(_text(transfer.get("from")) and _text(transfer.get("to"))
                 and transfer["from"] in all_nodes and transfer["to"] in all_nodes
                 and _text(transfer.get("decision")), f"Invalid transfer {transfer['id']} endpoints/decision")
        for key in ("source_scope", "target_scope"):
            if key not in transfer:
                continue
            scope = transfer[key]
            _require(isinstance(scope, dict) and len(scope) <= 16 and all(_text(field) for field in scope),
                     f"Transfer {transfer['id']}.{key} requires at most 16 named scope fields")
            _require(all(value is None or type(value) in (str, bool, int, float) for value in scope.values()),
                     f"Transfer {transfer['id']}.{key} must contain JSON atomic values")

    result = {"schema_version": 1, "advisor_type": "FRONTIER_DISCOVERY",
              "as_of": cutoff.isoformat() if cutoff else None,
              "temporal_policy": "AS_OF" if cutoff else "UNSCOPED",
              "evidence_status": "INPUT_REPORTED", "scientific_support": "UNKNOWN",
              "reachability_only": True,
              "gaps": [], "program_proposals": [], "unknown": [], "excluded": [],
              "residual_checks": [], "transfer_checks": [], "formal_checks": [], "statistics": {},
              "truncation": {"truncated": False, "reasons": [], "limits": dict(limits)},
              "limitations": ["Paths use supplied SUPPORTED labels, not independently verified relations.",
                              "Residuals require the supplied numeric protocol; no causal conclusion follows.",
                              "Integer dimensions permit formulas; they do not establish physical laws.",
                              "Source references retain locator fields; other metadata is bounded and omitted.",
                              "Enumeration is finite; unexplored concepts and exponents may remain."]}

    def truncated(reason):
        result["truncation"]["truncated"] = True
        if reason not in result["truncation"]["reasons"]:
            result["truncation"]["reasons"].append(reason)

    def available(name, row, index):
        when = row.get("available_on")
        reason = "UNKNOWN_AVAILABILITY" if cutoff and when is None else \
                 "FUTURE_RECORD" if cutoff and _date(when, "available_on") > cutoff else None
        if reason:
            record_id = f"edge:{index}" if name == "edges" else row["id"]
            result["excluded"].append({"record_type": name, "id": record_id,
                                       "reason": reason, "available_on": when})
        return reason is None

    eligible = {name: [row for index, row in enumerate(rows) if available(name, row, index)]
                for name, rows in records.items()}
    if len(eligible["nodes"]) > limits["max_nodes"]:
        truncated("node limit")
    nodes = {node["id"]: node for node in eligible["nodes"][:limits["max_nodes"]]}
    dated_ids = {node["id"] for node in eligible["nodes"]}

    def usable(name, row, references):
        missing = [rid for rid in references if rid not in nodes]
        if missing:
            reason = "NODE_LIMIT" if all(rid in dated_ids for rid in missing) else "UNAVAILABLE_NODE"
            result["unknown"].append({"record_type": name, "id": row["id"], "status": "UNKNOWN",
                                      "reason": reason, "missing_node_ids": missing})
            return False
        return True

    edges = [edge for edge in eligible["edges"] if edge["from"] in nodes and edge["to"] in nodes]
    if len(edges) > limits["max_edges"]:
        truncated("edge limit")
    edges = edges[:limits["max_edges"]]
    family_gaps = {kind: [] for kind in FAMILIES}
    for record in eligible["formal_records"]:
        if not usable("formal_records", record, [record["node"]]):
            continue
        from rds_frontier_proposals import formal_gate
        gate = formal_gate(record["statement"], record.get("certificate"))
        result["formal_checks"].append({"record_id": record["id"], "node": record["node"],
                                       **gate})
        if not gate["admitted"]:
            family_gaps["FORMAL_OBLIGATION"].append(_gap("FORMAL_OBLIGATION", record,
                [record["node"]], record["node"], [_ref("formal_record", record)],
                "Native proof or its application premises are unclosed; reported flags cannot close them.",
                f"Which explicit premises and supported Lean obligation would close the side condition for {_describe(nodes[record['node']])}?",
                formal_obligation=deepcopy(record["statement"]),
                formal_status=gate["status"], formal_assurance=gate["assurance"],
                application_status=gate.get("application_status", "UNKNOWN")))
    paths, goal_ranges = {}, []
    for goal in eligible["goals"]:
        if not usable("goals", goal, [goal["target"], *goal["anchors"]]):
            continue
        target = goal["target"]
        relations = tuple(sorted(goal["relations"])) if "relations" in goal else None
        path_key = (target, relations)
        if path_key not in paths:
            reverse, forward = defaultdict(set), defaultdict(set)
            for edge in edges:
                if edge["status"] == "SUPPORTED" and (relations is None or edge["relation"] in relations):
                    reverse[edge["to"]].add(edge["from"])
                    forward[edge["from"]].add(edge["to"])
            paths[path_key] = (_walk([target], reverse), forward)
        ancestors, forward = paths[path_key]
        goal_ranges.append({"goal": goal, "nodes": (_walk(goal["anchors"], forward) & ancestors) | {target}})
        if "reformulation" in goal:
            request = {**goal["reformulation"], "id": goal["id"]}
            current = request["current_model"]
            if available("reformulations", request, 0) and usable("reformulations", request, [current]):
                family_gaps["THEORY_REFORMULATION"].append(_gap("THEORY_REFORMULATION", goal,
                    [current], target, [_ref("goal", goal), _ref("reformulation", request),
                        *[_ref("node", nodes[rid]) for rid in dict.fromkeys([current, *goal["anchors"], target])]],
                    "An explicit review requests a broader or alternative formulation; no theory is declared exhausted.",
                    f"Which sourced reformulation of {_describe(nodes[current])} addresses {request['reason']} "
                    f"while preserving the goal {_describe(nodes[target])}? State the map, changed assumptions "
                    "and a deciding proof check or comparison; wider scope alone is not evidence of gain.",
                    goal_id=goal["id"], decision=goal["decision"], current_model=current,
                    original_anchors=list(goal["anchors"]), review_reason=request["reason"],
                    required_proposal_fields=["theory_bridge", "assumptions", "relations", "test",
                                              "next_if_positive", "next_if_negative"],
                    execution_authorized=False))
        missing = [anchor for anchor in goal["anchors"] if anchor not in ancestors]
        if not missing:
            continue
        if any(reason in result["truncation"]["reasons"] for reason in ("node limit", "edge limit")):
            result["unknown"].append({"record_type": "goals", "id": goal["id"], "status": "UNKNOWN",
                                      "reason": "REACHABILITY_SEARCH_TRUNCATED"})
            continue
        refs = [_ref("goal", goal), *[_ref("node", nodes[anchor]) for anchor in missing], _ref("node", nodes[target])]
        family_gaps["MISSING_BRIDGE"].append(_gap("MISSING_BRIDGE", goal, missing, target, refs,
            "These sourced goal anchors have no directed SUPPORTED path to the target in the available reported graph.",
            f"What testable relation could connect {', '.join(_describe(nodes[rid]) for rid in missing)} "
            f"to {_describe(nodes[target])} for decision {goal['decision']}?",
            goal_id=goal["id"], decision=goal["decision"], relations=list(relations) if relations else None,
            reachability_only=True))

    for transfer in eligible["transfers"]:
        if not usable("transfers", transfer, [transfer["from"], transfer["to"]]):
            continue
        relevant = [row["goal"] for row in goal_ranges if transfer["to"] in row["nodes"]]
        if not relevant:
            result["transfer_checks"].append({"transfer_id": transfer["id"], "status": "OUTSIDE_GOAL_SCOPE"})
            continue
        source_scope, target_scope = transfer.get("source_scope", {}), transfer.get("target_scope", {})
        conflicts, missing = [], []
        for key in ("source_scope", "target_scope"):
            if not transfer.get(key):
                missing.append({"field": key, "missing_in": "record"})
        for key in sorted(set(source_scope) | set(target_scope)):
            left, right = source_scope.get(key), target_scope.get(key)
            if left is None or right is None:
                for side, value in (("source_scope", left), ("target_scope", right)):
                    if value is None:
                        missing.append({"field": key, "missing_in": side})
            elif left != right or isinstance(left, bool) != isinstance(right, bool):
                conflicts.append({"field": key, "source_value": deepcopy(left), "target_value": deepcopy(right)})
        comparison = {"transfer_id": transfer["id"], "status": "MISMATCH" if conflicts else "UNKNOWN" if missing else "IDENTICAL_DECLARED_SCOPE",
                      "conflicts": conflicts, "missing_fields": missing, "evidence_status": "INPUT_REPORTED"}
        result["transfer_checks"].append(comparison)
        if missing and not conflicts:
            result["unknown"].append({"record_type": "transfers", "id": transfer["id"], "status": "UNKNOWN",
                                      "reason": "MISSING_SCOPE_FIELDS", "missing_fields": missing})
        if conflicts:
            family_gaps["TRANSFER_GAP"].append(_gap("TRANSFER_GAP", transfer, [transfer["from"]], transfer["to"],
                [_ref("transfer", transfer), _ref("node", nodes[transfer["from"]]), _ref("node", nodes[transfer["to"]]),
                 *[_ref("goal", goal) for goal in relevant]],
                "Reported source and target scopes differ; a result in the source scope does not establish performance in the target scope.",
                f"What bridge test would justify transferring {_describe(nodes[transfer['from']])} to "
                f"{_describe(nodes[transfer['to']])} across the declared differences {', '.join(row['field'] for row in conflicts)}?",
                transfer_id=transfer["id"], decision=transfer["decision"],
                source_scope=deepcopy(source_scope), target_scope=deepcopy(target_scope),
                scope_comparison=deepcopy(comparison)))

    for observation in eligible["observations"]:
        if not usable("observations", observation, [observation["model"], observation["node"]]):
            continue
        missing = [key for key in ("observed", "predicted", "tolerance") if observation.get(key) is None]
        protocol = observation["protocol"]
        units = [protocol.get(key) for key in ("observed_unit", "predicted_unit")] if isinstance(protocol, dict) else []
        incompatible_units = bool(units and any(unit is not None for unit in units)
                                  and (not all(_text(unit) for unit in units) or units[0] != units[1]))
        if missing or incompatible_units:
            result["unknown"].append({"record_type": "observations", "id": observation["id"], "status": "UNKNOWN",
                                      "reason": "INCOMPATIBLE_UNITS" if incompatible_units else "MISSING_NUMERIC_INPUT",
                                      "missing_fields": missing})
            continue
        residual = abs(observation["observed"] - observation["predicted"])
        if not _finite(residual):
            result["unknown"].append({"record_type": "observations", "id": observation["id"], "status": "UNKNOWN",
                                      "reason": "NONFINITE_RESIDUAL"})
            continue
        exceeds = residual > observation["tolerance"]
        result["residual_checks"].append({"observation_id": observation["id"], "residual": residual,
            "tolerance": observation["tolerance"], "exceeds_tolerance": exceeds, "evidence_status": "INPUT_REPORTED"})
        if exceeds:
            family_gaps["MODEL_FAILURE"].append(_gap("MODEL_FAILURE", observation, [observation["model"]],
                observation["node"], [_ref("observation", observation), _ref("node", nodes[observation["model"]]),
                                      _ref("node", nodes[observation["node"]])],
                "The absolute residual exceeds the reported tolerance under the supplied protocol; the cause remains unknown.",
                f"Which changed assumption or rival relation predicts the residual between {_describe(nodes[observation['model']])} "
                f"and {_describe(nodes[observation['node']])}, and what would falsify it?",
                observation_id=observation["id"], residual=residual, tolerance=observation["tolerance"],
                protocol=deepcopy(protocol)))

    states, proposals = [], {}
    for request in eligible["dimension_requests"]:
        variables, target = request["variables"], request["target"]
        if not usable("dimension_requests", request, [target, *variables]):
            continue
        if any("dimensions" not in nodes[rid] for rid in [target, *variables]):
            result["unknown"].append({"record_type": "dimension_requests", "id": request["id"],
                                      "status": "UNKNOWN", "reason": "MISSING_DIMENSIONS"})
            continue
        dimensions = [_dimensions(nodes[rid]["dimensions"], rid) for rid in variables]
        target_dimensions = _dimensions(nodes[target]["dimensions"], target)
        count = len(variables)
        total = sum(math.comb(count, terms) * (2 * limits["max_power"]) ** terms
                    for terms in range(1, min(count, limits["max_terms"]) + 1))
        states.append({"request": request, "dimensions": dimensions, "target": target_dimensions,
                       "iterator": _vectors(count, limits["max_power"], limits["max_terms"]),
                       "total": total, "examined": 0, "solutions": {}})
    queue = deque(states)
    examined = 0
    while queue and examined < limits["max_combinations"]:
        state = queue.popleft()
        vector = next(state["iterator"])
        state["examined"] += 1
        examined += 1
        actual = defaultdict(int)
        for powers, exponent in zip(state["dimensions"], vector):
            for axis, power in powers.items():
                actual[axis] += power * exponent
        actual = {axis: power for axis, power in actual.items() if power}
        if actual == state["target"]:
            divisor = math.gcd(*vector)
            if not state["target"]:
                vector = tuple(exponent // divisor for exponent in vector)
            if vector not in state["solutions"]:
                request = state["request"]
                exponents = dict(zip(request["variables"], vector))
                pid = _identifier("proposal.", [request["id"], exponents, state["target"]])
                proposal = {"id": pid, "request_id": request["id"], "kind": "DIMENSIONAL_BRIDGE",
                    "anchors": list(request["variables"]), "target": request["target"],
                    "status": "PROPOSED", "evidence_status": "INPUT_REPORTED", "scientific_support": "UNKNOWN",
                    "exponents": exponents, "exponent_gcd": math.gcd(*vector),
                    "ast": {"op": "product", "terms": [{"node_id": rid, "exponent": exponent}
                                                         for rid, exponent in exponents.items() if exponent]},
                    "dimension_check": {"status": "SATISFIED", "actual": actual, "target": dict(state["target"])},
                    "evidence_refs": [_ref("dimension_request", request)] + [_ref("node", nodes[rid])
                                       for rid in (request["target"], *request["variables"])],
                    "assumptions": ["Declared variable and target dimensions are correct.",
                                    "Numerical coefficients, mechanisms and applicability are unknown."],
                    "cost": {"status": "UNKNOWN"}}
                state["solutions"][vector] = pid
                proposals[pid] = proposal
        if state["examined"] < state["total"]:
            queue.append(state)
    if queue:
        truncated("combination limit")
    for state in states:
        request = state["request"]
        if state["solutions"]:
            family_gaps["DIMENSIONAL_BRIDGE"].append(_gap("DIMENSIONAL_BRIDGE", request, request["variables"],
                request["target"], [_ref("dimension_request", request)] + [_ref("node", nodes[rid])
                                    for rid in (request["target"], *request["variables"])],
                "Finite integer search found dimensionally admissible expressions; no physical relationship is established.",
                f"Which expression using {', '.join(_describe(nodes[rid]) for rid in request['variables'])}, if any, predicts "
                f"{_describe(nodes[request['target']])} under explicit assumptions and an independent test?",
                request_id=request["id"], decision=request["decision"], proposal_ids=list(state["solutions"].values()),
                combinations_examined=state["examined"]))
        else:
            result["unknown"].append({"record_type": "dimension_requests", "id": request["id"],
                "status": "UNKNOWN", "reason": "SEARCH_TRUNCATED" if state["examined"] < state["total"]
                                              else "NO_FORMULA_IN_BOUNDED_DOMAIN",
                "combinations_examined": state["examined"]})

    pending = {kind: deque(rows) for kind, rows in family_gaps.items()}
    while any(pending.values()) and len(result["gaps"]) < limits["max_gaps"]:
        for kind in FAMILIES:
            if pending[kind] and len(result["gaps"]) < limits["max_gaps"]:
                result["gaps"].append(pending[kind].popleft())
    if any(pending.values()):
        truncated("gap limit")
    # Retrieve only for emitted, explicitly scoped requests. Never load the
    # catalogue into ordinary advice or feed contemporary tools to old cutoffs.
    tool_reviews = {}
    for gap in result["gaps"]:
        if gap["kind"] != "THEORY_REFORMULATION":
            continue
        request = next(goal["reformulation"] for goal in eligible["goals"] if goal["id"] == gap["goal_id"])
        signals = tuple(dict.fromkeys(request.get("signals", [])))
        if signals:
            if signals not in tool_reviews:
                from rds_theory_tools import shortlist
                tool_reviews[signals] = shortlist(list(signals), limit=3)
            tools = tool_reviews[signals]
            if cutoff and _date(tools["available_on"], "catalogue.available_on") > cutoff:
                gap["theory_tools"] = {"status": "UNAVAILABLE_AT_CUTOFF", "cards": []}
            else:
                gap["theory_tools"] = deepcopy(tools)
    used_proposals = {pid for gap in result["gaps"] for pid in gap.get("proposal_ids", [])}
    result["program_proposals"] = [proposal for pid, proposal in proposals.items() if pid in used_proposals]
    result["statistics"] = {"nodes_used": len(nodes), "edges_used": len(edges),
        "supported_edges_used": sum(edge["status"] == "SUPPORTED" for edge in edges),
        "goals_examined": len(eligible["goals"]), "observations_examined": len(eligible["observations"]),
        "dimension_requests_examined": len(eligible["dimension_requests"]), "combinations_examined": examined,
        "transfers_examined": len(eligible["transfers"]),
        "gaps_generated": sum(len(rows) for rows in family_gaps.values()), "gaps_emitted": len(result["gaps"]),
        "gaps_by_kind": {kind: len(rows) for kind, rows in family_gaps.items()},
        "gaps_emitted_by_kind": {kind: sum(gap["kind"] == kind for gap in result["gaps"]) for kind in FAMILIES},
        "program_proposals_generated": len(proposals), "program_proposals_emitted": len(result["program_proposals"]),
        "excluded_records": len(result["excluded"]), "unknown_records": len(result["unknown"])}
    return result

"""Admit bounded AI bridge definitions for testing; never adopt scientific facts."""
from collections import defaultdict
from copy import deepcopy
import json


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 2000


def review_proposals(frontier, spec, pack):
    """Check a reply against the current gap and return a proposed subgraph.

    IDs, finite structure, gap coverage and a discriminating test are checked.
    Prediction truth, causal validity, test cost and execution remain unknown.
    """
    if (not isinstance(pack, dict) or type(pack.get("schema_version")) is not int
            or pack["schema_version"] != 1 or not isinstance(pack.get("proposals"), list)
            or len(pack["proposals"]) > 16):
        raise ValueError("Proposal pack schema_version=1 requires at most 16 proposals")
    if len(json.dumps(pack, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 128 * 1024:
        raise ValueError("Proposal pack exceeds 128 KiB")
    gaps = {gap["id"]: gap for gap in frontier["gaps"]}
    excluded = {row["id"] for row in frontier["excluded"] if row["record_type"] == "nodes"}
    limits = frontier.get("truncation", {}).get("limits", {})
    existing = {node["id"] for node in [node for node in spec.get("nodes", [])
                if node["id"] not in excluded][:limits.get("max_nodes", 512)]}
    excluded_edges = {row["id"] for row in frontier["excluded"] if row["record_type"] == "edges"}
    available_edges = [edge for index, edge in enumerate(spec.get("edges", []))
        if f"edge:{index}" not in excluded_edges
        and edge.get("from") in existing and edge.get("to") in existing][:limits.get("max_edges", 4096)]
    results, seen = [], set()
    for proposal in pack["proposals"]:
        if not isinstance(proposal, dict):
            raise ValueError("Each proposal must be an object")
        pid = proposal.get("id")
        if not _text(pid) or pid in seen:
            raise ValueError("Proposal IDs must be distinct nonempty strings")
        seen.add(pid)
        gap = gaps.get(proposal.get("gap_id")) if isinstance(proposal.get("gap_id"), str) else None
        errors = []
        if gap is None:
            errors.append("gap_id is not an open gap in this frontier result")
        nodes, relations = proposal.get("new_nodes", []), proposal.get("relations", [])
        if not isinstance(nodes, list) or len(nodes) > 16 or not isinstance(relations, list) or not 1 <= len(relations) <= 32:
            errors.append("Require at most 16 new nodes and 1..32 proposed relations")
            nodes, relations = [], []
        defined = set(existing)
        for node in nodes:
            if (not isinstance(node, dict) or not _text(node.get("id")) or node["id"] in defined
                    or node.get("kind") not in ("observable", "model", "concept", "requirement", "operation")
                    or not _text(node.get("label"))):
                errors.append("New nodes require fresh IDs, known kinds and labels")
            else:
                defined.add(node["id"])
        adjacency = defaultdict(set)
        for edge in available_edges:
            if edge.get("status") == "SUPPORTED" and (gap is None or not gap.get("relations")
                    or edge.get("relation") in gap["relations"]):
                adjacency[edge["from"]].add((edge["to"], False))
        for relation in relations:
            if (not isinstance(relation, dict) or not isinstance(relation.get("from"), str)
                    or not isinstance(relation.get("to"), str) or relation["from"] not in defined
                    or relation["to"] not in defined or not _text(relation.get("relation"))):
                errors.append("Relations require defined endpoints and a named relation")
            elif gap is None or not gap.get("relations") or relation["relation"] in gap["relations"]:
                adjacency[relation["from"]].add((relation["to"], True))
        if gap is not None:
            starts = [anchor for anchor in gap["anchors"] if anchor != gap["target"]]
            visited = {(anchor, False) for anchor in starts}
            pending = list(visited)
            while pending:
                node, used_proposal = pending.pop()
                for child, proposed in adjacency[node]:
                    state = (child, used_proposal or proposed)
                    if state not in visited:
                        visited.add(state)
                        pending.append(state)
            if (gap["target"], True) not in visited:
                errors.append("Proposed relations do not bridge a gap anchor to its target using its required relation types")
        assumptions = proposal.get("assumptions")
        if not isinstance(assumptions, list) or not 1 <= len(assumptions) <= 16 or not all(_text(x) for x in assumptions):
            errors.append("Declare 1..16 assumptions")
        prediction = proposal.get("prediction")
        if (not isinstance(prediction, dict) or not isinstance(prediction.get("observable"), str)
                or prediction["observable"] not in defined or not _text(prediction.get("if_proposal"))
                or not _text(prediction.get("if_rival"))
                or prediction["if_proposal"].strip() == prediction["if_rival"].strip()):
            errors.append("Prediction requires a defined observable and distinct proposal/rival outcomes")
        test = proposal.get("test")
        if not isinstance(test, dict) or not all(_text(test.get(key)) for key in ("protocol", "measurement", "stop_condition")):
            errors.append("Test requires protocol, measurement and stop_condition")
        positive, negative = proposal.get("next_if_positive"), proposal.get("next_if_negative")
        if not _text(positive) or not _text(negative) or positive.strip() == negative.strip():
            errors.append("Positive and negative results must change different next decisions")
        report = {"id": pid, "gap_id": proposal.get("gap_id"),
                  "status": "NEEDS_DEFINITION" if errors else "NEEDS_EVIDENCE",
                  "definition_errors": errors, "scientific_support": "UNKNOWN",
                  "evidence_status": "INPUT_REPORTED", "execution_authorized": False,
                  "cost": {"status": "UNKNOWN"}}
        if not errors:
            # Only the typed proposal fields survive. Caller success/support flags
            # cannot create evidence or replace the original research question.
            report["subgraph"] = {"nodes": [{key: node[key] for key in ("id", "kind", "label")} for node in nodes], "edges": [
                {"from": edge["from"], "to": edge["to"], "relation": edge["relation"], "status": "PROPOSED"}
                for edge in relations]}
            report.update(assumptions=deepcopy(assumptions),
                          prediction={key: prediction[key] for key in ("observable", "if_proposal", "if_rival")},
                          test={key: test[key] for key in ("protocol", "measurement", "stop_condition")},
                          next_if_positive=positive, next_if_negative=negative,
                          evidence_refs=deepcopy(gap["evidence_refs"]), original_decision=gap.get("decision"))
        results.append(report)
    return {"schema_version": 1, "advisor_type": "FRONTIER_PROPOSAL_REVIEW", "proposals": results,
            "adopted_relations": 0, "executed_tests": 0,
            "limitations": ["Distinct prediction text does not establish experimental discriminability.",
                            "This definition check does not validate causal claims, cost, code or scientific gains."]}

"""Bounded AND/OR dependency analysis of reported labels, never a proof kernel.

Schema: nodes=[{id,status,source}], hyperedges=[{id,premises,conclusion,
status,source}], goals=[node_id], optional limits. A source is a locator
string or {locator,file?,sha256?}. Unknown nodes can be proved directly;
their evidence atoms are ``node:<id>``. Proposed rules add ``rule:<id>``.
Only UNKNOWN leaves default to direct evidence atoms; derived nodes need
explicit allow_direct_evidence=true for a separate direct-proof route.
SUPPORTED closure never uses those hypothetical evidence atoms.
"""
import argparse
from copy import deepcopy
import hashlib
import heapq
import json
from pathlib import Path

ASSURANCE = "INPUT_REPORTED_DEPENDENCY_ANALYSIS_NOT_PROOF"
DEFAULT_LIMITS = {"max_nodes": 256, "max_hyperedges": 512,
                  "max_blocker_sets": 128, "max_combinations": 50000,
                  "max_source_bytes": 8 * 1024 * 1024}
HARD_LIMITS = {"max_nodes": 4096, "max_hyperedges": 16384,
               "max_blocker_sets": 2048, "max_combinations": 1000000,
               "max_source_bytes": 64 * 1024 * 1024}


class _Truncated(Exception):
    pass


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _source(value):
    if isinstance(value, str):
        _require(bool(value.strip()), "source locator must be nonempty")
        return
    _require(isinstance(value, dict) and isinstance(value.get("locator"), str)
             and value["locator"].strip(), "source must contain a locator")
    if "file" in value or "sha256" in value:
        _require(isinstance(value.get("file"), str) and value["file"],
                 "auditable source requires file and sha256")
        digest = value.get("sha256")
        _require(isinstance(digest, str) and len(digest) == 64
                 and all(c in "0123456789abcdefABCDEF" for c in digest),
                 "source sha256 must have 64 hexadecimal characters")


def _validate(spec):
    _require(isinstance(spec, dict) and spec.get("schema", 1) == 1,
             "hypergraph schema must be 1")
    limits = dict(DEFAULT_LIMITS)
    supplied = spec.get("limits", {})
    _require(isinstance(supplied, dict) and not (set(supplied) - set(limits)),
             "unknown hypergraph limit")
    limits.update(supplied)
    for name, value in limits.items():
        _require(type(value) is int and 1 <= value <= HARD_LIMITS[name],
                 "limits must be bounded positive integers: " + name)
    nodes, edges, goals = [spec.get(name) for name in ("nodes", "hyperedges", "goals")]
    _require(isinstance(nodes, list) and len(nodes) <= limits["max_nodes"],
             "max_nodes exceeded or nodes is not a list")
    _require(isinstance(edges, list) and len(edges) <= limits["max_hyperedges"],
             "max_hyperedges exceeded or hyperedges is not a list")
    _require(isinstance(goals, list) and len(goals) <= limits["max_nodes"],
             "goals must be a bounded list")
    index, edge_ids = {}, set()
    for node in nodes:
        _require(isinstance(node, dict), "node must be an object")
        ident = node.get("id")
        _require(isinstance(ident, str) and 0 < len(ident) <= 256
                 and ident not in index, "invalid or duplicate node id")
        _require(node.get("status") in ("SUPPORTED", "UNKNOWN", "CONTRADICTED"),
                 "invalid node status")
        _require("allow_direct_evidence" not in node
                 or type(node["allow_direct_evidence"]) is bool,
                 "allow_direct_evidence must be boolean")
        _source(node.get("source"))
        index[ident] = node
    for edge in edges:
        _require(isinstance(edge, dict), "hyperedge must be an object")
        ident, tails, head = edge.get("id"), edge.get("premises"), edge.get("conclusion")
        _require(isinstance(ident, str) and 0 < len(ident) <= 256
                 and ident not in edge_ids, "invalid or duplicate hyperedge id")
        edge_ids.add(ident)
        _require(isinstance(tails, list) and all(isinstance(t, str) and t in index for t in tails)
                 and len(tails) == len(set(tails)), "invalid or duplicate premises")
        _require(isinstance(head, str) and head in index, "unknown conclusion")
        _require(edge.get("status") in ("SUPPORTED", "PROPOSED", "CONTRADICTED"),
                 "invalid hyperedge status")
        _source(edge.get("source"))
    _require(all(isinstance(goal, str) and goal in index for goal in goals)
             and len(goals) == len(set(goals)), "unknown or duplicate goal")
    return index, edges, goals, limits


def audit_sources(spec, base_dir=None):
    """Check optional file digests; matching bytes cannot verify a statement."""
    nodes, edges, _, limits = _validate(spec)
    remaining = limits["max_source_bytes"]
    rows = []
    base = Path.cwd() if base_dir is None else Path(base_dir)
    for kind, records in (("node", nodes.values()), ("rule", edges)):
        for record in records:
            source = record["source"]
            if not isinstance(source, dict) or "file" not in source:
                continue
            path = Path(source["file"])
            if not path.is_absolute():
                path = base / path
            row = {"kind": kind, "id": record["id"], "source": deepcopy(source)}
            try:
                size = path.stat().st_size
                if size > remaining:
                    row["status"] = "BYTE_LIMIT_EXCEEDED"
                else:
                    with path.open("rb") as stream:
                        raw = stream.read(remaining + 1)
                    if len(raw) > remaining:
                        row["status"] = "BYTE_LIMIT_EXCEEDED"
                    else:
                        remaining -= len(raw)
                        actual = hashlib.sha256(raw).hexdigest()
                        row.update(status="MATCH" if actual == source["sha256"].lower() else "MISMATCH",
                                   actual_sha256=actual)
            except OSError as exc:
                row.update(status="UNAVAILABLE", reason=type(exc).__name__)
            rows.append(row)
    return {"assurance": "FILE_BYTES_ONLY_NOT_STATEMENT_VERIFICATION", "audits": rows,
            "all_requested_files_match": all(row["status"] == "MATCH" for row in rows)}


def _supported_closure(nodes, edges):
    """Declared closure with the original scan-order first derivation witnesses."""
    closure = {ident for ident, node in nodes.items() if node["status"] == "SUPPORTED"}
    derivations, conflicts, pending = {}, set(), []
    # Forward-ordered graphs finish in one scan, without a dependency index.
    for i, edge in enumerate(edges):
        head = edge["conclusion"]
        if edge["status"] != "SUPPORTED" or head in closure:
            continue
        if not all(tail in closure for tail in edge["premises"]):
            pending.append(i)
        elif nodes[head]["status"] == "CONTRADICTED":
            conflicts.add(edge["id"])
        else:
            closure.add(head)
            derivations[head] = edge["id"]
    # Without new support, the first pass already reached the fixed point.
    if pending and derivations:
        missing, waiting, ready = {}, {}, []
        for i in pending:
            edge = edges[i]
            if edge["conclusion"] in closure:
                continue
            tails = [tail for tail in edge["premises"] if tail not in closure]
            missing[i] = len(tails)
            for tail in tails:
                waiting.setdefault(tail, []).append(i)
            if not tails:
                ready.append((1, i))
        heapq.heapify(ready)
        while ready:
            turn, i = heapq.heappop(ready)
            edge = edges[i]
            head = edge["conclusion"]
            if nodes[head]["status"] == "CONTRADICTED":
                conflicts.add(edge["id"])
            elif head not in closure:
                closure.add(head)
                derivations[head] = edge["id"]
                for j in waiting.pop(head, ()):
                    missing[j] -= 1
                    if missing[j] == 0:
                        # Earlier rules wait for the next virtual ordered scan.
                        heapq.heappush(ready, (turn + (j <= i), j))
    return closure, derivations, conflicts


def _goal_relevance(edges, goals):
    """Reverse reachability through supported and proposed rules only."""
    incoming = {}
    for edge in edges:
        if edge["status"] != "CONTRADICTED":
            incoming.setdefault(edge["conclusion"], []).append(edge)
    relevant_nodes, relevant_edges = set(goals), set()
    pending = list(goals)
    while pending:
        for edge in incoming.get(pending.pop(), ()):
            relevant_edges.add(edge["id"])
            for tail in edge["premises"]:
                if tail not in relevant_nodes:
                    relevant_nodes.add(tail)
                    pending.append(tail)
    return relevant_nodes, relevant_edges


def analyze_hypergraph(spec):
    """Least declared closure and complete minimal missing-evidence sets, or UNKNOWN."""
    nodes, edges, goals, limits = _validate(spec)
    closure, derivations, conflicts = _supported_closure(nodes, edges)
    relevant_nodes, relevant_edges = _goal_relevance(edges, goals)

    incoming = {edge["conclusion"] for edge in edges}
    direct = {ident for ident, node in nodes.items()
              if node["status"] == "UNKNOWN"
              and node.get("allow_direct_evidence", ident not in incoming)}
    families = {ident: {frozenset()} if ident in closure else
                {frozenset({"node:" + ident})} if ident in direct else set()
                for ident, node in nodes.items()}
    combinations, truncated, reason = 0, False, None

    def insert(family, candidate):
        if any(old <= candidate for old in family):
            return False
        updated = {old for old in family if not candidate < old}
        updated.add(candidate)
        if len(updated) > limits["max_blocker_sets"]:
            raise _Truncated("max_blocker_sets exceeded")
        family.clear()
        family.update(updated)
        return True

    def spend():
        nonlocal combinations
        if combinations >= limits["max_combinations"]:
            raise _Truncated("max_combinations exceeded")
        combinations += 1

    # ponytail: antichain fixed point is exponential in the worst case;
    # explicit set/work caps return UNKNOWN rather than incomplete minimums.
    try:
        changed = True
        while changed:
            changed = False
            for edge in edges:
                head = edge["conclusion"]
                if edge["id"] not in relevant_edges or edge["status"] == "CONTRADICTED" \
                        or head in closure or nodes[head]["status"] == "CONTRADICTED":
                    continue
                plans = {frozenset({"rule:" + edge["id"]})} if edge["status"] == "PROPOSED" \
                    else {frozenset()}
                for tail in edge["premises"]:
                    joined = set()
                    for left in sorted(plans, key=lambda v: (len(v), sorted(v))):
                        for right in sorted(families[tail], key=lambda v: (len(v), sorted(v))):
                            spend()
                            insert(joined, left | right)
                    plans = joined
                    if not plans:
                        break
                for plan in sorted(plans, key=lambda v: (len(v), sorted(v))):
                    spend()
                    changed |= insert(families[head], plan)
    except _Truncated as exc:
        truncated, reason = True, str(exc)

    ready = []
    for edge in edges:
        if edge["id"] in relevant_edges and edge["status"] == "PROPOSED" \
                and edge["conclusion"] not in closure \
                and nodes[edge["conclusion"]]["status"] != "CONTRADICTED" \
                and set(edge["premises"]) <= closure:
            ready.append({"token": "rule:" + edge["id"], "kind": "PROPOSED_RULE_PROOF",
                          "premises_declared_supported": list(edge["premises"]),
                          "conclusion": edge["conclusion"], "source": deepcopy(edge["source"])})
    for ident in sorted(relevant_nodes - closure):
        if ident in direct:
            ready.append({"token": "node:" + ident,
                          "kind": "DIRECT_PROOF_ALTERNATIVE" if ident in incoming else "LEAF_NODE_EVIDENCE",
                          "source": deepcopy(nodes[ident]["source"])})

    results = {}
    for goal in goals:
        supported = goal in closure
        status = "DECLARED_SUPPORTED" if supported else nodes[goal]["status"]
        if status == "UNKNOWN" and not truncated and not families[goal]:
            status = "UNRESOLVED"
        sets = [[]] if supported else [] if truncated else \
            [sorted(v) for v in sorted(families[goal], key=lambda v: (len(v), sorted(v)))]
        results[goal] = {"status": status, "minimal_missing_evidence_sets": sets,
                         "blocker_sets_complete": supported or not truncated}
    return {"schema": 1, "assurance": ASSURANCE,
            "declared_supported_closure": sorted(closure),
            "declared_derivation_rules": derivations,
            "active_contradicted_conclusion_rules": sorted(conflicts),
            "goals": results, "ready_obligations": ready,
            "truncated": truncated, "truncation_reason": reason,
            "combinations_examined": combinations, "limits": limits,
            "blocker_semantics": "UNKNOWN leaves default to direct evidence; derived nodes need explicit allow_direct_evidence=true. Proposed rule IDs remain separate proof obligations. No cost or probability is inferred.",
            "direct_evidence_node_ids": sorted(direct),
            "reported_nodes": deepcopy(spec["nodes"]),
            "reported_hyperedges": deepcopy(spec["hyperedges"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--audit-files", action="store_true")
    args = parser.parse_args()
    path = Path(args.input)
    _require(path.stat().st_size <= 8 * 1024 * 1024, "input file exceeds 8 MiB")
    spec = json.loads(path.read_text(encoding="utf-8"))
    result = analyze_hypergraph(spec)
    if args.audit_files:
        result["source_file_audit"] = audit_sources(spec, path.parent)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with Path(args.output).open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    else:
        print(text)
    return 2 if result["truncated"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

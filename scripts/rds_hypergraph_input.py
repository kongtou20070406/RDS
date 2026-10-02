"""Compile small dependency declarations into the existing hypergraph schema.

Only unambiguous input repairs are automatic. Missing evidence stays unknown;
the generated table is an implementation detail, not a new proof format.
"""
from copy import deepcopy
import hashlib
import json
import math


def load_input(text):
    """Accept JSON, a whole JSON code fence, and trailing commas; execute nothing."""
    text = text.lstrip("\ufeff").strip()
    repairs = []
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].strip().lower() in ("```", "```json") \
            and lines[-1].strip() == "```":
        text = "\n".join(lines[1:-1])
        repairs.append("removed JSON code fence")
    output, quoted, escaped, removed = [], False, False, False
    for i, char in enumerate(text):
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            output.append(char)
        elif char == ",":
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] in "}]":
                removed = True
            else:
                output.append(char)
        else:
            output.append(char)
    if removed:
        repairs.append("removed trailing commas outside strings")

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key: " + key + "; supply one value for this field")
            value[key] = item
        return value

    def constant(value):
        raise ValueError("Non-finite JSON value: " + value)

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Non-finite JSON value: " + value)
        return result

    try:
        return json.loads("".join(output), object_pairs_hook=pairs, parse_constant=constant,
                          parse_float=number), repairs
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Dependency input must contain one JSON object: " + str(exc)) from exc


def prepare_input(value, locator="input"):
    """Fill the internal table and collect all input ambiguities in one review."""
    review = {"repairs": [], "warnings": [], "errors": [], "generated_node_ids": []}

    def note(bucket, path, reason):
        review[bucket].append({"path": path, "reason": reason})

    if not isinstance(value, dict):
        note("errors", "$", "supply an object containing claims/nodes, rules and goal(s)")
        return None, review
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('dependency declaration exceeds 8 MiB')
    except (ValueError, TypeError, RecursionError) as exc:
        note('errors', '$', 'supply bounded, finite JSON data: ' + str(exc))
        return None, review
    spec = deepcopy(value)
    if isinstance(spec.get("dependency_map"), dict) and (
            spec.get("assurance") == "INPUT_REPORTED_DEPENDENCY_ANALYSIS_NOT_PROOF"
            or not any(k in spec for k in ("nodes", "claims", "hyperedges", "rules"))):
        spec = spec["dependency_map"]
        note("repairs", "$", "loaded the program-generated dependency_map snapshot")
    # Existing valid maps retain their exact metadata and reported identities.
    # Alias handling is an input adapter, not a reinterpretation of canonical rows.
    from rds_hypergraph import _validate
    try:
        _validate(spec)
    except ValueError:
        pass
    else:
        return spec, review

    def field(row, names, default, path):
        present = [name for name in names if name in row]
        if len(present) > 1 and any(row[name] != row[present[0]] for name in present[1:]):
            note("errors", path, "conflicting aliases: " + ", ".join(present))
        if present and present[0] != names[0]:
            note("repairs", path, present[0] + " -> " + names[0])
        return row[present[0]] if present else default

    def rows(value, path, cap):
        if isinstance(value, dict):
            if len(value) > cap:
                note("errors", path, "record count exceeds the hard bound")
                return []
            result = []
            for ident, row in value.items():
                row = deepcopy(row) if isinstance(row, dict) else {"status": row}
                if "id" in row and row["id"] != ident:
                    note("errors", path + "." + str(ident), "map key and id disagree")
                row.setdefault("id", ident)
                result.append(row)
            note("repairs", path, "expanded keyed records into the internal table")
            return result
        if isinstance(value, list) and len(value) <= cap:
            return value
        note("errors", path, "supply a list or an object keyed by record ID within the hard bound")
        return []

    def ident(value, path):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
            note("errors", path, "supply a nonempty identifier of at most 256 characters")
            return None
        if value != value.strip():
            note("repairs", path, "trimmed identifier whitespace")
        return value.strip()

    def status(value, rule, path):
        default = "PROPOSED" if rule else "UNKNOWN"
        if value is None:
            note("repairs", path, "defaulted to " + default)
            return default
        result = value.strip().upper() if isinstance(value, str) else ""
        if result in ({"SUPPORTED", "PROPOSED", "CONTRADICTED"} if rule
                      else {"SUPPORTED", "UNKNOWN", "CONTRADICTED"}):
            if result != value:
                note("repairs", path, "normalized status spelling")
            return result
        note("warnings", path, "unrecognized status retained as " + default)
        return default

    def source(row, path):
        value = row.get("source")
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict) and isinstance(value.get("locator"), str) and value["locator"].strip():
            return value
        note("warnings", path + ".source", "source not supplied; locator records this input declaration only")
        if row["status"] == "SUPPORTED":
            row["status"] = "PROPOSED" if path.startswith("hyperedges") else "UNKNOWN"
            note("repairs", path + ".status", "withheld support until a source is supplied")
        return {"locator": str(locator) + "#" + path}

    nodes, index = [], {}
    node_rows = rows(field(spec, ("nodes", "claims"), [], "nodes"), "nodes", 4096)
    for i, item in enumerate(node_rows):
        path = "nodes[" + str(i) + "]"
        row = {"id": item} if isinstance(item, str) else deepcopy(item)
        if not isinstance(row, dict):
            note("errors", path, "supply a claim ID or object")
            continue
        name = ident(field(row, ("id", "name"), None, path + ".id"), path + ".id")
        if name is None:
            continue
        if name in index:
            note("errors", path + ".id", "duplicate claim ID: " + name)
            continue
        row["id"] = name
        row["status"] = status(field(row, ("status", "state"), None, path + ".status"), False, path + ".status")
        row["source"] = source(row, path)
        for alias in ("name", "state"):
            row.pop(alias, None)
        nodes.append(row)
        index[name] = row

    def placeholder(name, path):
        if name not in index:
            row = {"id": name, "status": "UNKNOWN", "source": {"locator": str(locator) + "#" + path}}
            nodes.append(row)
            index[name] = row
            review["generated_node_ids"].append(name)
            note("repairs", path, "created UNKNOWN claim for reference " + name)

    edges, edge_ids = [], set()
    edge_rows = rows(field(spec, ("hyperedges", "rules"), [], "hyperedges"), "hyperedges", 16384)
    for i, item in enumerate(edge_rows):
        path = "hyperedges[" + str(i) + "]"
        if not isinstance(item, dict):
            note("errors", path, "supply a rule object with from/premises and to/conclusion")
            continue
        row = deepcopy(item)
        tails = field(row, ("premises", "from", "if"), None, path + ".premises")
        if isinstance(tails, str):
            tails = [tails]
            note("repairs", path + ".premises", "expanded one premise into a list")
        if not isinstance(tails, list) or len(tails) > 4096:
            note("errors", path + ".premises", "supply the premises; use [] only for an explicit assumption-free rule")
            continue
        names = [ident(v, path + ".premises") for v in tails]
        head = ident(field(row, ("conclusion", "to", "then"), None, path + ".conclusion"), path + ".conclusion")
        if head is None or any(v is None for v in names):
            continue
        row["premises"] = list(dict.fromkeys(names))
        if len(row["premises"]) != len(names):
            note("repairs", path + ".premises", "removed repeated AND premises")
        row["conclusion"] = head
        row["status"] = status(field(row, ("status", "state"), None, path + ".status"), True, path + ".status")
        row["source"] = source(row, path)
        for alias in ("state", "from", "if", "to", "then"):
            row.pop(alias, None)
        if "id" not in row:
            raw = json.dumps({k: row[k] for k in ("premises", "conclusion", "source")}, sort_keys=True).encode()
            row["id"] = "rule-" + hashlib.sha256(raw).hexdigest()[:20]
            note("repairs", path + ".id", "generated stable rule ID " + row["id"])
        name = ident(row["id"], path + ".id")
        if name is None:
            continue
        if name in edge_ids:
            note("errors", path + ".id", "duplicate rule ID: " + name)
            continue
        row["id"] = name
        edge_ids.add(name)
        for name in row["premises"] + [head]:
            placeholder(name, path)
        edges.append(row)

    goals = field(spec, ("goals", "goal"), [], "goals")
    if isinstance(goals, str):
        goals = [goals]
        note("repairs", "goals", "expanded one goal into a list")
    if not isinstance(goals, list) or len(goals) > 4096:
        note("errors", "goals", "supply a goal ID or list of goal IDs")
        goals = []
    goals = [ident(v, "goals") for v in goals]
    goals = list(dict.fromkeys(v for v in goals if v is not None))
    for name in goals:
        placeholder(name, "goals")
    result = {k: v for k, v in spec.items() if k not in {"claims", "rules", "goal"}}
    result.update(schema=spec.get("schema", 1), nodes=nodes, hyperedges=edges, goals=goals)
    return result, review

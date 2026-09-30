"""Read-only, bounded artifact import. Observation never certifies a mechanism."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path

from rds_costs import COST_BINDING_FIELDS, finite, receipt_identity, receipt_issues, sha256, summarize_costs
from rds_verify_types import digest, require

SCHEMA = "rds-artifact-manifest-v1"
REPORT_SCHEMA = "rds-artifact-report-v1"
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10000
MAX_SOURCES = 64
MAX_FACTS = 256
SELF_SIGNED = {"verified", "pass", "manipulation_verified", "falsifier_triggered",
               "primary_metric_gain", "final_run_authorized", "matched_recipe", "matched_compute"}
BINDING_FIELDS = ("run_id",) + COST_BINDING_FIELDS + ("metric",)


class ArtifactFact(dict):
    """In-memory importer origin; serialized dictionaries cannot self-sign it."""
    def __init__(self, record):
        super().__init__(record)
        self.provenance_status = {"OBSERVED": "ARTIFACT_OBSERVED", "DECLARED": "ARTIFACT_DECLARED",
                                  "DERIVED": "PROGRAM_DERIVED"}.get(record.get("kind"), "UNKNOWN")


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("non-finite JSON constant: " + value)

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    _finite_tree(result)
    return result


def _finite_tree(value, depth=0):
    require(depth <= 32, "JSON nesting exceeds 32")
    if isinstance(value, float):
        require(finite(value), "non-finite numeric value")
    elif isinstance(value, dict):
        for child in value.values():
            _finite_tree(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _finite_tree(child, depth + 1)


def _read(path, base):
    path = (base / path).resolve()
    path.relative_to(base)
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    require(len(raw) <= MAX_FILE_BYTES, "file exceeds 2 MiB limit")
    return raw


def _pointer(document, pointer):
    require(isinstance(pointer, str) and (pointer == "" or pointer.startswith("/")), "expected JSON pointer")
    segments = pointer.split("/")[1:] if pointer else []
    require(len(segments) <= 32, "pointer depth exceeds 32")
    result = document
    for segment in segments:
        # RFC 6901 escapes; malformed escapes cannot alias a different field.
        require("~" not in segment.replace("~0", "").replace("~1", ""), "invalid JSON pointer escape")
        key = segment.replace("~1", "/").replace("~0", "~")
        if isinstance(result, list):
            require(key.isdigit() and (key == "0" or not key.startswith("0")), "invalid array index")
            result = result[int(key)]
        else:
            result = result[key]
    return result


def _parse(raw, kind, fmt):
    text = raw.decode("utf-8-sig")
    if fmt == "json":
        return strict_json(text)
    if fmt == "csv" and kind == "metric":
        reader = csv.DictReader(io.StringIO(text))
        require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames), "CSV needs unique headers")
        rows = []
        for row in reader:
            require(len(rows) < MAX_ROWS, "CSV row limit exceeded")
            require(None not in row and None not in row.values(), "CSV row/header width mismatch")
            rows.append(row)
        return rows
    if fmt in ("jsonl", "kv") and kind == "log":
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            require(number <= MAX_ROWS, "log row limit exceeded")
            if fmt == "jsonl":
                rows.append((number, strict_json(line)))
            else:
                require("=" in line, "log must contain explicit key=value records")
                key, value = line.split("=", 1)
                key = key.strip()
                require(key and key not in {r[1] for r in rows}, "duplicate or empty log key")
                try:
                    parsed = strict_json(value.strip())
                except json.JSONDecodeError:
                    parsed = value.strip()
                rows.append((number, key, parsed))
        return rows
    raise ValueError("unsupported source kind/format")


def _metadata(document, fmt):
    if fmt == "jsonl":
        objects = [r[1] for r in document]
    elif fmt == "kv":
        objects = [{row[1]: row[2] for row in document}]
    elif isinstance(document, list):
        objects = document
    else:
        objects = [document]
    result, conflicts = {}, []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        identity, collision = receipt_identity(obj)
        conflicts.extend(collision)
        origins = [obj] + [obj[k] for k in ("binding", "protocol") if isinstance(obj.get(k), dict)]
        for origin in origins:
            if "metric" in origin:
                if "metric" in identity and identity["metric"] != origin["metric"]:
                    conflicts.append("metric")
                else:
                    identity["metric"] = origin["metric"]
        for key in BINDING_FIELDS:
            if key not in identity:
                continue
            if key in result and result[key] != identity[key]:
                conflicts.append(key)
            else:
                result[key] = identity[key]
    return result, sorted(set(conflicts))


def _extract(document, selector, fmt):
    if fmt == "csv":
        row, column = selector.get("row"), selector.get("column")
        require(type(row) is int and 1 <= row <= len(document), "CSV row is 1-based and must exist")
        value = document[row - 1][column]
        if selector.get("type", "number") == "number":
            value = strict_json(value)
            require(finite(value), "CSV metric is not a finite number")
        else:
            require(selector["type"] == "string", "unsupported CSV value type")
        return value, "row:" + str(row) + ":column:" + str(column), column
    if fmt == "kv":
        matching = [row for row in document if row[1] == selector.get("key")]
        require(len(matching) == 1, "log key missing or ambiguous")
        number, key, value = matching[0]
        return value, "line:" + str(number) + ":key:" + key, key
    if fmt == "jsonl":
        number = selector.get("row")
        matching = [row for row in document if row[0] == number]
        require(len(matching) == 1, "JSONL physical line must exist")
        pointer = selector.get("pointer")
        return _pointer(matching[0][1], pointer), "line:" + str(number) + ":pointer:" + pointer, pointer.rsplit("/", 1)[-1]
    pointer = selector.get("pointer")
    return _pointer(document, pointer), "pointer:" + pointer, pointer.rsplit("/", 1)[-1]


def _fact(fid, value, kind, source, binding, **extra):
    record = {"id": fid, "value": value, "kind": kind, "source": deepcopy(source),
              "binding": deepcopy(binding), "reliable": kind != "UNKNOWN", **extra}
    return ArtifactFact(record)


def _unknown(record, reason):
    if record["kind"] != "UNKNOWN":
        record["declared_value"] = record["value"]
    record.update(value=None, kind="UNKNOWN", reliable=False, reason=reason)
    record.provenance_status = "UNKNOWN"


def ingest_manifest(path, root=None, receipts=None):
    """Import only named values, keeping missing/conflicting evidence explicit.

    Hashes bind exact bytes. Manifest binding metadata remains a declaration;
    an OBSERVED fact means that value was read, never executor/mechanism proof.
    `receipts` accepts optional records from an append-only project store.
    """
    path = Path(path).resolve()
    base = Path(root).resolve() if root is not None else path.parent
    manifest = strict_json(_read(str(path), base).decode("utf-8-sig"))
    require(isinstance(manifest, dict) and manifest.get("schema") == SCHEMA, "unsupported manifest schema")
    sources, derived = manifest.get("sources", []), manifest.get("derived", [])
    require(isinstance(sources, list) and len(sources) <= MAX_SOURCES, "source limit exceeded")
    require(isinstance(derived, list) and len(derived) <= MAX_FACTS, "derived fact limit exceeded")
    report = {"schema": REPORT_SCHEMA, "status": "IMPORTED", "manifest_sha256": digest(manifest),
              "facts": {}, "source_inventory": [], "conflicts": [], "missing": [],
              "context": {"decision": deepcopy(manifest.get("decision", "choose_next")), "facts": {},
                          "costs": {}, "budget": deepcopy(manifest.get("budget", {}))}}
    require(receipts is None or isinstance(receipts, (list, tuple)), "receipts must be a list")
    receipt_records, by_run, owners, source_ids = list(receipts or []), {}, {}, set()
    file_cache = {}
    for spec in sources:
        require(isinstance(spec, dict) and isinstance(spec.get("id"), str) and spec["id"], "source needs an id")
        require(spec["id"] not in source_ids, "duplicate source id")
        source_ids.add(spec["id"])
        selectors = spec.get("facts", [])
        require(isinstance(selectors, list) and len(selectors) + len(report["facts"]) <= MAX_FACTS, "fact limit exceeded")
        kind, name = spec.get("kind"), spec.get("path")
        require(kind in {"config", "metric", "log", "receipt"} and isinstance(name, str), "source needs kind and path")
        fmt = spec.get("format", Path(name).suffix.lstrip(".").lower())
        if fmt in ("txt", "log"):
            fmt = "kv"
        require(kind not in {"config", "receipt"} or fmt == "json", "config/receipt must be JSON")
        inventory = {"id": spec["id"], "kind": kind, "path": name, "status": "UNKNOWN"}
        report["source_inventory"].append(inventory)
        binding = deepcopy(spec.get("binding", {}))
        require(isinstance(binding, dict), "source binding must be an object")
        problems, document, actual_sha = [], None, None
        try:
            cache_key = str((base / name).resolve())
            if cache_key not in file_cache:
                raw = _read(name, base)
                file_cache[cache_key] = (raw, digest(raw))
            raw, actual_sha = file_cache[cache_key]
            inventory["sha256"] = actual_sha
            require(sha256(spec.get("expected_sha256")), "expected_sha256 is missing or invalid")
            require(actual_sha == spec["expected_sha256"], "source hash mismatch")
            document = _parse(raw, kind, fmt)
            observed, collisions = _metadata(document, fmt)
            for key in BINDING_FIELDS:
                if key in binding and key in observed and binding[key] != observed[key]:
                    collisions.append(key)
                elif key not in binding and key in observed:
                    binding[key] = deepcopy(observed[key])
            if kind == "config" and binding.get("config_sha256") not in (None, actual_sha):
                collisions.append("config_sha256")
            if collisions:
                report["conflicts"].append({"source_id": spec["id"], "fields": sorted(set(collisions))})
                problems.append("conflicting source binding")
            absent = [k for k in ("run_id",) + COST_BINDING_FIELDS if binding.get(k) in (None, "", "UNKNOWN")]
            if kind == "metric" and (not isinstance(binding.get("metric"), dict) or
                                      not all(binding["metric"].get(k) for k in ("definition", "reduction"))):
                absent.append("metric.definition/reduction")
            if absent:
                problems.append("missing binding: " + ", ".join(absent))
            if kind == "receipt":
                problems.extend(receipt_issues(document, {k: binding[k] for k in ("run_id",) + COST_BINDING_FIELDS if k in binding}))
                receipt_records.append(document)
            inventory.update(status="CONFLICT" if collisions else "MISSING" if problems else "READ", binding=deepcopy(binding),
                             binding_status="DECLARED_AND_CHECKED_WHERE_PRESENT")
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
            problems.append(str(exc))
            inventory["status"] = "MISSING"
        if problems:
            report["missing"].append({"source_id": spec["id"], "reasons": problems})
        run_id = binding.get("run_id")
        if run_id:
            previous = by_run.setdefault(run_id, {})
            for key in BINDING_FIELDS[1:]:
                if key not in binding:
                    continue
                if key in previous and previous[key][0] != binding[key]:
                    report["conflicts"].append({"run_id": run_id, "fields": [key],
                                                "source_ids": [previous[key][1], spec["id"]]})
                else:
                    previous[key] = (deepcopy(binding[key]), spec["id"])
        for selector in selectors:
            require(isinstance(selector, dict) and isinstance(selector.get("id"), str) and selector["id"], "fact needs id")
            fid = selector["id"]
            value, locator, selected, reason = None, "unresolved", "", "; ".join(problems)
            if document is not None and not problems:
                try:
                    value, locator, selected = _extract(document, selector, fmt)
                    _finite_tree(value)
                    if selected in SELF_SIGNED or fid in SELF_SIGNED:
                        reason = "self-signed validation cannot be imported as evidence"
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    reason = str(exc)
                    report["missing"].append({"fact_id": fid, "source_id": spec["id"], "reason": reason})
            fact_kind = "UNKNOWN" if reason else "DECLARED" if kind == "config" else "OBSERVED"
            fact = _fact(fid, None if reason else value, fact_kind,
                         {"path": name, "sha256": actual_sha, "locator": locator}, binding,
                         **({"reason": reason, "declared_value": value} if reason else {}))
            if fid in report["facts"]:
                report["conflicts"].append({"fact_id": fid, "reason": "duplicate fact identity",
                                            "source_ids": [owners[fid], spec["id"]]})
                _unknown(report["facts"][fid], "duplicate fact identity")
            else:
                report["facts"][fid], owners[fid] = fact, spec["id"]
    # Store receipts are also identity evidence; do not ignore a contradictory one.
    for receipt in list(receipts or []):
        if not isinstance(receipt, dict):
            report["missing"].append({"reason": "provided receipt is not an object"})
            continue
        identity, collisions = receipt_identity(receipt)
        run_id = identity.get("run_id")
        for key, (value, source_id) in by_run.get(run_id, {}).items():
            if key in identity and value != identity[key]:
                collisions.append(key)
        if collisions:
            report["conflicts"].append({"run_id": run_id, "fields": sorted(set(collisions)),
                                        "source_ids": [item[1] for item in by_run.get(run_id, {}).values()]})
    # Poison every involved source, never let import order choose the winner.
    bad_sources = set()
    for conflict in report["conflicts"]:
        bad_sources.update(conflict.get("source_ids", []))
        if conflict.get("source_id"):
            bad_sources.add(conflict["source_id"])
    for fid, record in report["facts"].items():
        if owners[fid] in bad_sources:
            _unknown(record, "source identity conflict")
    for spec in derived:
        require(isinstance(spec, dict) and isinstance(spec.get("id"), str), "derived fact needs id")
        fid, method, ids = spec["id"], spec.get("method"), spec.get("input_fact_ids")
        require(fid not in report["facts"], "duplicate derived fact id")
        require(method in {"difference", "mean"} and isinstance(ids, list) and 0 < len(ids) <= MAX_FACTS and
                all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids),
                "only bounded difference/mean derivations are supported")
        require(method != "difference" or len(ids) == 2, "difference needs two inputs")
        inputs = [report["facts"].get(i) for i in ids]
        reason = ""
        if any(not r or r["kind"] == "UNKNOWN" or not finite(r["value"]) for r in inputs):
            reason = "derived input missing, conflicted or non-numeric"
        else:
            for key in ("data_sha256", "data_split", "metric"):
                if any(key not in r["binding"] for r in inputs) or any(inputs[0]["binding"][key] != r["binding"][key] for r in inputs):
                    reason = "derived inputs have unknown or incompatible " + key
        value = None if reason else inputs[0]["value"] - inputs[1]["value"] if method == "difference" else sum(r["value"] / len(inputs) for r in inputs)
        if value is not None and not finite(value):
            reason, value = "non-finite derived result", None
        record = _fact(fid, value, "UNKNOWN" if reason else "DERIVED",
                       {"path": path.name, "sha256": report["manifest_sha256"], "locator": "derived:" + fid},
                       {"inputs": [r["binding"] if r else None for r in inputs]},
                       input_fact_ids=ids, method=method, conditions={"same_data_split_metric": not bool(reason),
                       "declared": deepcopy(spec.get("conditions", []))}, **({"reason": reason} if reason else {}))
        report["facts"][fid] = record
        if reason:
            report["missing"].append({"fact_id": fid, "reason": reason})
    report["cost_report"] = summarize_costs(receipt_records)
    report["context"]["facts"] = report["facts"]
    # Explicitly choose one historical resource; never collapse a resource vector.
    cost_bindings = manifest.get("cost_bindings", [])
    require(isinstance(cost_bindings, list) and len(cost_bindings) <= MAX_FACTS, "cost binding limit exceeded")
    for cost in cost_bindings:
        require(isinstance(cost, dict) and all(isinstance(cost.get(k), str) and cost[k] for k in
                ("action_id", "run_id", "resource", "comparison_group")), "cost binding needs action/run/resource/comparison group")
        action_id = cost["action_id"]
        require(action_id not in report["context"]["costs"], "duplicate action cost binding")
        rows = [m for m in report["cost_report"]["measurements"] if m["run_id"] == cost["run_id"] and
                m["resource"] == cost["resource"] and ("attempt_id" not in cost or m["attempt_id"] == cost["attempt_id"])]
        reasons = []
        if len(rows) != 1:
            reasons.append("historical resource missing or ambiguous; select a completed attempt")
        if any(record["binding"].get("run_id") == cost["run_id"] and owners.get(fid) in bad_sources
               for fid, record in report["facts"].items()):
            reasons.append("historical run has an import identity conflict")
        if rows and "unit" in cost and rows[0]["unit"] != cost["unit"]:
            reasons.append("historical cost unit mismatch")
        records = [r for r in receipt_records if isinstance(r, dict) and r.get("run_id") == cost["run_id"] and
                   ("attempt_id" not in cost or r.get("attempt_id", r.get("run_id")) == cost["attempt_id"])]
        binding = receipt_identity(records[0])[0] if records else {}
        source = rows[0]["source"] if rows else {"receipt_id": cost["run_id"], "locator": "/resources/" + cost["resource"]}
        value = rows[0]["value"] if rows and not reasons else None
        record = _fact(action_id, value, "UNKNOWN" if reasons else "OBSERVED", source, binding,
                       resource=cost["resource"], unit=rows[0]["unit"] if rows else cost.get("unit"),
                       comparison_group=cost["comparison_group"], historical=True,
                       prediction_status="UNKNOWN", **({"reason": "; ".join(reasons)} if reasons else {}))
        report["context"]["costs"][action_id] = record
        if reasons:
            report["missing"].append({"action_id": action_id, "reasons": reasons})
    report["status"] = "CONFLICT" if report["conflicts"] else "INCOMPLETE" if report["missing"] or any(
        f["kind"] == "UNKNOWN" for f in report["facts"].values()) else "IMPORTED"
    return report

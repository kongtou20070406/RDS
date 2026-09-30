"""Receipt measurements and bounded control reuse; no scientific certification."""
from copy import deepcopy
import math
from pathlib import Path
import re

from rds_verify_types import digest

SCHEMA = "rds-cost-report-v1"
TERMINAL = {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "INTERRUPTED"}
IDENTITY_FIELDS = ("code_sha256", "config_sha256", "data_sha256", "data_split",
                   "init", "seed", "checkpoint", "schedule", "sample_work", "numeric_protocol")
COST_BINDING_FIELDS = ("code_sha256", "config_sha256", "data_sha256", "data_split")
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_RECEIPTS = 1024


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value) is not None


def _known(value):
    if value is None or isinstance(value, str) and (not value.strip() or value.upper() == "UNKNOWN"):
        return False
    if isinstance(value, (list, dict)):
        children = value.values() if isinstance(value, dict) else value
        return bool(value) and all(_known(child) for child in children)
    return not isinstance(value, float) or finite(value)


def receipt_identity(receipt):
    """Return declared identity and conflicts without preferring one record."""
    result, conflicts = {}, []
    for origin in (receipt, receipt.get("binding", {}), receipt.get("protocol", {})):
        if not isinstance(origin, dict):
            continue
        values = {k: origin[k] for k in IDENTITY_FIELDS if k in origin}
        for old, new in (("source_sha256", "code_sha256"), ("dataset_sha256", "data_sha256")):
            if old in origin:
                if new in values and values[new] != origin[old]:
                    conflicts.append(new)
                values[new] = origin[old]
        if "run_id" in origin:
            values["run_id"] = origin["run_id"]
        for key, value in values.items():
            if key in result and result[key] != value:
                conflicts.append(key)
            else:
                result[key] = deepcopy(value)
    return result, sorted(set(conflicts))


def receipt_issues(receipt, expected=None):
    if not isinstance(receipt, dict):
        return ["receipt is not an object"]
    issues = []
    try:
        body = {k: v for k, v in receipt.items() if k != "sha256"}
        if not sha256(receipt.get("sha256")) or digest(body) != receipt["sha256"]:
            issues.append("receipt integrity hash missing or mismatched")
    except (TypeError, ValueError):
        issues.append("receipt contains non-finite or unsupported values")
    identity, conflicts = receipt_identity(receipt)
    issues.extend("conflicting receipt identity: " + k for k in conflicts)
    for key in ("run_id",) + COST_BINDING_FIELDS:
        if not _known(identity.get(key)):
            issues.append("missing receipt identity: " + key)
        elif key.endswith("sha256") and not sha256(identity[key]):
            issues.append("invalid receipt identity hash: " + key)
    for key, value in (expected or {}).items():
        if not _known(identity.get(key)):
            issues.append("missing expected binding: " + key)
        elif identity[key] != value:
            issues.append("receipt binding mismatch: " + key)
    if receipt.get("run_status") not in TERMINAL:
        issues.append("receipt is not a completed attempt")
    return issues


def summarize_costs(receipts, bindings=None):
    """Keep units separate; failures and evaluations consume real resources too.

    A hash checks integrity, not honesty. Callers obtain receipts from the local
    append-only store or hash-bound source files, rather than model declarations.
    `bindings` is an optional run_id -> expected identity mapping.
    """
    if not isinstance(receipts, (list, tuple)) or len(receipts) > MAX_RECEIPTS:
        raise ValueError("receipts must be a bounded list")
    report = {"schema": SCHEMA, "status": "KNOWN", "measurements": [], "estimates": [],
              "totals": [], "missing": [], "conflicts": [], "attempts": []}
    if not receipts:
        report["missing"].append({"reason": "no completed receipts; resource cost is unknown"})
    seen, totals = {}, {}
    for receipt in receipts:
        run_id = receipt.get("run_id") if isinstance(receipt, dict) else None
        attempt = receipt.get("attempt_id", run_id) if isinstance(receipt, dict) else None
        identity_key = (run_id, attempt)
        try:
            fingerprint = digest(receipt)
        except (ValueError, TypeError):
            fingerprint = None
        if identity_key in seen:
            if seen[identity_key] != fingerprint:
                report["conflicts"].append({"run_id": run_id, "attempt_id": attempt,
                                            "reason": "different receipts for one attempt"})
            continue
        seen[identity_key] = fingerprint
        expected = (bindings or {}).get(run_id, {})
        issues = receipt_issues(receipt, expected)
        if issues:
            report["missing"].append({"run_id": run_id, "attempt_id": attempt, "reasons": issues})
            continue
        report["attempts"].append({"run_id": run_id, "attempt_id": attempt,
                                    "run_status": receipt["run_status"], "purpose": receipt.get("purpose", "UNKNOWN")})
        resources = deepcopy(receipt.get("resources", {}))
        if not isinstance(resources, dict):
            report["missing"].append({"run_id": run_id, "reason": "resources are not an object"})
            continue
        if "wall_seconds" not in resources and finite(receipt.get("elapsed_ms")):
            resources["wall_seconds"] = {"measured": receipt["elapsed_ms"] / 1000, "unit": "seconds"}
        for name in ("cpu_seconds", "gpu_seconds", "api_tokens", "api_cost"):
            if name not in resources:
                report["missing"].append({"run_id": run_id, "resource": name, "reason": "not measured"})
        if not resources:
            report["missing"].append({"run_id": run_id, "reason": "no resource measurements"})
        for name, entry in resources.items():
            if not isinstance(entry, dict):
                report["missing"].append({"run_id": run_id, "resource": name, "reason": "no measured resource record"})
                continue
            unit, value = entry.get("unit"), entry.get("measured")
            source = {"receipt_id": run_id, "sha256": receipt["sha256"], "locator": "/resources/" + name}
            if name == "wall_seconds" and "wall_seconds" not in receipt.get("resources", {}):
                source["locator"] = "/elapsed_ms"
            if isinstance(unit, str) and unit and finite(value) and value >= 0 and entry.get("unknown") is not True:
                item = {"run_id": run_id, "attempt_id": attempt, "resource": name, "value": value,
                        "unit": unit, "source": source, "status": "RECEIPT_RECORDED_MEASUREMENT"}
                report["measurements"].append(item)
                key = (name, unit)
                total = totals.setdefault(key, {"resource": name, "unit": unit, "value": 0, "receipt_ids": []})
                total["value"] += value
                total["receipt_ids"].append(run_id)
            else:
                report["missing"].append({"run_id": run_id, "resource": name, "reason": "measurement or unit unknown/invalid"})
            estimate = entry.get("charged_estimate")
            if finite(estimate) and estimate >= 0 and isinstance(unit, str) and unit:
                report["estimates"].append({"run_id": run_id, "resource": name, "value": estimate,
                                            "unit": unit, "source": source, "status": "CHARGED_ESTIMATE"})
        if isinstance(receipt.get("charged_allocation"), dict):
            report["estimates"].append({"run_id": run_id, "allocation": deepcopy(receipt["charged_allocation"]),
                                        "status": "CHARGED_ALLOCATION_NOT_MEASURED"})
    # Conflicting duplicates cannot retain the favourable first record.
    bad = {(c["run_id"], c["attempt_id"]) for c in report["conflicts"]}
    if bad:
        report["measurements"] = [m for m in report["measurements"] if (m["run_id"], m["attempt_id"]) not in bad]
        report["attempts"] = [m for m in report["attempts"] if (m["run_id"], m["attempt_id"]) not in bad]
        report["estimates"] = [m for m in report["estimates"] if m["run_id"] not in {b[0] for b in bad}]
        totals = {}
        for m in report["measurements"]:
            total = totals.setdefault((m["resource"], m["unit"]), {"resource": m["resource"], "unit": m["unit"], "value": 0, "receipt_ids": []})
            total["value"] += m["value"]
            total["receipt_ids"].append(m["run_id"])
    report["totals"] = []
    for total in totals.values():
        if finite(total["value"]):
            report["totals"].append(total)
        else:
            report["missing"].append({"resource": total["resource"], "unit": total["unit"], "reason": "total exceeds finite range"})
    report["status"] = "CONFLICT" if report["conflicts"] else "PARTIAL" if report["missing"] else "KNOWN"
    return report


def _operation_identity(record):
    """Accept a receipt/explicit operation or an existing registered project run."""
    result, conflicts = {}, []
    for origin in (record, record.get("manifest", {})):
        if not isinstance(origin, dict):
            conflicts.append("manifest")
            continue
        for key in ("arm", "argv", "cwd"):
            if key not in origin:
                continue
            if key in result and result[key] != origin[key]:
                conflicts.append(key)
            else:
                result[key] = origin[key]
    return result, sorted(set(conflicts))


def check_control_reuse(candidate, current, root=None):
    """Match a real control's protocol and exact operation in the project root.

    A bare protocol cannot identify which allowed command/arm was executed.
    Current must also declare arm=control and its complete expected argv, or
    supply a registered run with those fields in its manifest.
    """
    if not isinstance(candidate, dict) or not isinstance(current, dict):
        return {"schema": "rds-control-reuse-v1", "reusable": False, "reasons": ["control/current must be objects"]}
    reasons = receipt_issues(candidate)
    previous, conflicts = receipt_identity(candidate)
    expected, current_conflicts = receipt_identity(current)
    reasons.extend("conflicting current identity: " + k for k in current_conflicts)
    operation_reasons, operation_unknown = [], False
    actual, actual_conflicts = _operation_identity(candidate)
    intended, intended_conflicts = _operation_identity(current)
    for label, operation, conflicts in (("candidate", actual, actual_conflicts),
                                        ("current", intended, intended_conflicts)):
        if conflicts:
            operation_reasons.extend("conflicting " + label + " operation: " + key for key in conflicts)
            operation_unknown = True
        if not _known(operation.get("arm")):
            operation_reasons.append("missing " + label + " control arm")
            operation_unknown = True
        elif operation["arm"] != "control":
            operation_reasons.append(label + " arm is not control")
        argv = operation.get("argv")
        if not isinstance(argv, list) or not argv or not isinstance(argv[0], str) or not argv[0] or any(
                not isinstance(arg, str) or "\0" in arg for arg in argv):
            operation_reasons.append("missing or invalid " + label + " control argv")
            operation_unknown = True
    if actual.get("argv") != intended.get("argv"):
        operation_reasons.append("control operation mismatch: argv")
    base, hashes = Path(root or ".").resolve(), {}
    for label, operation in (("candidate", actual), ("current", intended)):
        # The actual root argument supplies current cwd; a receipt must record
        # its original cwd. An explicit current cwd must agree with that root.
        if label == "current" and "cwd" not in operation:
            continue
        cwd = operation.get("cwd")
        if not isinstance(cwd, str) or not cwd or not Path(cwd).is_absolute():
            operation_reasons.append("missing or invalid " + label + " control cwd")
            operation_unknown = True
        elif Path(cwd).resolve() != base:
            operation_reasons.append(label + " control cwd differs from project root")
    reasons.extend(operation_reasons)
    if candidate.get("run_status") != "SUCCEEDED":
        reasons.append("control did not finish SUCCEEDED")
    for key in IDENTITY_FIELDS:
        if not _known(previous.get(key)) or not _known(expected.get(key)):
            reasons.append("missing control identity: " + key)
        elif previous[key] != expected[key]:
            reasons.append("control identity mismatch: " + key)
    before, after = candidate.get("bindings_before"), candidate.get("bindings_after")
    if not isinstance(before, list) or not before or len(before) > 128:
        reasons.append("control needs a bounded original input binding inventory")
        before = []
    elif not {"code", "config", "data", "protocol"} <= {b.get("role") for b in before if isinstance(b, dict)}:
        reasons.append("control input inventory lacks code/config/data/protocol")
    if before != after:
        reasons.append("input bindings changed during the control run")
    artifacts = candidate.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts or len(artifacts) > 128:
        reasons.append("control needs a bounded artifact inventory with paths and hashes")
        artifacts = []
    for artifact in before + artifacts:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str) or not sha256(artifact.get("sha256")):
            reasons.append("invalid control artifact entry")
            continue
        path = (base / artifact["path"]).resolve()
        try:
            path.relative_to(base)
            if path not in hashes:
                with path.open("rb") as handle:
                    raw = handle.read(MAX_ARTIFACT_BYTES + 1)
                hashes[path] = digest(raw) if len(raw) <= MAX_ARTIFACT_BYTES else None
            if hashes[path] != artifact["sha256"]:
                reasons.append("control artifact hash/size mismatch: " + artifact["path"])
        except (OSError, ValueError):
            reasons.append("control artifact missing or outside root: " + artifact["path"])
    return {"schema": "rds-control-reuse-v1", "reusable": not reasons, "reasons": sorted(set(reasons)),
            "identity_fields": list(IDENTITY_FIELDS), "candidate_run_id": candidate.get("run_id"),
            "control_run_id": candidate.get("run_id") if actual.get("arm") == "control" else None,
            "operation_identity": {"status": "UNKNOWN" if operation_unknown else
                                   "MISMATCH" if operation_reasons else "MATCHED",
                                   "fields": ["arm", "argv", "cwd"]},
            "scientific_assessment": "UNKNOWN"}

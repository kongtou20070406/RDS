"""Paired, budgeted numeric confirmation; never a model's self-assessment.

Hashes, dates and source locators bind supplied records. Their independence and
authenticity remain INPUT_REPORTED; an external execution wrapper supplies them.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re


ARMS = ("baseline", "advisor")
TASK_KINDS = ("general", "extension_challenge", "retention_control")
MAX_TASKS = 64
MAX_CONFIRMATIONS = 8
MAX_ATTEMPTS = 128
MAX_METADATA_BYTES = 1024


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _number(value, name, nonnegative=False):
    _require(_finite(value) and (not nonnegative or value >= 0), f"Invalid finite numeric {name}")
    return value


def _timestamp(value, name):
    _require(_text(value), f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp") from exc
    _require(parsed.tzinfo is not None, f"{name} must be a timezone-aware ISO timestamp")
    return parsed


def _hash(value, name):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), f"Invalid {name} SHA256 identity")
    return value


def _json(value, name, cap):
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise ValueError(f"{name} must contain finite JSON values") from exc
    _require(len(raw) <= cap, f"{name} exceeds {cap} UTF-8 JSON bytes")
    return raw


def _source(value, name):
    _require(_text(value) or isinstance(value, dict) and any(_text(value.get(key))
             for key in ("path", "url", "locator", "receipt_id")), f"{name} requires a source locator")
    _json(value, name, MAX_METADATA_BYTES)


def _binding(row, protocol, protocol_sha):
    _require(row.get("protocol_id") == protocol["id"] and type(row.get("protocol_version")) is type(protocol["version"])
             and row["protocol_version"] == protocol["version"], "Protocol identity/version mismatch")
    if "protocol_sha256" in row:
        _require(row["protocol_sha256"] == protocol_sha, "Protocol content binding mismatch")


def _protocol(protocol):
    _require(isinstance(protocol, dict) and type(protocol.get("schema_version")) is int
             and protocol["schema_version"] == 1, "Advancement schema_version must be 1")
    raw = _json(protocol, "protocol", 512 * 1024)
    _require(_text(protocol.get("id")) and (_text(protocol.get("version")) or type(protocol.get("version")) is int
             and protocol["version"] > 0), "Protocol requires id and version")
    _require(_text(protocol.get("model_id")), "Protocol requires model_id")
    _hash(protocol.get("starting_evidence_sha256"), "starting_evidence")
    frozen = _timestamp(protocol.get("frozen_at"), "frozen_at")
    budget = protocol.get("budget")
    _require(isinstance(budget, dict) and 1 <= len(budget) <= 8, "Protocol requires 1..8 budget resources")
    for resource, row in budget.items():
        _require(_text(resource) and isinstance(row, dict) and _text(row.get("unit")), "Invalid budget resource/unit")
        _number(row.get("cap"), f"budget.{resource}.cap", True)
    tasks = protocol.get("tasks")
    _require(isinstance(tasks, list) and 1 <= len(tasks) <= MAX_TASKS, "Protocol requires 1..64 nonempty tasks")
    indexed = {}
    for task in tasks:
        _require(isinstance(task, dict) and _text(task.get("id")) and task["id"] not in indexed, "Task IDs must be unique")
        _require(task.get("kind", "general") in TASK_KINDS, "Invalid task kind")
        confirmations = task.get("confirmations")
        _require(isinstance(confirmations, list) and 1 <= len(confirmations) <= MAX_CONFIRMATIONS,
                 f"Task {task['id']} requires 1..8 frozen confirmations")
        contracts = {}
        for confirmation in confirmations:
            _require(isinstance(confirmation, dict) and _text(confirmation.get("id"))
                     and confirmation["id"] not in contracts, "Confirmation IDs must be unique within task")
            _hash(confirmation.get("intervention_sha256"), "intervention")
            _require(_text(confirmation.get("metric")) and _text(confirmation.get("unit")), "Confirmation requires metric/unit")
            _number(confirmation.get("tolerance"), "confirmation.tolerance", True)
            contracts[confirmation["id"]] = confirmation
        indexed[task["id"]] = contracts
    return indexed, frozen, hashlib.sha256(raw).hexdigest()


def evaluate_advancement(protocol, trajectories, confirmations):
    """Evaluate all frozen tasks under the same per-arm total budget vector.

    A task passes only when every preregistered numerical confirmation passes.
    The primary rate stays null until the complete cohort and budget are known.
    """
    tasks, frozen, protocol_sha = _protocol(protocol)
    _require(isinstance(trajectories, list) and len(trajectories) <= MAX_TASKS * 2, "At most 128 trajectories are allowed")
    _require(isinstance(confirmations, list) and len(confirmations) <= MAX_TASKS * MAX_CONFIRMATIONS * 2,
             "At most 1024 confirmation records are allowed")
    _json([trajectories, confirmations], "evaluation records", 4 * 1024 * 1024)
    errors = {(tid, arm): [] for tid in tasks for arm in ARMS}
    trajectory_index, confirmation_index, global_errors = {}, {}, []
    cost = {arm: {resource: {"unit": row["unit"], "cap": row["cap"], "known_subtotal": 0,
                            "unknown_events": [], "errors": []} for resource, row in protocol["budget"].items()} for arm in ARMS}
    non_budget_costs = []
    holdout_ids = {identifier for tid, contracts in tasks.items() for cid, contract in contracts.items()
                   for identifier in (cid, f"{tid}:{cid}", contract["intervention_sha256"])}

    def error(key, message):
        if key in errors:
            errors[key].append(message)
        else:
            global_errors.append(message)

    def costs(row, key, event_id):
        arm = key[1]
        if arm not in ARMS:
            return
        vector = row.get("costs")
        if vector is None:
            for aggregate in cost[arm].values():
                aggregate["unknown_events"].append(event_id)
            return
        try:
            _require(isinstance(vector, dict) and len(vector) <= 16 and all(_text(resource) for resource in vector),
                     "Invalid cost vector")
            _json(vector, "cost vector", 4096)
        except ValueError:
            error(key, f"Invalid cost vector: {event_id}")
            for aggregate in cost[arm].values():
                aggregate["errors"].append(event_id)
            return
        for resource, aggregate in cost[arm].items():
            record = vector.get(resource)
            if record is None:
                aggregate["unknown_events"].append(event_id)
                continue
            if not isinstance(record, dict) or record.get("unit") != aggregate["unit"]:
                aggregate["errors"].append(f"{event_id}: incompatible {resource} unit")
                error(key, f"Incompatible cost unit for {resource}: {event_id}")
                continue
            amount = record.get("value")
            if amount is None:
                aggregate["unknown_events"].append(event_id)
            elif not _finite(amount) or amount < 0:
                aggregate["errors"].append(f"{event_id}: invalid numeric cost")
                error(key, f"Invalid numeric cost: {event_id}")
            else:
                total = aggregate["known_subtotal"] + amount
                if not _finite(total):
                    aggregate["errors"].append(f"{event_id}: nonfinite cost sum")
                    error(key, f"Nonfinite cost sum: {event_id}")
                else:
                    aggregate["known_subtotal"] = total
        for resource, record in vector.items():
            if resource not in protocol["budget"]:
                non_budget_costs.append({"task_id": key[0], "arm": arm, "event_id": event_id,
                    "resource": resource, "record": deepcopy(record), "status": "UNKNOWN",
                    "reason": "Resource outside declared budget; no aggregation or conversion"})

    for index, row in enumerate(trajectories):
        if not isinstance(row, dict) or not _text(row.get("task_id")) or row.get("arm") not in ARMS:
            global_errors.append(f"Invalid trajectory identity at index {index}")
            continue
        key = (row["task_id"], row["arm"])
        if key not in errors:
            global_errors.append(f"Trajectory task outside frozen cohort: {row['task_id']}")
        if key in trajectory_index:
            error(key, "Duplicate trajectory")
        else:
            trajectory_index[key] = row
        attempts = row.get("attempts")
        if attempts is None or attempts == []:
            for aggregate in cost[row["arm"]].values():
                aggregate["unknown_events"].append(f"{row['task_id']}:missing_attempt_ledger")
        elif not isinstance(attempts, list) or len(attempts) > MAX_ATTEMPTS:
            error(key, "Attempts must be a list of at most 128 records")
            for aggregate in cost[row["arm"]].values():
                aggregate["errors"].append(f"{row['task_id']}:invalid_attempt_ledger")
        else:
            seen = set()
            for attempt in attempts:
                if not isinstance(attempt, dict) or not _text(attempt.get("id")):
                    error(key, "Invalid attempt identity")
                    for aggregate in cost[row["arm"]].values():
                        aggregate["errors"].append(f"{row['task_id']}:invalid_attempt")
                    continue
                if attempt["id"] in seen:
                    error(key, "Duplicate attempt identity")
                seen.add(attempt["id"])
                if attempt.get("status") not in ("SUCCEEDED", "FAILED", "INTERRUPTED", "TIMED_OUT"):
                    error(key, "Invalid attempt lifecycle status")
                if "model_id" in attempt and attempt["model_id"] != protocol["model_id"]:
                    error(key, "Attempt model identity mismatch")
                costs(attempt, key, f"{row['task_id']}:attempt:{attempt['id']}")
    for index, row in enumerate(confirmations):
        if not isinstance(row, dict) or not _text(row.get("task_id")) or row.get("arm") not in ARMS \
                or not _text(row.get("confirmation_id")):
            global_errors.append(f"Invalid confirmation identity at index {index}")
            continue
        key = (row["task_id"], row["arm"])
        cid = row["confirmation_id"]
        if key not in errors or cid not in tasks.get(row["task_id"], {}):
            global_errors.append(f"Confirmation outside frozen cohort: {row['task_id']}:{cid}")
        record_key = (*key, cid)
        if record_key in confirmation_index:
            error(key, f"Duplicate confirmation: {cid}")
        else:
            confirmation_index[record_key] = row
        costs(row, key, f"{row['task_id']}:confirmation:{cid}")

    graded, structure_changes = {}, []
    for tid, contracts in tasks.items():
        for arm in ARMS:
            key = (tid, arm)
            trajectory = trajectory_index.get(key)
            checks, missing = [], []
            if trajectory is None:
                missing.append("trajectory")
                for aggregate in cost[arm].values():
                    aggregate["unknown_events"].append(f"{tid}:missing_trajectory")
            else:
                try:
                    _binding(trajectory, protocol, protocol_sha)
                    _source(trajectory.get("source"), "trajectory.source")
                    _require(trajectory.get("model_id") == protocol["model_id"], "Model identity mismatch")
                    _require(trajectory.get("starting_evidence_sha256") == protocol["starting_evidence_sha256"], "Starting evidence mismatch")
                    selected = _timestamp(trajectory.get("selected_at"), "selected_at")
                    _require(frozen <= selected, "Confirmation protocol was not frozen before selection")
                    used = trajectory.get("selection_used_ids")
                    _require(isinstance(used, list) and len(used) <= 128 and all(_text(cid) for cid in used),
                             "selection_used_ids disclosure is required")
                    _require(not set(used) & holdout_ids, "Confirmation intervention was used for selection")
                    predictions = trajectory.get("predictions", [])
                    _require(isinstance(predictions, list) and len(predictions) <= MAX_CONFIRMATIONS, "Predictions must be a bounded list")
                    prediction_index = {}
                    for prediction in predictions:
                        _require(isinstance(prediction, dict) and _text(prediction.get("confirmation_id")), "Invalid prediction identity")
                        cid = prediction["confirmation_id"]
                        _require(cid in contracts and cid not in prediction_index, "Unexpected or duplicate prediction identity")
                        prediction_index[cid] = prediction
                    for cid, contract in contracts.items():
                        prediction = prediction_index.get(cid)
                        confirmation = confirmation_index.get((*key, cid))
                        if prediction is None or confirmation is None:
                            if prediction is None:
                                missing.append(f"{cid}:prediction")
                            if confirmation is None:
                                missing.append(f"{cid}:confirmation")
                                for aggregate in cost[arm].values():
                                    aggregate["unknown_events"].append(f"{tid}:missing_confirmation:{cid}")
                            continue
                        _binding(confirmation, protocol, protocol_sha)
                        _source(confirmation.get("source"), "confirmation.source")
                        _require(confirmation.get("intervention_sha256") == contract["intervention_sha256"], "Intervention identity mismatch")
                        _require(confirmation.get("used_for_selection") is False, "Confirmation independence disclosure must be false")
                        _require(prediction.get("metric") == confirmation.get("metric") == contract["metric"]
                                 and prediction.get("unit") == confirmation.get("unit") == contract["unit"], "Prediction/observation metric or unit mismatch")
                        predicted_at = _timestamp(prediction.get("predicted_at"), "predicted_at")
                        observed_at = _timestamp(confirmation.get("observed_at"), "observed_at")
                        _require(frozen <= selected <= predicted_at < observed_at, "Prediction/observation ordering violates frozen confirmation")
                        predicted, observed = prediction.get("value"), confirmation.get("observed")
                        if predicted is None or observed is None:
                            if confirmation.get("success") is True or confirmation.get("verified") is True:
                                raise ValueError("Self-signed success is not a numeric observation")
                            missing.append(f"{cid}:numeric_observation_or_prediction")
                            continue
                        _number(predicted, "prediction")
                        _number(observed, "observation")
                        residual = abs(predicted - observed)
                        if not _finite(residual):
                            missing.append(f"{cid}:nonfinite_residual")
                            continue
                        checks.append({"confirmation_id": cid, "predicted": predicted, "observed": observed,
                            "metric": contract["metric"], "unit": contract["unit"], "absolute_error": residual,
                            "tolerance": contract["tolerance"], "status": "PASS" if residual <= contract["tolerance"] else "FAIL"})
                    for name in ("generation", "selection"):
                        if name in trajectory:
                            _require(isinstance(trajectory[name], dict), f"{name} manifest must be an object")
                            _json(trajectory[name], name, MAX_METADATA_BYTES)
                except ValueError as exc:
                    errors[key].append(str(exc))
            status = "INVALID" if errors[key] else "UNMEASURED" if missing else \
                     "FAIL" if any(check["status"] == "FAIL" for check in checks) else "PASS"
            graded[key] = {"status": status, "confirmation_checks": checks, "missing": missing,
                           "possible_success": not any(check["status"] == "FAIL" for check in checks), "errors": list(errors[key])}
        change = {"task_id": tid, "assurance": "INPUT_REPORTED"}
        for name in ("generation", "selection"):
            manifests = {}
            for arm in ARMS:
                value = trajectory_index.get((tid, arm), {}).get(name)
                try:
                    _require(isinstance(value, dict), "Manifest absent or invalid")
                    _json(value, name, MAX_METADATA_BYTES)
                    manifests[arm] = deepcopy(value)
                except ValueError:
                    manifests[arm] = None
            change[name] = {**manifests, "changed": manifests["baseline"] != manifests["advisor"]
                           if all(value is not None for value in manifests.values()) else None}
        structure_changes.append(change)

    budget_status = {}
    for arm in ARMS:
        for aggregate in cost[arm].values():
            aggregate["status"] = "INVALID" if aggregate["errors"] else \
                "OVER_BUDGET" if aggregate["known_subtotal"] > aggregate["cap"] else \
                "UNKNOWN" if aggregate["unknown_events"] else "KNOWN"
            aggregate["value"] = aggregate["known_subtotal"] if aggregate["status"] == "KNOWN" else None
        statuses = {aggregate["status"] for aggregate in cost[arm].values()}
        budget_status[arm] = "INVALID" if statuses & {"INVALID", "OVER_BUDGET"} else "UNKNOWN" if "UNKNOWN" in statuses else "IN_BUDGET"
        for tid in tasks:
            row = graded[(tid, arm)]
            if budget_status[arm] == "INVALID":
                row["errors"].append("Total arm budget is invalid or exceeded")
                row["status"] = "INVALID"
            elif budget_status[arm] == "UNKNOWN" and row["status"] != "INVALID":
                row["missing"].append("total_arm_cost")
                row["status"] = "UNMEASURED"

    paired_tasks, unmeasured, invalid = [], [], []
    for tid in tasks:
        baseline, advisor = graded[(tid, "baseline")], graded[(tid, "advisor")]
        measured = all(row["status"] in ("PASS", "FAIL") for row in (baseline, advisor))
        difference = int(advisor["status"] == "PASS") - int(baseline["status"] == "PASS") if measured else None
        status = "INVALID" if "INVALID" in (baseline["status"], advisor["status"]) else \
                 "UNMEASURED" if not measured else advisor["status"]
        kind = next(task.get("kind", "general") for task in protocol["tasks"] if task["id"] == tid)
        paired_tasks.append({"task_id": tid, "kind": kind, "status": status, "baseline": baseline, "advisor": advisor, "paired_difference": difference})
        for arm, row in (("baseline", baseline), ("advisor", advisor)):
            if row["status"] == "UNMEASURED":
                unmeasured.append({"task_id": tid, "arm": arm, "reasons": list(row["missing"])})
            elif row["status"] == "INVALID":
                invalid.append({"task_id": tid, "arm": arm, "reasons": list(row["errors"])})
    metric_status = "INVALID" if invalid or global_errors else "UNMEASURED" if unmeasured else "MEASURED"
    denominator = len(tasks)
    rates = {}
    for arm in ARMS:
        counts = {status: sum(graded[(tid, arm)]["status"] == status for tid in tasks)
                  for status in ("PASS", "FAIL", "UNMEASURED", "INVALID")}
        rates[arm] = {"successes": counts["PASS"], "denominator": denominator,
            "rate": counts["PASS"] / denominator if metric_status == "MEASURED" else None, "counts": counts,
            "bounds": {"lower": counts["PASS"] / denominator,
                       "upper": (counts["PASS"] + sum(graded[(tid, arm)]["status"] == "UNMEASURED"
                                 and graded[(tid, arm)]["possible_success"] for tid in tasks)) / denominator}
                      if not invalid and not global_errors else None}
    differences = [row["paired_difference"] for row in paired_tasks if row["paired_difference"] is not None]
    by_kind = {}
    for kind in TASK_KINDS:
        members = [row for row in paired_tasks if row["kind"] == kind]
        if not members:
            continue
        by_kind[kind] = {"denominator": len(members)}
        for arm in ARMS:
            measured = [row[arm] for row in members if row[arm]["status"] in ("PASS", "FAIL")]
            passes = sum(row["status"] == "PASS" for row in measured)
            by_kind[kind][arm] = {"measured_denominator": len(measured), "successes": passes,
                "conditional_success_rate": passes / len(measured) if measured else None,
                "conditional_failure_rate": (len(measured) - passes) / len(measured) if measured else None}
    return {"schema_version": 1, "assurance": "INPUT_REPORTED", "status": metric_status,
        "bindings": {"protocol_id": protocol["id"], "protocol_version": protocol["version"], "protocol_sha256": protocol_sha},
        "primary_metric": {"name": "INDEPENDENT_INTERVENTION_SUCCESS_RATE", "status": metric_status,
            "baseline": rates["baseline"], "advisor": rates["advisor"],
            "paired_difference": sum(differences) / denominator if metric_status == "MEASURED" else None},
        "conditional_measured_pairs": {"denominator": len(differences), "paired_difference": sum(differences) / len(differences) if differences else None},
        "paired_tasks": paired_tasks, "unmeasured": unmeasured, "invalid": invalid, "validation_errors": global_errors,
        "costs": {"per_arm": cost, "budget_status": budget_status, "non_budget_costs": non_budget_costs},
        "task_kind_summaries": by_kind, "structure_changes": structure_changes,
        "false_replacement": {"status": "UNMEASURED", "reason": "Requires an independent structural/equivalence-class adjudicator"},
        "mechanism_truth": "UNMEASURED",
        "limitations": ["Independence, identities, dates and sources are supplied claims, not authenticated by this evaluator.",
                        "Success means frozen numeric predictions match reported independent interventions within tolerance.",
                        "Unknown observations or costs are not zero; the frozen task denominator never shrinks.",
                        "Generation/selection changes and prediction success do not establish mechanism truth."]}

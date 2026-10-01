"""Plan one simultaneous batch from reviewed candidates; never reserve or execute.

Capacity is reusable slots. Duration, additive cost, and slot-seconds are separate
reported estimates, not measurements or scientific utility scores.
"""
from decimal import Decimal
import math


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "UNKNOWN"


def _number(value, name, *, positive=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid or (positive and value == 0):
        raise ValueError(f"{name} must be a finite {'positive' if positive else 'nonnegative'} number")
    return value


def _slots(value, name):
    if not isinstance(value, dict) or len(value) > 32:
        raise ValueError(f"{name} must be an object of at most 32 resource slots")
    for key, count in value.items():
        if not _text(key) or type(count) is not int:
            raise ValueError(f"{name} must contain named integer slot counts")
        _number(count, f"{name}.{key}")
    return dict(value)


def _names(value, name):
    if not isinstance(value, list) or not all(_text(item) for item in value):
        raise ValueError(f"{name} must be an explicit list of names")
    return set(value)


def plan_resource_batch(search, context):
    """Use explicit priority, then completion time; cost is a constraint.

    ``budget.available`` already excludes spent/active allocations. ``reserve``
    is only an additional future-work floor. Optional ``resource_seconds_caps``
    are spendable slot-seconds after reservations, not capacity or measurements.
    Every resource dimension needs explicit occupied and demand counts, including
    zero. Missing estimates stay pending. All proposed jobs start together;
    dependencies must have finished before this batch, not elsewhere in it.
    """
    if not isinstance(search, dict) or not isinstance(context, dict):
        raise ValueError("Search and resource context must be objects")
    candidates = search.get("candidates", [])
    if (not isinstance(candidates, list) or len(candidates) > 256
            or not all(isinstance(row, dict) and _text(row.get("id")) for row in candidates)):
        raise ValueError("Resource planning needs at most 256 named candidates")
    if len({row["id"] for row in candidates}) != len(candidates):
        raise ValueError("Resource planning candidate IDs must be unique")
    report = {"schema": "rds-resource-plan-v1", "status": "PENDING", "assurance": "INPUT_ESTIMATE",
              "authorization": "UNCHANGED", "execution_started": False, "budget_reserved": False,
              "method": "INPUT_PRIORITY_THEN_EARLIEST_COMPLETION", "batch": [], "pending": [],
              "tradeoffs": [], "completion_seconds": None, "total_attempt_wall_seconds": 0,
              "resources": {}, "budget": None, "context_source": context.get("source"),
              "limitations": [
                  "Input priority is a supplied research judgment, not measured scientific utility.",
                  "One greedy simultaneous batch, not a globally optimal scheduler or execution permission.",
                  "Inventory is a snapshot; occupied slots stay unavailable for this batch and are not waste.",
                  "Full durations must include setup, control work, evaluation and other required overhead.",
                  "Slot-seconds are INPUT_ESTIMATE; makespan is not cumulative attempt wall_seconds or measured GPU use.",
                  "Available budget must already exclude spent and active reservations; reserve protects additional future work only.",
                  "A wall_seconds budget charges the sum of full attempt durations, never the concurrent makespan.",
                  "No GPU IDs or slots are locked. Registration and atomic execution admission must still recheck budgets.",
                  "Legacy cost-only dominance is not a selection rule when capacity and completion time are supplied."]}

    def pending(cid, status, reason):
        report["pending"].append({"candidate_id": cid, "status": status, "reason": reason})

    eligible = []
    for row in candidates:
        if row.get("status") != "READY":
            pending(row["id"], "NOT_READY", "Upstream evidence or gate requirements remain unresolved")
        elif (any(flag.get("kind") == "LOOP_HISTORY_REVIEW_ERROR"
                  for flag in search.get("loop_review", {}).get("flags", []))
              or row.get("loop_review", {}).get("kind") == "REOPEN_REVIEW"):
            pending(row["id"], "HISTORY_REVIEW_REQUIRED", "Resolve the existing loop-history review first")
        else:
            eligible.append(row)
    # Upstream removals are displayed, never reintroduced through estimate keys.
    for key in ("blocked_candidates", "discarded_candidates"):
        for row in search.get(key, []):
            pending(row.get("id"), "UPSTREAM_BLOCKED", row.get("status", row.get("reason", key)))

    required = ("capacity", "occupied", "window_seconds", "budget", "completed", "source", "estimates")
    missing = [key for key in required if context.get(key) is None]
    if not _text(context.get("source")):
        missing.append("source")
    budget = context.get("budget")
    if isinstance(budget, dict):
        missing.extend("budget." + key for key in ("available", "reserve", "unit") if budget.get(key) is None)
        if not _text(budget.get("unit")):
            missing.append("budget.unit")
    if missing:
        for row in eligible:
            pending(row["id"], "NEEDS_EVIDENCE", "Missing resource context: " + ", ".join(sorted(set(missing))))
        return report
    if not isinstance(budget, dict) or not isinstance(context["estimates"], dict):
        raise ValueError("Resource budget and estimates must be objects")
    capacity, occupied = (_slots(context[key], key) for key in ("capacity", "occupied"))
    if not capacity or set(capacity) != set(occupied):
        for row in eligible:
            pending(row["id"], "NEEDS_EVIDENCE", "Capacity and occupied must explicitly cover the same resources")
        return report
    if any(occupied[key] > capacity[key] for key in capacity):
        raise ValueError("Occupied slots cannot exceed capacity")
    window = _number(context["window_seconds"], "window_seconds", positive=True)
    available = Decimal(str(_number(budget["available"], "budget.available")))
    reserve = Decimal(str(_number(budget["reserve"], "budget.reserve")))
    completed = _names(context["completed"], "completed")
    caps = context.get("resource_seconds_caps", {})
    if not isinstance(caps, dict) or not set(caps) <= set(capacity):
        raise ValueError("resource_seconds_caps must name known resources")
    if any(value is None for value in caps.values()):
        for row in eligible:
            pending(row["id"], "NEEDS_EVIDENCE", "A supplied resource-seconds cap is unknown")
        return report
    caps = {key: _number(value, f"resource_seconds_caps.{key}") for key, value in caps.items()}
    valid = []
    fields = ("experiment_id", "resources", "wall_seconds", "incremental_cost", "priority",
              "parallel_safe", "depends_on", "mutex_groups", "decision_use", "source")
    for row in eligible:
        cid, estimate = row["id"], context["estimates"].get(row["id"])
        if estimate is None:
            pending(cid, "NEEDS_EVIDENCE", "Missing full resource estimate")
            continue
        if not isinstance(estimate, dict):
            raise ValueError(f"Estimate for {cid} must be an object")
        missing = [key for key in fields if estimate.get(key) is None]
        missing += [key for key in ("experiment_id", "decision_use", "source") if not _text(estimate.get(key))]
        if missing:
            pending(cid, "NEEDS_EVIDENCE", "Missing estimate fields: " + ", ".join(sorted(set(missing))))
            continue
        demand = _slots(estimate["resources"], f"{cid}.resources")
        if set(demand) != set(capacity):
            pending(cid, "NEEDS_EVIDENCE", "Demand must explicitly cover every resource, including zero")
            continue
        duration = _number(estimate["wall_seconds"], f"{cid}.wall_seconds", positive=True)
        cost = _number(estimate["incremental_cost"], f"{cid}.incremental_cost")
        if budget["unit"] == "wall_seconds" and Decimal(str(cost)) != Decimal(str(duration)):
            raise ValueError(f"{cid}.incremental_cost must equal full wall_seconds for a wall_seconds budget")
        priority = estimate["priority"]
        if type(priority) is not int or priority < 0 or type(estimate["parallel_safe"]) is not bool:
            raise ValueError(f"{cid} needs a nonnegative integer priority and explicit boolean parallel_safe")
        dependencies = _names(estimate["depends_on"], f"{cid}.depends_on")
        mutex = _names(estimate["mutex_groups"], f"{cid}.mutex_groups")
        group = estimate.get("comparison_group")
        if group is not None and not _text(group):
            raise ValueError(f"{cid}.comparison_group must be a nonempty name")
        seconds = {key: _number(demand[key] * duration, f"{cid}.{key} slot-seconds") for key in capacity}
        valid.append({"candidate_id": cid, "experiment_id": estimate["experiment_id"], "resources": demand,
                      "wall_seconds": duration, "incremental_cost": cost, "priority": priority,
                      "parallel_safe": estimate["parallel_safe"], "depends_on": sorted(dependencies),
                      "mutex_groups": sorted(mutex), "decision_use": estimate["decision_use"],
                      "source": estimate["source"], "comparison_group": group, "resource_seconds": seconds})

    for fast in valid:
        for slow in valid:
            if (not fast["comparison_group"] or fast["comparison_group"] != slow["comparison_group"]
                    or fast["wall_seconds"] >= slow["wall_seconds"]):
                continue
            extra = {key: fast["resource_seconds"][key] - slow["resource_seconds"][key] for key in capacity}
            if fast["incremental_cost"] > slow["incremental_cost"] or any(value > 0 for value in extra.values()):
                report["tradeoffs"].append({"comparison_group": fast["comparison_group"],
                    "faster": fast["candidate_id"], "slower": slow["candidate_id"],
                    "seconds_saved": slow["wall_seconds"] - fast["wall_seconds"],
                    "extra_incremental_cost": fast["incremental_cost"] - slow["incremental_cost"],
                    "extra_resource_seconds": extra,
                    "basis": "Reported same-goal comparison; alternatives remain subject to all constraints"})

    assigned, consumed = dict.fromkeys(capacity, 0), dict.fromkeys(capacity, 0)
    spent, experiments, mutex_used = Decimal(0), set(), set()
    # ponytail: one priority-ordered batch; add time-expanded scheduling only for a measured need.
    for item in sorted(valid, key=lambda row: (row["priority"], row["wall_seconds"], row["candidate_id"])):
        cid = item["candidate_id"]
        cost = Decimal(str(item["incremental_cost"]))
        if set(item["depends_on"]) - completed:
            pending(cid, "DEPENDENCY_PENDING", "Required completed evidence: " + ", ".join(sorted(set(item["depends_on"]) - completed)))
        elif item["wall_seconds"] > window:
            pending(cid, "WINDOW_EXCEEDED", "Full duration exceeds the available time window")
        elif item["experiment_id"] in experiments:
            pending(cid, "ALTERNATIVE_SELECTED", "Another configuration of this experiment is already in the batch")
        elif set(item["mutex_groups"]) & mutex_used:
            pending(cid, "MUTEX_CONFLICT", "A selected experiment uses a declared mutually exclusive group")
        elif report["batch"] and (not item["parallel_safe"] or not all(row["parallel_safe"] for row in report["batch"])):
            pending(cid, "PARALLELISM_UNSUPPORTED", "Safe concurrent execution was not declared for all selected experiments")
        elif any(item["resources"][key] + assigned[key] + occupied[key] > capacity[key] for key in capacity):
            pending(cid, "CAPACITY_UNAVAILABLE", "Requested slots exceed the currently unassigned capacity")
        elif spent + cost > available - reserve:
            pending(cid, "BUDGET_PENDING", "Additive incremental cost would consume the protected future-work budget")
        elif any(consumed[key] + item["resource_seconds"][key] > cap for key, cap in caps.items()):
            pending(cid, "RESOURCE_QUOTA_PENDING", "Estimated total slot-seconds exceed a spendable resource quota")
        else:
            report["batch"].append(item)
            spent += cost
            experiments.add(item["experiment_id"])
            mutex_used.update(item["mutex_groups"])
            for key in capacity:
                assigned[key] += item["resources"][key]
                consumed[key] = _number(consumed[key] + item["resource_seconds"][key], f"total {key} slot-seconds")
    makespan = max((row["wall_seconds"] for row in report["batch"]), default=None)
    report["completion_seconds"] = makespan
    report["total_attempt_wall_seconds"] = _number(sum(row["wall_seconds"] for row in report["batch"]), "total attempt wall_seconds")
    report["status"] = "PROPOSED" if report["batch"] else "PENDING"
    report["budget"] = {"unit": budget["unit"], "available": float(available), "reserve": float(reserve),
                        "batch_incremental_cost": float(spent), "remaining_after_batch": float(available - spent)}
    for key, total in capacity.items():
        free = total - occupied[key] - assigned[key]
        reasons = sorted({row["status"] for row in report["pending"]}) if free else []
        report["resources"][key] = {"capacity": total, "occupied": occupied[key], "proposed_slots": assigned[key],
            "unassigned_available_slots": free, "start_utilization_fraction": (occupied[key] + assigned[key]) / total if total else None,
            "batch_slot_seconds": consumed[key], "assurance": "INPUT_ESTIMATE",
            "batch_available_utilization_fraction": consumed[key] / ((total - occupied[key]) * makespan)
                if makespan and total > occupied[key] else None,
            "resource_seconds_cap": caps.get(key), "quota_status": "SUPPLIED" if key in caps else "NOT_SUPPLIED",
            "idle_reasons": reasons or (["NO_ADDITIONAL_READY_WORK"] if free else [])}
    return report

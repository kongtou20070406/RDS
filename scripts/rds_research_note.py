"""Read-only review of an agent/retrieved-evidence compact decision summary.

This weak anti-loop graph does not replace original evidence or restore a chat.
Stable IDs and typed interventions are compared; prose is never semantic proof.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import re

from rds_artifacts import strict_json


MAX_BYTES = 256 * 1024
KINDS = ("proposal", "decision", "discussion", "result", "goal_change")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512


def _json(value, cap=MAX_BYTES):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
        _require(len(raw.encode("utf-8")) <= cap, "Research summary JSON exceeds byte limit")
        strict_json(raw)
        return raw
    except (TypeError, RecursionError, UnicodeError, OverflowError) as exc:
        raise ValueError("Research summary must be finite, bounded JSON") from exc


def _source(value):
    _require(_text(value) or isinstance(value, dict) and _text(value.get("locator")), "Explicit source locator required")
    _json(value, 1024)


def _scope(value):
    _require(isinstance(value, dict) and len(value) <= 16 and all(_text(key) and
             (child is None or type(child) in (str, int, float, bool)) for key, child in value.items()),
             "scope/parameters must have at most 16 JSON atomic fields")
    _json(value, 2048)


def _goal(value):
    _require(isinstance(value, dict) and _text(value.get("revision")) and _text(value.get("direction")), "Invalid goal identity/direction")
    metric, budget = value.get("metric"), value.get("budget")
    _require(isinstance(metric, dict) and _text(metric.get("name")) and _text(metric.get("unit")), "Goal requires metric name/unit")
    _require(isinstance(budget, dict) and 1 <= len(budget) <= 8, "Goal requires 1..8 budget resources")
    for key, row in budget.items():
        amount = row.get("cap") if isinstance(row, dict) else None
        try:
            finite = type(amount) in (int, float) and math.isfinite(amount) and amount >= 0
        except OverflowError:
            finite = False
        _require(_text(key) and isinstance(row, dict) and _text(row.get("unit")) and finite, "Invalid goal budget cap/unit")
    _source(value.get("source"))
    _json(value, 8192)


def load_research_note(path):
    """Read exactly one explicit rds-research JSON fence; never write/execute."""
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    _require(len(raw) <= MAX_BYTES, "Research note exceeds 256 KiB")
    try:
        text = raw.decode("utf-8-sig")
        starts = re.findall(r"(?m)^```rds-research[ \t]*\r?$", text)
        blocks = re.findall(r"(?ms)^```rds-research[ \t]*\r?\n(.*?)^```[ \t]*(?:\r?\n|$)", text)
        _require(len(starts) == len(blocks) == 1, "Expected exactly one complete rds-research JSON fence")
        spec = strict_json(blocks[0])
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid UTF-8 or deeply nested research note") from exc
    review_research_note(spec)
    return spec


def _graph(spec, flags):
    nodes = {"goal:" + spec["goal"]["revision"]: {"id": "goal:" + spec["goal"]["revision"], "kind": "goal", "ref_id": spec["goal"]["revision"]}}
    edges, events = [], {event["id"]: event for event in spec["events"]}

    def connect(left, right, relation, event, **fields):
        for kind, key in (left, right):
            nodes[kind + ":" + key] = {"id": kind + ":" + key, "kind": kind, "ref_id": key}
        edges.append({"from": left[0] + ":" + left[1], "to": right[0] + ":" + right[1], "relation": relation,
            "event_id": event["id"], "question_id": event.get("question_id"), "goal_revision": event.get("goal_revision"),
            "source": deepcopy(event["source"]), "assurance": "INPUT_REPORTED", **fields})

    for event in events.values():
        if event["kind"] in ("proposal", "decision"):
            connect(("goal", event["goal_revision"]), ("idea", event["idea_id"]),
                    "considered" if event["kind"] == "proposal" else event["outcome"], event,
                    reason=event.get("reason"), next_if_positive=event.get("next_if_positive"), next_if_negative=event.get("next_if_negative"))
        elif event["kind"] == "goal_change":
            connect(("goal", event["new_goal"]["revision"]), ("goal", event["old_goal"]["revision"]), "supersedes", event)
    for row in flags:
        if row["kind"] in ("REOPEN_REVIEW", "REPEAT_REJECTED_IDEA"):
            event, prior = events[row["event_id"]], events[row["rejection_ref"]]
            connect(("idea", event["idea_id"]), ("idea", prior["idea_id"]),
                    "reopens" if row["kind"] == "REOPEN_REVIEW" else "repeats_rejected", event,
                    status="REVIEW_REQUIRED" if row["kind"] == "REOPEN_REVIEW" else "REPEAT",
                    rejection_ref=prior["id"], reason=row["reason"], new_evidence_refs=list(event.get("new_evidence_refs", [])))
    return {"nodes": list(nodes.values()), "edges": edges, "purpose": "ANTI_LOOP_BOOKKEEPING"}


def review_research_note(spec):
    """Return explicit bookkeeping flags, never scientific validation/authority."""
    _json(spec)
    _require(isinstance(spec, dict) and type(spec.get("schema_version")) is int and spec["schema_version"] == 1,
             "Research summary schema_version must be 1")
    _goal(spec.get("goal"))
    events, config = spec.get("events"), spec.get("config", {})
    _require(isinstance(events, list) and len(events) <= 200, "events must be an ordered list of at most 200 records")
    _require(isinstance(config, dict), "config must be an object")
    limit = config.get("discussion_limit", 6)
    _require(type(limit) is int and 1 <= limit <= 200, "discussion_limit must be 1..200")
    changes = [e for e in events if isinstance(e, dict) and e.get("kind") == "goal_change"]
    active = changes[0].get("old_goal", {}).get("revision") if changes and isinstance(changes[0].get("old_goal"), dict) else spec["goal"]["revision"]
    last_goal = changes[0].get("old_goal") if changes else spec["goal"]
    ids, definitions, proposals, rejected, decisions, discussions = set(), {}, {}, [], {}, {}
    flags, raw_refs = [], []
    counts = {"repeat_proposal_count": 0, "ineffective_experiment_count": 0, "discussion_without_plan": 0}

    def flag(kind, event, **fields):
        flags.append({"kind": kind, "event_id": event["id"], **fields})

    for event in events:
        _require(isinstance(event, dict) and _text(event.get("id")) and event["id"] not in ids and event.get("kind") in KINDS,
                 "Each event requires a unique id and known kind")
        ids.add(event["id"])
        _json(event, 8192)
        _source(event.get("source"))
        raw_refs.append({"event_id": event["id"], "source": deepcopy(event["source"])})
        kind = event["kind"]
        if kind == "goal_change":
            old, new = event.get("old_goal"), event.get("new_goal")
            _goal(old)
            _goal(new)
            _require(old["revision"] == active and new["revision"] != active, "Goal changes must preserve ordered revision history")
            _require(all(old[key] == last_goal[key] for key in ("revision", "metric", "budget", "direction")), "Old goal cannot silently change")
            flag("GOAL_DRIFT", event, old_goal=deepcopy(old), new_goal=deepcopy(new))
            active, last_goal = new["revision"], new
            continue
        _require(_text(event.get("question_id")) and event.get("goal_revision") == active, "Event requires current question/goal revision")
        scope = event.get("scope", {})
        _scope(scope)
        group = (event["question_id"], active, _json(scope))
        if kind == "discussion":
            discussions.setdefault(group, []).append(event)
            continue
        _require(_text(event.get("idea_id")), "Proposal/decision/result requires stable idea_id")
        idea_key = (event["question_id"], active, event["idea_id"])
        intervention = event.get("intervention", proposals.get(idea_key, {}).get("intervention"))
        if intervention is not None:
            _require(isinstance(intervention, dict) and _text(intervention.get("type")), "Typed intervention requires type")
            _scope(intervention.get("parameters", {}))
            _json(intervention, 2048)
        if kind == "proposal":
            _require(intervention is not None, "Proposal requires a typed intervention")
            for name in ("next_if_positive", "next_if_negative"):
                _require(_text(event.get(name)), "Proposal requires next decision IDs for both outcomes")
            refs = event.get("new_evidence_refs", [])
            _require(isinstance(refs, list) and len(refs) <= 32 and all(_text(ref) for ref in refs), "Invalid new_evidence_refs")
            raw_refs[-1]["new_evidence_refs"] = list(refs)
            for prior in reversed(rejected):
                if prior["question_id"] != event["question_id"] or prior["goal_revision"] != active:
                    continue
                same_idea = prior["idea_id"] == event["idea_id"]
                same_operation = _json(intervention) == _json(prior.get("intervention")) and _json(scope) == _json(prior["scope"])
                if same_idea or same_operation:
                    changed = bool(refs) or _json(scope) != _json(prior["scope"]) or _json(intervention) != _json(prior.get("intervention"))
                    flag("REOPEN_REVIEW" if changed else "REPEAT_REJECTED_IDEA", event, rejection_ref=prior["event_id"],
                         reason="New information requires review; old rejection remains" if changed else "No explicit new evidence, scope or intervention")
                    counts["repeat_proposal_count"] += not changed
                    break
            if event["next_if_positive"] == event["next_if_negative"]:
                counts["ineffective_experiment_count"] += 1
                flag("INEFFECTIVE_EXPERIMENT", event, decision_id=event["next_if_positive"])
            proposals[idea_key] = {"intervention": deepcopy(intervention), "scope": deepcopy(scope)}
        elif kind == "decision":
            _require(_text(event.get("decision_id")) and event.get("outcome") in ("rejected", "plan_locked", "deferred", "accepted")
                     and _text(event.get("reason")), "Decision requires stable id, outcome and source-bound reason")
            _require(event["outcome"] != "plan_locked" or intervention is not None, "A locked plan requires a typed intervention")
            definition = (group, event["idea_id"], event["outcome"], _json(intervention))
            _require(event["decision_id"] not in definitions or definitions[event["decision_id"]] == definition,
                     "A stable decision_id cannot change meaning")
            definitions[event["decision_id"]] = definition
            history = decisions.setdefault(group, [])
            decision = {**event, "scope": deepcopy(scope), "intervention": deepcopy(intervention)}
            if not history or history[-1]["decision_id"] != event["decision_id"]:
                history.append(decision)
                if len(history) >= 3 and history[-3]["decision_id"] == history[-1]["decision_id"]:
                    flag("DECISION_OSCILLATION", event, decision_ids=[row["decision_id"] for row in history[-3:]])
            else:
                history[-1] = decision
            if event["outcome"] == "rejected":
                rejected.append({"event_id": event["id"], "idea_id": event["idea_id"], "question_id": event["question_id"],
                    "goal_revision": active, "scope": deepcopy(scope), "intervention": deepcopy(intervention),
                    "reason": event["reason"], "source": deepcopy(event["source"])})
    _require(active == spec["goal"]["revision"], "Current goal must match final revision")
    if changes:
        _require(all(changes[-1]["new_goal"][key] == spec["goal"][key] for key in ("revision", "metric", "budget", "direction")),
                 "Current goal must preserve the last goal_change values")
    for group, history in discussions.items():
        current = decisions.get(group, [])
        if not current or current[-1]["outcome"] != "plan_locked":
            counts["discussion_without_plan"] += len(history)
            if len(history) >= limit:
                flag("CONVERGENCE_SUGGESTION", history[-1], question_id=group[0], discussion_count=len(history),
                     reason="Review a bounded plan; this suggestion does not choose or authorize it")
    current = [{key: deepcopy(history[-1][key]) for key in ("id", "question_id", "goal_revision", "scope", "idea_id", "decision_id", "outcome", "intervention", "reason", "source") if key in history[-1]}
               for history in decisions.values()]
    return {"schema_version": 1, "assurance": "INPUT_REPORTED", "goal": deepcopy(spec["goal"]), "rejections": rejected,
            "current_decisions": current, "next": [row for row in flags if row["kind"] in ("REOPEN_REVIEW", "CONVERGENCE_SUGGESTION")],
            "flags": flags, "statistics": counts, "raw_refs": raw_refs, "result_assurance": "INPUT_REPORTED",
            "graph": _graph(spec, flags), "precise_recovery": "REQUIRES_ORIGINAL_EVIDENCE",
            "authorization": "NOT_GRANTED_BY_NOTE", "limitations": ["Explicit bookkeeping only; no semantic recall, science benefit or authenticated results.",
            "History, accepted/verified labels and plan_locked declarations never create execution authorization.",
            "This compact decision summary does not replace Obelisk or restore conversation history."]}

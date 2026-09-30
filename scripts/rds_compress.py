"""Deep Learning Log & Metric Compressor for RDS-L3.

Extracts a bounded summary of common training-log fields:
1. Strips repetitive step-by-step stdout/stderr output (e.g. tqdm bars, ETA lines).
2. Extracts critical numerical signatures: final losses, convergence trend, NaN/Inf anomaly flags,
   peak gradient norms, and empirical throughput (samples/sec).
3. Keeps differently named losses separate. Token usage is not measured here.
"""
import math
import re
from typing import Any, Dict, List


def compress_training_log(raw_log: str, max_samples: int = 10) -> Dict[str, Any]:
    """Compresses large training stdout/stderr into a lightweight semantic signature."""
    lines = raw_log.strip().splitlines()
    if type(max_samples) is not int or max_samples < 1:
        raise ValueError("max_samples must be a positive integer")
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?"
    loss_pattern = re.compile(
        r"(?<![\w.])((?:(?:train|val|eval|test|validation)[_ -])?loss(?:_(?:train|val|eval|test|validation))?|mse)"
        + r"(?:\s*[:=]\s*|\s+)(" + number + r")(?![\w.])", re.IGNORECASE)
    throughput_pattern = re.compile(r"(?<![\w.])(" + number + r")\s*(?:samples/s|it/s|fps)(?!\w)", re.IGNORECASE)
    grad_norm_pattern = re.compile(r"(?<![\w.])(?:grad_norm|gnorm)(?:\s*[:=]\s*|\s+)(" + number + r")(?![\w.])", re.IGNORECASE)
    nonfinite_pattern = re.compile(r"(?<![\w.])[+-]?(?:nan|inf(?:inity)?)(?![\w.])", re.IGNORECASE)

    loss_series = {}
    throughputs = []
    grad_norms = []
    nan_or_inf_detected = False

    for line in lines:
        if nonfinite_pattern.search(line):
            nan_or_inf_detected = True

        for match in loss_pattern.finditer(line):
            loss_type = re.sub(r"[ -]", "_", match.group(1).lower())
            val = float(match.group(2))
            if not math.isfinite(val):
                nan_or_inf_detected = True
                continue
            series = loss_series.setdefault(loss_type, {
                "initial_loss": val, "final_loss": val, "min_loss": val,
                "sample_count": 0, "samples": [], "loss_trend": "UNKNOWN",
            })
            series["final_loss"] = val
            series["min_loss"] = min(series["min_loss"], val)
            series["sample_count"] += 1
            series["samples"].append(val)
            del series["samples"][:-max_samples]

        for match in throughput_pattern.finditer(line):
            val = float(match.group(1))
            if not math.isfinite(val):
                nan_or_inf_detected = True
            elif val >= 0:
                throughputs.append(val)

        for match in grad_norm_pattern.finditer(line):
            val = float(match.group(1))
            if not math.isfinite(val):
                nan_or_inf_detected = True
            elif val >= 0:
                grad_norms.append(val)

    # ponytail: endpoint trends are heuristic; add step-aligned statistics when needed.
    for series in loss_series.values():
        if series["sample_count"] >= 2:
            delta = series["final_loss"] - series["initial_loss"]
            margin = abs(series["initial_loss"]) * 0.05
            series["loss_trend"] = "DECREASING" if delta < -margin else "EXPLODING" if delta > margin else "STAGNANT"
    loss_type = next((key for key in ("loss", "train_loss", "loss_train", "mse") if key in loss_series),
                     next(iter(loss_series), None))
    primary = loss_series.get(loss_type, {})

    mean_throughput = round(sum(value / len(throughputs) for value in throughputs), 2) if throughputs else None
    peak_grad_norm = round(max(grad_norms), 3) if grad_norms else None

    return {
        "compressed": True,
        "raw_lines": len(lines),
        "raw_characters": len(raw_log),
        "loss_type": loss_type,
        "loss_series": loss_series,
        "initial_loss": primary.get("initial_loss"),
        "final_loss": primary.get("final_loss"),
        "min_loss": primary.get("min_loss"),
        "loss_trend": primary.get("loss_trend", "UNKNOWN"),
        "trend_assurance": "HEURISTIC_ONLY",
        "nan_or_inf": nan_or_inf_detected,
        "peak_grad_norm": peak_grad_norm,
        "mean_throughput": mean_throughput,
    }


def project_graph_rules(graph: Dict[str, Any], query_tags: List[str]) -> List[Dict[str, Any]]:
    """Projects only relevant judgment rules into context, avoiding massive graph bloat."""
    relevant = []
    nodes = graph.get("nodes", [])
    query_set = set(t.lower() for t in query_tags)

    for node in nodes:
        content = (node.get("id", "") + " " + node.get("trigger", "") + " " + node.get("correction", "")).lower()
        if any(tag in content for tag in query_set):
            relevant.append({
                "id": node.get("id"),
                "trigger": node.get("trigger"),
                "correction": node.get("correction"),
                "falsifier": node.get("falsifier"),
            })
            if len(relevant) >= 3:  # Hard cap at 3 rules to protect context
                break

    return relevant

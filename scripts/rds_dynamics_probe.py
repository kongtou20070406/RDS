"""Descriptive diagnostics of bounded exported snapshots; never execute models."""
import argparse
import importlib
import hashlib
import json
import math
from pathlib import Path

MAX_BYTES = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and abs(value) <= 1e100,
            "Snapshot numbers must be finite and have magnitude <= 1e100")
    return float(value)


def vector(value):
    require(isinstance(value, list) and 1 <= len(value) <= 64, "Vectors require 1..64 entries")
    return [number(item) for item in value]


def matrix(value, square=False):
    require(isinstance(value, list) and 1 <= len(value) <= (64 if square else 128),
            "Matrix row count exceeds the snapshot bound")
    rows = [vector(row) for row in value]
    require(all(len(row) == len(rows[0]) for row in rows), "Matrix rows must have equal length")
    require(not square or len(rows) == len(rows[0]), "Jacobian must be square")
    return rows


def inspect_probe(spec):
    require(isinstance(spec, dict), "Probe specification must be an object")
    try:
        encoded = json.dumps(spec, allow_nan=False).encode("utf-8")
    except (TypeError, RecursionError) as exc:
        raise ValueError("Probe specification must be bounded JSON data") from exc
    require(len(encoded) <= MAX_BYTES,
            "Probe specification exceeds 1 MiB")
    require(set(spec) <= {"schema", "source", "declared_scope", "source_identity", "residual", "jacobian", "refinement"},
            "Unknown probe specification fields")
    require(type(spec.get("schema")) is int and spec["schema"] == 1, "Expected probe schema 1")
    for key in ("source", "declared_scope"):
        value = spec.get(key)
        require(isinstance(value, str) and 0 < len(value) <= 4096 and value.strip()
                and value.strip().upper() != "UNKNOWN", key + " must describe the exported snapshot")
    identity = spec.get("source_identity", {})
    require(isinstance(identity, dict) and len(identity) <= 16 and all(
        isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip()
        and len(key) <= 128 and len(value) <= 4096 for key, value in identity.items()),
        "source_identity must contain bounded string metadata")
    require(any(key in spec for key in ("residual", "jacobian", "refinement")), "At least one diagnostic is required")
    arrays = {key: matrix(spec[key], square=key == "jacobian")
              for key in ("residual", "jacobian") if key in spec}
    result = {"schema": "rds-dynamics-probe-v1", "status": "ANALYZED",
              "input_sha256": hashlib.sha256(encoded).hexdigest(),
              "assurance": "DESCRIPTIVE_SNAPSHOT_ESTIMATE", "source": spec["source"],
              "declared_scope": spec["declared_scope"], "source_identity": identity,
              "identity_assurance": "INPUT_REPORTED", "model_execution_started": False,
              "causal": "UNKNOWN", "global_stability": "UNKNOWN", "task_gain": "UNKNOWN",
              "limitations": ["Residual energy concentration does not identify minimal hidden-state dimension.",
                              "A local Jacobian away from equilibrium does not establish limit cycles or global divergence.",
                              "Fixed-horizon refinement differences do not prove a continuum limit."]}
    if "refinement" in spec:
        refinement = spec["refinement"]
        require(isinstance(refinement, dict) and set(refinement) == {"time_horizon", "levels"},
                "Refinement requires a shared time_horizon and levels")
        horizon = number(refinement["time_horizon"])
        require(horizon > 0, "Refinement time_horizon must be positive")
        levels = refinement["levels"]
        require(isinstance(levels, list) and 2 <= len(levels) <= 16, "Refinement requires 2..16 levels")
        previous_steps, previous, differences = 0, None, []
        for level in levels:
            require(isinstance(level, dict) and set(level) == {"steps", "value"}, "Invalid refinement level")
            steps = level["steps"]
            require(type(steps) is int and previous_steps < steps <= 10**9, "Refinement steps must strictly increase within 1..1e9")
            current = vector(level["value"])
            if previous is not None:
                require(len(previous) == len(current), "Refinement snapshots must have equal dimensions")
                delta = math.hypot(*(a - b for a, b in zip(current, previous)))
                scale = math.hypot(*current)
                relative = delta / scale if scale else None
                differences.append({"from_steps": previous_steps, "to_steps": steps,
                                    "l2_difference": delta, "relative_l2_difference": relative if relative is not None and math.isfinite(relative) else None})
            previous_steps, previous = steps, current
        result["refinement"] = {"status": "ESTIMATED", "backend": "python_stdlib",
                                "time_horizon": horizon, "differences": differences}
    if arrays:
        try:
            numpy = importlib.import_module("numpy")
        except ImportError:
            numpy = None
        for key, rows in arrays.items():
            section = {"shape": [len(rows), len(rows[0])], "backend": "numpy.linalg"}
            if numpy is None:
                result[key] = {**section, "status": "UNAVAILABLE", "reason": "Optional NumPy is not installed"}
                continue
            try:
                array = numpy.asarray(rows, dtype=float)
                singular = numpy.linalg.svd(array, compute_uv=False).tolist()
                section.update(status="ESTIMATED", singular_values=singular, numpy_version=numpy.__version__)
                if key == "residual":
                    scale = singular[0]
                    energy = [(value / scale) ** 2 for value in singular] if scale else [0.0] * len(singular)
                    scaled_total = math.fsum(energy)
                    fractions = [value / scaled_total if scaled_total else 0.0 for value in energy]
                    total = math.fsum(value * value for value in singular)
                    underflow = scale > 0 and total == 0
                    section.update(total_squared_energy=None if underflow else total,
                                   total_squared_energy_status="UNDERFLOW" if underflow else "REPRESENTABLE",
                                   energy_fractions=fractions,
                                   cumulative_energy_fractions=[math.fsum(fractions[:i]) for i in range(1, len(fractions) + 1)])
                else:
                    eigenvalues = sorted(numpy.linalg.eigvals(array), key=lambda value: (float(value.real), float(value.imag)))
                    section.update(eigenvalues=[{"real": float(value.real), "imag": float(value.imag)} for value in eigenvalues],
                                   spectral_radius=max(float(abs(value)) for value in eigenvalues))
                require(all(math.isfinite(value) for value in singular), "Nonfinite numerical decomposition")
                json.dumps(section, allow_nan=False)
                result[key] = section
            except (ValueError, OverflowError, FloatingPointError, numpy.linalg.LinAlgError) as exc:
                result[key] = {"status": "UNAVAILABLE", "backend": "numpy.linalg", "shape": section["shape"], "reason": str(exc)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        with Path(args.input).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "Probe specification exceeds 1 MiB")
        result = inspect_probe(json.loads(raw.decode("utf-8-sig")))
        result["input_file_sha256"] = hashlib.sha256(raw).hexdigest()
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if args.output:
            require(Path(args.output).resolve() != Path(args.input).resolve(), "Output must not replace the original input")
            Path(args.output).write_text(encoded + "\n", encoding="utf-8")
        estimates = {}
        if result.get("residual", {}).get("status") == "ESTIMATED":
            estimates["leading_energy_fractions"] = result["residual"]["energy_fractions"][:3]
        if result.get("jacobian", {}).get("status") == "ESTIMATED":
            estimates["local_spectral_radius"] = result["jacobian"]["spectral_radius"]
            estimates["local_operator_norm"] = result["jacobian"]["singular_values"][0]
        if "refinement" in result:
            estimates["last_refinement_difference"] = result["refinement"]["differences"][-1]["l2_difference"]
        print(json.dumps({"status": result["status"], "output": args.output,
                          "input_file_sha256": result["input_file_sha256"],
                          "sections": {key: result[key]["status"] for key in ("residual", "jacobian", "refinement") if key in result},
                          "detail": "Use --output to retain full estimates" if not args.output else "Saved",
                          "estimates": estimates, "assurance": result["assurance"], "task_gain": "UNKNOWN"}))
        return 0
    except (ValueError, TypeError, OSError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

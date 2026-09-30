"""Exact interval certificates for bounded dense/ReLU networks.

The modeled weights and arithmetic are rational numbers over the reals. These
certificates do not describe IEEE floating point or exported PyTorch execution.
Interval bounds are sufficient proofs; an inconclusive enclosure is not a
counterexample. Counterexamples are checked by exact forward evaluation.
"""
from fractions import Fraction

from rds_verify_types import (MAX_CERTIFICATE_BYTES, bounded, canonical, digest,
                              rational, require)

BACKEND = "rds_exact_network_interval"
VERSION = 1
MAX_DIMENSION = 64
MAX_LAYERS = 32
MAX_PARAMETERS = 16384
MAX_OPERATIONS = 1000000
MAX_CANDIDATES = 32
KINDS = {"network_bounds", "network_margin"}
SEMANTICS = "rational_weights_and_real_dense_relu_arithmetic"


def _box(value, dimension, name):
    require(isinstance(value, list) and len(value) == dimension, f"{name} dimension mismatch")
    box = []
    for pair in value:
        require(isinstance(pair, list) and len(pair) == 2, f"{name} requires [lower, upper] pairs")
        lo, hi = (rational(v) for v in pair)
        require(lo <= hi, f"{name} has an inverted interval")
        box.append((lo, hi))
    return box


def _validate(spec):
    require(isinstance(spec, dict), "Specification must be an object")
    require(len(canonical(spec).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Specification exceeds size limit")
    require(type(spec.get("schema")) is int and spec["schema"] == 1, "Unsupported specification schema")
    require(spec.get("kind") in KINDS, "Unsupported network verification kind")
    fields = {"schema", "kind", "model", "input_box"}
    fields |= {"output_bounds"} if spec["kind"] == "network_bounds" else {"target", "margin"}
    require(set(spec) == fields, "Unexpected or missing network specification fields")
    model = spec["model"]
    require(isinstance(model, dict) and set(model) == {"input_dim", "layers"}, "Model requires input_dim and layers")
    dimension = model["input_dim"]
    require(type(dimension) is int and 1 <= dimension <= MAX_DIMENSION, "Input dimension exceeds 1..64")
    input_box = _box(spec["input_box"], dimension, "input_box")
    raw_layers = model["layers"]
    require(isinstance(raw_layers, list) and 1 <= len(raw_layers) <= MAX_LAYERS, "Network requires 1..32 layers")
    layers, parameters, weights, activations = [], 0, 0, 0
    for layer in raw_layers:
        require(isinstance(layer, dict), "Layer must be an object")
        if layer.get("kind") == "relu":
            require(set(layer) == {"kind"}, "ReLU layer has unsupported fields")
            layers.append({"kind": "relu"})
            activations += dimension
            continue
        require(layer.get("kind") == "linear" and set(layer) == {"kind", "weight", "bias"},
                "Only dense linear and ReLU layers are supported")
        matrix, bias = layer["weight"], layer["bias"]
        require(isinstance(matrix, list) and 1 <= len(matrix) <= MAX_DIMENSION,
                "Linear output dimension exceeds 1..64")
        require(isinstance(bias, list) and len(bias) == len(matrix), "Linear bias dimension mismatch")
        require(all(isinstance(row, list) and len(row) == dimension for row in matrix),
                "Linear weight shape mismatch")
        parameters += len(matrix) * (dimension + 1)
        weights += len(matrix) * dimension
        require(parameters <= MAX_PARAMETERS, "Network exceeds the 16384-parameter limit")
        layers.append({"kind": "linear", "weight": [[rational(v) for v in row] for row in matrix],
                       "bias": [rational(v) for v in bias]})
        dimension = len(matrix)
    if spec["kind"] == "network_bounds":
        property_value = _box(spec["output_bounds"], dimension, "output_bounds")
    else:
        require(dimension >= 2, "Network margin requires at least two outputs")
        require(type(spec["target"]) is int and 0 <= spec["target"] < dimension, "Invalid target output index")
        margin = rational(spec["margin"])
        require(margin >= 0, "Network margin must be nonnegative")
        property_value = spec["target"], margin
    return layers, input_box, property_value, 4 * weights + activations, 2 * weights + activations


def _encode_box(box):
    return [[str(lo), str(hi)] for lo, hi in box]


def _interval_step(layer, box):
    if layer["kind"] == "relu":
        return [(max(Fraction(0), lo), max(Fraction(0), hi)) for lo, hi in box]
    output = []
    for row, bias in zip(layer["weight"], layer["bias"]):
        lo = hi = bias
        for weight, (left, right) in zip(row, box):
            a, b = bounded(weight * left), bounded(weight * right)
            lo, hi = bounded(lo + min(a, b)), bounded(hi + max(a, b))
        output.append((lo, hi))
    return output


def _forward_step(layer, point):
    if layer["kind"] == "relu":
        return [max(Fraction(0), value) for value in point]
    output = []
    for row, bias in zip(layer["weight"], layer["bias"]):
        value = bias
        for weight, x in zip(row, point):
            value = bounded(value + bounded(weight * x))
        output.append(value)
    return output


def _interval_proves(kind, box, property_value):
    if kind == "network_bounds":
        return all(wanted_lo <= lo <= hi <= wanted_hi
                   for (lo, hi), (wanted_lo, wanted_hi) in zip(box, property_value))
    target, margin = property_value
    return all(bounded(box[target][0] - hi) >= margin
               for index, (_, hi) in enumerate(box) if index != target)


def _violates(kind, output, property_value):
    if kind == "network_bounds":
        return any(not lo <= value <= hi for value, (lo, hi) in zip(output, property_value))
    target, margin = property_value
    return any(bounded(output[target] - value) < margin
               for index, value in enumerate(output) if index != target)


def _candidate_inputs(box):
    """Bounded search hints only; never a proof of universal correctness."""
    center = tuple(bounded(bounded(lo + hi) / 2) for lo, hi in box)
    yield center
    yield tuple(lo for lo, _ in box)
    yield tuple(hi for _, hi in box)
    yield tuple(pair[index % 2] for index, pair in enumerate(box))
    yield tuple(pair[1 - index % 2] for index, pair in enumerate(box))
    for index, (lo, hi) in enumerate(box):
        for endpoint in (lo, hi):
            yield center[:index] + (endpoint,) + center[index + 1:]
    for mask in range(min(1 << len(box), 8)):
        yield tuple(pair[(mask >> index) & 1] for index, pair in enumerate(box))


def _certificate(spec, verdict, method, trace, witness):
    return {"version": VERSION, "backend": BACKEND, "spec_sha256": digest(spec),
            "model_sha256": digest(spec["model"]), "kind": spec["kind"],
            "verdict": verdict, "method": method, "trace": trace, "witness": witness}


def check_certificate(spec, certificate):
    """Replay each declared layer and the property, without calling verify.

    The checker trusts only the restricted specification and exact arithmetic.
    Producer status fields and unbound traces cannot establish a result.
    """
    try:
        require(isinstance(certificate, dict), "Certificate must be an object")
        require(len(canonical(certificate).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Certificate exceeds size limit")
        require(set(certificate) == {"version", "backend", "spec_sha256", "model_sha256", "kind",
                                     "verdict", "method", "trace", "witness"}, "Malformed certificate")
        require(type(certificate["version"]) is int and certificate["version"] == VERSION, "Certificate version mismatch")
        require(certificate["backend"] == BACKEND and certificate["kind"] == spec["kind"], "Certificate backend mismatch")
        require(certificate["spec_sha256"] == digest(spec)
                and certificate["model_sha256"] == digest(spec["model"]), "Certificate binding mismatch")
        layers, input_box, property_value, _, _ = _validate(spec)
        trace = certificate["trace"]
        require(isinstance(trace, list) and len(trace) == len(layers), "Incomplete layer trace")
        if certificate["method"] == "interval" and certificate["verdict"] == "PASS":
            require(certificate["witness"] is None, "Interval proof must not contain a witness")
            box = input_box
            for index, (layer, entry) in enumerate(zip(layers, trace)):
                box = _interval_step(layer, box)
                require(entry == {"layer": index, "kind": layer["kind"], "bounds": _encode_box(box)},
                        "Incorrect interval trace")
            return _interval_proves(spec["kind"], box, property_value)
        if certificate["method"] == "counterexample" and certificate["verdict"] == "FAIL":
            witness = certificate["witness"]
            require(isinstance(witness, dict) and set(witness) == {"input"}, "Malformed witness")
            values = witness["input"]
            require(isinstance(values, list) and len(values) == len(input_box), "Witness dimension mismatch")
            point = []
            for text, (lo, hi) in zip(values, input_box):
                require(isinstance(text, str) and len(text) <= 2500, "Malformed witness value")
                value = bounded(Fraction(text))
                require(str(value) == text and lo <= value <= hi, "Witness outside input box")
                point.append(value)
            for index, (layer, entry) in enumerate(zip(layers, trace)):
                point = _forward_step(layer, point)
                require(entry == {"layer": index, "kind": layer["kind"], "values": [str(v) for v in point]},
                        "Incorrect forward trace")
            return _violates(spec["kind"], point, property_value)
        return False
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError):
        return False


def verify(spec):
    """Prove an enclosure or find an exact witness; otherwise return UNKNOWN."""
    result = {"status": "UNKNOWN", "assurance": "NONE", "backend": BACKEND,
              "semantics": SEMANTICS, "certificate": None}
    try:
        layers, box, property_value, interval_ops, forward_ops = _validate(spec)
        trace = []
        for index, layer in enumerate(layers):
            box = _interval_step(layer, box)
            trace.append({"layer": index, "kind": layer["kind"], "bounds": _encode_box(box)})
        if _interval_proves(spec["kind"], box, property_value):
            certificate = _certificate(spec, "PASS", "interval", trace, None)
            require(check_certificate(spec, certificate), "Interval certificate did not verify")
            return {**result, "status": "PASS", "assurance": "CERTIFICATE_CHECKED", "certificate": certificate}
        # Reserve arithmetic for certificate replay as well as candidate search.
        limit = min(MAX_CANDIDATES, max(0, (MAX_OPERATIONS - 2 * interval_ops) // max(1, forward_ops) - 1))
        seen = set()
        input_box = _box(spec["input_box"], spec["model"]["input_dim"], "input_box")
        for point in _candidate_inputs(input_box):
            if point in seen:
                continue
            if len(seen) >= limit:
                break
            seen.add(point)
            values, forward_trace = list(point), []
            for index, layer in enumerate(layers):
                values = _forward_step(layer, values)
                forward_trace.append({"layer": index, "kind": layer["kind"], "values": [str(v) for v in values]})
            if _violates(spec["kind"], values, property_value):
                certificate = _certificate(spec, "FAIL", "counterexample", forward_trace,
                                           {"input": [str(v) for v in point]})
                require(check_certificate(spec, certificate), "Counterexample certificate did not verify")
                return {**result, "status": "FAIL", "assurance": "EXACT_COUNTEREXAMPLE_CHECKED",
                        "certificate": certificate, "candidates_checked": len(seen)}
        return {**result, "reason": "Interval enclosure is inconclusive; bounded exact search found no counterexample",
                "candidates_checked": len(seen)}
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError) as exc:
        return {**result, "reason": str(exc)}

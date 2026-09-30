"""Exact certificates for concrete row-major tensor calculations.

Literal tensors, add, scale, transpose and non-broadcasting batched matmul are
supported. This is equality/bounds checking for declared concrete values, not a
symbolic theorem about all tensors or IEEE floating-point implementations.
All nodes together may materialize at most 4096 elements in one certificate.
"""
from fractions import Fraction
from itertools import product
from math import prod

from rds_verify_types import (MAX_CERTIFICATE_BYTES, bounded, canonical, digest,
                              rational, require)

BACKEND = "rds_exact_tensor"
VERSION = 1
MAX_RANK = 4
MAX_DIMENSION = 64
MAX_NODES_PER_EXPRESSION = 128
MAX_TRACE_ELEMENTS = 4096
MAX_OPERATIONS = 1000000
KINDS = {"tensor_identity", "tensor_bounds"}
SEMANTICS = "concrete_row_major_tensors_with_exact_real_rational_arithmetic"


def _compile_expression(expr, plan, budget):
    nodes = 0

    def push(node, shape, operations=0):
        elements = prod(shape)
        budget["elements"] += elements
        budget["operations"] += operations
        require(budget["elements"] <= MAX_TRACE_ELEMENTS, "Tensor trace exceeds 4096 cumulative elements")
        require(budget["operations"] <= MAX_OPERATIONS, "Tensor expression exceeds 1000000 arithmetic operations")
        node["shape"] = tuple(shape)
        plan.append(node)
        return len(plan) - 1

    def visit(value):
        nonlocal nodes
        nodes += 1
        require(nodes <= MAX_NODES_PER_EXPRESSION, "Tensor expression exceeds 128 nodes")
        require(isinstance(value, dict), "Tensor expression must be an object")
        op = value.get("op")
        if op == "literal":
            require(set(value) == {"op", "shape", "values"}, "Literal requires shape and flat values")
            shape, values = value["shape"], value["values"]
            require(isinstance(shape, list) and len(shape) <= MAX_RANK, "Tensor rank exceeds 4")
            require(all(type(dim) is int and 1 <= dim <= MAX_DIMENSION for dim in shape),
                    "Tensor dimensions must be integers in 1..64")
            require(prod(shape) <= MAX_TRACE_ELEMENTS, "Literal exceeds 4096 elements")
            require(isinstance(values, list) and len(values) == prod(shape), "Literal flat values do not match shape")
            return push({"op": op, "values": tuple(rational(v) for v in values)}, shape)
        if op in {"add", "matmul"}:
            require(set(value) == {"op", "left", "right"}, f"{op} requires left and right")
            left, right = visit(value["left"]), visit(value["right"])
            a, b = plan[left]["shape"], plan[right]["shape"]
            if op == "add":
                require(a == b, "Tensor addition requires identical shapes")
                return push({"op": op, "left": left, "right": right}, a, prod(a))
            require(2 <= len(a) <= 4 and len(a) == len(b), "Matmul requires equal ranks in 2..4")
            require(a[:-2] == b[:-2] and a[-1] == b[-2], "Matmul requires matching batch and contraction dimensions")
            shape = a[:-2] + (a[-2], b[-1])
            return push({"op": op, "left": left, "right": right}, shape, 2 * prod(shape) * a[-1])
        if op == "scale":
            require(set(value) == {"op", "factor", "arg"}, "Scale requires factor and arg")
            arg = visit(value["arg"])
            shape = plan[arg]["shape"]
            return push({"op": op, "arg": arg, "factor": rational(value["factor"])}, shape, prod(shape))
        if op == "transpose":
            require(set(value) == {"op", "axes", "arg"}, "Transpose requires axes and arg")
            arg = visit(value["arg"])
            shape, axes = plan[arg]["shape"], value["axes"]
            require(isinstance(axes, list) and all(type(axis) is int for axis in axes)
                    and sorted(axes) == list(range(len(shape))), "Transpose axes must permute all input axes")
            return push({"op": op, "arg": arg, "axes": tuple(axes)}, tuple(shape[axis] for axis in axes))
        raise ValueError("Unsupported tensor operation")

    return visit(expr)


def _prepare(spec):
    require(isinstance(spec, dict), "Specification must be an object")
    require(len(canonical(spec).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Specification exceeds size limit")
    require(type(spec.get("schema")) is int and spec["schema"] == 1, "Unsupported specification schema")
    require(spec.get("kind") in KINDS, "Unsupported tensor verification kind")
    plan, budget = [], {"elements": 0, "operations": 0}
    if spec["kind"] == "tensor_identity":
        require(set(spec) == {"schema", "kind", "left", "right"}, "Identity requires left and right expressions")
        roots = [_compile_expression(spec["left"], plan, budget), _compile_expression(spec["right"], plan, budget)]
        require(plan[roots[0]]["shape"] == plan[roots[1]]["shape"], "Tensor identity requires identical output shapes")
        bounds = None
    else:
        require(set(spec) == {"schema", "kind", "expr", "lower", "upper"}, "Tensor bounds requires expr, lower and upper")
        roots = [_compile_expression(spec["expr"], plan, budget)]
        bounds = rational(spec["lower"]), rational(spec["upper"])
        require(bounds[0] <= bounds[1], "Tensor bounds are inverted")
    # Each exact arithmetic operation is repeated by the independent checker.
    require(2 * budget["operations"] <= MAX_OPERATIONS, "Tensor verification and replay exceed the arithmetic budget")
    return plan, roots, bounds


def _evaluate_node(node, plan, states):
    op = node["op"]
    if op == "literal":
        return node["values"]
    if op == "add":
        return tuple(bounded(a + b) for a, b in zip(states[node["left"]], states[node["right"]]))
    if op == "scale":
        return tuple(bounded(node["factor"] * value) for value in states[node["arg"]])
    if op == "transpose":
        old_shape = plan[node["arg"]]["shape"]
        old_strides = tuple(prod(old_shape[index + 1:]) for index in range(len(old_shape)))
        source, output = states[node["arg"]], []
        for coordinate in product(*(range(dim) for dim in node["shape"])):
            old_coordinate = [0] * len(old_shape)
            for axis, index in zip(node["axes"], coordinate):
                old_coordinate[axis] = index
            output.append(source[sum(index * stride for index, stride in zip(old_coordinate, old_strides))])
        return tuple(output)
    left, right = states[node["left"]], states[node["right"]]
    a, b = plan[node["left"]]["shape"], plan[node["right"]]["shape"]
    m, k, n = a[-2], a[-1], b[-1]
    output = []
    for batch in range(prod(a[:-2])):
        for row in range(m):
            for col in range(n):
                total = Fraction(0)
                for inner in range(k):
                    term = bounded(left[batch * m * k + row * k + inner]
                                   * right[batch * k * n + inner * n + col])
                    total = bounded(total + term)
                output.append(total)
    return tuple(output)


def _trace_entry(index, node, values):
    return {"node": index, "op": node["op"], "shape": list(node["shape"]),
            "values": [str(value) for value in values]}


def _conclusion(kind, plan, roots, bounds, states):
    shape = list(plan[roots[0]]["shape"])
    if kind == "tensor_identity":
        for index, (left, right) in enumerate(zip(states[roots[0]], states[roots[1]])):
            if left != right:
                return "FAIL", {"case": "unequal_element", "shape": shape, "index": index,
                                "left": str(left), "right": str(right)}
        return "PASS", {"case": "all_elements_equal", "shape": shape}
    lower, upper = bounds
    for index, value in enumerate(states[roots[0]]):
        if not lower <= value <= upper:
            return "FAIL", {"case": "element_outside_bounds", "shape": shape, "index": index,
                            "value": str(value), "lower": str(lower), "upper": str(upper)}
    return "PASS", {"case": "all_elements_within_bounds", "shape": shape,
                    "lower": str(lower), "upper": str(upper)}


def check_certificate(spec, certificate):
    """Replay shape and exact values for every node; do not call verify."""
    try:
        require(isinstance(certificate, dict), "Certificate must be an object")
        require(len(canonical(certificate).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Certificate exceeds size limit")
        require(set(certificate) == {"version", "backend", "spec_sha256", "kind", "verdict", "trace", "conclusion"},
                "Malformed tensor certificate")
        require(type(certificate["version"]) is int and certificate["version"] == VERSION, "Certificate version mismatch")
        require(certificate["backend"] == BACKEND and certificate["spec_sha256"] == digest(spec)
                and certificate["kind"] == spec["kind"], "Certificate binding mismatch")
        plan, roots, bounds = _prepare(spec)
        trace = certificate["trace"]
        require(isinstance(trace, list) and len(trace) == len(plan), "Incomplete tensor trace")
        states = []
        for index, (node, entry) in enumerate(zip(plan, trace)):
            require(isinstance(entry, dict) and type(entry.get("node")) is int
                    and isinstance(entry.get("shape"), list)
                    and all(type(dim) is int for dim in entry["shape"]), "Malformed tensor trace entry")
            values = _evaluate_node(node, plan, states)
            require(entry == _trace_entry(index, node, values), "Incorrect tensor shape or value trace")
            states.append(values)
        verdict, conclusion = _conclusion(spec["kind"], plan, roots, bounds, states)
        claim = certificate["conclusion"]
        require(isinstance(claim, dict) and ("index" not in claim or type(claim["index"]) is int),
                "Malformed tensor conclusion")
        return certificate["verdict"] == verdict and claim == conclusion
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError):
        return False


def verify(spec):
    """Certify a concrete calculation, or return UNKNOWN for invalid/large inputs."""
    result = {"status": "UNKNOWN", "assurance": "NONE", "backend": BACKEND,
              "semantics": SEMANTICS, "certificate": None}
    try:
        plan, roots, bounds = _prepare(spec)
        states, trace = [], []
        for index, node in enumerate(plan):
            values = _evaluate_node(node, plan, states)
            states.append(values)
            trace.append(_trace_entry(index, node, values))
        verdict, conclusion = _conclusion(spec["kind"], plan, roots, bounds, states)
        certificate = {"version": VERSION, "backend": BACKEND, "spec_sha256": digest(spec),
                       "kind": spec["kind"], "verdict": verdict, "trace": trace, "conclusion": conclusion}
        require(len(canonical(certificate).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Certificate exceeds size limit")
        require(check_certificate(spec, certificate), "Tensor certificate did not verify")
        return {**result, "status": verdict,
                "assurance": "CERTIFICATE_CHECKED" if verdict == "PASS" else "EXACT_COUNTEREXAMPLE_CHECKED",
                "certificate": certificate}
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError) as exc:
        return {**result, "reason": str(exc)}

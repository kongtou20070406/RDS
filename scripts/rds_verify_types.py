"""Bounded exact arithmetic and bindings shared by domain certificate checkers."""
import hashlib
import json
import re
from fractions import Fraction

MAX_BITS = 4096
MAX_CERTIFICATE_BYTES = 2 * 1024 * 1024
SEMANTICS = "exact_real_model_with_rational_parameters"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bounded(value):
    value = Fraction(value)
    require(max(value.numerator.bit_length(), value.denominator.bit_length()) <= MAX_BITS,
            "Exact arithmetic exceeds the 4096-bit limit")
    return value


def bounded_json(value, *, max_nodes=100000, max_depth=64, allow_bool=True, allow_none=True):
    """Admit exact JSON; bound containers before expansion and serialization.

    Domain checkers can reject booleans/null without duplicating this walker.
    Floating values are never admitted.
    """
    stack, nodes, text_bytes = [(value, 0)], 0, 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        require(nodes <= max_nodes and depth <= max_depth, "Declaration resource limit exceeded")
        if isinstance(item, dict):
            require(nodes + len(stack) + 2 * len(item) <= max_nodes, "Declaration node limit exceeded")
            require(all(isinstance(key, str) for key in item), "JSON object keys must be strings")
            stack.extend((part, depth + 1) for pair in item.items() for part in pair)
        elif isinstance(item, list):
            require(nodes + len(stack) + len(item) <= max_nodes, "Declaration node limit exceeded")
            stack.extend((part, depth + 1) for part in item)
        elif isinstance(item, str):
            require(len(item) <= MAX_CERTIFICATE_BYTES, "Declaration string limit exceeded")
            text_bytes += len(item.encode("utf-8"))
            require(text_bytes <= MAX_CERTIFICATE_BYTES, "Declaration exceeds byte limit")
        else:
            require(type(item) is int or allow_bool and type(item) is bool or allow_none and item is None,
                    "Declarations require exact JSON values")
            if type(item) is int:
                require(item.bit_length() <= MAX_BITS, "Declared integer exceeds resource limit")
    require(len(canonical(value).encode("utf-8")) <= MAX_CERTIFICATE_BYTES,
            "Declaration exceeds byte limit")


def rational(value):
    """Accept finite exact declarations, including binary floating-point exports.

    Python floats and bools are rejected; a decimal/scientific string denotes an
    exact real decimal, and a ratio string denotes an exact rational number.
    """
    if type(value) is int:
        return bounded(value)
    require(isinstance(value, str) and 0 < len(value) <= 2500,
            "Expected a bounded exact rational string or integer")
    require(re.fullmatch(r"[+-]?(?:[0-9]+/[0-9]+|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,4})?)", value),
            "Expected a finite integer, decimal, scientific or rational string")
    if "e" in value.lower():
        require(abs(int(value.lower().split("e")[1])) <= 1200,
                "Decimal exponent exceeds the exact arithmetic resource limit")
    return bounded(Fraction(value))


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))


def digest(value):
    raw = value if isinstance(value, bytes) else canonical(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

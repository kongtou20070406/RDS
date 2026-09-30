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

"""Small exact checker for scalar affine rational threshold certificates.

Proof search and checking are separate. The trusted checker uses Fraction and
the affine endpoint theorem; it does not trust a solver's PASS or use SymPy.
This models real rational expressions, not floating point or neural networks.
"""
import ast
import hashlib
import json
from fractions import Fraction

VERSION = 1
MAX_BITS = 4096
MAX_CERTIFICATE_BYTES = 65536
STATEMENTS = {"threshold_separation", "threshold_necessity"}


class UnsupportedExpression(ValueError):
    """Outside the deliberately bounded affine rational proof fragment."""


class ResourceLimit(UnsupportedExpression):
    """Do not forward excessive exact work to another backend."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))


def bounded(value):
    value = Fraction(value)
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > MAX_BITS:
        raise ResourceLimit("Exact arithmetic exceeds the 4096-bit limit")
    return value


def _poly(values):
    values = tuple(bounded(v) for v in values)
    while len(values) > 1 and values[-1] == 0:
        values = values[:-1]
    if len(values) > 2:
        raise UnsupportedExpression("Exact certificates require affine numerators and denominators")
    return values


def _add(a, b, sign=1):
    return _poly((a[i] if i < len(a) else 0) + sign * (b[i] if i < len(b) else 0)
                 for i in range(max(len(a), len(b))))


def _mul(a, b):
    values = [Fraction(0)] * (len(a) + len(b) - 1)
    for i, left in enumerate(a):
        for j, right in enumerate(b):
            values[i + j] = bounded(values[i + j] + bounded(left * right))
    return _poly(values)


def _forms(functions):
    """Trusted AST interpretation. Keep every original division obligation."""
    obligations = []
    if sum(1 for expression in functions.values() for _ in ast.walk(expression)) > 160:
        raise ResourceLimit("Certificate AST exceeds the 160-node limit")

    def translate(node):
        if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) <= 1000000:
            return ((Fraction(node.value),), (Fraction(1),))
        if isinstance(node, ast.Name) and node.id == "x":
            return ((Fraction(0), Fraction(1)), (Fraction(1),))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            n, d = translate(node.operand)
            return (_poly(-v for v in n), d) if isinstance(node.op, ast.USub) else (n, d)
        if not isinstance(node, ast.BinOp):
            raise UnsupportedExpression("Unsupported certificate AST")
        n, d = translate(node.left)
        if isinstance(node.op, ast.Pow):
            if (not isinstance(node.right, ast.Constant) or type(node.right.value) is not int
                    or not 0 <= node.right.value <= 4):
                raise UnsupportedExpression("Only literal powers 0..4 are allowed")
            result_n, result_d = (Fraction(1),), (Fraction(1),)
            for _ in range(node.right.value):
                result_n, result_d = _mul(result_n, n), _mul(result_d, d)
            return result_n, result_d
        other_n, other_d = translate(node.right)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            sign = -1 if isinstance(node.op, ast.Sub) else 1
            if d == other_d:
                return _add(n, other_n, sign), d
            return _add(_mul(n, other_d), _mul(other_n, d), sign), _mul(d, other_d)
        if isinstance(node.op, ast.Mult):
            return _mul(n, other_n), _mul(d, other_d)
        if isinstance(node.op, ast.Div):
            obligations.append((other_n, other_d))
            return _mul(n, other_d), _mul(d, other_n)
        raise UnsupportedExpression("Unsupported certificate operator")

    if set(functions) != {"control", "treatment"}:
        raise UnsupportedExpression("Both scalar arms are required")
    forms = {arm: translate(functions[arm]) for arm in ("control", "treatment")}
    return forms, obligations


def _encode(form):
    return {"numerator": [str(v) for v in form[0]],
            "denominator": [str(v) for v in form[1]]}


def _value(poly, x):
    return bounded(poly[0] + (bounded(poly[1] * x) if len(poly) == 2 else 0))


def _nonzero(poly, domain):
    a, b = (_value(poly, x) for x in domain)
    # An affine function on a closed interval is a convex combination of its
    # endpoints. Strictly equal endpoint signs exclude every zero in between.
    return a > 0 and b > 0 or a < 0 and b < 0


def _at(form, x):
    return bounded(_value(form[0], x) / _value(form[1], x))


def _inputs(functions, formal):
    if formal.get("statement") not in STATEMENTS:
        raise ValueError("A typed threshold statement is required")
    domain = tuple(bounded(Fraction(v)) for v in formal["domain"])
    if len(domain) != 2 or domain[0] > domain[1]:
        raise ValueError("A nonvacuous closed domain is required")
    threshold = bounded(Fraction(formal["threshold"]))
    source = {arm: ast.dump(functions[arm], include_attributes=False)
              for arm in ("control", "treatment")}
    hash_value = lambda value: hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    return domain, threshold, hash_value(source), hash_value(formal)


def check_certificate(functions, formal, certificate):
    """Replay a bounded proof object against the original AST and full claim.

    Returns False for forged, incomplete, differently bound or unsupported
    objects. A caller must also require certificate['verdict'] == 'PASS'.
    No certificate generation/search routine is called by this checker.
    """
    try:
        if not isinstance(certificate, dict) or len(canonical(certificate).encode("utf-8")) > MAX_CERTIFICATE_BYTES:
            return False
        if set(certificate) != {"version", "source_sha256", "formal_sha256", "statement",
                                "domain", "threshold", "forms", "denominators",
                                "endpoint_values", "verdict", "case", "witness"}:
            return False
        domain, threshold, source_sha, formal_sha = _inputs(functions, formal)
        if (type(certificate["version"]) is not int or certificate["version"] != VERSION
                or certificate["source_sha256"] != source_sha
                or certificate["formal_sha256"] != formal_sha
                or certificate["statement"] != formal["statement"]
                or certificate["domain"] != [str(x) for x in domain]
                or certificate["threshold"] != str(threshold)):
            return False
        forms, obligations = _forms(functions)
        if (certificate["forms"] != {arm: _encode(form) for arm, form in forms.items()}
                or certificate["denominators"] != [_encode(form) for form in obligations]):
            return False
        if any(not _nonzero(n, domain) or not _nonzero(d, domain) for n, d in obligations):
            return False
        if any(not _nonzero(form[1], domain) for form in forms.values()):
            return False
        values = {arm: tuple(_at(form, x) for x in domain) for arm, form in forms.items()}
        if certificate["endpoint_values"] != {arm: [str(v) for v in vals] for arm, vals in values.items()}:
            return False
        witness = certificate["witness"]
        if certificate["verdict"] == "FAIL" and certificate["case"] == "no_treatment_crossing":
            # A defined affine rational function is monotone (or constant), so
            # endpoint bounds cover the entire closed interval.
            return witness is None and all(v < threshold for v in values["treatment"])
        if not isinstance(witness, dict) or set(witness) != {"arm", "x", "value"}:
            return False
        if not isinstance(witness["x"], str) or len(witness["x"]) > 2500:
            return False
        x = bounded(Fraction(witness["x"]))
        if not domain[0] <= x <= domain[1]:
            return False
        if certificate["verdict"] == "PASS" and certificate["case"] == "separation":
            return (witness["arm"] == "treatment" and all(v < threshold for v in values["control"])
                    and witness["value"] == str(_at(forms["treatment"], x))
                    and _at(forms["treatment"], x) >= threshold)
        if certificate["verdict"] == "FAIL" and certificate["case"] == "control_not_below":
            return (witness["arm"] == "control" and witness["value"] == str(_at(forms["control"], x))
                    and _at(forms["control"], x) >= threshold)
        return False
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError, OverflowError, RecursionError):
        return False


def exact_probe(functions, formal):
    """Search for endpoint proofs/witnesses, then submit them to the checker.

    UnsupportedExpression means the caller may use a separately labeled solver
    fallback. An undefined original expression yields UNKNOWN, never PASS.
    """
    domain, threshold, source_sha, formal_sha = _inputs(functions, formal)
    forms, obligations = _forms(functions)
    if (any(not _nonzero(n, domain) or not _nonzero(d, domain) for n, d in obligations)
            or any(not _nonzero(form[1], domain) for form in forms.values())):
        return {"status": "UNKNOWN", "assurance": "NONE", "backend": "rds_exact_affine",
                "reason": "denominator may vanish in domain"}
    values = {arm: tuple(_at(form, x) for x in domain) for arm, form in forms.items()}
    if any(v >= threshold for v in values["control"]):
        verdict, case, arm = "FAIL", "control_not_below", "control"
    elif any(v >= threshold for v in values["treatment"]):
        verdict, case, arm = "PASS", "separation", "treatment"
    else:
        verdict, case, arm = "FAIL", "no_treatment_crossing", None
    witness = None
    if arm:
        i = next(i for i, value in enumerate(values[arm]) if value >= threshold)
        witness = {"arm": arm, "x": str(domain[i]), "value": str(values[arm][i])}
    certificate = {"version": VERSION, "source_sha256": source_sha, "formal_sha256": formal_sha,
                   "statement": formal["statement"], "domain": [str(x) for x in domain],
                   "threshold": str(threshold), "forms": {arm: _encode(form) for arm, form in forms.items()},
                   "denominators": [_encode(form) for form in obligations],
                   "endpoint_values": {arm: [str(v) for v in vals] for arm, vals in values.items()},
                   "verdict": verdict, "case": case, "witness": witness}
    if len(canonical(certificate).encode("utf-8")) > MAX_CERTIFICATE_BYTES:
        raise ResourceLimit("Exact certificate exceeds the 65536-byte limit")
    if not check_certificate(functions, formal, certificate):
        raise ValueError("Generated exact certificate did not pass the independent checker")
    return {"status": verdict, "assurance": "CERTIFICATE_CHECKED", "backend": "rds_exact_affine",
            "backend_version": str(VERSION), "semantics": "exact_rational_execution_and_real_affine_model",
            "statement": formal["statement"], "domain": formal["domain"], "threshold": formal["threshold"],
            "certificate": certificate, "reason": "threshold discrimination only; no causal mechanism conclusion"}

"""Exact triangular spectra and sufficient Gershgorin spectral bounds.

A large Gershgorin bound is inconclusive. It never certifies that the true
spectral radius is large. No floating-point eigenvalue calculation is used.
"""
from fractions import Fraction

from rds_verify_types import (MAX_CERTIFICATE_BYTES, bounded, canonical, digest,
                              rational, require)

MAX_DIMENSION = 64
KINDS = {"matrix_spectral_bound", "matrix_spectral_exact"}
CERTIFICATE_KEYS = {"version", "spec_sha256", "method", "row_bounds", "diagonal", "bound", "verdict"}


def _read_spec(spec):
    require(isinstance(spec, dict) and set(spec) == {"schema", "kind", "matrix", "threshold"},
            "Spectral declaration requires schema, kind, matrix and threshold")
    require(len(canonical(spec).encode("utf-8")) <= MAX_CERTIFICATE_BYTES,
            "Spectral declaration exceeds the byte limit")
    require(type(spec["schema"]) is int and spec["schema"] == 1, "Expected spectral schema 1")
    require(isinstance(spec["kind"], str) and spec["kind"] in KINDS, "Unknown spectral verification kind")
    raw = spec["matrix"]
    require(isinstance(raw, list) and 1 <= len(raw) <= MAX_DIMENSION, "Matrix dimension must be 1..64")
    matrix = []
    for row in raw:
        require(isinstance(row, list) and len(row) == len(raw), "Spectral matrix must be square")
        require(all(isinstance(value, str) for value in row), "Matrix entries must be exact rational strings")
        matrix.append([rational(value) for value in row])
    require(isinstance(spec["threshold"], str), "Spectral threshold must be an exact rational string")
    threshold = rational(spec["threshold"])
    require(threshold > 0, "Spectral threshold must be positive")
    return matrix, threshold


def verify(spec):
    """Generate an exact certificate, or report an insufficient bound UNKNOWN."""
    matrix, threshold = _read_spec(spec)
    dimension = len(matrix)
    upper = all(matrix[i][j] == 0 for i in range(dimension) for j in range(i))
    lower = all(matrix[i][j] == 0 for i in range(dimension) for j in range(i + 1, dimension))
    rows = []
    for row in matrix:
        total = Fraction(0)
        for value in row:
            total = bounded(total + abs(value))
        rows.append(total)
    diagonal = None
    if upper or lower:
        method = "exact_triangular"
        diagonal = [matrix[i][i] for i in range(dimension)]
        bound = max(abs(value) for value in diagonal)
        verdict = "PASS" if bound < threshold else "FAIL"
    elif spec["kind"] == "matrix_spectral_exact":
        return {"status": "UNKNOWN", "assurance": "NONE", "backend": "rds_exact_matrix_spectral",
                "reason": "Exact spectral radius is supported only for triangular matrices"}
    else:
        method, bound = "gershgorin", max(rows)
        if bound >= threshold:
            return {"status": "UNKNOWN", "assurance": "NONE", "backend": "rds_exact_matrix_spectral",
                    "method": method, "row_bounds": [str(value) for value in rows], "bound": str(bound),
                    "reason": "Gershgorin sufficient bound does not decide rho(A) < threshold"}
        verdict = "PASS"
    certificate = {"version": 1, "spec_sha256": digest(spec), "method": method,
                   "row_bounds": [str(value) for value in rows],
                   "diagonal": [str(value) for value in diagonal] if diagonal is not None else None,
                   "bound": str(bound), "verdict": verdict}
    require(check_certificate(spec, certificate), "Generated spectral certificate failed independent check")
    return {"status": verdict, "assurance": "CERTIFICATE_CHECKED", "backend": "rds_exact_matrix_spectral",
            "certificate": certificate, "scope": "rho(A) < threshold for the declared exact rational matrix"}


def check_certificate(spec, certificate):
    """Replay the triangular-spectrum or Gershgorin theorem without generation."""
    try:
        if not isinstance(certificate, dict) or set(certificate) != CERTIFICATE_KEYS:
            return False
        if len(canonical(certificate).encode("utf-8")) > MAX_CERTIFICATE_BYTES:
            return False
        matrix, threshold = _read_spec(spec)
        dimension = len(matrix)
        if (type(certificate["version"]) is not int or certificate["version"] != 1
                or certificate["spec_sha256"] != digest(spec)):
            return False
        rows = []
        upper, lower = True, True
        for i, row in enumerate(matrix):
            total = Fraction(0)
            for j, value in enumerate(row):
                total = bounded(total + abs(value))
                if i > j and value != 0:
                    upper = False
                if i < j and value != 0:
                    lower = False
            rows.append(total)
        if certificate["row_bounds"] != [str(value) for value in rows]:
            return False
        if certificate["method"] == "exact_triangular":
            if not (upper or lower):
                return False
            diagonal = [matrix[i][i] for i in range(dimension)]
            if certificate["diagonal"] != [str(value) for value in diagonal]:
                return False
            bound = max(abs(value) for value in diagonal)
            verdict = "PASS" if bound < threshold else "FAIL"
        elif certificate["method"] == "gershgorin":
            if spec["kind"] != "matrix_spectral_bound" or certificate["diagonal"] is not None:
                return False
            bound = max(rows)
            if bound >= threshold:
                return False
            verdict = "PASS"
        else:
            return False
        return certificate["bound"] == str(bound) and certificate["verdict"] == verdict
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError, OverflowError, RecursionError):
        return False

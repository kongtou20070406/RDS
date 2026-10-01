"""Bounded exact whole-disk coverage replay; no global-optimality conclusion.

The byte-preserved core implements the finite Voronoi/circle extrema lemma.
This adapter bounds declarations and binds both implementations. Generation
may propose coverers using floats; accepted inequalities and frozen replay
are exact. Invalid or uncovered inputs do not produce a PASS certificate.
"""
import argparse
import json
from pathlib import Path

import rds_unit_disk_voronoi_core as core
from rds_verify_types import MAX_CERTIFICATE_BYTES, bounded_json, digest, rational, require

VERSION = 1
KIND = "unit_disk_rational_voronoi"
RULE = "geometry.unit_disk_rational_voronoi"
BACKEND = "rds_exact_rational_voronoi"
SEMANTICS = "whole_closed_unit_disk_coverage_only_no_global_optimality"
MAX_CENTERS = 256
MAX_INPUT_BITS = 512
MAX_NODES = 100000
MAX_DEPTH = 32
CERTIFICATE_KEYS = {"version", "spec_sha256", "checker_sha256", "method",
                    "backend", "semantics", "verdict", "core_certificate"}


def _checker_id():
    here = Path(__file__).resolve().parent
    return digest({name: digest((here / name).read_bytes()) for name in
                   ("rds_rational_voronoi_verify.py", "rds_unit_disk_voronoi_core.py",
                    "rds_verify_types.py")})


def _exact_json(value):
    bounded_json(value, max_nodes=MAX_NODES, max_depth=MAX_DEPTH, allow_bool=False, allow_none=False)


def _number(value):
    require(type(value) is int or isinstance(value, str) and 0 < len(value) <= 160,
            "Expected a bounded rational string or integer")
    number = rational(value)
    require(max(number.numerator.bit_length(), number.denominator.bit_length()) <= MAX_INPUT_BITS,
            "Voronoi input exceeds the 512-bit arithmetic limit")
    return number


def _read_spec(spec):
    _exact_json(spec)
    require(isinstance(spec, dict) and set(spec) ==
            {"schema", "kind", "centers", "radius_squared"}, "Invalid Voronoi declaration fields")
    require(type(spec["schema"]) is int and spec["schema"] == 1 and spec["kind"] == KIND,
            "Expected schema 1 unit_disk_rational_voronoi")
    raw = spec["centers"]
    require(isinstance(raw, list) and 1 <= len(raw) <= MAX_CENTERS, "1..256 centers required")
    for point in raw:
        require(isinstance(point, list) and len(point) == 2, "Two exact coordinates required")
        require(all(abs(_number(value)) <= 8 for value in point), "Coordinates must lie in [-8,8]")
    require(0 <= _number(spec["radius_squared"]) <= 64, "Squared radius must lie in [0,64]")
    return {**spec, "kind": "unit_disk_cover"}


def _certificate(spec, frozen):
    return {"version": VERSION, "spec_sha256": digest(spec), "checker_sha256": _checker_id(),
            "method": RULE, "backend": BACKEND, "semantics": SEMANTICS,
            "verdict": "PASS", "core_certificate": frozen}


def _pass(certificate):
    _exact_json(certificate)
    return {"status": "PASS", "assurance": "CERTIFICATE_CHECKED", "backend": BACKEND,
            "semantics": SEMANTICS, "certificate": certificate}


def from_core_certificate(spec, frozen):
    """Replay an original frozen core certificate before wrapping its bindings."""
    source = _read_spec(spec)
    _exact_json(frozen)
    checked = core.compute(source, frozen)
    require(checked.get("verdict") == "pass", "Frozen core certificate does not prove coverage")
    return _pass(_certificate(spec, checked))


def check_certificate(spec, certificate):
    """Regenerate the complete candidate set and check only recorded coverers."""
    try:
        source = _read_spec(spec)
        _exact_json(certificate)
        require(isinstance(certificate, dict) and set(certificate) == CERTIFICATE_KEYS,
                "Invalid Voronoi certificate fields")
        require(type(certificate["version"]) is int and certificate["version"] == VERSION
                and certificate["spec_sha256"] == digest(spec)
                and certificate["checker_sha256"] == _checker_id()
                and certificate["method"] == RULE and certificate["backend"] == BACKEND
                and certificate["semantics"] == SEMANTICS and certificate["verdict"] == "PASS",
                "Voronoi certificate binding or claim mismatch")
        checked = core.compute(source, certificate["core_certificate"])
        return checked.get("verdict") == "pass"
    except (ValueError, TypeError, KeyError, AttributeError, OSError, ArithmeticError, RecursionError):
        return False


def verify(spec):
    """Generate a coverage certificate; diagnostics remain UNKNOWN without it."""
    try:
        result = core.compute(_read_spec(spec))
        require(result.get("verdict") == "pass", "No coverage certificate: " + result.get("reason", "unknown"))
        return _pass(_certificate(spec, result))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, ArithmeticError, RecursionError) as exc:
        return {"status": "UNKNOWN", "assurance": "NONE", "backend": BACKEND,
                "semantics": SEMANTICS, "reason": str(exc)}


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "Duplicate JSON key")
        value[key] = item
    return value


def _read_json(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_CERTIFICATE_BYTES + 1)
    require(len(raw) <= MAX_CERTIFICATE_BYTES, "JSON file exceeds byte limit")
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _reject_constant(value):
    raise ValueError("Nonfinite JSON value: " + value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    replay = parser.add_mutually_exclusive_group()
    replay.add_argument("--certificate", help="Replay an adapter certificate or result")
    replay.add_argument("--core-certificate", help="Replay and bind a frozen original core certificate")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        spec = _read_json(args.spec)
        if args.core_certificate:
            result = from_core_certificate(spec, _read_json(args.core_certificate))
        elif args.certificate:
            raw = _read_json(args.certificate)
            certificate = raw.get("certificate", raw)
            require(check_certificate(spec, certificate), "Invalid frozen Voronoi certificate")
            result = _pass(certificate)
        else:
            result = verify(spec)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, ArithmeticError, RecursionError) as exc:
        result = {"status": "UNKNOWN", "assurance": "NONE", "reason": str(exc)}
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "certificate"}))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

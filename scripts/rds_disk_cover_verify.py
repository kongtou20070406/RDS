"""Exact whole-unit-disk coverage certificates; no optimality conclusion.

A finite full dyadic quadtree partitions [-1,1]^2. Each closed leaf is either
strictly outside the unit disk or has all four corners in one declared closed
covering disk. Convexity covers that whole rectangle, including its boundary.
The independent checker never calls the search routine or samples the disk.
"""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from rds_verify_types import (MAX_CERTIFICATE_BYTES, bounded, canonical, digest,
                              rational, require)

VERSION = 1
MAX_CENTERS = 256
MAX_DEPTH = 32
MAX_LEAVES = 24000
SEMANTICS = "whole_closed_unit_disk_coverage_only_no_global_optimality"
CERTIFICATE_KEYS = {"version", "spec_sha256", "checker_sha256", "method",
                    "semantics", "verdict", "leaves"}


def _checker_id():
    here = Path(__file__).resolve()
    return digest({"checker": digest(here.read_bytes()),
                   "arithmetic": digest(here.with_name("rds_verify_types.py").read_bytes())})


def _read_spec(spec):
    require(isinstance(spec, dict) and set(spec) ==
            {"schema", "kind", "centers", "radius_squared"},
            "Disk cover requires exactly schema, kind, centers and radius_squared")
    require(type(spec["schema"]) is int and spec["schema"] == 1,
            "Expected disk-cover schema 1")
    require(spec["kind"] == "unit_disk_cover", "Unsupported coverage claim")
    require(len(canonical(spec).encode("utf-8")) <= MAX_CERTIFICATE_BYTES,
            "Disk-cover declaration exceeds byte limit")
    raw = spec["centers"]
    require(isinstance(raw, list) and 1 <= len(raw) <= MAX_CENTERS,
            "Disk cover requires 1..256 centers")
    centers = []
    for point in raw:
        require(isinstance(point, list) and len(point) == 2 and
                all(isinstance(value, str) for value in point),
                "Centers require two exact rational strings")
        centers.append(tuple(rational(value) for value in point))
    require(isinstance(spec["radius_squared"], str),
            "Squared radius must be an exact rational string")
    radius_squared = rational(spec["radius_squared"])
    require(radius_squared > 0, "Squared radius must be positive")
    return centers, radius_squared


def _children(box):
    x0, x1, y0, y1 = box
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    # Path digit: x-upper bit + 2*y-upper bit.
    return ((x0, xm, y0, ym), (xm, x1, y0, ym),
            (x0, xm, ym, y1), (xm, x1, ym, y1))


def _box(path):
    box = (Fraction(-1), Fraction(1), Fraction(-1), Fraction(1))
    for digit in path:
        box = _children(box)[int(digit)]
    return box


def _strictly_outside(box):
    x0, x1, y0, y1 = box
    dx = 0 if x0 <= 0 <= x1 else min(abs(x0), abs(x1))
    dy = 0 if y0 <= 0 <= y1 else min(abs(y0), abs(y1))
    return bounded(dx * dx + dy * dy) > 1


def _corners_covered(box, center, radius_squared):
    x0, x1, y0, y1 = box
    cx, cy = center
    # This is exactly the maximum over all four corner squared distances.
    dx, dy = max(abs(x0 - cx), abs(x1 - cx)), max(abs(y0 - cy), abs(y1 - cy))
    return bounded(bounded(dx * dx) + bounded(dy * dy)) <= radius_squared


def _contains_unit_disk(center, radius_squared):
    # max_{||x||<=1} ||x-c|| = 1+||c||. Squaring only after delta>=0
    # is equivalent to radius_squared >= (1+sqrt(||c||^2))^2.
    norm_squared = bounded(bounded(center[0] * center[0]) + bounded(center[1] * center[1]))
    delta = bounded(radius_squared - 1 - norm_squared)
    return delta >= 0 and bounded(delta * delta) >= bounded(4 * norm_squared)


def _full_partition(leaves):
    """Require every internal quadtree node to have all four children."""
    require(isinstance(leaves, list) and 1 <= len(leaves) <= MAX_LEAVES,
            "Quadtree leaf count exceeds limit or is empty")
    tree = {}
    for leaf in leaves:
        require(isinstance(leaf, list) and len(leaf) == 2, "Invalid leaf")
        path, cover = leaf
        require(isinstance(path, str) and len(path) <= MAX_DEPTH and
                all(digit in "0123" for digit in path), "Invalid dyadic path")
        require(cover is None or type(cover) is int, "Leaf cover must be a center index or null")
        node = tree
        for digit in path:
            require("leaf" not in node, "Overlapping ancestor and descendant leaves")
            node = node.setdefault(digit, {})
        require(not node, "Duplicate or overlapping leaves")
        node["leaf"] = True
    stack = [tree]
    while stack:
        node = stack.pop()
        if "leaf" in node:
            require(set(node) == {"leaf"}, "Overlapping leaf")
        else:
            require(set(node) == set("0123"), "Incomplete quadtree partition")
            stack.extend(node.values())


def check_certificate(spec, certificate):
    """Replay a complete exact proof, independently of generation/search."""
    try:
        centers, radius_squared = _read_spec(spec)
        require(isinstance(certificate, dict) and set(certificate) == CERTIFICATE_KEYS,
                "Invalid disk-cover certificate fields")
        require(len(canonical(certificate).encode("utf-8")) <= MAX_CERTIFICATE_BYTES,
                "Disk-cover certificate exceeds byte limit")
        require(type(certificate["version"]) is int and certificate["version"] == VERSION and
                certificate["spec_sha256"] == digest(spec) and
                certificate["checker_sha256"] == _checker_id() and
                certificate["method"] in {"full_dyadic_quadtree_corner_convexity",
                                          "single_disk_unit_disk_containment"} and
                certificate["semantics"] == SEMANTICS and certificate["verdict"] == "PASS",
                "Certificate binding, method or claim mismatch")
        leaves = certificate["leaves"]
        _full_partition(leaves)
        if certificate["method"] == "single_disk_unit_disk_containment":
            require(len(leaves) == 1 and leaves[0][0] == "" and type(leaves[0][1]) is int,
                    "Whole-unit-disk containment requires exactly one root leaf")
            cover = leaves[0][1]
            require(0 <= cover < len(centers) and _contains_unit_disk(centers[cover], radius_squared),
                    "Declared single disk does not contain the whole unit disk")
            return True
        for path, cover in leaves:
            box = _box(path)
            if cover is None:
                require(_strictly_outside(box), "Outside leaf intersects the closed unit disk")
            else:
                require(0 <= cover < len(centers), "Invalid covering-center index")
                require(_corners_covered(box, centers[cover], radius_squared),
                        "A rectangle corner is outside its claimed covering disk")
        return True
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError,
            OverflowError, RecursionError):
        return False


def verify(spec, max_depth=MAX_DEPTH, max_leaves=MAX_LEAVES):
    """Bounded certificate search. An insufficient enclosure is UNKNOWN."""
    centers, radius_squared = _read_spec(spec)
    require(type(max_depth) is int and 0 <= max_depth <= MAX_DEPTH,
            "Search depth must be 0..32")
    require(type(max_leaves) is int and 1 <= max_leaves <= MAX_LEAVES,
            "Search leaf limit must be 1..24000")
    containing = next((i for i, center in enumerate(centers) if _contains_unit_disk(center, radius_squared)), None)
    leaves = []
    stack = [("", (Fraction(-1), Fraction(1), Fraction(-1), Fraction(1)))] if containing is None else []
    if containing is not None:
        leaves.append(["", containing])
    while stack:
        path, box = stack.pop()
        if _strictly_outside(box):
            leaves.append([path, None])
        else:
            x0, x1, y0, y1 = box
            midpoint = ((x0 + x1) / 2, (y0 + y1) / 2)
            nearest = min(range(len(centers)), key=lambda i:
                          (centers[i][0] - midpoint[0]) ** 2 +
                          (centers[i][1] - midpoint[1]) ** 2)
            if _corners_covered(box, centers[nearest], radius_squared):
                leaves.append([path, nearest])
            elif len(path) >= max_depth or len(leaves) + len(stack) + 4 > max_leaves:
                return {"status": "UNKNOWN", "assurance": "NONE", "backend": "rds_exact_disk_cover",
                        "semantics": SEMANTICS, "reason": "Finite quadtree search limit reached",
                        "completed_leaves": len(leaves), "unresolved_path": path}
            else:
                stack.extend((path + str(i), child) for i, child in reversed(list(enumerate(_children(box)))))
    certificate = {"version": VERSION, "spec_sha256": digest(spec),
                   "checker_sha256": _checker_id(),
                   "method": "full_dyadic_quadtree_corner_convexity" if containing is None else
                             "single_disk_unit_disk_containment", "semantics": SEMANTICS,
                   "verdict": "PASS", "leaves": leaves}
    require(check_certificate(spec, certificate), "Generated disk-cover certificate failed replay")
    return {"status": "PASS", "assurance": "CERTIFICATE_CHECKED", "backend": "rds_exact_disk_cover",
            "semantics": SEMANTICS, "certificate": certificate,
            "reason": "Every point of the closed unit disk is covered; global optimality remains unproved"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--certificate", help="Replay this certificate or complete result; no search")
    parser.add_argument("--max-depth", type=int, default=MAX_DEPTH)
    parser.add_argument("--max-leaves", type=int, default=MAX_LEAVES)
    args = parser.parse_args()
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        if args.certificate:
            supplied = json.loads(Path(args.certificate).read_text(encoding="utf-8"))
            certificate = supplied.get("certificate", supplied)
            ok = check_certificate(spec, certificate)
            result = {"status": "PASS" if ok else "UNKNOWN", "assurance": "CERTIFICATE_CHECKED" if ok else "NONE",
                      "backend": "rds_exact_disk_cover", "semantics": SEMANTICS,
                      "reason": "Independent complete certificate replay" if ok else "Invalid certificate"}
        else:
            result = verify(spec, args.max_depth, args.max_leaves)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        result = {"status": "UNKNOWN", "assurance": "NONE", "reason": str(exc)}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "certificate"}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

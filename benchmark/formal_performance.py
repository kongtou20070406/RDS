"""Standard-library timings for fresh rules and separate WAL cache phases.

python -B benchmark/formal_performance.py --repeats 5 --output results.json
"""
import argparse
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_verify as engine
from rds_proof_cache import ProofCache
from rds_verify_types import digest


def measure(operation, repeats):
    values = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    return {"median_ms": round(statistics.median(values), 4),
            "samples_ms": [round(v, 4) for v in values]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--spec", action="append", type=Path,
                        help="Specification path; repeat for multiple cases")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 1000:
        parser.error("--repeats must be 1..1000")
    paths = args.spec or [ROOT / "examples/formal/affine_dynamics.json",
                          ROOT / "examples/formal/theorem_module.json"]
    result = {"environment": {"python": sys.version, "platform": platform.platform(),
                              "verifier_sha256": engine.verifier_id()},
              "repeats": args.repeats, "cases": []}
    with tempfile.TemporaryDirectory(prefix="rds-formal-benchmark-") as directory:
        for index, path in enumerate(paths):
            spec = json.loads(path.read_text(encoding="utf-8-sig"))
            cache = ProofCache(Path(directory) / str(index) / "proofs.sqlite3")
            fresh = engine.verify(spec)
            case = {"path": str(path.resolve()), "kind": spec.get("kind"),
                    "status": fresh.get("status"), "assurance": fresh.get("assurance"),
                    "fresh_verify": measure(lambda: engine.verify(spec), args.repeats)}
            certificate = fresh.get("certificate")
            if certificate is not None and fresh.get("status") in {"PASS", "FAIL"}:
                key = digest(spec) + engine.verifier_id()
                case["independent_check"] = measure(
                    lambda: engine.checked_result(spec, certificate), args.repeats)
                first = cache.verify(spec)
                case["initial_cache"] = first["cache"]
                case["read_only_sqlite"] = measure(lambda: cache._read(key), args.repeats)
                case["short_sqlite_store"] = measure(lambda: cache._store(key, certificate), args.repeats)
                case["warm_read_and_check"] = measure(lambda: cache.verify(spec), args.repeats)
                case["warm_result"] = cache.verify(spec)["cache"]
                writer = sqlite3.connect(cache.path, timeout=0, isolation_level=None)
                try:
                    writer.execute("BEGIN IMMEDIATE")
                    writer.execute("UPDATE proofs SET certificate=? WHERE cache_key=?", (b"pending-forged", key))
                    assert cache._read(key) == certificate
                    case["active_writer"] = {
                        "read_only_sqlite": measure(lambda: cache._read(key), args.repeats),
                        "warm_read_and_check": measure(lambda: cache.verify(spec), args.repeats),
                        "warm_result": cache.verify(spec)["cache"],
                    }
                    assert case["active_writer"]["warm_result"]["hit"]
                finally:
                    writer.rollback()
                    writer.close()
            else:
                case["cache_note"] = "No checked PASS/FAIL certificate; no proof cache timing"
            result["cases"].append(case)
    result["limitations"] = [
        "One interpreter and local filesystem; medians are descriptive, not latency guarantees.",
        "Fresh verification regenerates rules in-process; these timings exclude CLI/interpreter startup.",
        "Independent checking includes framework/source binding checks; read/store phases exclude mathematical work.",
        "Active-writer timings hold an uncommitted cache update; readers replay the previous committed certificate.",
        "Tiny exact affine maps and theorem modules do not measure PyTorch, GPU, or stochastic training convergence.",
    ]
    raw = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw + "\n", encoding="utf-8")
    print(raw)


if __name__ == "__main__":
    main()

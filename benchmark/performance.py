"""Bounded local timings, synthetic scalar inputs; never a GPU benchmark.

Run python -B benchmark/performance.py [--output timings.json].
"""
import argparse
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark.run import C7_CONTROL, C7_FORMAL, Project
from rds_cli import RDSState, cmd_status, formal_gate
from rds_probe import admission_probe


def measure(fn, repeats, inner=1):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        for _ in range(inner):
            fn()
        samples.append((time.perf_counter() - start) * 1000 / inner)
    return {"median_ms": round(statistics.median(samples), 3),
            "samples_ms": [round(x, 3) for x in samples], "calls_per_sample": inner}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("--repeats must be 1..20")
    source = C7_CONTROL + "def treatment(x): return 2*x/(1+x)\n"
    hypothesis = {"formal": C7_FORMAL}
    result = {"environment": {"python": platform.python_version(), "platform": platform.platform()},
              "repeats": args.repeats,
              "ast_admission": measure(lambda: admission_probe({}, source), args.repeats, 1000),
              "formal_gate_fresh_process": measure(lambda: formal_gate(hypothesis, source), args.repeats),
              "formal_result": formal_gate(hypothesis, source)}
    project = Project(source=source).init(C7_FORMAL)
    try:
        result["first_plan_gate"] = measure(
            lambda: project.call("gate", "check", spec=project.plan(), flag="--plan"), 1)
        project.call("plan", "create", spec=project.plan("CACHE"))
        result["repeated_plan_gate"] = measure(
            lambda: project.call("gate", "check", spec=project.plan("CHECK"), flag="--plan"), args.repeats)
        result["advisor_valid_plan"] = measure(
            lambda: project.call("advise", spec=project.plan("CHECK"), flag="--plan"), args.repeats)
        result["advisor_result"] = project.call("advise", spec=project.plan("CHECK"), flag="--plan")
        result["status_by_cache_rows"] = []
        state = RDSState(project.root)
        for count in (1, 1000, 10000):
            with state.transaction() as (_, snapshot):
                snapshot["baseline_cache"] = {"synthetic": {"observations": {
                    str(i): {"control": "1", "control_loss": "1"} for i in range(count)}}}
            result["status_by_cache_rows"].append({"rows": count, **measure(
                lambda: cmd_status(None, state), args.repeats)})
    finally:
        project.close()
    result["limitations"] = [
        "One local environment, bounded repetitions; inspect distributions before claiming a speedup.",
        "Fresh-process and CLI timings include interpreter startup; status timings are in-process.",
        "Synthetic scalar programs and cache rows do not measure neural-network training or GPU savings.",
    ]
    raw = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(raw + "\n", encoding="utf-8")
    print(raw)


if __name__ == "__main__":
    main()

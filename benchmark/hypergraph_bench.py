"""Matched synthetic closure workloads; parity includes witnesses and conflicts."""
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rds_accelerator as accelerator


def run_benchmark(num_chains=20, chain_len=25, reverse=False):
    nodes = [{"id": f"root_{i}", "status": "SUPPORTED"} for i in range(num_chains)]
    edges = []
    for c in range(num_chains):
        prev = f"root_{c}"
        for step in range(chain_len):
            curr = f"node_c{c}_s{step}"
            nodes.append({"id": curr, "status": "UNKNOWN"})
            edges.append({"id": f"edge_c{c}_s{step}", "premises": [prev, f"root_{(c+1)%num_chains}"],
                          "conclusion": curr, "status": "SUPPORTED"})
            prev = curr
    if reverse:
        edges.reverse()
    initial = {n["id"] for n in nodes if n["status"] == "SUPPORTED"}
    expected = accelerator.python_hypergraph_closure(nodes, edges, initial)
    measurements = {}
    for name, fn in (("python_reference", accelerator.python_hypergraph_closure),
                     ("selected_backend", accelerator.compute_hypergraph_closure)):
        fn(nodes, edges, initial)  # Warm the selected library separately.
        elapsed = []
        for _ in range(20):
            start = time.perf_counter()
            actual = fn(nodes, edges, initial)
            elapsed.append((time.perf_counter() - start) * 1000)
            if actual != expected:
                raise AssertionError("Closure, first derivations or conflicts differ")
        measurements[name] = {"median_ms": statistics.median(elapsed),
                             "min_ms": min(elapsed), "max_ms": max(elapsed)}
    status = accelerator.get_accelerator_status()
    return {"nodes": len(nodes), "edges": len(edges), "reversed": reverse,
            "samples": 20, "closure_size": len(expected[0]), "backend": status["backend"],
            "compiled_native_checked": status["native_library_loaded"],
            "parity": "MATCHED_ON_THIS_WORKLOAD", "measurements": measurements,
            "assurance": "SYNTHETIC_CLOSURE_NOT_FULL_ADVISOR_OR_SCIENTIFIC_GAIN"}


if __name__ == "__main__":
    print(json.dumps([run_benchmark(), run_benchmark(reverse=True)], allow_nan=False))

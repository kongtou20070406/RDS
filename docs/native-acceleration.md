# Optional native closure

The closure adapter preserves the existing declared-label AND/OR semantics:
contradicted nodes cannot become premises, initial nodes get no new derivation,
and the first derivation follows the original ordered fixed-point traversal.
This is dependency analysis, not a proof of the statements in the graph.

Python remains the default when no usable compiled library is present. Cargo
availability is reported separately and does not make `rust_native` available.
Nothing installs a compiler or compiles during an ordinary Advisor call.

From the repository root, with an existing Rust toolchain:

```text
cargo test --offline --manifest-path native/rds_accelerator/Cargo.toml
cargo build --offline --release --manifest-path native/rds_accelerator/Cargo.toml
python -B scripts/rds_capabilities.py --capability rust_native
python -B -m unittest discover -s tests -p test_rds_accelerator.py -v
python -B benchmark/hypergraph_bench.py
```

The trusted local library is loaded only from this checkout's crate `target`
directory and must expose ABI version 2, its smoke check and the closure entry.
Absent, incompatible or incomplete libraries leave the Python path available.
An old experimental ABI is not loaded. Rebuild before starting a new process;
the selected library is cached for the current process.

ABI v2 includes contradicted flags, closure flags, first-edge witnesses and
conflict flags. It rejects malformed indices/encodings without partial output;
the C caller still owns valid non-overlapping buffers. This is not an OS sandbox
or protection from hostile local libraries. Python marshals inputs into C arrays;
the call is not zero-copy.

Native CI on Windows and Ubuntu compiles the actual library, requires that it is
loaded, and compares 300 deterministic synthetic graphs to the ordered Python
reference. The tests cover cycles, conjunctions, alternative derivations,
contradictions, empty rules and invalid ABI/input paths. These finite regressions
do not prove equivalence for every program or improve a scientific score.

The microbenchmark compares the same ordered and reversed 520-node/500-edge
workloads over 20 warmed samples, reports median and range, and checks the full
closure/witness/conflict tuple. A fallback-only run reports that native was not
checked. It measures closure with marshalling, not all of Advisor or graph-gap
analysis; no speedup is promised before the selected workload is measured.

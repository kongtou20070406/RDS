# Mathematical checks within RDS research workflows

RDS automates assistance to human research: evidence investigation, experiment
selection, budgeted execution, result assessment and continuation. Mathematical
checks discharge applicable side conditions within that workflow. A proved
property of a declared model does not establish task gain or causality.

The framework borrows Lean's separation of declarations, proof search and
checking. JSON is an exchange format for bounded proof obligations. It is not a
replacement for Lean4's language, dependent types, kernel or mathlib.

## Commands and evidence

```powershell
python -B scripts/rds_cli.py --root . formal rules
python -B scripts/rds_cli.py --root . formal verify --spec examples/formal/theorem_module.json --output proof.json
python -B scripts/rds_cli.py --root . formal check --spec examples/formal/theorem_module.json --certificate proof.json
python -B scripts/rds_cli.py --root . formal verify --spec examples/formal/spectral_radius.json --tactics spectral_radius
```

These commands need no initialized research contract. Exit codes are 0 for PASS,
1 for checked FAIL and 2 for UNKNOWN. `check` accepts a certificate or a complete
result containing it, ignores the result's reported verdict and reconstructs the
mathematical conclusion. A valid FAIL certificate still exits 1.

`verify` and `check_certificate` are distinct Python APIs in `rds_verify.py`.
Checkers do not call generators or symbolic search. Original declarations and
checker sources are bound by hashes, which identify artifacts rather than prove
their meaning. The checker must replay the actual domain proof.

The assurance levels distinguish these activities:

| Assurance | Scope |
| --- | --- |
| `CERTIFICATE_CHECKED` | Bounded exact mathematical certificate replay in Python |
| `LEAN_KERNEL_CHECKED` | Native Lean check of a supported generated closed obligation, with audited axioms |
| `SYMBOLIC_CHECKED` | Legacy scalar SymPy result, without an independent certificate |
| `EXACT_OBSERVATION_CHECKED` | Values actually computed by the scalar rational reference runner |
| `HEURISTIC_ONLY` | Advisor signals, paper excerpts and candidate rules |
| `NONE` | No checked proof or counterexample |

## Supported proof obligations

All declarations use `schema: 1`. Exact rational values use strings such as
`"1/2"` or `"0.125"`; the latter denotes an exact decimal. Numeric JSON floats
are rejected. No stochastic training or IEEE rounding semantics are implied.

| Kind | Trusted rule | Mathematical statement |
| --- | --- | --- |
| `scalar_threshold` | `scalar.threshold_separation` | Control stays strictly below a threshold on a closed interval, and treatment crosses at some exact point |
| `lean_obligation` | `lean.rational_relation` | Native Lean proof of a closed rational `eq`, `lt` or `le` proposition |
| `affine_contraction` | `matrix.infinity_contraction` | The declared affine map has induced infinity norm strictly below its threshold |
| `affine_fixed_point` | `matrix.fixed_point` | The declared point satisfies `A p + b = p` |
| `affine_dynamics` | `dynamics.affine` | Both preceding obligations |
| `matrix_spectral_bound` | `matrix.gershgorin` | A sufficient exact bound proves `rho(A) < threshold`; a large sufficient bound is UNKNOWN |
| `matrix_spectral_exact` | `matrix.spectral_radius` | Exact triangular spectrum proves or refutes `rho(A) < threshold`; other matrices are UNKNOWN |
| `scale_equivariance` | `network.positive_homogeneity` | For a declared positive scale, `F(s*x)=s*F(x)` for every real vector, for zero-bias Linear/ReLU models; scale 1 is an identity |
| `network_bounds` | `network.interval_bounds` | Every output is inside its declared bounds for every input in the declared box |
| `network_margin` | `network.interval_margin` | Target output exceeds every other output by at least the declared margin throughout the input box |
| `tensor_identity` | `tensor.exact_identity` | Two concrete exact tensor computations have the same shape and values |
| `tensor_bounds` | `tensor.exact_bounds` | All values of a concrete tensor computation lie within closed bounds |

Examples are in `examples/formal/`. Affine specs have `model.matrix` and
`model.bias`, plus `threshold` and/or `point` for the selected kind. Spectral
specs have `matrix` and a positive `threshold`. A spectral radius below 1 does
not prove a one-step spectral-norm or infinity-norm contraction. In particular,
`[[1/2,100],[0,1/2]]` is spectrally stable while its infinity norm exceeds 1.

Network specs have `model.input_dim`, ordered `linear`/`relu` layers and
`input_box`. Linear layers declare `weight` and `bias`. Bounds use
`output_bounds`; margins use `target` and nonnegative `margin`. Interval
enclosures can lose variable correlations. An enclosure outside a bound is
UNKNOWN unless an actual in-box point independently violates the property.
The candidate search is bounded, and FAIL contains an exact forward trace.

Tensor expressions use `literal` (row-major `shape` and flat `values`), `add`
(`left`, `right`), `scale` (`factor`, `arg`), `transpose` (`axes`, `arg`), and
`matmul` (`left`, `right`). Matmul supports rank 2 and equal batches at ranks 3–4,
without broadcasting. Identity uses `left`/`right`; bounds use `expr`, `lower`
and `upper`. Shape mismatch is UNKNOWN. Concrete evaluation is not a universal
symbolic tensor identity theorem.

## Named declarations and rule composition

```json
{
  "schema": 1,
  "kind": "theorem_module",
  "definitions": {
    "map": {"matrix": [["1/2"]], "bias": ["1/2"]}
  },
  "theorems": [
    {"name": "stable", "statement": {"schema": 1, "kind": "affine_contraction", "model": {"$ref": "map"}, "threshold": "1"}, "by": {"rule": "matrix.infinity_contraction"}},
    {"name": "fixed", "statement": {"schema": 1, "kind": "affine_fixed_point", "model": {"$ref": "map"}, "point": ["1"]}, "by": {"rule": "matrix.fixed_point"}},
    {"name": "joint", "statement": {"kind": "all", "of": ["stable", "fixed"]}, "by": {"rule": "logic.and_intro", "premises": ["stable", "fixed"]}}
  ]
}
```

Definitions and theorem premises may have forward references. Cycles, missing
names, duplicate names, mismatched proof rules, empty conjunctions and extra
axiom fields are rejected. A conjunction's premises must match its statement.
The module is PASS when all obligations are proved, FAIL when all are decided
and at least one is refuted, and UNKNOWN when any obligation remains undecided.
Unknown modules expose partial statuses but no complete module certificate.

`RuleRegistry` is a trusted application whitelist. Extending it means adding a
domain generator and an independent checker in reviewed Python source. JSON
cannot register code, shell commands, causal assertions or user-written axioms.

`LeanFormalEngine` accepts finite chains of `rule`, `gershgorin`,
`spectral_radius`, `scale_invariance`, `lean4` and `interval`. Each tactic only
handles its compatible statement kinds. The scaling tactic proves the stated
equivariance equation, not scale-invariant losses. Incompatible or unavailable
tactics are UNKNOWN. Duplicate chains are rejected, and two names selecting the
same generator cannot cause repeated search. Explicit CLI `--tactics` bypasses
the default disk cache so the requested tactic's scope is respected.

## Link mathematical side conditions to research plans

A hypothesis can declare:

```json
{"formal": {"kind": "declarative", "statement": {"schema": 1, "kind": "affine_fixed_point", "model": {"matrix": [["1/2"]], "bias": ["1/2"]}, "point": ["1"]}}}
```

Admission checks the statement before reserving compute, then atomically
rechecks source, hypothesis, engine, dataset and budget bindings. Execution
independently replays the committed proof. An invalid proof cannot obtain a
reservation. Receipts label this `declared_side_condition_only` and assessments
record `formal_status`; `manipulation` is `NOT_APPLICABLE` and mechanism is
`NOT_TESTED`. A matrix or network JSON object has no automatic equivalence to
the scalar runner or an arbitrary training graph. That mapping needs a separate
checked export/semantics argument.

## Performance and resource limits

`.rds/proofs.sqlite3` is a rebuildable WAL cache separate from the research budget
ledger. It stores checked certificates, keyed by the full declaration and
verifier implementation. Every hit is independently checked after its read
connection closes. Generation never owns a SQLite transaction. Existing WAL
caches initialize through read-only queries; misses use short writes with a
50 ms busy limit, and cache unavailability does not change a mathematical result.
UNKNOWN is never cached as a proof.

Advisor excerpts use a separate `.rds/advisor.sqlite3` WAL store. Parsing happens
before a short batch transaction. Concurrent imports preserve updates and
deduplicate entries. Legacy JSON migration occurs once during explicit import
and preserves the original file. Recommendation reads do not acquire a writer
lock and fall back after a short busy timeout. Writes can wait for another writer;
SQLite is not a lock-free database.

`benchmark/formal_performance.py` measures generation, independent checking,
database reads/writes and reads during an active writer separately. Samples and
medians describe one machine, exclude CLI startup and are not worst-case latency
guarantees. Small exact proofs can cost less to regenerate than a disk-cache hit.
No GPU savings are inferred.

Limits are 2 MiB per generic declaration/certificate, 64 theorem declarations,
bounded depth/node expansion and 4096-bit exact arithmetic. Matrix dimensions
and network layer widths are at most 64; networks have at most 32 layers and
16,384 parameters. Tensor rank is at most 4, with 128 nodes and 4096 cumulative
trace cells. Domain operation budgets reject explosive arithmetic before work.
The legacy scalar AST and certificate limits remain smaller. Exceeding any limit
does not refute the mathematical claim.

## Lean4, mathlib and model-export interoperability

The native Lean interface generates supported closed proof obligations and
checks them with an explicitly configured existing Lean4 executable. It audits
the generated theorem's axioms, binds the source and original statement, and
replays native checking instead of trusting cached stdout or an exit code alone.
It neither downloads a toolchain nor accepts arbitrary Lean text as a proof of
a JSON model. Broader mathlib lemmas and symbolically quantified network/model
translation need dedicated adapters and tests; Python certificates do not
automatically become Lean proofs.

Set `RDS_LEAN_EXECUTABLE` to an absolute path to an existing native Lean4
toolchain binary, then use `formal verify --spec examples/formal/lean_obligation.json
--tactics lean4`. The spec contains `relation` (`eq`, `lt`, `le`) and rational
`left`/`right` values. The adapter uses only a fixed, validated Lean source
template with `by decide`, checks with `--trust=0`, and accepts only an empty
axiom audit for the generated named theorem. Failure, missing configuration or
a 3-second process budget yields UNKNOWN, not scientific refutation. Cache
replay invokes Lean again outside the database connection. This small native
subtask receives `LEAN_KERNEL_CHECKED`; a mixed Python theorem module retains
`CERTIFICATE_CHECKED`, since its whole composition was not proved in Lean.

`export_sequential(model)` is an optional PyTorch adapter for an existing
eval-mode `Sequential` containing exact `Linear`/`ReLU` classes. It snapshots
stored finite floats as exact binary rational values, rejects altered modules,
hooks and unsupported layers, and never loads checkpoints or executes forward.
Pure guard tests run without PyTorch. Actual PyTorch tests are skipped when the
optional dependency is absent. A real-number parameter model does not prove the
floating-point runtime's behavior.

Current preparation references are [Lean proof validation and axiom auditing](https://lean-lang.org/doc/reference/latest/ValidatingProofs/),
[mathlib](https://github.com/leanprover-community/mathlib4),
[Vehicle's specification/verification workflow](https://github.com/vehicle-lang/vehicle),
[ONNX consistency checks](https://onnx.ai/onnx/api/checker.html), and
[alpha-beta-CROWN](https://github.com/Verified-Intelligence/alpha-beta-CROWN).
ONNX, Vehicle and CROWN are not integrated RDS backends. Keep empirical research
evidence separate from mathematical model certificates when adding them.

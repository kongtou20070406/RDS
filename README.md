# RDS — automated assistance for human research

Research Direction Selector **5.4.0** is a research skill with an executable local
reference runner, a declarative formal verification framework, an Obelisk history
bridge, and five historical decision packets.

Its purpose is to help humans and AI keep research moving: turn ideas into
testable experiments, retain real evidence, and use it to choose the next step
with less manual upkeep. Formal checks are one part of that research workflow.

- Reuse the installed Obelisk CLI/CodeAct sandbox for history; no separate memory store or vector database.
- Ordinary experiments use lightweight AST checks. Scalar thresholds first use an exact affine-rational certificate generator and a separate checker; other supported expressions fall back to optional SymPy. Explicit declarative statements cover supported affine dynamics; unsupported properties remain `UNKNOWN`.
- Formal statements distinguish threshold separation from threshold necessity. A crossing alone cannot refute an arbitrary proposition or establish a causal mechanism.
- Standalone mathematical declarations cover affine matrix contraction and fixed points, bounded dense Linear/ReLU networks, and concrete multidimensional tensor identities and bounds.
- Named theorem modules reuse declared models and compose checked results with trusted rules. Unknown kinds or rules return `UNKNOWN`; text labels never register executable rules.
- Exact proof objects are independently replayed, including cache hits. Supported closed rational obligations can also be checked by an explicitly configured native Lean4 binary with an empty axiom audit. The SQLite proof cache is separate from experiment contracts and budgets.
- Admission replays checked certificates from matching locked plans. Solver work runs outside the budget write transaction; reservations still recheck bindings, exposure and budget atomically.
- Transactional budgets, data-exposure tracking and hash-bound execution receipts keep task gain, mechanism evidence and run status separate.
- Replay July 8 baseline, Aug 2 compiler ablation, Aug 30 GoPro instruction, Sep 13 C7 boundary and Sep 14 48h allocation decisions.

The kernel executes restricted scalar rational programs with paired MSE. It is
not a PyTorch trainer, a PSNR evaluator, an OS sandbox or a proof of autonomous
research performance. Historical training scores are reported evidence; automated
replays use explicitly synthetic scalar inputs.

## Install and verify

Use Python 3.11 or newer. Ordinary operation needs no third-party Python package.
Obelisk must already be installed for live history retrieval. The declarative
exact backends use the standard library. SymPy is optional for the legacy scalar
fallback; PyYAML is optional for judgment graph parsing. To install these optional
dependencies and run the checks:

```powershell
python -m pip install -r requirements-formal.txt
python -B -m unittest discover -s tests -v
python -B benchmark/run.py
python -B benchmark/performance.py
```

For skill discovery, place this repository's contents in a skill directory named
`research-direction-selector` under your host's skills root. Start with
[SKILL.md](SKILL.md); the agent should retrieve history only when it affects a decision.

## Run the example

```powershell
python -B scripts/rds_cli.py --root examples/reference-run init --contract examples/reference-run/contract.json
python -B scripts/rds_cli.py --root examples/reference-run hypothesis add --spec examples/reference-run/hypothesis.json
python -B scripts/rds_cli.py --root examples/reference-run plan create --spec examples/reference-run/plan.json
python -B scripts/rds_cli.py --root examples/reference-run run execute --id P1
```

Pass the returned `run_id` to `decide --run`, using the same `--root`. The example
is development-only and produces exploratory task evidence. `init` never erases
existing state. Use a fresh copy/root for a new contract.

See [CLI semantics and formal declarations](references/l3-state-machine.md),
[declarative formal checks](references/formal_framework.md),
[Obelisk retrieval](references/obelisk.md), and [benchmark protocol](benchmark/README.md).
Operational `.rds` databases and local query files are excluded from Git.

## Verify a declaration or theorem module

```powershell
python -B scripts/rds_cli.py --root . formal rules
python -B scripts/rds_cli.py --root . formal verify --spec examples/formal/theorem_module.json --output proof.json
python -B scripts/rds_cli.py --root . formal check --spec examples/formal/theorem_module.json --certificate proof.json
```

These commands do not require a research contract. `verify` returns a checked
`PASS`, a checked `FAIL`, or `UNKNOWN`; their exit codes are respectively 0, 1,
and 2. `check` keeps the mathematical verdict: a valid counterexample certificate
still exits 1. `--no-cache` requests fresh generation, and every replay otherwise
checks the complete declaration and engine binding again.

Python callers can import `verify`, `check_certificate`, and `rules` from
[`scripts/rds_verify.py`](scripts/rds_verify.py). The [framework reference](references/formal_framework.md)
defines atomic schemas, named declarations, rule composition, resource limits,
and the boundary between a formal model and a research result.

An optional [`export_sequential(model)`](scripts/rds_model_export.py) adapter exports
an existing eval-mode PyTorch `Sequential` of exact `Linear`/`ReLU` classes into
the network model schema. It captures detached parameter values using exact
binary ratios and never loads a checkpoint or runs `forward`. PyTorch is imported
only on export. It is absent in the current development environment, so actual
PyTorch tests are explicitly skipped; pure encoding and interface guard tests run.
Exported parameters define a real-number model, with a separate claim needed for
IEEE floating-point execution or arbitrary Python behavior.

## Certificate checks and research advice

The exact checker uses Python's `Fraction` and bounded algebra. It verifies the
closed domain, original denominator obligations, the control bound and an exact
treatment witness. In the legacy experiment gate, `CERTIFICATE_CHECKED` describes
this scalar model. Declarative backends check their explicitly stated matrix,
network or tensor models with the same rational arithmetic trust boundary.
Python domain certificates are not Lean proofs and do not establish training
convergence, generalization or floating-point execution correctness.
SymPy-only results remain `SYMBOLIC_CHECKED`.

For a native Lean subtask, set `RDS_LEAN_EXECUTABLE` to an existing toolchain's
native executable, then verify `examples/formal/lean_obligation.json` with
`--tactics lean4`. The adapter generates a closed rational relation, checks it
with `--trust=0`, audits an empty axiom set and replays the source independently.
Only this supported native obligation receives `LEAN_KERNEL_CHECKED`. No
toolchain is downloaded, arbitrary Lean text is not accepted, and broader
mathlib/model translation remains future adapter work. Compilation is measured
separately from millisecond WAL reads.

Declare `formal.statement: "threshold_necessity"` when an executed low-loss
crossing is intended to refute that specific necessity model. Other boundary
declarations default to `threshold_separation` and cannot receive that refutation.
See [formal semantics and trust boundaries](references/l3-state-machine.md).

Advisor diagnoses and rule linting are marked `HEURISTIC_ONLY`. Scalar loss
numbers do not identify the cause of underfitting or overfitting. Automatic repair
reads the current SQLite ledger and returns candidates for review; keyword matches
do not establish precision or authorize automatic rule application.

The performance script reports individual samples and medians on synthetic scalar
programs. It does not estimate GPU savings or autonomous research quality.

For broader backends, current design references include
[Lean proof validation and axiom auditing](https://lean-lang.org/doc/reference/latest/ValidatingProofs/),
[ONNX model consistency checks](https://onnx.ai/onnx/api/checker.html), and the
[alpha-beta-CROWN verifier](https://github.com/Verified-Intelligence/alpha-beta-CROWN).
The Lean adapter currently covers closed rational obligations; general mathlib,
ONNX and CROWN integration remain preparation work.

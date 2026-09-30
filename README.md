# RDS-L3

Research Direction Selector **5.4.0** is a research skill with an executable local
reference kernel, an Obelisk history bridge, and five historical decision packets.

- Reuse the installed Obelisk CLI/CodeAct sandbox for history; no separate memory store or vector database.
- Ordinary experiments use lightweight AST checks. Scalar thresholds first use an exact affine-rational certificate generator and a separate checker; other supported expressions fall back to optional SymPy. Unsupported dynamics fail closed as `UNKNOWN`.
- Formal statements distinguish threshold separation from threshold necessity. A crossing alone cannot refute an arbitrary proposition or establish a causal mechanism.
- Admission replays checked certificates from matching locked plans. Solver work runs outside the budget write transaction; reservations still recheck bindings, exposure and budget atomically.
- Transactional budgets, data-exposure tracking and hash-bound execution receipts keep task gain, mechanism evidence and run status separate.
- Replay July 8 baseline, Aug 2 compiler ablation, Aug 30 GoPro instruction, Sep 13 C7 boundary and Sep 14 48h allocation decisions.

The kernel executes restricted scalar rational programs with paired MSE. It is
not a PyTorch trainer, a PSNR evaluator, an OS sandbox or a proof of autonomous
research performance. Historical training scores are reported evidence; automated
replays use explicitly synthetic scalar inputs.

## Install and verify

Use Python 3.11 or newer. Ordinary operation needs no third-party Python package.
Obelisk must already be installed for live history retrieval. To enable the
formal adapter and run all tests:

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
[Obelisk retrieval](references/obelisk.md), and [benchmark protocol](benchmark/README.md).
Operational `.rds` databases and local query files are excluded from Git.

## Certificate checks and research advice

The exact checker uses Python's `Fraction` and bounded algebra. It verifies the
closed domain, original denominator obligations, the control bound and an exact
treatment witness. `CERTIFICATE_CHECKED` describes this scalar model; it is not a
Lean proof or a theorem about a PyTorch model, training convergence or generalization.
SymPy-only results remain `SYMBOLIC_CHECKED`.

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

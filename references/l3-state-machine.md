# RDS-L3 5.1 executable contract

This release provides a local **scalar reference kernel**, not a general training
scheduler. Python 3.11+ and the standard library suffice for ordinary runs.
Install `requirements-formal.txt` only for declared scalar formal properties.

## Commands and state

`init --contract`, `hypothesis add --spec`, `gate check --plan`, `plan create
--spec`, `plan cancel --id`, `run execute --id`, `run recover --id`, `data expose
--split --purpose --actor --reason`, `decide --run`, and `status` accept the global
`--root` before the command. See [the runnable example](../examples/reference-run/contract.json).

`gate check` is advisory and reserves nothing. `plan create` repeats admission in
an SQLite write transaction and atomically reserves `runtime_ms` and one `run`.
Exploration cannot spend `confirmation_floor`. Cancellation returns an unstarted
reservation. Starting execution charges its entire allocation once, even if it
fails or times out. Duplicate commands do not charge again. A lost worker becomes
`RECOVERY_REQUIRED` after its lease; the tool does not automatically rerun it.

Each allocation is at most 60 seconds. The ledger is conservative allocated
worker runtime, **not** a full GPU campaign wall-clock scheduler; setup, validation
and control-plane overhead are outside it. External long jobs that must survive a
session should use the user's scheduler (Windows Task Scheduler on this host).

`.rds/state.sqlite3` holds only operational contracts, allocations, data exposure,
raw execution artifacts and append-only receipts. It is not a conversational
memory index. History retrieval goes exclusively through Obelisk's public CLI.

## Input and evidence binding

Contracts lock the claim, paired MSE evaluator, positive minimum useful delta,
baseline control AST, split hashes, sample identities, source lineage and budget.
The source language is exactly `control(x)` and `treatment(x)` returning bounded
rational expressions. Calls, imports, decorators and arbitrary Python execution
are rejected. Plans bind source, dataset, hypothesis, contract and verifier hashes.
Changing any binding requires a new plan or contract, as applicable.

Confirmation data must declare `prior_exposure: none_declared`; `unknown` and
`exposed` are ineligible. Same bytes, overlapping sample IDs and shared cohorts
propagate exposure. A final plan freezes selection. Data access is logged before
execution, including failures. Discovered contamination marks existing final
assessments for review. A declaration of no prior exposure is still a custodian's
assertion; the kernel cannot discover unreported off-system access.

`decide` reads an engine-produced receipt. It does not accept external JSON metric
gains, `manipulation_verified`, `falsifier_triggered` or imported permits.
Task gain, mechanism and execution status are separate axes:

| Axis | Interpretation |
|---|---|
| `task_gain` | `EXPLORATORY` on development; `CONFIRMED`/`REFUTED` only for the frozen finite dataset comparison and predeclared gain threshold. Population claims stay exploratory/inconclusive. |
| `mechanism` | Ordinary runs remain `UNTESTED`. Failed separation is `NOT_TESTED`; successful separation alone is `INCONCLUSIVE`, never causal support. An exact executed counterexample can refute only the declared scalar necessity model. |
| `run_status` | `RESERVED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, or `RECOVERY_REQUIRED`; a failed run is not scientific refutation. |

Conflicting scientific assessments are retained as `DISPUTED`. The runner never
infers a research-search policy improvement from one model result.

## Formal routing

Omit `formal` for ordinary runs: admission parses the AST, and execution uses
exact rational arithmetic without importing SymPy. Ordinary numeric parameters
or a target metric do not trigger formal verification.

For a mathematical threshold necessity claim, declare:

```json
{"formal": {"kind": "contraction_boundary", "quantity": "scalar_property",
            "domain": ["0", "100"], "threshold": "1", "max_loss": "1"}}
```

Accepted kinds are `strict_algebraic_threshold`, `contraction_boundary`, and
`dynamics`. `threshold_necessity` is retained as an explicit scalar adapter name.
The scalar adapter means: control stays below the threshold on the closed domain;
treatment can reach or cross it; an executed crossing with both arms' loss at most
`max_loss` is a counterexample to necessity **in this scalar model**. The modeled
quantity must be a measured scalar property, not an undocumented output proxy.

Admission runs the symbolic probe in a subprocess with a 15-second timeout. It
never opens confirmation targets. The runner subsequently checks actual sample
crossings. Original denominator obligations survive symbolic cancellation.
`UNKNOWN` (including an unavailable dependency) and `FAIL` both block admission;
only `PASS` allows the mathematical test. Current dynamics claims return `UNKNOWN`
because no dynamics verifier is implemented. General matrix, ODE, floating-point
and PyTorch properties require a separately implemented, tested adapter.

The agent must classify the hypothesis honestly: prose cannot be reliably parsed
into a mathematical obligation, and omitting a declaration is not proof that none
exists. A verifier pass never establishes causal isolation, population inference
or a general stability theorem.

## Trust boundary

SQLite transactions and hashes prevent routine races, replay and accidental
artifact substitution. A user with write access to the verifier, database and
data can replace all of them; this local kernel is not tamper-proof. For a hostile
proposer, isolate custody and execution outside its writable environment. Ordinary
research does not require claiming this stronger deployment already exists.

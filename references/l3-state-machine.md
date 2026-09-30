# RDS-L3 5.4 executable contract

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
{"formal": {"kind": "contraction_boundary", "statement": "threshold_necessity", "quantity": "scalar_property",
            "domain": ["0", "100"], "threshold": "1", "max_loss": "1"}}
```

Accepted kinds are `strict_algebraic_threshold`, `contraction_boundary`, and
`dynamics`. `threshold_necessity` is retained as an explicit scalar adapter name.
The scalar adapter means: control stays below the threshold on the closed domain;
treatment can reach or cross it; an executed crossing with both arms' loss at most
`max_loss` is a counterexample to necessity **in this scalar model**. The modeled
quantity must be a measured scalar property, not an undocumented output proxy.

Admission performs solver work outside SQLite's write transaction. The short
reservation transaction repeats source, hypothesis, engine, budget and exposure
checks before committing. Admission never opens confirmation targets. The runner
subsequently checks actual sample crossings. Original denominator obligations
survive algebraic cancellation.
`UNKNOWN` (including an unavailable dependency) and `FAIL` both block admission;
only `PASS` allows the mathematical test. Current dynamics claims return `UNKNOWN`
because no dynamics verifier is implemented. General matrix, ODE, floating-point
and PyTorch properties require a separately implemented, tested adapter.

Declare the statement independently of the property's label.
`threshold_separation` (the default for boundary declarations) asks whether both
arms are defined on the closed domain, control is below the threshold everywhere,
and treatment has at least one crossing witness. It does not assert a necessity
theorem. Only `statement: threshold_necessity`, or the legacy explicit
`kind: threshold_necessity`, permits an executed low-loss counterexample to refute
that scalar necessity model. Existing declarations that intended necessity must
add the statement and use a new contract when the engine binding changes.

The dependency-free exact backend generates a certificate for affine-rational
expressions. A separate checker reconstructs the restricted AST's algebra and
checks the source/specification binding, original denominator obligations,
closed-domain control bound and rational treatment witness. Intermediate algebra
is bounded; unsupported cases may use optional SymPy. Assurance labels are:

| Assurance | What was checked |
|---|---|
| `AST_ONLY` | Restricted syntax; no declared mathematical property. |
| `CERTIFICATE_CHECKED` | Exact scalar obligations replayed by the Python certificate checker. |
| `SYMBOLIC_CHECKED` | Optional SymPy result without an independent certificate. |
| `EXACT_OBSERVATION_CHECKED` | An executed scalar crossing check, separate from the admission certificate. |
| `NONE` | No mathematical assurance; unsupported or unknown. |

Matching locked plans can supply certificates for repeated admission. Source,
hypothesis and engine hashes must match, and the checker replays the certificate.
Execution also rechecks the bound admission certificate, saving a second solve;
uncertified fallback results require fresh verification. This cache changes
neither the declared budget nor data-exposure rules.

An admitted crossing witness can exist even when the chosen samples never cross.
Execution therefore retains `admission_status` and `admission_assurance`, and
reports `observed_status` and `execution_assurance` separately. The combined
legacy `probe.status` is `FAIL` for a missed executed crossing; its observation
assurance does not change a valid admission certificate into a failure proof.

This checker is ordinary reviewed Python code, not a machine-proved Lean kernel.
Borrowing Lean's separation of proof search and checking does not make it a Lean
proof. A future Lean adapter must bind the exact trusted theorem statement, audit
axiom dependencies and recheck proof objects; see the
[official proof validation guidance](https://lean-lang.org/doc/reference/latest/ValidatingProofs/).
For actual neural-network specifications, evaluate adapters to existing tools such
as [Vehicle](https://github.com/vehicle-lang/vehicle) and
[alpha-beta-CROWN](https://github.com/Verified-Intelligence/alpha-beta-CROWN).
Their results need explicit model/export/numerical semantics and evidence labels.

The agent must classify the hypothesis honestly: prose cannot be reliably parsed
into a mathematical obligation, and omitting a declaration is not proof that none
exists. A verifier pass never establishes causal isolation, population inference
or a general stability theorem.

## Trust boundary

Advisor diagnostics are hypotheses (`HEURISTIC_ONLY`), not deductions about a
training run's cause. Loss summaries and keyword-based rule linting do not establish
empirical precision, false-positive rates or causal alignment. Automatic repair
reads `.rds/state.sqlite3` and produces candidates for review; it cannot promote
keyword matches into automatically applied scientific rules.

`status` and advisor reads use read-only SQLite snapshots. They do not reserve
budget, rewrite state or take the reservation write lock.

SQLite transactions and hashes prevent routine races, replay and accidental
artifact substitution. A user with write access to the verifier, database and
data can replace all of them; this local kernel is not tamper-proof. For a hostile
proposer, isolate custody and execution outside its writable environment. Ordinary
research does not require claiming this stronger deployment already exists.

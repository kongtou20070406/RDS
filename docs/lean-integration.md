# Lean4 integration: a deep-learning research extension

[简体中文](lean-integration.zh-CN.md) · [Formal verification](formal-verification.md) · [Rule obligations](rule-obligations.md)

RDS primarily automates assistance to human research: investigate evidence, propose and select experiments, arrange execution, assess results, and resume after reflection. Lean4 compatibility supports suitable mathematical subproblems within that loop. The current narrow adapter uses Lean's Rat definitions; wider integration should reuse Lean4 and [mathlib](https://github.com/leanprover-community/mathlib4), while RDS supplies model/property adapters, experiment obligations and evidence bindings. RDS should not recreate Lean's logic or treat a Python method named `linarith` as Lean's arithmetic tactic.

This page separates the implemented narrow interface from the broader integration design. Current `main` includes the native closed-rational adapter introduced by [PR #2](https://github.com/kongtou20070406/research-direction-selector/pull/2) at `995e8eb`. The older `f020b2c` base did not contain this adapter; broader model/mathlib integration remains future work.

## Implemented closed-rational interface

`kind: lean_obligation` is registered as `lean.rational_relation` in `scripts/rds_verify.py` and is reachable through the `formal` CLI using `rule` or `lean4`. It accepts exactly `schema`, `kind`, `relation`, `left` and `right`: schema 1, a closed rational `eq`, `lt` or `le` proposition, and exact rational literals rather than JSON floats. The existing example is:

```json
{"schema":1,"kind":"lean_obligation","relation":"lt","left":"1/2","right":"3/4"}
```

Use current `main` or v5.5.0-rc.2. Replace the path below with an existing absolute native Lean4 toolchain binary. The adapter does not download a toolchain and rejects elan and `.elan/bin` shims.

```powershell
$env:RDS_LEAN_EXECUTABLE = 'C:\path\to\native-toolchain\bin\lean.exe'
python -B scripts/rds_cli.py --root . formal verify --spec examples/formal/lean_obligation.json --output lean-proof.json --tactics lean4
python -B scripts/rds_cli.py --root . formal check --spec examples/formal/lean_obligation.json --certificate lean-proof.json
```

The fixed template uses Lean's Rat definitions and `by decide` for `RDS.obligation`. The adapter invokes Lean with `--trust=0` and requires the exact empty-axiom audit. Independent checking re-renders the expected template, checks statement/source bindings, executable fingerprint and version, and calls Lean again. It does not replay a saved `.olean` proof object or accept cached stdout as proof.

An accepted atomic result is PASS / `LEAN_KERNEL_CHECKED`, with `backend: lean4_closed_rational` and `semantics: closed_Lean_Rat_relation`. False propositions, missing tools, compilation failure and resource limits currently produce UNKNOWN / `NONE`, not checked refutations. CLI exit codes are 0/1/2 for PASS/FAIL/UNKNOWN; this native adapter does not currently produce FAIL. A finite theorem module containing native leaves still has outer `CERTIFICATE_CHECKED`.

`formal check` accepts a framework certificate or a complete framework result and reconstructs its conclusion. The lower-level native checker accepts its domain certificate and repeats the native check. These formats are distinct. Arbitrary Lean text, user tactics, general mathlib translation and proofs of an executed training graph remain unsupported; the mathematical side condition does not establish utility or causality. See [all registered kinds and evidence boundaries](formal-verification.md) and the [versioned implementation contract](https://github.com/kongtou20070406/research-direction-selector/blob/995e8eb98f75697ef1ce43a9991f0686e5c29caa/references/formal_framework.md).

## Division of responsibility

The broader integration design assigns the responsibilities below. The current closed-rational adapter does not implement general model translation or the full future proof-request contract.

| Component | Responsibility |
| --- | --- |
| Lean4 / mathlib | Express the mathematical proposition, use established definitions and lemmas, generate proof terms and check them with the actual Lean kernel. |
| RDS model adapter | Translate only supported operators into an explicit mathematical model; bind parameters, shapes, domain and numerical semantics. Refuse unsupported operators. |
| RDS obligation adapter | Map a scoped rule's algebraic subclaim to an exact expected theorem. Preserve its assumptions and quantifiers. |
| Proof bridge | Pin toolchain and library revisions, identify the expected theorem, collect proof artifacts, audit axioms and recheck the result. |
| Experiment runner | Check authorization, budget, data exposure and actual execution; produce independent receipts and observations. |
| Research assessment | Interpret measured task gain, intervention validity and mechanism evidence. Empirical observations do not become axioms proving future performance. |

The 23 methodology rules are an obligation catalog. Their provenance, fair-comparison and empirical conditions cannot all be discharged by a mathematical theorem. Start with local algebraic obligations such as the reachable mass formula, parameter bounds and precisely specified finite linear maps; keep measured resource fit and causal attribution in their respective evidence channels.

## Proposed proof-request contract

The bridge needs a versioned request containing: the rule ID; trusted expected theorem and referenced definitions; complete model/specification digests; assumptions, quantifiers and domain; numerical semantics; Lean/toolchain/mathlib revisions; and the requested checking policy. These are design requirements, not currently accepted universal `hypothesis.formal` fields.

Proof evidence should identify the checked theorem, module, proof/declaration artifacts, axiom dependencies and checker versions. Cache keys must bind the full request and checker dependencies. An old proof cannot cover changed weights, operators, assumptions or versions just because its informal label stayed the same.

Actual checkpoint weights can be represented as exact rationals in a real-valued model. A mathematical proof then concerns that declared abstraction; representation alone is not proof. Floating-point inference, autograd, training updates and export equivalence require additional explicit semantics and evidence; they are not implied by that abstraction.

## Acceptance conditions for broader integration

1. Construct the expected theorem independently of the candidate proof, with audited definitions and model bindings.
2. Build in the pinned Lean project and identify the declaration being checked. A successful unrelated file is insufficient.
3. Inspect the theorem's axiom dependencies. Reject unfinished proofs using `sorryAx` and any unapproved axioms; an empirical premise requires its own evidence and cannot be silently asserted.
4. Recheck the stored declarations with the appropriate Lean checker. Use trusted-statement comparison and external checking when the deployment requires it.
5. Return the scoped mathematical result separately from the runner and scientific assessment.

Lean documents axiom inspection, `lean4checker --fresh` and trusted-statement comparison in its [proof validation guidance](https://lean-lang.org/doc/reference/latest/ValidatingProofs/). Projects should pin matching [Lake](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/) and mathlib dependencies rather than track moving branches during an experiment.

A failed proof search or compilation means no accepted proof was obtained; it does not prove the proposition false. A negative mathematical result needs a checked counterexample or a proof of the relevant negation. Resource limits and unsupported models remain inconclusive. The historical, separate local prototype's `LEAN_TACTIC_PROVED` and `LEAN4_CERTIFIED` labels did not satisfy these conditions; they are not the current native adapter's assurances.

## Migration sequence

Retain the existing CLI for scalar experiment accounting and the implemented closed-rational bridge. Next add source-bound algebraic or model obligations using existing mathlib definitions, with valid, false, unrelated-theorem, unfinished-proof, changed-source and missing-toolchain cases. Validate export correspondence separately. Extend admission only after each new adapter's bindings and checking conditions pass; the current declarative path admits mathematical side conditions, not automatic training-graph equivalence.

Prefer Lean's existing prover and checker. C++ can serve measured parsing, serialization or numerical-adapter bottlenecks later; it is not a reason to build another theorem prover. Proof-checking latency, cache latency and SQLite transaction time should be measured separately, with reproducible inputs and percentile distributions. No GPU speedup or millisecond-wide system guarantee follows from choosing C++.

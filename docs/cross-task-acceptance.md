# Cross-task acceptance for RDS 5.8

RDS is a general-purpose research direction selector. This refines the existing [V1–V6 plan](5.8-vision.md#focused-work-packages-and-acceptance)
and [issue #22](https://github.com/kongtou20070406/research-direction-selector/issues/22).
It is an implementation and review plan, not a claim that the checks below are
already enforced. Initial priority is deep learning, software/tool development,
then mathematics. They provide the first acceptance coverage, not a restriction
to three domains. Other fields can use the same core with applicable optional
adapters and declared acceptance predicates.

This repository-wide boundary also applies to optional tools and examples: do
not ship project-specific solutions, recipes or policies. Retain reusable
parameterized methods and minimal public/synthetic failure cases. Existing
project-specific executable material should be removed from shipped tool paths
or replaced by such a reproducer; keep the original evidence privately.

## What the initial settings test together

| Shared requirement | Deep-learning example | Software/tool example | Mathematics example |
| --- | --- | --- | --- |
| Original-goal progress | Training runs but the required quality curve still fails. | Tests pass but the advertised CLI never reaches its consumer. | A covering upper bound leaves global optimality open. |
| Applicable checks | An inactive loss has a finite zero derivative; connectivity needs a controlled probe. | A missing optional backend differs from malformed input or a software failure. | An inconclusive interval box is unresolved, not a counterexample. |
| Valid transfer | Different evaluation shapes require checking the declared geometry and metric protocol. | A faster kernel must preserve callers, witnesses and recovery semantics. | A changed problem size requires reinstantiating the theorem's premises. |
| Useful next decision | Compare interventions with different predictions, preserving failed recipes. | Repair the demonstrated boundary before adding another abstraction. | Identify a missing reduction or stronger bound instead of renaming an open branch. |
| Recovery and cost | Reconcile the original remote launch and committed checkpoint after interruption. | A charged interrupted attempt must not trigger another launch or refund. | Retain the unresolved frontier and consumed search allowance. |
| Proportionate evidence | Reuse unchanged metric/calibration evidence without rerunning training. | Reuse per-operation graph/hash work and measure complete-entry latency. | Reuse a bound certificate without reprinting its entire proof tree. |

The examples describe failure patterns rather than assigning every historical
failure to RDS. Check raw evidence and the exact installed revision first. For
example, source-inventory identity and manual-cost merging already have repairs
in #30 and #11. A project-specific checker or GPU script needs its own reproducer;
an error reported through RDS is not automatically an RDS implementation defect.

## Implementation order and observable acceptance

### 1. Repetition and ownership — V2/V4

Finish the frozen opt-in execution policy in the current SQLite transactions.
Test refused duplicate registration before charge, concurrent callers, renamed
requests, changed bound inputs, successful-result reuse, corrupted receipts,
missing children after charge and stale/copied child identities. A valid new
comparison or authorized replication must have an explicit route through the
contract. Exact identity checks do not establish semantic equivalence between
arbitrary algorithms.

### 2. Gate evidence and useful diagnostics — V1/V3/V5

Keep operational validity, scientific qualification, capacity and final-goal
acceptance distinct in the existing protocol, facts and receipt fields. Each
configured gate needs a source, applicable domain, evidence and a consumer. A
failure must name the actual field or check, expected condition, observed value
and relevant artifact. Missing measurements stay unknown.

For neural-network adapters, test live-but-inactive, disconnected, cancellation,
nonfinite and shape-mismatch cases with small controlled inputs. A zero gradient
alone proves neither correct wiring nor disconnection; a local response gain
alone does not establish final quality. For theory adapters, include unresolved,
refuted and verified obligations under stated premises. For developer adapters,
include invalid input, unavailable dependencies and actual implementation faults.

Keep resource authorization hard. Record an administrative mismatch separately
from a mathematical or empirical verdict; investigate its provenance rather
than rewriting a failure as success. A conditional theorem remains conditional
when its implementation or application premises are unverified.

### 3. Outcomes that change selection — V1/V2/V3

Consume a project's declared vector of outcomes, units, direction, uncertainty,
comparison identity and acceptance predicates. This can describe quality versus
inference work, proof obligations versus remaining domain, or correctness versus
latency/context cost. Do not prescribe PSNR, a fixed step grid, a universal
monotonicity threshold or a single aggregate score.

Tests should distinguish an improving primary metric with a failed protected
condition, a plateau, incompatible comparisons and missing measurements. Advisor
must retain those distinctions in the next action. A stalled route should name
the unresolved assumption and a different prediction or proof obligation, then
compare the proposed check with the smallest repair. Do not automatically change
loss weights, adopt an architecture or consume another experiment allowance.

### 4. Transfer and continuation — V3/V4/V5

Use explicit adapter inputs for domain parameters, shapes, backend/interpreter
and resource limits. Validate them before expensive dispatch. A compatible
dynamic shape is not a failure merely because a previous input had a different
tile count; a changed scientific evaluation protocol still needs a new binding.

Extend existing runner/adapter ownership rather than creating a second daemon.
Test stale process IDs, interrupted transport, a live owned job, a completed job
whose collection failed, and an atomic committed checkpoint with a partial next
write. Report unsupported remote reconciliation as unresolved, with no duplicate
launch or claim that a process has stopped. Stop only an identified owned job
under the bound policy. Estimated charges, reservations, wall time and measured
device time remain distinct; a missing measurement is not zero.

### 5. Performance and feedback — V5/V6

Profile complete user entries before further acceleration: cold CLI startup,
source read/hash reuse, graph/blocker analysis, candidate review, serialization
and necessary verification. Keep raw parity checks and matched before/after
samples. The Python optimization in #32 is the new comparison baseline; native
speedups must include loading, conversion and caller overhead on matched inputs.

Use brief output and load only decision-relevant records. The private handoff
workflow in #33 should retain minimal reproducible failures, original decisions,
bound versions and omissions. Compact history summaries are not complete replay
packages. Read examples are development evidence, not untouched confirmation.

## Delivery boundary

Each implementation PR should identify the shared mechanism it repairs and test
applicable cases from the three columns, including a changed-condition case.
Use public or clearly labelled synthetic fixtures; keep private archives and
machine identifiers out of the repository. No fixed round count proves that a
research method cannot work, and no general-purpose pruning theorem or arbitrary
algebraic recovery guarantee is part of these software changes. Scientific
algorithm improvements need their own scoped evidence and review.

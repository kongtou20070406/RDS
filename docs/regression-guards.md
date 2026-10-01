# Explicit regression guards

Exploration can fail. Preserve the failed or weaker result and gate its promotion rather than hiding the observation or claiming every exploration step must improve. These checks do not publish a model, mutate an incumbent, change authorization or establish scientific-policy gain.

## Comparable observations

`guard --policy guard.json --json` compares named observations. `exec --guard guard.json --output outputs/candidate.json -t 10 probe.py` freezes the policy and baseline dependencies with the command, retains the original execution receipt and appends the review in existing events/checkpoints. The policy's wall cap is reserved inside the exec allowance; it reduces the child's runtime cap. Background exec remains the existing runner and needs a separate review after completion.

Minimal policy:

```json
{
  "schema": 1,
  "wall_seconds": 2,
  "comparison": {
    "question_id": "fixed-task",
    "goal_revision": "v1",
    "scope": {"domain": "declared"},
    "metric_definition": "fixed-score-definition",
    "unit": "ratio",
    "cohort": "fixed-cohort",
    "protocol": "fixed-protocol"
  },
  "metrics": [{
    "name": "score", "direction": "max", "pointer": "/score",
    "baseline": {"path": "baseline.json", "sha256": "<actual SHA-256>"},
    "candidate": "outputs/candidate.json"
  }]
}
```

Both observations need `status: "PASS"`, the exact same `comparison` object and the named field. Explicit withdrawal, changed protocol/scope, missing fields or unsupported numbers return UNKNOWN. Integer, rational and decimal spellings are compared exactly; this is a comparison of recorded values, not a proof that the measurements are correct. `max` requires candidate ≥ baseline; `min` reverses it. Multiple declared checks must all pass. CLI exits 0/1/2 for PASS/FAIL/UNKNOWN. The original child may still have `run_status: "SUCCEEDED"` when its review fails.

Inputs are bounded to 2 MiB each, with 1–32 checks and a shared review cap ≤60 seconds. Policy-relative baseline/spec/certificate references stay inside the source root and carry their original hashes. Candidate paths are job-relative declared outputs. Frozen requests and stored review hashes prevent a changed input or modified CAS report from reusing a previous PASS. The trusted local runner is not an OS sandbox.

## Frozen milestones

The optional `milestones` list uses:

```json
{
  "id": "previous-obligation",
  "spec": {"path": "spec.json", "sha256": "<actual SHA-256>"},
  "certificate": {"path": "certificate.json", "sha256": "<actual SHA-256>"},
  "expected": {"status": "PASS", "backend": "rds_python_closed_rational", "assurance": "CERTIFICATE_CHECKED"}
}
```

The existing bounded independent checker replays the supplied certificate without regeneration. Backend and assurance must match exactly; Python rational checking cannot stand in for a frozen native Lean expectation. A certificate may prove a conditional theorem whose empirical application premises remain unknown. Replay is software/proof compatibility evidence, not independent confirmation of research-policy improvement.

## Declared negative intervals

`reject --evidence witness.json --reason "why this scoped route fails" --domain domain.json` reuses the current recorded question, revision, scope and action. Example domain:

```json
{"parameters": {"c": {"min": "1/5", "max": "22/100"}}, "justification": "Explain the independently justified reason this witness applies throughout the interval."}
```

Use 1–8 explicit `min`, `max` or exclusive `eq` predicates. The original point must belong to the declared domain. Advisor only suppresses another point when the question/revision/scope, relevant facts and predicates, action family and all undeclared parameters are unchanged; it rereads the witness CAS hash. Changed evidence reopens review. Missing/non-point parameters have no exclusion authority. A single point counterexample does not establish an interval: no range is inferred automatically, and this remains `RECORDED_INPUT_NOT_SCIENTIFIC_VERIFICATION`.

Python callers use `record_falsification(..., domain=...)` through the same gates. There is no second ledger or autonomous rule adoption.

Design sources and the separation between implementation, hypothesis and unmeasured gain are in the [dated prior-art review](guardrails-prior-art-20261001.md).

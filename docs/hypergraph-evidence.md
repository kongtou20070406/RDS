# Receipt-bound evidence and OR-surviving retraction

The dependency map reports labels; it was never a proof kernel
(`INPUT_REPORTED_DEPENDENCY_ANALYSIS_NOT_PROOF`). Two upgrades make its
labels worth consuming while keeping that honesty: evidence bindings that
tie SUPPORTED claims to executed runs, and retraction semantics that
recompute closure so healthy OR alternatives survive.

## Evidence bindings: `SUPPORTED` with a receipt

Any node or hyperedge may declare an evidence binding naming one receipt in
a frozen, append-only project ledger (`.rds/project.sqlite3`):

```json
{"id": "B", "status": "SUPPORTED", "source": "paper, p.7",
 "evidence": {"receipt": {"project_root": "C:/proj", "sha256": "<receipt sha256>"}}}
```

`rds_cli.py hypergraph --input map.json --audit-receipts` grounds the
binding: the named ledger must contain a receipt with that sha256 whose
`run_status` is `SUCCEEDED` (read-only; append-only triggers are never
touched). Outcomes per binding land in `receipt_audit.audits`:
`GROUNDED`, `RECEIPT_NOT_FOUND`, `RECEIPT_NOT_SUCCEEDED`,
`RECEIPT_BODY_INVALID` (the stored body does not decode to a JSON object,
or fails the ledger's own receipt check: a repeated key, another run, a
sha256 that does not match the row or the recomputed digest, or a value with
no canonical encoding; `reason` names the type or the failure),
`RECEIPT_AMBIGUOUS` (more than one stored receipt
carries the sha256), or `LEDGER_UNAVAILABLE`.

- **Fail-closed in both modes**: declaring a binding never promotes the
  record. Without the audit (or when grounding fails) the record stays out
  of the closure and is listed in `receipt_blocked_node_ids` — a SUPPORTED
  label with an unverified receipt behaves like an UNKNOWN premise, never
  like silent trust.
- **Blocked records surface repair**: a blocked premise node degrades to a
  direct-evidence obligation (`node:<id>`); a blocked SUPPORTED rule
  surfaces a `RECEIPT_REVALIDATION` ready obligation for the rule, so the
  map still names the next action instead of going dark.
- A succeeded run is not a statement proof; the audit upgrades the
  receipt's existence, not the claim's truth.

## Retraction: one derivation dies, its OR alternatives live

Retraction is expressed by editing the record's status in the input map
(CONTRADICTED, or UNKNOWN for evidence loss) and re-running analysis. The
closure recomputes from scratch, so a conclusion keeps support whenever any
grounded route remains; only conclusions whose every route lost support are
retracted. Aggregate failure never names a guilty premise, and receipt
blockades compose with this: a receipt-blocked premise retracts downstream
derivations exactly as a status flip does.

## Bounds and truncation

Existing limits are unchanged (`DEFAULT_LIMITS`), and blocker-set
incompleteness still means `UNRESOLVED`, never impossibility. Receipt
audits are read-only and bounded by the ledger they name.

## Verification

`tests/test_hypergraph_evidence.py` drives the analyzer and the real CLI:
grounded binding keeps closure and reports `GROUNDED`; missing receipt
downgrades the node while a healthy OR route keeps downstream goals
DECLARED_SUPPORTED; with the sole route retracted the map reports the
repair atom (`node:B`) as the ready obligation; a FAILED receipt never
grounds; a blocked SUPPORTED rule surfaces `RECEIPT_REVALIDATION`; malformed
bindings are rejected; and declaring without auditing is fail-closed.

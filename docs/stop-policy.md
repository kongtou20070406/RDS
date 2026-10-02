# Configured stop policy and maintenance allowance

The project runner stops a hung experiment in two configured ways instead of
letting a bounded reservation burn the whole campaign. Both are frozen into the
contract at `initialize()` time; neither can be added, changed or removed
afterwards. No configured policy means the previous behavior is unchanged: the
per-attempt `timeout_seconds` and the budget vector remain the only bounds.

## Contract fields

```json
{
  "stop_policy": {
    "schema": 1,
    "wall_seconds": 3600,
    "progress": {"window_seconds": 900, "min_bytes": 1}
  },
  "maintenance_allowance": {
    "schema": 1,
    "wall_seconds": 120,
    "max_uses": 4
  }
}
```

- `stop_policy.wall_seconds` is a campaign deadline measured from the start of
  the current attempt (`CAMPAIGN_DEADLINE`). It is distinct from the manifest's
  per-attempt `timeout_seconds` and from the budget vector: it bounds wall time
  even while budget remains.
- `stop_policy.progress` is a growth watchdog over the two byte streams the
  controller actually owns, `stdout.bin` and `stderr.bin` in the run's artifact
  directory. If the combined stream size grows by less than `min_bytes` over
  the trailing `window_seconds`, the controller stops the process
  (`PROGRESS_NO_GROWTH`). Both streams are hashed into the receipt as
  artifacts, so the watchdog watches exactly what the evidence trail retains.

## What a stop does and does not claim

A policy stop records `stop_reason` on the receipt and the error list
(`Stop policy: <REASON>`), preserves partial `stdout.bin`/`stderr.bin`, marks
the run `FAILED`, and settles measured wall time against the budget. It does
not claim the experiment is scientifically impossible, does not write any
output path, and does not infer a task or mechanism gain; `assessment` stays
`UNKNOWN`. A stopped run is terminal: `execute` refuses a second dispatch and
`recover` returns the recorded receipt.

The watchdog only claims what it polls. It cannot see progress in a file, a
database or a network stream; that silence is a documented limit, not proof of
a stalled program.

## Maintenance allowance

A contract with `maintenance_allowance` may admit runs whose manifest carries a
`maintenance` declaration:

```json
{
  "reason": "MAINTENANCE",
  "blocker": "config reader rejects empty file",
  "affected_obligation": "obligation: dataset freshness",
  "repair": "regenerate config.json",
  "acceptance": "code.py exits 0 on refreshed config"
}
```

Registration refuses a maintenance run when no allowance is frozen, when the
wall estimate exceeds `maintenance_allowance.wall_seconds` (unless that cap is
`0`, which disables the cap), or when `max_uses` prior maintenance runs are
already recorded (`MAINTENANCE_USE` events, append-only in the ledger). The
four declaration strings are required and must be nonempty; a maintenance run
without a concrete blocker, obligation, repair and acceptance is refused.

Maintenance runs consume the same budget vector and their resources are
measured and charged exactly like any other run. Their receipts are marked
`maintenance: true` and their `assessment.purpose` is `MAINTENANCE`, so repair
work can never be read as scientific progress: `task_gain` and `mechanism`
stay `UNKNOWN`.

## Regression coverage

- `tests/test_rds_project.py::StopPolicyAndMaintenanceTests` — contract
  validation, deadline stop with partial stdout preserved, no-growth stop,
  growth completes normally, no-policy regression guard, maintenance
  admission/exhaustion and declaration validation.

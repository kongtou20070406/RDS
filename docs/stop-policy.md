# Configured project stops and goal-bound maintenance

These optional fields freeze at project initialization. An absent policy keeps
the existing manifest timeout and resource budget. They apply to the owning
`project create --manifest` / `project execute` ledger, including its scheduled workers.
Quick child execution and theory allowances refuse a parent/source contract
with either field: those routes cannot silently discard these policies. Use a
project manifest until their own policy integration has been reviewed.

## Stop policy

```json
{"stop_policy": {"schema": 1, "wall_seconds": 3600,
                 "progress": {"window_seconds": 900, "min_bytes": 1}}}
```

`wall_seconds` is an elapsed campaign limit, distinct from both per-attempt
timeouts and the sum-of-work resource budget. The first successful reservation
appends `CAMPAIGN_STARTED` to the existing ledger, binding the contract hash
and UTC start. All later registrations and starts use that same absolute
deadline. Idle time, renamed jobs, reopened controllers and recovery count;
checkpoint continuation retains the event. A new root needs explicit new
authorization. Across processes this relies on the system UTC clock; during
an owned attempt the remaining interval is enforced with a monotonic clock.

`progress` checks growth of the controller's retained `stdout.bin` and
`stderr.bin` over a trailing window. Less than `min_bytes` triggers
`PROGRESS_NO_GROWTH`; zero disables that growth condition. This measures log
bytes, not research progress. Silent file/database work can trigger it and
meaningless logging can satisfy it. Configure it only when that signal is
appropriate. It supplies no scientific forecast or proof of feasibility.

The controller terminates only its owned process tree, records
`CAMPAIGN_DEADLINE` or `PROGRESS_NO_GROWTH`, retains partial logs and settles
costs into a FAILED receipt with UNKNOWN scientific assessment. A worker
arriving after the deadline records a terminal failure without launch.
Recovery returns that receipt and never restarts it. Normal execution-policy
observation still applies; inspecting an existing receipt grants no new work.

## Maintenance allowance

Bind a [native objective](native-research.md) before initializing the contract.
Add an ordinary config binding for the goal context file; the allowance uses
its exact path and SHA256, rather than a second goal registry:

```json
{"maintenance_allowance": {"schema": 1, "wall_seconds": 120, "max_uses": 4,
                           "context": {"path": "maintenance-context.json",
                                       "sha256": "<actual file SHA256>"}}}
```

The context uses the existing Advisor shape: exact `objective_binding`
(`question_id`, `goal_revision`, original asset `sha256`), compatible `scope`
and `dependency_map`. Include `completion_standard` among the map's goals.
No arbitrary textual objective, absent binding or stale revision is accepted.

A maintenance manifest adds this declaration, for example for an unresolved
`config_health` node linked to the original completion predicate:

```json
{"maintenance": {
  "reason": "MAINTENANCE", "blocker": "node:config_health",
  "affected_obligation": "config_health",
  "repair": "check the config reader on the authorized synthetic fixture",
  "acceptance": "retain the reader result and review the original obligation",
  "goal_contribution": {"target": "completion_standard",
                        "path": ["config_health", "completion_standard"],
                        "source": "the original task's declared dependency"}
}}
```

The runner reuses Advisor's current dependency review. The action must start
at the affected obligation and end at bound `completion_standard`; the blocker
token (`node:<id>` or `rule:<id>`) must match that start, be ready, and occur in
an unresolved minimal missing-evidence set. Incomplete/truncated maps,
unsupported links, already supported goals and irrelevant side tasks refuse
admission. The context/hash/objective is checked again before dispatch.
These are input-reported structural checks, **not verified proof** that a
repair helps research or that any graph label is scientifically true.

`wall_seconds` is the **total** conservative maintenance allowance. Each
successful reservation atomically appends `MAINTENANCE_USE` with its estimate
and review, while reserving the normal budget. Admission uses the larger of
each retained estimate, observed wall time and settled cost. `max_uses` limits
admitted runs. Zero wall allowance refuses all maintenance. Failed admission
rolls back the event and reservation; admitted failures and recovery never
refund the maintenance allowance. Renaming cannot reset it. Late-settled
overruns are also checked before a previously reserved run starts.

Maintenance consumes the ordinary resource vector; it creates no extra budget
or permission. Receipts retain `maintenance_review`, `maintenance: true` and
`assessment.purpose: MAINTENANCE`; task gain and mechanism remain UNKNOWN.
Frozen source inputs are still immutable: a repair requiring source/config
changes needs an explicitly rebound authorized project, not writes over them.

## Validation and remaining scope

The project tests exercise real CLI refusals without state mutation, native
objective/context binding, unrelated/completed/truncated obligations, atomic
concurrent total allowances, zero/exhausted caps, failed-cost retention, shared
deadlines at admission/worker startup and partial-output stops. The shared
execution/state checks, historical examples and red-team scenarios still apply.

This delivers configured project stopping and a bounded maintenance consumer.
It does not finish V4 host enforcement, all quick/theory continuation routes,
scope-bound research forecasts or the rest of the V5/V6 acceptance work.
The 5.8 umbrella issue remains open; software tests do not prove research gain.

---
name: research-direction-selector
description: Choose and audit metric-driven research experiments with scoped evidence, budgets and authorized execution. Current implementations focus on ML, with optional bounded mathematical checks; not general GPU scheduling or a promise of autonomous discovery.
metadata:
  version: v5.6.0-rc.2
  engine: rds-cli-v5.6
---

# Research Direction Selector

Help the researcher make the next useful decision and advance authorized work. Current support focuses on ML; another domain needs its own executable protocol and evidence.

## Small decision loop

- Infer goal, metric, evidence, rival explanation, budget and next decision from the request and project. Fill low-risk detail internally; require no form. Missing evaluation calls for a minimal protocol before material commitments, never an invented goal, frozen metric or threshold.
- Unless following a clear authorized instruction, internally consider >=3 causally distinct routes: task gain, rival representation/mechanism and consequential diagnostic; replace irrelevant categories. Do not expose a three-item menu each turn.
- Recommend one default and at most one serious alternative, with a deciding observation, fair comparison and stop/revision condition. Proceed within existing authorization; unanswered advice is never acceptance. Ask only for an uninferable material goal, method or resource choice.
- Optimize useful research progress and time to a decision within authorized limits. Cost is a constraint and a trade-off, not a savings target. Inspect available and occupied capacity, the usable time window, marginal charges, dependencies and shared bottlenecks; one recommended plan may contain several independent experiments. When worthwhile ready work fits idle resources, propose a compatible parallel batch instead of defaulting to serial checks. Explain avoidable idle capacity and retain legitimate idle reasons; do not run redundant work merely to raise utilization. Hardware ownership does not make energy, memory or other resource costs zero.
- In stalled discussion, advance the smallest useful decision or reversible check. Do not force an unknown objective or spend on an unaccepted material proposal. Follow clear instructions even when preferring another route.
- Keep rejected proposals' scope and falsifying evidence. Reopen on changed evidence, scope or intervention, naming the change; do not repeat unchanged advocacy.

## Evidence that changes decisions

Separate task gain, mechanism and search-policy evidence. Published, proxy, oracle, toy and reused-development results motivate tests, not local confirmation. Precommit comparison and untouched confirmation; track exposure. Policy claims need whole trajectories at equal total budget. Reuse compatible controls; do not default to multi-seed campaigns.

Check what executed computation changes: a knob name or mathematical side condition does not establish a mechanism. Preserve raw observations and failures. Missing evidence stays unknown; hashes bind artifacts and exit code 0 records execution, not science. Self-signed success creates no evidence or authority.

## Continuity and preferences

Record structured route decisions with `checkpoint save --decision` in the existing project/reference SQLite ledger. For local anti-loop review, supply `--research-context` with the question ID, goal revision, scope and current facts. Advisor verifies the checkpoint hashes and contract binding before pruning unchanged rejected routes; changed evidence or conditions reopen review, and A→B→A warns without veto. See [local decision workflow](docs/lightweight-workflow.md).

Checkpoints authenticate recorded choices, not their scientific validity or execution authority. Keep unanswered proposals pending and existing receipt/formal gates intact. Do not add chat mirrors, source indexes or parallel state machines. The standalone `--research-note` Markdown route is retired.

[Obelisk](references/obelisk.md) is an optional history enhancement when exact past wording, parameters or numbers are needed. Its existing bridge wraps the public CLI, requiring no second service. `history preflight` checks enhanced-mode setup; missing/unusable CLI leaves local anti-loop review usable, but must never be reported as a completed Obelisk query. Version success does not establish index freshness, skill loading or project coverage.

Apply and persist research preferences only with explicit opt-in. [Optional preferences](references/optional-preferences.md) are 空投's examples, not others' defaults or experiment authority.

## Load detail only for the current task

| Need | Read or use |
|---|---|
| Substantive comparison or evidence/human-direction conflict | Relevant [research discipline](references/research-discipline.md) sections: decision contract, direction program, evidence, output. Keep schemas internal. |
| A general rule could change this decision | Relevant [judgment graph](references/judgment-graph.yaml) nodes: date, scope, applicability, counterexample. For RSI comparisons read [RSI evidence](references/rsi-evidence.md). These are scoped corrections, not universal laws; do not load all libraries. |
| Execute the scalar reference protocol | [L3 contract](references/l3-state-machine.md), then the discipline's CLI section. Its restricted rational AST/MSE receipts do not validate external training. |
| Execute/resume a project or develop RDS | [Development loop](docs/development-loop.md): authorized argv, bindings, raw artifacts, live checkpoints. Inspect existing runs before another attempt. |
| Allocate available compute to useful work | [Resource-aware planning](docs/resource-planning.md): capacity, elapsed time, marginal cost and compatible batches. Advisory plans retain execution gates and do not reserve devices. |
| Mathematical obligation / Lean certificate | [Formal framework](references/formal_framework.md) and discipline's formal section: actual checker and declared scope; `UNKNOWN` stays unknown. |
| Graph gaps / Advisor advancement | [Frontier](docs/advisor-frontier.md) or [advancement protocol](docs/advisor-advancement.md). Proposed nodes/ASTs need independent evidence. |

Runner, Lean and RSI remain optional capabilities with their gates intact. Advisor and rule lint are heuristic; rule adoption needs bound evaluation. Software or historical-fixture success is not research-policy gain.

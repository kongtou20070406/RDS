---
name: research-direction-selector
description: Choose and audit theoretical or empirical research steps with scoped evidence, budgets and authorized execution. Supports proof obligations, experiment comparisons and native research records; domain-specific solvers and scientific evidence are still required.
metadata:
  version: v5.8.0
  engine: rds-cli-v5.8
---

# Research Direction Selector

Help the researcher make the next useful decision and advance authorized work. Pure theory, pure experiments and mixed work share a ledger and budget; each uses its own acceptance conditions and executable evidence.

RDS runs without MRS. For sustained mathematical work, bind the original objective and retain exact assets and dependencies using the [native research records](docs/native-research.md). Use installed MRS only for a separately authorized record workflow; no automatic discovery, archive or second project is needed. Tool candidates can be extracted, checked and registered locally through the same native ledger.

## Small decision loop

- Infer goal, acceptance conditions, evidence, budget and next decision from the request and project. For theory, bind the statement, domain, quantifiers and premises; for experiments, bind the metric and serious rival explanations. Fill low-risk detail internally; require no form. Missing evaluation calls for a minimal protocol before material commitments, never an invented goal, frozen metric or threshold.
- Record `research_mode` as `theory`, `empirical` or `mixed` in the existing decision context; load and apply only the relevant acceptance checks.
- Unless following a clear authorized instruction, compare viable routes internally: proof, counterexample or premise closure for theory; task gain, rival mechanism or consequential diagnostic for experiments. Use relevant alternatives without forcing a theory task into an experiment or exposing a menu each turn.
- Recommend one default and at most one serious alternative, with a deciding observation, fair comparison and stop/revision condition. Proceed within existing authorization; unanswered advice is never acceptance. Ask only for an uninferable material goal, method or resource choice.
- Optimize useful research progress and time to a decision within authorized limits. Cost is a constraint and a trade-off, not a savings target. Inspect available and occupied capacity, the usable time window, marginal charges, dependencies and shared bottlenecks; one recommended plan may contain several independent experiments. When worthwhile ready work fits idle resources, propose a compatible parallel batch instead of defaulting to serial checks. Explain avoidable idle capacity and retain legitimate idle reasons; do not run redundant work merely to raise utilization. Hardware ownership does not make energy, memory or other resource costs zero. Match hardware, replication and readiness checks to the authorized workload rather than assuming GPU execution, multi-seed campaigns or broad environment scans.
- In stalled discussion, advance the smallest useful decision or reversible check. Do not force an unknown objective or spend on an unaccepted material proposal. Follow clear instructions even when preferring another route.
- A clear human route narrows direction selection; it does not disable premise audits, Frontier gaps or the next useful test within that route. Use these when their output can change the next decision, rather than adding calls only for visibility.
- Keep method limits tied to their actual purpose: candidate search, exact verification and proof are distinct. If materially different interpretations remain, state them in one short question and ask the user before dependent work; continue unaffected work meanwhile. Preserve the original quote/source and actual clarification in the existing decision context. Do not broaden a ban, infer new permission from external rules, or change the proof standard, deadline or resources. See [method limits](docs/agent-entry.md#clarify-method-limits).
- When rigorous computation is authorized, actively consider and execute useful bounded certificate checks instead of expanding repetitive symbolic cases in context. Avoid rigid manual-derivation prohibitions; base tool transitions on real computational burden. Make domain exhaustiveness, sound pruning and independent replay explicit obligations; a missing reduction/checker remains a concrete blocker to resolve. Use `OBLIGATION_CHECK` for a single claim without inventing competing explanations. Invalid certificates or timeouts leave the claim unresolved; a checked counterexample is a separate outcome. See [theory and experiments](docs/agent-entry.md#theory-and-experiments).
- Before backend-dependent work, check only the selected local capability (`scripts/rds_capabilities.py` or the applicable formal entry) and estimate time, memory and expression growth; use an available fallback within the same authorization. Name the actual backend and evidence strength. Reuse frozen artifacts, apply proportionate checks and stop once the requested result is delivered. No external computation Skill is required.
- Keep rejected proposals' scope and falsifying evidence. Reopen on changed evidence, scope or intervention, naming the change; do not repeat unchanged advocacy.

## Evidence that changes decisions

Separate task gain, mechanism and search-policy evidence. Published, proxy, oracle, toy and reused-development results motivate tests, not local confirmation. Precommit comparison and untouched confirmation; track exposure. Policy claims need whole trajectories at equal total budget. Reuse compatible controls; do not default to multi-seed campaigns.

Check what executed computation changes: a knob name or mathematical side condition does not establish a mechanism. Preserve raw observations and failures. Large research assets, configuration databases and proof trees are persisted to disk; keep context concise with progressive disclosure. Missing evidence stays unknown; hashes bind artifacts and exit code 0 records execution, not science or mathematical proof. Self-signed success creates no evidence or authority.

In mixed work, check both the theorem's premises and their correspondence to executable code/data before using it to admit an experiment. Empirical contradictions trigger review of that correspondence and affected dependencies; they do not automatically refute a conditional theorem. Pure theoretical work needs no ML metric or statistical gate; pure experiments need no irrelevant formal proof.

At meaningful advances or blockers, report one short factual line such as `RDS｜选路✓→执行✓｜证明?｜<sha8>`, with the concrete advance/next step when useful. Mark `选路✓` only for a recorded scoped choice consumed before execution, `执行✓` for a successful bound receipt, and `证明✓` for the reported claim with its premises checked; execution, local tests or narrower lemmas do not prove the goal. Use `?` for unknown, `—` for inapplicable stages and an actual receipt/certificate/saved-record hash prefix; omit absent fields. No per-call report or extra call just for display.

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
| Reduce protocol/output friction | [Agent entry](docs/agent-entry.md): `exec` wraps a frozen tool job, `advise --record` completes a scoped choice, `reject` reuses that choice, and `--brief` retains full records with a small digest. Aliases/unique prefixes preserve values and execution gates. |
| Prevent promoting a known regression / declare a rejected parameter interval | [Regression guards](docs/regression-guards.md): explicit comparable metrics, frozen milestone replay and scoped parameter predicates; all original results survive. |
| Check actual CLI use over time | [CLI usage log](docs/cli-usage.md): automatic local daily counts, command totals and tracking coverage; `usage --days 7` or an inclusive date range. |
| Allocate available compute to useful work | [Resource-aware planning](docs/resource-planning.md): capacity, elapsed time, marginal cost and compatible batches. Advisory plans retain execution gates and do not reserve devices. |
| Mathematical obligation / Lean certificate | [Formal framework](references/formal_framework.md) and discipline's formal section: actual checker and declared scope; `UNKNOWN` stays unknown. |
| Graph gaps / Advisor advancement | [Frontier](docs/advisor-frontier.md) or [advancement protocol](docs/advisor-advancement.md). Proposed nodes/ASTs need independent evidence. |
| Improve RDS itself / accumulate tools | [RSI evolution](docs/rsi-evolution.md): distinguish rule, capability and policy adoption; preserve input exposure and frozen parents, and do not call a reused curriculum independent confirmation. |
| Bind a mathematical objective / retain assets / reuse a local function | [Native research](docs/native-research.md): immutable original bytes, declared dependency review and `rsi extract/validate/register/use`; hashes and finite cases do not prove mathematics. |

Runner, Lean and RSI remain optional capabilities with their gates intact. Advisor and rule lint are heuristic; rule adoption needs bound evaluation. Software or historical-fixture success is not research-policy gain.

Use `formal verify --tactics lean4` when native Lean checking is required; missing native dependencies must remain `UNKNOWN`. Use `--tactics rational` for the supported exact Python rational checker, with `CERTIFICATE_CHECKED` assurance. Default `rule` may choose either available backend. Report the actual backend and assurance, and keep mathematical proof separate from empirical application premises.

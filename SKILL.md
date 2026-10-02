---
name: research-direction-selector
description: Choose and audit theoretical or empirical research steps with scoped evidence, budgets and authorized execution. Supports proof obligations, experiment comparisons and native research records; domain-specific solvers and scientific evidence are still required.
metadata:
  version: v5.8.0
  engine: rds-cli-v5.8
---

# Research Direction Selector

Pick the goal type, run its one command, and drive the work from the kernel's own next step. All commands run from the RDS checkout as `python -B scripts/rds_cli.py …`; `--root <dir>` selects the project directory. This file is the entry point, not the rulebook: acceptance philosophy lives in the linked docs and is loaded only when the current decision needs it.

## Decision tree

| Goal | Run | Detail on demand |
| --- | --- | --- |
| Start from a plain-language request (first time) | Follow the [plain-language quick start](docs/quickstart.md) — copyable prompts, a generated first project, and `[RDS-REJECT]` recovery | [Project runner example](examples/project-runner/README.md) |
| Start a locked experiment campaign | `project init --contract <contract.json>` — template below | [Project tools](docs/development-loop.md) |
| Advance a running campaign | `project next` — prints the derived step and its runnable command | [Development loop](docs/development-loop.md) |
| Decide a research direction | `advise --context <context.json> --graph <graph.json> --brief`; lock the route with `--choose <candidate-id> --record <checkpoint-id>` | [Research discipline](references/research-discipline.md) |
| Audit evidence into the ledger | `artifacts import --manifest <manifest.json>` | [Agent entry](docs/agent-entry.md) |
| Check a mathematical claim | `formal verify --spec <spec.json> --tactics rational` | [Formal framework](references/formal_framework.md) |
| Reuse or register a local tool | `rsi extract --source <file> --entry <function> --name <id>`, then `rsi validate --name <id> --cases <cases.json>` → `rsi register --name <id>` | [Native research](docs/native-research.md) |
| Wrap one frozen tool job | `exec --name <id> --timeout 30 -- <command…>` — receipt-bound execution without contract JSON | [Agent entry](docs/agent-entry.md#wrap-a-command) |
| Record a decision or rejection | `checkpoint save --id <id> --decision <decision.json>` (kind auto-selects from the root); `reject --reason '<text>' --evidence <file>` reuses the current choice | [Local decision workflow](docs/lightweight-workflow.md) |

**Driving pattern:** after any campaign-changing command, run `project status --brief` or `project next` and execute the printed `next_move` — register, execute, recover, compare, record — instead of memorizing a command sequence. The kernel derives the step from recorded ledger state only.

**Non-negotiables** (details in the linked docs): infer goal, acceptance conditions, evidence and budget from the request and project — never invent a metric, threshold or goal, and missing evaluation calls for a minimal protocol before material commitments. Missing evidence stays `UNKNOWN`; exit code 0 and self-signed success are execution records, not science. Recommend one default and at most one serious alternative, with a deciding observation, fair comparison and a stop/revision condition. Ask only for an uninferable material goal, method or resource choice.

## Minimal project contract template

Validated by `project init`: relative paths, hex SHA-256 of each file, all five binding roles required, `min_useful_delta` as an exact rational string. Optional fields (`objective_sha256`, `execution_policy`, `stop_policy`, `maintenance_allowance`) are documented in [stop policy](docs/stop-policy.md) and [native research](docs/native-research.md). Generate a real, immediately valid contract with `python -B examples/project-runner/prepare.py --root <new-empty-dir>`.

```json
{
  "schema": 1,
  "description": "CPU demonstration, not scientific confirmation",
  "bindings": [
    {"role": "code",      "path": "experiment.py", "sha256": "<sha256>"},
    {"role": "config",    "path": "config.json",   "sha256": "<sha256>"},
    {"role": "data",      "path": "data.csv",      "sha256": "<sha256>"},
    {"role": "evaluator", "path": "evaluate.py",   "sha256": "<sha256>"},
    {"role": "protocol",  "path": "protocol.json", "sha256": "<sha256>"}
  ],
  "allowed_commands": [
    ["python", "-B", "experiment.py", "--arm", "control",   "--output", "outputs/control.json"],
    ["python", "-B", "experiment.py", "--arm", "treatment", "--output", "outputs/treatment.json"]
  ],
  "output_roots": ["outputs"],
  "budget": {"wall_seconds": 20},
  "primary_metric": {"name": "mse", "direction": "min", "min_useful_delta": "1/100"}
}
```

Then `project init --contract <root>/contract.json`, register each arm with `project create --manifest <root>/<arm>.json`, and follow `project next`.

## Load more only when the decision needs it

- Goal-linked dependencies, method limits, theory/experiment acceptance: [agent entry](docs/agent-entry.md)
- Evidence classes, output contract, controls, precommitted comparison: [research discipline](references/research-discipline.md)
- Capacity, idle resources, parallel batches: [resource-aware planning](docs/resource-planning.md)
- Stalled formulation, plateau, theory-tool lookup: [theory reformulation](docs/theory-reformulation.md)
- Anti-loop checkpoint review: [local decision workflow](docs/lightweight-workflow.md)
- Formal scope, `UNKNOWN` semantics, Lean backends: [formal framework](references/formal_framework.md)
- Native objectives, asset retention, RSI ledger: [native research](docs/native-research.md)
- Optional history enhancement: [Obelisk](references/obelisk.md); preferences apply only with explicit opt-in: [optional preferences](references/optional-preferences.md)

Runner, Lean and RSI remain optional capabilities with their gates intact. Advisor and rule lint are heuristic; report the actual backend and assurance (`CERTIFICATE_CHECKED` for the rational checker, `LEAN_KERNEL_CHECKED` for native Lean) and keep unresolved results unknown.

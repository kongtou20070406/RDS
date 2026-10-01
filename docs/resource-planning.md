# Resource-aware research planning

RDS should advance the research question within authorized constraints and reach useful decisions sooner. Minimizing expenditure and maximizing hardware utilization are both incomplete objectives. Idle capacity is a missed opportunity when independent, worthwhile work could have completed within the available window.

## Distinguish four quantities

| Quantity | Meaning | Example |
| --- | --- | --- |
| Available capacity | Resources that can be used concurrently, after other work and protected allocations | Four compatible GPU slots, of which one is occupied |
| Elapsed completion time | When this batch can return its last result | Four independent one-hour tasks can finish in about one hour when all run together |
| Total resource consumption | Sum of each task's demand times duration | Those tasks still consume four GPU-hours |
| Incremental charges | Additional money or another explicitly identified consumable budget | A prepaid allocation and an on-demand rental can have different incremental charges |

Owned hardware is not automatically free: power, wear, memory, operators, and competing workloads can matter. Conversely, using fewer GPU-hours does not prove a plan is preferable if it unnecessarily delays an important decision. Never infer linear multi-GPU speedup. Use supported estimates that include setup, fair controls, evaluation and interference.

The current `ProjectStore.wall_seconds` budget is **summed attempt wall time**, not a campaign deadline. Four parallel one-hour attempts require about four hours of that ledger allowance, even when batch elapsed time is about one hour. The planner does not reinterpret or discount the existing budget. CPU/GPU device-time remains an estimate unless an execution instrument actually measures it.

## Choose a useful batch

The ordinary Advisor generates candidates and applies its graph prerequisites and scoped repeat-rejection review. Optional resource planning then considers surviving `READY` candidates. It uses an explicit resource context, sourced per-candidate estimates and declared priorities to suggest a batch that fits the available capacity, time window and remaining budget. The priorities are research judgments supplied to the planner, not measured scientific utility. The planner does not independently prove formal obligations or replace execution admission.

The candidate order first honors those priorities and then considers earlier completion. A lower scalar cost does not automatically remove a slower or faster alternative. Alternatives for the same experiment are grouped so only one configuration is chosen. Distinct hypotheses, compatible controls and measurements may run concurrently when independence and lack of contention are explicitly supported. A diagnostic-dependent intervention must wait for its deciding result.

The plan reports selected candidates, delayed or unresolved candidates, estimated resource use, completion time, and idle capacity with reasons. Missing estimates or uncertain parallel safety stay unresolved. Occupied capacity is not reported as idle. Budget protected for confirmation is not available for opportunistic exploration.

The first implementation proposes one batch with a bounded deterministic heuristic. It does not claim optimal scheduling, forecast scientific gains, allocate GPU IDs, lock devices, submit cloud jobs or launch the batch. Device compatibility, VRAM and I/O constraints must be represented in the supplied resource groups/requirements or checked by the project's executor. A plan is a snapshot; actual execution still goes through transactional budget and output reservations and the original authorization gates. Long-running authorized Windows work uses the existing Task Scheduler path.

## Supply the resource context

Call the ordinary CLI with a research context containing `resources`:

```text
python -B scripts/rds_cli.py advise --graph <graph.json> --research-context <context.json>
```

`resources` is preserved when this command also imports an artifact manifest. The response adds a `RESOURCE_BATCH_PLAN` recommendation with a `resource_plan` object. The normal candidate report remains available.

| Field | Meaning |
| --- | --- |
| `capacity`, `occupied` | Objects of named nonnegative integer slots; both must explicitly cover every resource |
| `window_seconds` | Positive full-duration limit for this simultaneous batch |
| `budget.available` | Additive budget already net of spent and active reservations |
| `budget.reserve` | Additional protected future-work floor, including zero when none applies |
| `budget.unit` | Explicit unit for every candidate's incremental cost; `wall_seconds` requires cost equal to full duration |
| `completed` | Explicit list of satisfied dependency IDs; selecting a job in this batch does not complete it |
| `source` | Inventory/budget source description; the planner treats it as reported input |
| `resource_seconds_caps` | Optional spendable slot-second caps by resource, already net of reservations |
| `estimates` | Records keyed by the exact surviving candidate ID |

Each estimate requires `experiment_id`, `resources`, `wall_seconds`, `incremental_cost`, integer `priority` (smaller first), boolean `parallel_safe`, `depends_on`, `mutex_groups`, `decision_use` and `source`. Resource demand explicitly includes zero for unused dimensions. `experiment_id` identifies mutually alternative configurations; `mutex_groups` additionally names incompatible jobs. Optional `comparison_group` permits reported time/cost trade-offs to be displayed, but does not establish parallel safety or scientific equivalence.

For example, one record under the `estimates` object can be:

```json
{
  "rule-id:action-id": {
    "experiment_id": "paired-comparison-a",
    "resources": {"gpu": 1},
    "wall_seconds": 3600,
    "incremental_cost": 10,
    "priority": 1,
    "parallel_safe": true,
    "depends_on": [],
    "mutex_groups": [],
    "decision_use": "Distinguish the two declared explanations and select the next intervention",
    "source": "Illustrative estimate only; replace with the actual measurement/protocol"
  }
}
```

This partial example does not claim that a real GPU is available or that the cost is known. Include the required inventory/window/budget fields and use the units of that budget. An absent `occupied`, `reserve`, duration, source or dependency list does not silently become zero or empty. The planner does not infer free use from hardware ownership.

## What should happen in the four-GPU example

These are hypothetical planning cases, not GPU benchmarks:

| Situation | Expected decision |
| --- | --- |
| Four independent useful one-GPU tasks, all prerequisites met, one-hour estimates and sufficient total budget | Propose all four in one batch; show about one hour elapsed and four GPU-hours of consumption |
| Only one meaningful task exists | Run the task if authorized; report that no other eligible work is available |
| Three tasks depend on the first result | Plan the first task and explain the dependency wait; do not invent independent work |
| One task has both a one-GPU and four-GPU configuration | Compare supported duration/resource/cost estimates and choose at most one configuration |
| Four slots exist but three belong to another workload | Plan against one free slot; do not call the occupied slots wasted |
| A prior rejected route is pruned while four unrelated ready tasks remain | Keep those four eligible; a repeat-warning on the removed route does not freeze the whole batch |
| More capacity is available but tasks would exceed a hard budget or protected reserve | Keep the budget boundary and report the limiting constraint |
| A cheaper task lacks a comparable scientific purpose | Keep it incomparable; matching decision text is not equal scientific value |

An idle report identifies a planning opportunity, not measured monetary loss. Waiting can be justified by prerequisites, confirmation reserves, memory or I/O contention, uncertainty, or the absence of useful work. When idle capacity is avoidable, propose the specific eligible work that would use it and how its result changes the next research decision.

## Develop and evaluate this policy with RDS

Use the current checkout's [self-development workflow](development-loop.md), with bound source and real test output. Focused acceptance uses CPU fixtures to represent resource inventories and tasks; it does not allocate actual GPUs. Retain the original failed and successful iterations, their budgets, import results and Advisor next-step records.

The acceptance question is whether RDS preserves relevant scientific alternatives and constructs a feasible useful batch without overriding unknowns, dependencies, repeat suppression or execution gates. Passing software cases establishes those finite behaviors. A claim that the research policy improves outcomes still requires fair complete trajectories with the same hardware access, time window, monetary/resource caps and confirmation protocol. Comparing only total spend would miss the improvement this policy is intended to test.

See also the [Lean ecosystem survey](lean4-ecosystem-survey.md) for complementary ways to use CPU/GPU capacity in proposal search and proof checking, and the [collaboration ledger](collaboration-ledger.md) for dated acceptance records.

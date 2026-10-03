# Research autonomy: the adopted L0–L5 framework

[Research workflow](research-workflow.md) · [科研工作流](research-workflow.zh-CN.md) · [Terminology](terminology.md)

RDS uses the framework in Kramer et al., *Automated Scientific Discovery: From Equation Discovery to Autonomous Discovery Systems*, formally published in *Machine Learning* 115, article 109, on 2026-04-29. The published §5 and Table 5 caption verify the driving-automation analogy and six-level framing. The names and scope summaries below were checked against the publicly readable **author preprint v2 (2025-05-26), §5 / Table 2**. The final journal table is numbered Table 5; its six cells were not individually checked against the final PDF in this review. RDS retains the original **L0–L5 numbering and meanings**; overview pages emphasize L1–L4 without defining a separate four-level scale. [Publication facts and journal §5](https://link.springer.com/article/10.1007/s10994-025-06955-2), [checked level definitions in preprint v2](https://arxiv.org/html/2305.02251v2#S5).

## Levels and scope

The original English names appear below. The Chinese entries and English explanations elsewhere in RDS are concise scope summaries, not full translations of the paper or additional definitions.

| Level | Original name | 简要含义 |
| --- | --- | --- |
| L0 | No automation | 传统科研由人完成。 |
| L1 | Machine assistance | 科研某一方面得到计算机辅助。 |
| L2 | Partial Automation | 一个重要科学发现环节完全自动化。 |
| L3 | Conditional Automation | 在限定领域内，完整科学发现循环自动化。 |
| L4 | High Automation | 跨多个科研领域完成发现闭环，并能有限自主设置目标。 |
| L5 | Full Automation | 科研各方面自动化，无需人类干预。 |

These levels concern the extent and domain coverage of scientific discovery automation. They are not a score for scientific usefulness, a safety certification, an SAE compliance claim, or a promise that an autonomous system will discover something valuable. Other research-autonomy frameworks exist; their numbering must not be mixed with this one.

## Current RDS evidence and historical names

RDS currently has scoped L2 functionality in automatic reference computations and explicitly bound candidate search. This mapping is limited to demonstrated component tasks, not a certification of general research capability. RDS combines a human-facing research protocol with restricted automated components: a bounded scalar reference runner, recorded contracts and budgets, mathematical checkers, Advisor search, history retrieval and a read-only dashboard. It has not demonstrated the complete scientific discovery loop required by the adopted L3, cross-domain L4 discovery, or an end-to-end GPU research service. Component regression tests do not establish those capabilities.

The implemented [program-owned Advisor loop](program-owned-advisor.md) connects goal predicates, current evidence, constraints and frozen candidate routes to the next permitted execution. Results and receipts update research state, which feeds Advisor again. This makes Advisor central to continuation within that declared scope; it does not demonstrate the scientific discovery cycle in the table above. Agents still supply hypotheses beyond the available candidate space, check application assumptions and use domain-specific verification.

A tested goal predicate may remain `FALSE` after successful execution; scientific support may remain `UNKNOWN` after a goal threshold is met. A receipt, recovered run or passing regression establishes its scoped engineering behavior, not scientific usefulness. A claim of better scientific decisions requires a fair prospective comparison on unused cases at equal total budgets, including failures and evaluation. No such gain is established by the program-owned loop's software regressions.

Existing names such as `rds_l3.py`, `references/l3-state-machine.md`, and the former L4 label for policy improvement are **historical engineering names**. They do not map to levels in the adopted paper. Code, CLI and file identifiers remain compatible; user-facing descriptions should say **bounded reference runner** or **RSI** as appropriate.

## Product coverage targets

The near-term goal is **L2 support across all six research stages**: usable automation for goal clarification, evidence and experiment selection, design checking, execution management, result assessment, and evidence retention with continuation. The researcher retains research direction, key judgments and acceptance of scientific results. This is RDS's product coverage target, not a new meaning of the paper's L2 or an assertion of the complete L3 cycle. Current functionality remains scoped and partial.

Long-term research targets are the original L4 and L5 scope: multi-domain discovery with limited autonomous goal setting, and comprehensive discovery autonomy. These are research directions, not implemented capability or delivery-time commitments. The [roadmap](roadmap.md) defines deliverables and evidence gates.

## RDS operating constraints, separately

An execution contract should specify allowed actions, data and evaluator bindings, the supported environment, resource caps, evidence gates, stopping conditions and recovery or handoff conditions. These are RDS operational constraints, not the paper's level definitions and not a new enforced CLI schema. Existing user authorization and caps govern actions; adoption of the framework adds no blanket approval step to each round.

For example, if data no longer matches a bound hash, stop new experiments, keep the original outputs and error, reconcile spent and reserved resources, and state what must be restored or reauthorized before resuming. An already authorized, bounded retry may be appropriate for a transient executor failure; otherwise pause and preserve the handoff. Do not broaden authorization, spend indefinitely, relabel used data as independent, or promote `UNKNOWN` to a conclusion. This failure response does not itself establish an autonomy level or scientific success.

## RSI is an independent axis

RSI proposes and evaluates changes to RDS's rules and research policies. Improving the policy is not the definition of L4; automation can increase without policy improvement, and a supervised workflow can evaluate policy changes.

An RSI improvement claim needs prospective comparisons of whole research trajectories on previously unused, independent cases at equal total budgets. Include unsuccessful trials, investigation, diagnosis, verification and evaluation; record policy versions, information exposure, stopping rules and negative results. Regression tests and historical replay check narrower behavior. RDS has not established prospective RSI gains across independent research trajectories.

# Research Direction Selector terminology

**English** · [简体中文](terminology.zh-CN.md)

This glossary aligns the vocabulary used by RDS's five components and documentation. RDS provides automated assistance for human research; the researcher sets goals and resources. Chinese labels explain the concepts; they do not rename fields or values in code. Keep identifiers such as `task_gain`, `run_status`, `status`, and `assurance` unchanged in commands, schemas, examples, and execution records.

## Component terms

The research protocol Skill, execution and acceptance kernel, and research state and memory form the three foundational components. Advisor and RSI are the two enhancements. These are software responsibilities; the adopted L0–L5 levels describe scientific-discovery automation across them.

| Component | 中文 | Meaning in RDS |
| --- | --- | --- |
| Research protocol Skill | 科研规程 Skill | The collaboration protocol for intent, evidence, experiment design, results and resumption. A protocol instruction is distinct from behavior enforced by a program. |
| Execution and acceptance kernel | 执行与验收内核 | The supported plan, constraint, execution, verification, artifact, receipt and recovery machinery. Applicable mathematical checking is one capability within this responsibility. |
| Research state and memory | 研究状态与记忆 | Project records in `.rds`, the judgment graph and Obelisk history retrieval used to preserve research evidence and decision reasons. Operational records and historical sources have different roles. |
| Advisor | 科研建议引擎 | Connect the original goal, current evidence, constraints and available candidate routes to the next executable action or blocker, preserving the reasons and unknowns. |
| RSI | 自改进 | The responsibility for proposing, evaluating, adopting or rolling back scoped changes to rules and work policies. It does not denote an automatic increase in a model's intelligence. |

Current Advisor helpers provide diagnostic hints, scoped rule retrieval and bounded graph search over source-labelled facts, explicit candidate bindings and prerequisite dependencies. They preserve unknowns and result-dependent next decisions. General automatic discovery and combination of research ideas remain development directions; the component benchmark does not measure independent scientific success. Rule matches are clues whose applicability needs evidence. Policy improvement through RSI requires independent comparisons of whole research trajectories at equal total budgets. Lean-compatible work applies to suitable mathematical subtasks and does not certify the broader scientific conclusion.

In a [program-owned project](program-owned-advisor.md), results and receipts update state before Advisor selects the next permitted route from the frozen policy. A goal predicate `FALSE` and scientific support `UNKNOWN` have separate meanings; command success does not promote either to scientific confirmation. This engineering loop does not establish prospective scientific decision benefit.

## Research and experiment terms

| English / identifier | 中文 | Meaning in RDS |
| --- | --- | --- |
| claim | 研究声明 | The research statement to be tested, with its scope, quantifiers, and required mechanism. A claim may be broader than a proposition checked by one formal backend. |
| proposition | 形式命题 | A mathematical statement expressed for checking under declared assumptions and a domain. Its validity does not automatically establish the broader research claim. |
| property | 性质 | The specific condition or behavior under test. A parameter change must actually change the declared property before it can test that property. |
| judgment | 判断 | A research decision informed by evidence. Judgment rules have applicability conditions and falsifiers; they are not universal performance laws. |
| assessment | 证据评估结论 | The interpretation recorded from a result, such as a task-gain or mechanism assessment. An assessment is distinct from the execution record it reads. |
| `task_gain` | 任务收益 | Improvement on the declared primary metric under the stated comparison protocol. A metric gain alone does not establish mechanism evidence. |
| mechanism | 机制证据 | Evidence about the explanation or property being tested. Successful execution or a threshold crossing alone does not establish causal support. |
| exposure | 数据暴露 | Recorded data access or use, including viewing, training, and selection. Here, exposure concerns the independence of later confirmation; it does not mean only a privacy leak. |
| control | 对照 | The comparison arm or computation used as the reference. Its relevant conditions must remain matched to the intervention. |
| treatment | 干预 | The comparison arm or computation that applies the proposed change. The executed change must match the declared intervention. |
| confirmation | 独立确认 | A predeclared evaluation after selection is frozen, using data that has not informed that selection. A repeatedly reused test set cannot supply independent confirmation. |
| policy improvement | 研究决策策略改进 | Improvement in the process that chooses research actions. It requires comparisons of whole research trajectories at equal total budgets; one successful model result is insufficient. |

## Verification and execution terms

| English / identifier | 中文 | Meaning in RDS |
| --- | --- | --- |
| admission | 准入 | A decision that a plan currently satisfies the relevant conditions before execution. Admission does not mean that its scientific claim is supported. |
| gate | 门禁 | A check of a required constraint, such as budget, data use, or a declared formal obligation. A gate is not an OS security boundary. |
| `status` | 检查状态 | The outcome reported by a check, such as `PASS`, `FAIL`, or `UNKNOWN`. Read it in the context of the record that produced it. |
| `assurance` | 验证依据类型 | A categorical description of the basis checked by the verifier. It is not a confidence score or a ranking of research quality. |
| certificate | 证书 | An evidence artifact submitted to the corresponding backend for checking. Its format, scope, and acceptance conditions are defined by the formal verification guide. |
| receipt | 执行收据 | An engine-produced record of execution, including its bindings, execution status, results, and artifact references. A receipt does not by itself prove a scientific interpretation. |
| recovery | 恢复 | Restoring or reconciling execution state and records after interrupted work. Recovery does not itself authorize a new run; rerun behavior follows the execution protocol. |

`run_status` is the execution state, separate from a verifier's `status`. Likewise, a receipt records execution facts, while an assessment interprets the result. Preserve these distinctions when translating logs or explaining a run.

## Check status and verification basis

`status` and `assurance` answer different questions: **what was the check's outcome, and what kind of basis was checked?** Neither field is a level score. In particular, `PASS` is not interchangeable with confirmed task gain or supported mechanism evidence.

| `assurance` value | Availability | Meaning |
| --- | --- | --- |
| `AST_ONLY` | Mainline | AST-only checking within the ordinary reference path. This is not a formal proof certificate. |
| `SYMBOLIC_CHECKED` | Mainline | A symbolic check within the declared adapter's scope. This is not automatically an independently checked certificate. |
| `NONE` | Mainline | No verification basis is asserted by this check. |
| `CERTIFICATE_CHECKED` | Mainline, introduced by PR #2 | A certificate has been checked within the supporting backend's declared scope. |
| `LEAN_KERNEL_CHECKED` | Mainline; configured native Lean required | Native Lean independently checks a fixed-template closed rational relation with an empty-axiom audit. Broader model claims are not covered. |
| `EXACT_OBSERVATION_CHECKED` | Mainline, introduced by PR #2 | An exact observation has been checked within the supporting backend's declared scope. |
| `EXACT_COUNTEREXAMPLE_CHECKED` | Adapter-specific evidence | An exact forward counterexample has been checked. The generic framework's outer conclusion uses `CERTIFICATE_CHECKED`; inspect the result field and version. |

These values are categories, not an ordered ladder or a list supported by every version. Read each value together with the check status, declared proposition, domain, and backend scope. For the precise support and acceptance conditions of each backend, use the [formal verification guide](formal-verification.md), which distinguishes the historical base, current mainline and future adapters.

## Adopted autonomy levels and historical identifiers

RDS adopts Kramer et al. (2026)'s six-level L0–L5 scientific-discovery automation framework, retaining its numbering and meaning. L1–L4 describe assistance, automation of a significant component, a complete domain-limited discovery cycle, and multi-domain cycles with limited autonomous goal setting, respectively. The [autonomy guide](research-autonomy.md) contains the original names and source.

The scale is not a component list, SQLite state machine, scientific-quality score or safety certification. Existing L3 reference-runner names and the former L4 policy-improvement label are historical engineering identifiers; they do not establish the corresponding external autonomy level. Keep code and CLI identifiers compatible and describe those tools as the bounded reference runner or RSI.

| Term | Meaning in RDS |
| --- | --- |
| Execution contract | The authorized actions, data, evaluators, environment, resources and evidence constraints for supported work. |
| Stop and recovery conditions | Operational responses to failed or invalid work, including preserving artifacts, reconciling resources and recording what permits resumption. They are not autonomy-level definitions. |
| RSI | A separate component for proposing and evaluating policy changes. Prospective gains at equal total budgets on unused independent cases are independent of autonomy. |

Contracts, hypotheses, gates, execution, receipts, assessment and the next decision form the actual experiment loop. Task gain, mechanism evidence and execution state remain separate; `PASS` or one assessment cannot establish an autonomy level. See the [workflow](research-workflow.md) for current capabilities.

## Related documentation

| Document | English | 简体中文 |
| --- | --- | --- |
| Project overview | [README](../README.md) | [README](../README.zh-CN.md) |
| Formal verification and backend scope | [Guide](formal-verification.md) | [指南](formal-verification.zh-CN.md) |
| Research responsibilities and experiment flow | [Guide](research-workflow.md) | [指南](research-workflow.zh-CN.md) |

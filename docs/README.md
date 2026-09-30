# RDS documentation

[简体中文](README.zh-CN.md) · [Project homepage](../README.md) · [Contributing](../CONTRIBUTING.md)

Start with the research workflow, then read the verifier guide for mathematical claims. The terminology guide keeps protocols, program checks and scientific conclusions consistent across languages.

| Guide | English | 简体中文 |
| --- | --- | --- |
| L1–L4 responsibilities and experiment flow | [Research workflow](research-workflow.md) | [科研工作流](research-workflow.zh-CN.md) |
| Declarations, certificates and verification scope | [Formal verification](formal-verification.md) | [形式化验证](formal-verification.zh-CN.md) |
| Reuse Lean4/mathlib for a deep-learning research extension | [Lean integration](lean-integration.md) | [Lean 兼容](lean-integration.zh-CN.md) |
| Preconditions, feasible domains and falsifiers for all 23 nodes | [Rule obligations](rule-obligations.md) | [规则义务](rule-obligations.zh-CN.md) |
| Shared language and exact code identifiers | [Terminology](terminology.md) | [术语表](terminology.zh-CN.md) |
| Reproducers, evidence and pull requests | [Contributing](../CONTRIBUTING.md) | [贡献指南](../CONTRIBUTING.zh-CN.md) |

The [execution contract](../references/l3-state-machine.md) defines the runtime in the checkout being used. [SKILL.md](../SKILL.md) defines the research protocol. When the two differ, report the inconsistency instead of interpreting a protocol instruction as an implemented guarantee.

The stable homepage examples target public `main`. The certificate implementation in [PR #2](https://github.com/kongtou20070406/RDS/pull/2) is under review. Its evolving multidimensional adapters must be checked against their own implementation revision; a module or design sketch does not establish support in the installed CLI. See the verifier guide's capability table before choosing a backend.

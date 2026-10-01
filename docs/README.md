# Research Direction Selector documentation

[简体中文](README.zh-CN.md) · [Project homepage](../README.md) · [Contributing](../CONTRIBUTING.md)

Start with the research workflow, then read the verifier guide for mathematical claims. The terminology guide keeps protocols, program checks and scientific conclusions consistent across languages.

This guide targets v5.6.0-rc.1, including the mathematical implementation introduced in PR #2, the Advisor/dashboard integration introduced in PR #3, and the first [M01–M06 tool workflow](development-loop.md). Mathematical capability tables retain `f020b2c` as a historical comparison; their supported scope is unchanged. Broader planned adapters remain unimplemented. See the [five components](rds-purpose.md), [Advisor design](advisor-graph-design.md), [dashboard](dashboard.md), [component benchmark](advisor-benchmark.md), and [roadmap](roadmap.md).

| Guide | English | 简体中文 |
| --- | --- | --- |
| Published autonomy taxonomy and current implementation scope | [Research autonomy](research-autonomy.md) | [原框架与当前能力](research-autonomy.md) |
| Research responsibilities and experiment flow | [Research workflow](research-workflow.md) | [科研工作流](research-workflow.zh-CN.md) |
| Declarations, certificates and verification scope | [Formal verification](formal-verification.md) | [形式化验证](formal-verification.zh-CN.md) |
| Reuse Lean4/mathlib for a deep-learning research extension | [Lean integration](lean-integration.md) | [Lean 兼容](lean-integration.zh-CN.md) |
| Build the pinned native library and audit conditional statistical laws | [Native Lean and statistics](lean-native.md) | [Native Lean and statistics](lean-native.md) |
| Preconditions, feasible domains and falsifiers for all 23 nodes | [Rule obligations](rule-obligations.md) | [规则义务](rule-obligations.zh-CN.md) |
| Shared language and exact code identifiers | [Terminology](terminology.md) | [术语表](terminology.zh-CN.md) |
| Reproducers, evidence and pull requests | [Contributing](../CONTRIBUTING.md) | [贡献指南](../CONTRIBUTING.zh-CN.md) |
| Concrete changes, deliverables and acceptance checks | [Development plan](roadmap.md) | [开发与验收计划](roadmap.md) |
| Real records, locked project runs, rule replay and RDS self-development | [Tool and development loop](development-loop.md) | [工具与开发反馈循环](development-loop.md) |
| Same-model skill comparison and benchmark selection | [Benchmark plan](benchmark-plan.md) | [基准选型与对比方案](benchmark-plan.md) |

The [execution contract](../references/l3-state-machine.md) defines the runtime in the checkout being used. [SKILL.md](../SKILL.md) defines the research protocol. When the two differ, report the inconsistency instead of interpreting a protocol instruction as an implemented guarantee.

The homepage examples target public `main`. Its checked certificate and scoped multidimensional interfaces originate in [PR #2](https://github.com/kongtou20070406/research-direction-selector/pull/2). Check each adapter's implementation revision and documented limits before choosing a backend. The release regression run skipped two native-Lean checks because a toolchain was not configured and two PyTorch checks because PyTorch was absent; those skips do not establish validation of the optional paths.

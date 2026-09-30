# Research Direction Selector 文档

[真实记录、项目执行、规则采用与用 RDS 开发 RDS](development-loop.md)提供 M01–M06 首版工具的命令和范围。

本指南面向 v5.6.0-rc.1，包含 PR #2 引入的数学实现、PR #3 引入的 Advisor／工作台，以及首版 [M01–M06 工具闭环](development-loop.md)。数学能力表保留 `f020b2c` 作为历史对照，原有支持范围没有扩大；更广泛的计划能力仍未实现。参见[五组件](rds-purpose.md)、[Advisor 设计](advisor-graph-design.md)、[工作台](dashboard.md)、[组件基准](advisor-benchmark.md)和[未来计划](roadmap.md)。

[English](README.md) · [项目首页](../README.zh-CN.md) · [贡献指南](../CONTRIBUTING.zh-CN.md)

先读科研工作流；涉及数学命题时再读形式化验证指南。术语表用于统一协议、程序检查和科学结论在不同语言中的表述。

| 指南 | 简体中文 | English |
| --- | --- | --- |
| 已有自主分级与当前实现范围 | [原框架与当前能力](research-autonomy.md) | [Research autonomy](research-autonomy.md) |
| 科研职责与单次实验流程 | [科研工作流](research-workflow.zh-CN.md) | [Research workflow](research-workflow.md) |
| 声明、证书与验证范围 | [形式化验证](formal-verification.zh-CN.md) | [Formal verification](formal-verification.md) |
| 复用 Lean4/mathlib 的深度学习科研扩展 | [Lean 兼容](lean-integration.zh-CN.md) | [Lean integration](lean-integration.md) |
| 23 节点的前置门禁、可行域与证伪条件 | [规则义务](rule-obligations.zh-CN.md) | [Rule obligations](rule-obligations.md) |
| 统一术语与准确的代码标识 | [术语表](terminology.zh-CN.md) | [Terminology](terminology.md) |
| 复现材料、证据与 PR | [贡献指南](../CONTRIBUTING.zh-CN.md) | [Contributing](../CONTRIBUTING.md) |
| 具体改法、交付物和通过条件 | [开发与验收计划](roadmap.md) | [Development plan](roadmap.md) |
| 同模型 skill 对比与基准选型 | [基准选型与对比方案](benchmark-plan.md) | [Benchmark plan](benchmark-plan.md) |

[可执行契约](../references/l3-state-machine.md) 定义所用 checkout 的运行行为，[SKILL.md](../SKILL.md) 定义科研协作协议。二者不一致时应报告差异，不能把协议要求解释为程序已实现的保证。

首页示例面向公开 `main`，其证书检查和有范围的多维接口来自 [PR #2](https://github.com/kongtou20070406/research-direction-selector/pull/2)。选择后端前请核对各适配器的实现版本与文档限制。本次发布回归因未配置工具链跳过了两项原生 Lean 检查，因未安装 PyTorch 跳过了两项 PyTorch 检查；跳过不代表这些可选路径已获验证。

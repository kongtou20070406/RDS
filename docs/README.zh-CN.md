# RDS 文档

[English](README.md) · [项目首页](../README.zh-CN.md) · [贡献指南](../CONTRIBUTING.zh-CN.md)

先读科研工作流；涉及数学命题时再读形式化验证指南。术语表用于统一协议、程序检查和科学结论在不同语言中的表述。

| 指南 | 简体中文 | English |
| --- | --- | --- |
| L1–L4 职责与单次实验流程 | [科研工作流](research-workflow.zh-CN.md) | [Research workflow](research-workflow.md) |
| 声明、证书与验证范围 | [形式化验证](formal-verification.zh-CN.md) | [Formal verification](formal-verification.md) |
| 复用 Lean4/mathlib 的深度学习科研扩展 | [Lean 兼容](lean-integration.zh-CN.md) | [Lean integration](lean-integration.md) |
| 23 节点的前置门禁、可行域与证伪条件 | [规则义务](rule-obligations.zh-CN.md) | [Rule obligations](rule-obligations.md) |
| 统一术语与准确的代码标识 | [术语表](terminology.zh-CN.md) | [Terminology](terminology.md) |
| 复现材料、证据与 PR | [贡献指南](../CONTRIBUTING.zh-CN.md) | [Contributing](../CONTRIBUTING.md) |

[可执行契约](../references/l3-state-machine.md) 定义所用 checkout 的运行行为，[SKILL.md](../SKILL.md) 定义科研协作协议。二者不一致时应报告差异，不能把协议要求解释为程序已实现的保证。

首页的稳定示例面向公开 `main`。[PR #2](https://github.com/kongtou20070406/RDS/pull/2) 的证书实现处于审阅阶段；持续开发的多维适配器须按各自实现版本核对。存在模块或设计草案，不代表安装的 CLI 已经支持。选择后端前请查看形式化验证指南的能力表。

## Problem and layer / 问题与层次

What changes, and is it skill protocol, runner, verifier, or an experimental L4 tool? L1–L4 describe responsibilities, not executable states.
说明问题与改动层次：技能协议、runner、verifier，或实验性 L4 工具。L1–L4 是工作职责，不是程序状态。

## Claim and release scope / 命题与发布范围

State the exact claim and assumptions. Separate released behavior on the base ref, this PR's changes, and development candidates. Use the selected adapter's schema; scalar `kind`/`statement`/`quantity`/`domain` fields are not universal multidimensional fields.
说明精确命题与假设，区分 base ref 已发布行为、本 PR 改动与开发候选。遵循所选 adapter 的 schema，不向所有多维 spec 强加标量字段。

For rule changes, identify preconditions, falsifiers and feasible-domain obligations. For Lean integration, identify the expected theorem, model binding, toolchain/library versions and axiom checks; tactic traces or a successful unrelated file are insufficient.
规则改动须指出前置门禁、证伪条件与可行域义务；Lean 接入须注明期望定理、模型绑定、工具链/库版本与公理检查，不能以 tactic 轨迹或无关文件编译成功替代。

## Public reproduction and results / 可公开复现与结果

Include minimal inputs, commands, version/commit/ref and adapter/backend, then actual `status` and `assurance` separately. Distinguish admission, execution, and scientific evidence; label synthetic or retrospective results.
提供最小输入、命令、版本/commit/ref 与 adapter/backend，分别记录实际 `status` 和 `assurance`；区分准入、执行与科学证据，标明合成或回顾性结果。

## Validation / 验证

List checks and outcomes, or explain skips. Small docs changes need link/command/synchronization checks. A claimed L4 policy improvement needs independent research trajectories at equal total cost.
列出检查与结果，或说明跳过原因。小文档改动检查链接、命令与同步；声称 L4 策略提升需独立、等总成本的科研轨迹证据。

## Translations and publication / 翻译与公开

- [ ] Shared commands and boundaries agree across affected translations, or other versions are unaffected. / 受影响译文的共享命令与边界一致，或其他版本不受影响。
- [ ] No private logs/data, `.rds/` state, credentials, or material I cannot publish. / 不包含私人日志或数据、`.rds/` 状态、凭据或无权公开的材料。

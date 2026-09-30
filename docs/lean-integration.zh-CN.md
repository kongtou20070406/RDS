# Lean4 兼容：深度学习科研扩展

[English](lean-integration.md) · [形式化验证](formal-verification.zh-CN.md) · [规则义务](rule-obligations.zh-CN.md)

RDS 的主体是自动化辅助人类科研：调查证据、生成与筛选实验、安排执行、评估结果、复盘接续。Lean4 兼容支持其中合适的数学子问题。当前窄接口使用 Lean 的 Rat 定义；更广接入应复用 Lean4 和 [mathlib](https://github.com/leanprover-community/mathlib4)，由 RDS 提供模型／性质适配、实验义务及证据绑定。RDS 不应重新实现 Lean 的逻辑，也不能把名为 `linarith` 的 Python 方法当作 Lean 的算术 tactic。

本页区分已实现的窄接口和更广的接入设计。当前 `main` 已包含 [PR #2](https://github.com/kongtou20070406/research-direction-selector/pull/2) 在 `995e8eb` 引入的原生闭合有理数适配器。较早的 `f020b2c` 基础版本不包含该接口；更广的模型／mathlib 接入仍是后续工作。

## 已实现的闭合有理数接口

`kind: lean_obligation` 在 `scripts/rds_verify.py` 中注册为 `lean.rational_relation`，可通过 `formal` CLI 的 `rule` 或 `lean4` 路径调用。它只接受 `schema`、`kind`、`relation`、`left`、`right` 这五个字段：schema 为 1，命题是闭合有理数的 `eq`、`lt` 或 `le` 关系，数值使用精确有理数常量，不接受 JSON 浮点数。现有示例为：

```json
{"schema":1,"kind":"lean_obligation","relation":"lt","left":"1/2","right":"3/4"}
```

使用当前 `main` 或 v5.5.0-rc.2，将下面路径替换为已有原生 Lean4 工具链程序的绝对路径。适配器不会下载工具链，拒绝 elan 和 `.elan/bin` shim。

```powershell
$env:RDS_LEAN_EXECUTABLE = 'C:\path\to\native-toolchain\bin\lean.exe'
python -B scripts/rds_cli.py --root . formal verify --spec examples/formal/lean_obligation.json --output lean-proof.json --tactics lean4
python -B scripts/rds_cli.py --root . formal check --spec examples/formal/lean_obligation.json --certificate lean-proof.json
```

固定模板使用 Lean 的 Rat 定义与 `by decide` 证明 `RDS.obligation`。适配器以 `--trust=0` 调用 Lean，并要求完全匹配的空公理审计结果。独立检查重新渲染期望模板，核对声明／源码绑定、程序指纹和版本，再次调用 Lean。它不重放已保存的 `.olean` 证明对象，也不把缓存 stdout 当作证明。

接受的原子结果为 PASS / `LEAN_KERNEL_CHECKED`，后端是 `backend: lean4_closed_rational`，语义为 `semantics: closed_Lean_Rat_relation`。假命题、工具缺失、编译失败和资源限制当前均产生 UNKNOWN / `NONE`，不是已检查的反驳。CLI 对 PASS／FAIL／UNKNOWN 的退出码是 0／1／2；该原生适配器当前不产生 FAIL。含原生叶子的有限定理模块外层仍为 `CERTIFICATE_CHECKED`。

`formal check` 接受框架证书或完整框架结果，重新构造结论；底层原生检查器接受自己的领域证书并重复原生检查，两种格式不同。任意 Lean 文本、用户 tactics、通用 mathlib 翻译和实际训练图的证明仍不支持；数学侧条件不能建立实用收益或因果性。见[全部注册 kind 与证据边界](formal-verification.zh-CN.md)和[版本化实现契约](https://github.com/kongtou20070406/research-direction-selector/blob/995e8eb98f75697ef1ce43a9991f0686e5c29caa/references/formal_framework.md)。

## 分工

更广的接入设计按下表分工。当前闭合有理数适配器不实现通用模型翻译或完整的后续证明请求契约。

| 组件 | 职责 |
| --- | --- |
| Lean4 / mathlib | 表达数学命题，使用已有定义与引理，生成证明项，并由真正的 Lean 内核检查。 |
| RDS 模型适配器 | 只将支持的算子翻译成明确的数学模型，绑定参数、形状、定义域与数值语义；拒绝不支持算子。 |
| RDS 义务适配器 | 将有范围规则的代数子命题映射为准确的期望定理，保留假设与量词。 |
| 证明桥接 | 固定工具链与库版本，识别期望定理，收集证明产物，审计公理并复核结果。 |
| 实验运行器 | 检查授权、预算、数据暴露和实际执行，生成独立收据与观测。 |
| 科研评估 | 解释实际任务收益、干预有效性和机制证据；实证观测不能变成证明未来性能的公理。 |

23 个方法论规则是义务目录，其来源、公平比较与实证条件不能全部由数学定理解决。先支持可达质量公式、参数边界、准确指定的有限线性映射等局部代数义务；资源可行性的实测和因果归因分别保留对应证据。

## 建议的证明请求契约

桥接请求需要版本化记录：规则 ID、可信的期望定理及引用定义、完整模型与声明摘要、假设和量词及定义域、数值语义、Lean／工具链／mathlib 版本，以及检查策略。这些是设计要求，不是当前通用 `hypothesis.formal` 已接受的字段。

证明证据应指明被检查的定理、模块、证明或声明产物、公理依赖和检查器版本。缓存键须绑定完整请求与检查器依赖；权重、算子、假设或版本改变后，不能因自然语言名称相同继续使用旧证明。

实际检查点权重可以在实数模型中表示为精确有理数；数学证明随后针对该声明抽象，表示本身不是证明。浮点推理、autograd、训练更新和导出等价需要额外的明确语义及证据，不能由这层抽象自动推出。

## 更广接入的接受条件

1. 独立于候选证明构造期望定理，审计定义和模型绑定。
2. 在固定版本的 Lean 项目内构建，并识别所检查声明；编译无关文件成功不够。
3. 查看定理的公理依赖，拒绝使用 `sorryAx` 的未完成证明与未批准公理；实证前提须有自己的证据，不能静默断言。
4. 用对应 Lean 检查器复核存储声明；部署需要时，加入可信目标比较与外部复核。
5. 将有范围的数学结果与运行器、科学评估分别返回。

Lean 的[证明验证指南](https://lean-lang.org/doc/reference/latest/ValidatingProofs/)说明了公理检查、`lean4checker --fresh` 和可信目标比较。实验期间应固定匹配的 [Lake](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/) 与 mathlib 依赖，避免跟随持续变化的分支。

证明搜索或编译失败，只表示尚未获得可接受证明，不表示命题为假。数学负结论需要检查过的反例或对应否定命题的证明；资源上限和不支持模型仍是不确定。历史上另一份本地 prototype 的 `LEAN_TACTIC_PROVED` 与 `LEAN4_CERTIFIED` 标识不满足这些条件，不是当前原生适配器的验证依据。

## 迁移顺序

保留现有 CLI 的标量实验计量和已实现的闭合有理数桥接。下一步利用已有 mathlib 定义扩展绑定源码的代数或模型义务，检查成立、不成立、无关定理、未完成证明、源码变化和缺失工具链案例；单独验证导出对应关系。每个新适配器的绑定与检查条件通过后再扩展准入；当前声明路径接纳数学侧条件，不自动证明训练图等价。

优先复用 Lean 已有证明器和检查器。C++ 可以在测量后服务于解析、序列化或数值适配的瓶颈，不作为再造证明器的理由。证明检查、缓存与 SQLite 事务耗时分别测量，提供可复现输入与延迟分布；选用 C++ 不会自动带来 GPU 加速或整个系统的毫秒级保证。

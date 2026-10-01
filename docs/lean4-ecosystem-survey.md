# Lean 4 生态、深度学习形式验证与 RDS 接入评估

核查日期：2026-10-01，Asia/Shanghai。面向 RDS 当前 L2/L3 交付，长期服务更高自治能力。本文区分上游已实现的能力、源码/API 核查、RDS 已验证的集成，以及尚待实现的工程方案。调研使用原始论文、官方仓库、固定源码和官方文档；未安装大型验证器、下载证明模型或运行 GPU 基准。文中的外部工具示例是接入草案，不能作为已完成集成的证据。

## 1. 建议先做什么

**当前主线采用 A 的数学库基础，加上逐步建设的 B 证书核验。** 保留有限命题和独立核验入口，直接复用 Mathlib 已有定理；对小型 Linear/ReLU 网络先评估 LeanCert Core；用 auto_LiRPA / α,β-CROWN 提出数值界、反例和待验证候选。需要更大范围证明产物时，再对 Marabou 的具体证书子集做桥接。C-FFI 用于加速计算，不因调用发生在 Lean 内就获得证明资格。

这个推荐有三个限定：B 并没有现成覆盖所有模型与算子的通用 Lean 适配器；证书核验未必很快；形式证明只涵盖精确定义的模型、规格和前提，不能证明实际训练自动符合它们。

| 复用优先级 | 工具或成果 | RDS 直接用途 | 本阶段动作 |
|---|---|---|---|
| 立即复用 | Mathlib 的 Hoeffding、条件 Azuma–Hoeffding、Markov、鞅与分析基础 | 提供有明确假设的统计/数学义务，阻止错误使用结论 | 固定版本，薄包装和实际消费者；不重复推导基础定理 |
| 近期小范围验证 | LeanCert Core 的有理数区间与 ReLU 网络 enclosure | 核验小网络的界、鲁棒性和收缩侧条件，改变候选可执行性 | 先对有限网络格式做命题与公理审计，再做正负样例 |
| 近期候选生成 | auto_LiRPA / α,β-CROWN | 大模型界估计、困难规格和反例线索 | Python 侧车，结果保留来源和未核验状态 |
| 需求出现后优化 | community REPL；LeanInteract 包装；Kimina 进程池 | 减少重复启动/import，把可用预算投入更多有用检查 | 先测本地真实瓶颈；最终产物仍独立重放 |
| 后续证书桥接 | Marabou 的 UNSAT/Alethe 证书，Imandra checker 先例 | 减少外部求解器进入可信基的范围 | 针对支持子集迁移 soundness 与具体重放，不从 SAFE 标签推论 |
| 可选搜索辅助 | LeanCopilot、Pantograph、DeepSeek/Goedel/Kimina 系列 | 补全形式证明、选择前提、探索 tactic 分支 | 与裁决器隔离，完整证明和原始命题共同验收 |
| 架构/检索参考 | Vehicle、TheoremGraph、AlphaProof Nexus | 规格与模型绑定、查找前提、分解问题和保存证明 | 复用现成接口和公开成果，不整套重建搜索基础设施 |
| 暂缓主线依赖 | SciLean 全量引入、LeanDojo-v2 训练栈、通用 C++ checker FFI | 对当前交付并非必需；版本或可信边界成本较高 | 仅在具体问题需要时隔离试验 |

逐项原始证据、版本和许可见后文。优先级是基于 RDS 现阶段需求的工程判断，没有声称这些工具已改善本项目科研收益。

## 2. 版本基线与“可直接用”的含义

官方发布接口本次确认 **Lean v4.34.1 与 Mathlib v4.34.1 均为最新稳定版，发布于 2026-09-24**。用户已允许升级。RDS 原生开发线的此前已验证基线为 4.33.1；升级后的验收必须来自该具体源码、工具链和依赖锁的真实构建，不以改动版本字符串代替兼容测试。[Lean release](https://github.com/leanprover/lean4/releases/tag/v4.34.1)、[Mathlib release](https://github.com/leanprover-community/mathlib4/releases/tag/v4.34.1)

当前集成树的 `formal/lean-toolchain` 与 `formal/lakefile.lean` 仍固定 **Lean/Mathlib 4.33.1**。下文的 4.34.1 配置是升级草案，不是当前安装命令或已通过的兼容结果；原生统计构建、真实证书重放与最终源码状态见[协作账本第八章](collaboration-ledger.md#八最终集成审查2026-10-01)。最新上游版本、项目依赖版本和外部组件兼容版本分别记录。

“拿来用”分三层：直接使用独立 CLI/Python API；经过少量 schema/版本适配后使用；仅可复用论文或核心理论、仍需新 checker。后文逐项说明，不把三层统称即插即用。Lean 包与 `.olean` 紧密依赖工具链；SciLean、TorchLean、REPL 和模型训练环境各自的版本不能未经检查混装。

## 3. A/B/C 三条附属工程路线

| 维度 | A：纯 Lean Lake 附属库 | B：外部搜索 + Lean 证书核验 | C：C-FFI / `extern_lib` |
|---|---|---|---|
| 主要工作 | 定义对象并证明通用性质，实例化已有定理 | 外部寻找 witness/certificate；Lean 检查每条可验证条件 | 将高性能计算实现接到 Lean runtime |
| 最适合 | 收敛/收缩定理、有限精确侧条件、Mathlib 统计包装 | 小网络区间界、线性松弛、有限分支证书、可复核反例 | 推理、预处理、搜索、批量数值计算 |
| 性能特点 | 编译/import 可复用；大张量归约和证明项可能昂贵 | 搜索可利用 GPU/多核；检查复杂度取决于证书与表示 | 接近原生库性能，但有 FFI/内存管理成本 |
| 新工程量 | 低到高：已有定理的薄包装低；新网络语义高 | 中到高：已有 checker 低；新证书格式/soundness/数值语义高 | 绑定较易；把外部结果升级为证明仍需额外工作 |
| 可信边界 | Lean 内核、允许公理及精确 imports；数值执行语义另证 | checker soundness、具体接受证明、完整输入绑定与 Lean 内核 | 若直接信任外部判定，C/C++ 实现及相关工具链仍在可信基内 |
| 对 RDS 的作用 | 将明确理论要求放到执行门禁前 | 以可核验依据排除或放行候选，支持失败定位 | 提高提案/搜索吞吐；本身不改变证据等级 |

### 3.1 路径 A：最小 Lake 依赖

以下是匹配稳定版本的配置草案，实际应使用开发分支生成并审查过的 `lake-manifest.json`：

```lean
import Lake
open Lake DSL

package rdsFormal

require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git" @ "v4.34.1"

lean_lib Formal
```

`formal/lean-toolchain` 同时写为 `leanprover/lean4:v4.34.1`。从 `formal` 执行 `lake update`、按该版本说明获取 Mathlib cache，再 `lake build`；将锁文件纳入版本控制。SciLean 等包需要先检查其所需 Lean/Mathlib 与本组合是否兼容，不能简单追加依赖后声称可信。

RDS 的 Python 适配应使用固定的模块/定理注册表和有限输入格式，保留已有超时、内存和输出边界。源码生成、目标命题、编译结果与证书重放须绑定同一输入；更换依赖会使旧构建产物失效。

### 3.2 路径 B：真正需要证明的链条

证书架构至少要闭合以下关系，不能只运行一个返回 `True` 的外部程序：

```text
研究规格、模型权重、输入域、算子语义
    → 外部搜索提出 certificate
    → Lean 中的 check(model, spec, certificate) = true
    → 已证明的 checker_sound
    → 对该 model / spec 的形式命题
    → 独立检查实验适用条件与实际执行一致性
    → RDS 的候选资格、采样、停止或复审决定
```

可信桥接的核心形式是 `check m s c = true → satisfies m s`。通用 soundness 定理和具体输入上 `check = true` 的证明缺一不可。对分支定界，还要保证分支覆盖完整；对线性松弛，需验证每条松弛不等式及组合；对反例，需验证输入属于规定域且在同一语义下违反规格。

浮点求解器的数不能直接当精确实数证明。可把有限二进制浮点值按精确有理数导入，再用有向舍入/有理数区间证书验证；但“以这些权重定义的实数网络”与“部署中的 IEEE 浮点网络”仍是不同规格。归一化、算子转换、输入边界、权重顺序和严格/非严格不等式都必须绑定。

普通 proof term/`decide`、`decide_cbv` 与 `native_decide` 的信任边界也不同。后者会引入编译后执行的信任；最新 Lean 的 `decide_cbv` 采用可核验的归约证明路线，但可用性与限制须按固定版本确认。不能统一写成“极速、零开销、绝对可信”。[Lean tactic reference](https://lean-lang.org/doc/reference/latest/Tactic-Proofs/Tactic-Reference/)

建议的首个桥接对象是与 RDS 当前有限网络/有理数输入相近的小型 Linear/ReLU 区间证书。先覆盖正确证书、伪造权重、错误输入域、坏舍入、漏分支、错误规格及超时，再考虑大型 ONNX 图。这是新增开发建议，本次调研没有实现该适配器。

### 3.3 路径 C：执行接口不自动成为证明接口

Lake 的 `extern_lib` 可以构建/链接外部对象与静态库，Lean 的 `@[extern ...]` 声明可对应 C ABI。具体构建要处理平台、Lean runtime 对象、所有权和动态库路径。最小路线是让外部函数返回候选数据，再走 B 的 checker；若直接把外部布尔判定当命题真值，就必须明确把该实现列入可信基。[Lake 外部库](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/)、[Lean C FFI](https://lean-lang.org/doc/reference/latest/Run-Time-Code/Foreign-Function-Interface/)

当前 Python 已可调用成熟验证器，因此在没有性能剖析证据之前，把求解器再移到 Lean FFI 不会天然提高科研决策质量。FFI 可以提升吞吐，不能代替规格一致性和独立核验。

## 4. AlphaProof、检索图与开放证明模型

### AlphaProof 的最新研究应看 Nexus

2026 年 *Advancing Mathematics Research with AI-Driven Formal Proof Search*（本次核查 v2，2026-06-08）提出 AlphaProof Nexus，面向研究级问题，报告在其选定的 Erdős/OEIS 问题集中获得形式化结果。其价值是展示自然语言推理、任务分解与形式搜索如何合作；这不证明 RDS 已拥有同样能力。[原始论文](https://arxiv.org/abs/2605.22763v2)

官方公开的 [alphaproof-nexus-results](https://github.com/google-deepmind/alphaproof-nexus-results) 是结果和证明材料，不能视为完整可安装的训练/搜索系统。仓库区分软件 Apache-2.0 与其他材料 CC-BY-4.0，并需尊重第三方来源。RDS 可复用公开证明、任务组织和失败归档方式；当前不应为了“复现 AlphaProof”建设一个新的大规模训练服务。

### TheoremGraph：检索线索和形式依赖要分层

2026 年 TheoremGraph 把非形式文献中的候选依赖与 Lean 声明依赖连接起来。其 LeanGraph 抽取类型、证明、定义等不同边；跨自然语言/形式语句的语义匹配仍包含模型判断。这样的边可帮助找前提、发现近似重复结论，不能直接写入 RDS 的“已证明事实”。[论文](https://arxiv.org/abs/2606.25363)、[TheoremSearch 仓库](https://github.com/uw-math-ai/TheoremSearch)

现有 REST 接口支持 `/graph/embedding` 的 formal/informal 检索，再用 `/graph/statement/{id}` 读依赖邻域；另有 `/search` 与 MCP `theorem_search`。先使用现成查询而非本地复制整个图；结果保留来源、edge_type、形式化声明与原文位置。下列是未执行的标准库调用示意，仅发送公开数学查询：[官方 API](https://www.theoremsearch.com/docs)

```python
import json
from urllib.parse import urlencode
from urllib.request import urlopen

query = urlencode({"query": "Hoeffding bounded independent random variables",
                   "formality": "formal", "n_results": 5})
with urlopen("https://api.theoremsearch.com/graph/embedding?" + query, timeout=15) as r:
    candidates = json.load(r)
```

实际获益应验证：是否少重复推导、是否找到更匹配的已有命题、是否更快改变候选资格。图规模和检索命中数不能代替这些结果。

### MiniF2F 与可复用模型

| 项目 | 定位及已核实公开内容 | 接入与 RDS 判断 |
|---|---|---|
| [MiniF2F Lean 4](https://github.com/yangky11/miniF2F-lean4) | 固定数学题目的形式证明基准，不是证明引擎 | 用于 prover 接口的回归/迁移探针；保留自身 toolchain，不把其通过率当作 DL 验证或研究策略收益 |
| [DeepSeek-Prover-V2](https://github.com/deepseek-ai/DeepSeek-Prover-V2) | 公开 Lean 4 证明模型与递归子目标分解方法；DeepSeek-V3 是其中使用的基础模型名称，不等于已确认存在 Prover-V3 | 作为可替换候选证明生成器；固定模型、采样预算、Lean 环境并独立重放。无需放进当前 CPU/统计门禁关键依赖 |
| [Goedel-Prover-V2](https://github.com/Goedel-LM/Goedel-Prover-V2) | 8B/32B 开放证明模型；ICLR 2026 论文讨论分层数据、自纠正等 | 官方运行说明仍采用 Lean4.9 与对应 Mathlib，不能当4.34.1即插即用；按相同预算比较适配后的有效证明产出。[论文](https://arxiv.org/abs/2508.03613) |
| [Goedel-Code-Prover](https://github.com/goedelcodeprover/Goedel-Code-Prover) | 2026 年层级代码验证证明搜索，将分解与补全分开 | 对未来校验实现性质有参考价值；代码验证题目通过率不等价于研究发现能力。[论文](https://arxiv.org/abs/2603.19329) |
| [Kimina](https://github.com/project-numina/kimina-lean-server) | 大批量 Lean 验证服务，可与证明模型配合 | 先复用 server 与已验证协议；不把模型、服务器和 checker 当同一组件 |

模型代码许可证、权重许可证、训练数据条款须按所选具体 release 分开记录；上表不凭“开放模型”字样推断所有产物都可任意再分发。不同 pass@k、计算预算、题集和版本的论文成绩不可直接排序。

## 5. 与 RDS 决策和资源利用的对应

本报告的接入次序以实际研究判断为依据：理论门禁应能影响候选是否执行；统计前提不闭合时应要求补证据；反例应改变范围或下一实验；超时应返回 UNKNOWN 并保留成本和重试条件。通用统计定理的条件证明不能自动成为真实数据上的统计结论。

资源政策同样重要。形式搜索和实验的预算上限是约束，不是“越省越好”的目标。已有空闲 GPU 可以承担多个彼此独立、能改变决策的候选；持久 REPL/进程池也可以利用 CPU 并行检查。分别记录累计资源用量、实际完成时间、可用容量、增量付费和等待机会成本，不能用低 GPU-hours 单独否决更快得到答案的方案，也不能为了占满硬件安排无效重复任务。

| 阶段 | 最小验收 | 决策改变 | 资源与信任记录 |
|---|---|---|---|
| 当前交付 | CPU 正常/最优初值/更新偏离；形式 FAIL/UNKNOWN 留存与下一轮读取；真实 native/统计检查 | 执行、停止重复、修实现、改范围或补应用前提 | 固定源码与版本；形式和经验成本均可追溯；实际预算范围明示 |
| 小网络 checker | 同一精确网络在 Python proposer 与 Lean checker 间往返；坏证书拒绝 | 候选规格通过、否决或未知 | 模型/域/规格/舍入绑定；检查 walltime、峰值内存和证书大小 |
| 批量形式请求 | 冷/热进程和必要并发比较；独立最终重放 | 同一窗口内更多有效候选完成，或更早做出实验选择 | 统计启动/import/排队/重试全成本；不只报每请求最快时间 |
| 证明模型辅助 | 在冻结的项目义务上比较有无 proposer | 少人工翻译、更少无效分支、较早闭合关键前提 | 相同总预算及可用硬件窗口；所有人工介入和未完成项 |

每项仍遵循四问：回答什么疑问；必要门禁是否前置；原始结果如何改变后续行动；失败是否被保存且下一轮实际读取。L2/L3 工程闭环、论文上的模型成绩和 L5 终极目标分别陈述。

## 6. 深度学习验证工具详表与接入示例

核查日期：2026-10-01（Asia/Shanghai）。本片段检查官方仓库、当前源码、项目文档及正式论文；没有安装或运行这些验证器，没有 GPU 实测，也没有编译下列示例。代码标为“API 已核对”，不标为“已通过运行”。提交日期只表示本次找到的默认分支快照，不代表发布日或算法完成度。

### 结论与推荐路线

建议分两步推进：先用 **auto_LiRPA / α,β-CROWN 做候选界、反例和性能基线，用 LeanCert Core 的小型 ReLU 网络定理建立可核验基线**；确实需要消费外部大求解器证据时，再做 Marabou 的有限范围证书桥接。Vehicle 优先作为“统一规格、模型身份、验证缓存、ITP 接口”的架构参考。ERAN 适合 DeepPoly 算法对照；VeriNet 和 NNV 不建议作为本项目第一条 Python→Lean 接入路径。这是结合下述兼容性和信任边界的工程判断，不是已完成的性能比较。

必须区分四件事：算法论文中的 soundness、求解器返回 `safe/unsat`、独立程序接受 certificate、Lean kernel 接受该具体命题的证明。前两项不能直接替代后两项；“有 Lean soundness theorem”也不能省略对具体输入和证书接受结果的证明。

| 工具 | 本次确认的输出/证据 | Lean 4 接入状态 | 对 RDS 的优先级 |
|---|---|---|---|
| auto_LiRPA / α,β-CROWN | 数值上下界、线性松弛参数、搜索结果/反例；API 未承诺独立 proof replay | 未找到将当前标准输出直接导入 LeanCert 的官方适配器 | 高：Python 候选生成、复杂模型基线 |
| Marabou | 判定、反例；可生成 UNSAT 证书；最新源码含 Alethe 写出 | 已有 Imandra 认证 checker 先例；不等于现成 Lean checker | 高：外部证书研究路径；中：立即集成 |
| ERAN | 抽象解释界、鲁棒分类判定、可选 LP/MILP 精化 | 本次范围未找到独立证书→Lean 接口 | 中：DeepPoly/浮点界对照 |
| LeanCert Core / SDK | Lean 中的网络 enclosure 定理；Python checked forward interval；部分通用数值证据可单独 kernel replay | 有现成 Lean 4 组件，但不等于通用 ONNX 或 CROWN/Marabou 证书导入器 | 高：小范围可信核；SDK 另看许可 |
| Vehicle | 规格编译、验证缓存/模型身份与 ITP 代码 | 2026 文献/源码面向 Agda、Rocq、Isabelle、Imandra；未确认 Lean 后端 | 高：系统组织先例；中低：本项目直接运行依赖 |
| VeriNet / NNV | 符号区间与分支搜索 / reachable sets 与判定 | 本次未确认独立证书→Lean 链路 | 低：首轮复用；保留相关对照 |

表格依据见各工具小节；“未找到”始终是有界检索结果。

### 1. α,β-CROWN 与 auto_LiRPA

#### 当前版本、依赖与接口

- α,β-CROWN 核查快照为 [`e5c7e17`](https://github.com/Verified-Intelligence/alpha-beta-CROWN/commit/e5c7e17bf0488843acb77b7519f59876717a49f4)，提交日期 2026-06-16。当前包元数据版本 `abcrown 0.7.0`，要求 Python `~=3.11.0`、`torch==2.11.0`，还带 ONNX、ONNX Runtime、onnx2pytorch 等转换依赖；**不能按“任意新版 Python/PyTorch 均可”部署**。[包元数据](https://github.com/Verified-Intelligence/alpha-beta-CROWN/blob/e5c7e17bf0488843acb77b7519f59876717a49f4/pyproject.toml)
- auto_LiRPA 核查快照为 [`5a098e8`](https://github.com/Verified-Intelligence/auto_LiRPA/commit/5a098e8f9fb5786a428a024981d833d303921f2d)，提交日期 2026-06-11。当前元数据要求 Python `~=3.11.0`、PyTorch `>=2.0.0,<2.12.0`、NumPy `>=2.0.0`；README 的宽泛描述应让位于实际安装元数据。[元数据](https://github.com/Verified-Intelligence/auto_LiRPA/blob/5a098e8f9fb5786a428a024981d833d303921f2d/pyproject.toml)
- 两项目均声明 BSD-3-Clause。α,β-CROWN 普通界传播/BaB 路径与 MIP/CPLEX-cut 路径的商业求解器需求应分开检查；包列表含 `gurobipy` 不等于每次验证都要求商业 Gurobi 许可证。GPU 环境要求和安装步骤以固定提交 README 为准。[α,β-CROWN 许可证](https://github.com/Verified-Intelligence/alpha-beta-CROWN/blob/e5c7e17bf0488843acb77b7519f59876717a49f4/LICENSE)、[安装和算法配置](https://github.com/Verified-Intelligence/alpha-beta-CROWN/tree/e5c7e17bf0488843acb77b7519f59876717a49f4)

高层 API 已提供 `ABCrownSolver`、`IOConstraints`、`ConfigBuilder`、`input_vars`、`output_vars`。`verify` 返回 `safe / unsafe-pgd / unsafe-bab / safe-incomplete / unknown`；`compute_bounds` 返回上下界，可要求线性界；`minimize/maximize` 的可行原始解搜索不能自动当全局最优证明。API 对输出规格只接受严格 `<, >`。因此 RDS 接口必须保留状态、时间限制和规格，不能将一个 `success` 布尔值概括为所有任务都完成。[高层 API](https://github.com/Verified-Intelligence/alpha-beta-CROWN/blob/e5c7e17bf0488843acb77b7519f59876717a49f4/complete_verifier/docs/abcrown_api.md)

#### 最小 Python 接入（API 已核对，未执行）

先用 auto_LiRPA 做两输入、单输出 ReLU 网络的界传播。这个模型有整数权重，便于与 Lean 端完全对齐。

```python
import numpy as np
import torch
from torch import nn
from auto_LiRPA import BoundedModule, BoundedTensor, PerturbationLpNorm

model = nn.Sequential(nn.Linear(2, 2), nn.ReLU(), nn.Linear(2, 1)).eval()
with torch.no_grad():
    model[0].weight.copy_(torch.tensor([[2., -2.], [-2., 2.]]))
    model[0].bias.zero_()
    model[2].weight.copy_(torch.tensor([[1., 1.]]))
    model[2].bias.zero_()

center = torch.zeros(1, 2)
bounded = BoundedModule(model, center)
region = BoundedTensor(center, PerturbationLpNorm(norm=np.inf, eps=1.0))
lower, upper = bounded.compute_bounds(x=(region,), method="backward")
print(lower, upper)
```

调用形状对应官方快速示例；以上自定义小网络是本次构造的探针，不是项目报告的 benchmark。[auto_LiRPA 官方入口](https://github.com/Verified-Intelligence/auto_LiRPA/tree/5a098e8f9fb5786a428a024981d833d303921f2d)

同一 `model` 可接 α,β-CROWN 的高层接口，验证整个输入盒中 `y < 5`：

```python
from abcrown import ABCrownSolver, IOConstraints, ConfigBuilder, input_vars, output_vars

x, y = input_vars((2,)), output_vars(1)
spec = IOConstraints(
    input_vars=x, output_vars=y,
    input_constraint=(x >= -1) & (x <= 1),
    output_constraint=y[0] < 5,
)
cfg = ConfigBuilder.from_defaults().set("general/device", "cpu")
result = ABCrownSolver(model, x, y, config=cfg).verify(constraints=spec)
print(result.status, result.success)
```

#### 能复用什么，仍缺什么

可以复用的是 PyTorch/ONNX 前端、候选界、攻击反例、分支策略和性能实现。`lower_A/upper_A` 一类仿射系数可成为未来证书格式的数据来源；**单独这些系数尚未证明每层松弛、父子分支覆盖、舍入误差和最终安全性**。当前文档没有把这些返回值定义为独立 checker 可接受的完整证明记录。[返回结构和线性界](https://github.com/Verified-Intelligence/alpha-beta-CROWN/blob/e5c7e17bf0488843acb77b7519f59876717a49f4/complete_verifier/docs/abcrown_api.md)

RDS 具体卡点：ONNX→PyTorch 翻译与预处理语义；浮点权重到实数/有理数解释；节点松弛有效性；分支覆盖；数值误差和超时状态。建议把求解器视作不可信候选生成器，从一层 affine+ReLU 的有理系数证据开始，而不先移植完整 GPU 验证器。这是设计建议；本次未实现桥接。

### 2. Marabou：最新证书出口比旧综述更强，但还没到 Lean 证明

#### 版本与运行环境

核查快照 [`1c2f478`](https://github.com/NeuralNetworkVerification/Marabou/commit/1c2f4788c32e2f4e407c356b763a8025c5578722)（2026-06-18）合入了 [Alethe proof generation PR #894](https://github.com/NeuralNetworkVerification/Marabou/pull/894)。GitHub 最近标记的稳定发布为 [v2.0.0](https://github.com/NeuralNetworkVerification/Marabou/releases/tag/v2.0.0)（2024-04-12），所以“最新源码功能”和 `pip install maraboupy` 某个 wheel 的功能不能混同。

核心为 C++，Python 通过 `maraboupy`；支持 ONNX 和 VNNLIB 等输入。当前 README 列出 Python 3.8–3.11、CMake/Boost/OpenBLAS/pybind11，面向 Linux/macOS；Windows 不再在其支持范围内。原生 Windows 用户宜隔离到受支持 Linux 环境后再评估。核心采用三条款 modified BSD，依赖各自保留许可。[安装文档](https://github.com/NeuralNetworkVerification/Marabou/tree/1c2f4788c32e2f4e407c356b763a8025c5578722)、[COPYING](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/COPYING)

#### 必须拆开的三条证据路线

1. **普通搜索结果**：`sat` 给赋值，`unsat` 表示约束系统无解，另有 timeout/unknown。把安全规格取反后得到 `unsat` 才对应原安全命题；直接看到 `unsat` 不能省略查询规格。
2. **内部证明生产/检查**：Python 的 `createOptions(produceProofs=True)` 和 CLI `--prove-unsat` 已存在；证明模式选择 native LP。普通证书激活支持列表为 ReLU、Sign、AbsoluteValue、Max、Disjunction、LeakyReLU。内置 checker 是 C++/浮点实现，不能直接称作 kernel proof。[Python 选项](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/maraboupy/Marabou.py)、[选项处理](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/src/configuration/Options.cpp)、[支持激活](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/src/proofs/UnsatCertificateUtils.cpp)
3. **Alethe 外部证书**：新 `AletheProofWriter` 当前只列 ReLU；`WRITE_ALETHE_PROOF` 是源码配置常量，默认 `false`。不能声称 Python 的 `produceProofs=True` 自动开启 Alethe 导出。启用该构建路径后，`Engine::certifyUNSATCertificate` 写 `.smt2` 与 `.smt2.alethe`，明确说明仍须单独认证。[Alethe writer 支持集合](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/src/proofs/AletheProofWriter.cpp#L853)、[默认配置](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/src/configuration/GlobalConfiguration.cpp#L118)、[写出过程](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/src/engine/Engine.cpp#L3724)

#### 已存在的形式化 checker：Imandra，而非 Lean 4

ITP 2025 的 *A Certified Proof Checker for Deep Neural Network Verification in Imandra* 正式发表于 2025-09-22，给出 Marabou 证书检查的形式化正确性工作。因此“神经网络验证没有认证 checker”已经不成立。但论文仍把从 Farkas/约束证据提升到完整 DNN 查询、认证规格编译列为后续工作；用于加速的 ReLU theory lemmas 已实现但还需认证其 soundness。该工作不能无条件覆盖今天所有 Marabou 算子和最新 Alethe 输出。[正式论文与作者源码入口](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ITP.2025.1)、[全文 §7.2](https://drops.dagstuhl.de/storage/00lipics/lipics-vol352-itp2025/html/LIPIcs.ITP.2025.1/LIPIcs.ITP.2025.1.html)

对 RDS 最有价值的移植对象是：精确线性组合/Farkas 检查、分支树覆盖、ReLU 分支/理论引理、查询与证书身份绑定。不要把“读取 Alethe 文件成功”当成“其规则已全部在 Lean 中证明正确”。本次没有核实 Marabou Alethe 与任一 Lean SMT checker 的规则集兼容性，列为待做兼容性探针。

#### 最小 Python 接入（API 已核对，未执行）

假定 `controller.onnx` 恰好有两个输入坐标、一个输出，权重/算子为约定的小网络；查询是否存在输入令 `y ≥ 5`。

```python
from maraboupy import Marabou

net = Marabou.read_onnx("controller.onnx")
inputs = net.inputVars[0].flatten()
output = net.outputVars[0].flatten()[0]
for variable in inputs:
    net.setLowerBound(variable, -1.0)
    net.setUpperBound(variable, 1.0)
net.setLowerBound(output, 5.0)
options = Marabou.createOptions(timeoutInSeconds=30, produceProofs=True)
status, values, stats = net.solve(options=options)
print(status)
```

此代码只展示查询和内部 proof mode；没有承诺生成 Alethe 文件或输出 Lean artifact。ONNX 文件本身没有在本次生成。[`read_onnx/createOptions`](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/maraboupy/Marabou.py)、[`solve` 返回值](https://github.com/NeuralNetworkVerification/Marabou/blob/1c2f4788c32e2f4e407c356b763a8025c5578722/maraboupy/MarabouNetwork.py#L55)

### 3. ERAN：DeepPoly 基线，数值可靠性不能一概而论

本次默认分支最近提交为 [`8771d31`](https://github.com/eth-sri/eran/commit/8771d3158b2c64a360d5bdfd4433490863257dd6)（2022-05-30），不是 2026 新版。项目实现 DeepZ/DeepPoly 及精化、GPU 等路径；许可证 Apache-2.0。安装说明沿用 TensorFlow、ELINA、GMP/MPFR、Gurobi 等较旧组合，集成成本不能按一个现代 `pip install` 包估算。[官方仓库和安装文档](https://github.com/eth-sri/eran/tree/8771d3158b2c64a360d5bdfd4433490863257dd6)

README 明确区分浮点可靠性：其界传播的相关实现考虑浮点 soundness，而 RefineZono/RefinePoly 中调用的 (MI)LP 不在同一承诺内。不能把“ERAN 支持浮点可靠分析”扩张为“所有域、所有精化模式和商业 LP 调用都已形式化认证”。这也不等于已导出 Lean 可核验的逐次证明。[官方 soundness 说明](https://github.com/eth-sri/eran/tree/8771d3158b2c64a360d5bdfd4433490863257dd6)

实际 Python 入口是 `tf_verify/eran.py` 中的 `ERAN(model, session=None, is_onnx=False)` 与 `analyze_box(...)`；返回鲁棒支配类别及界等分析结果，不是 Lean 证明。[接口源码](https://github.com/eth-sri/eran/blob/8771d3158b2c64a360d5bdfd4433490863257dd6/tf_verify/eran.py)

```python
# 在按 ERAN 安装说明设置好 tf_verify 导入路径的环境中使用。
import numpy as np
import onnx
from eran import ERAN

model = onnx.load("controller.onnx")
analysis = ERAN(model, is_onnx=True).analyze_box(
    specLB=np.array([-1.0, -1.0]),
    specUB=np.array([1.0, 1.0]),
    domain="deeppoly",
    timeout_lp=1.0,
    timeout_milp=1.0,
    use_default_heuristic=True,
)
print(analysis)
```

这是调用入口示例；ERAN 的默认目标是分类支配关系，上述单输出 toy model 不构成有意义的分类鲁棒性 benchmark。对 RDS 应先选符合接口的分类网络及归一化规则，再比较界；本次不臆造其证书导出 API。

### 4. LeanCert：现成 Lean 组件确实存在，须按定理逐项验收

#### 快照与许可不能合并成一个标签

- **Core**：[`7f91b6e`](https://github.com/alerad/leancert/commit/7f91b6eb3567437f6cfac03ed279706603ee22f4)（2026-09-29），当前 [`lean-toolchain`](https://github.com/alerad/leancert/blob/7f91b6eb3567437f6cfac03ed279706603ee22f4/lean-toolchain) 指向 Lean `v4.34.1`；最新已查到发布为 [v4.34.0](https://github.com/alerad/leancert/releases/tag/v4.34.0)。核心 [Apache-2.0](https://github.com/alerad/leancert/blob/7f91b6eb3567437f6cfac03ed279706603ee22f4/LICENSE)。用户已允许升级 Lean，仍应固定 Core 提交与 Mathlib/Lake 依赖组合，不能仅改 toolchain 版本号。
- **Python SDK**：[`a4309c8`](https://github.com/alerad/leancert-python/commit/a4309c8f9faaed55c27c2da347fd0ea3eaf71e3a)（2026-08-19），包版本 `2.3.0`，CPython `>=3.10,<3.15`，依赖 `lean-runtime>=4.0.1,<5.0.0`、NumPy，PyTorch 为可选项。[元数据](https://github.com/alerad/leancert-python/blob/a4309c8f9faaed55c27c2da347fd0ea3eaf71e3a/pyproject.toml)
- 最新 SDK **不是整体 Apache 开源包**：官方声明后续新增部分为 evaluation/source-available 许可，允许其定义范围内的非商业研究/评估，生产、商业开发、服务部署另需书面许可；较早 `v0.3.2-apache-final` 基线、Core 和 Bridge 各自保留 Apache-2.0。文件级范围见 `LICENSE_SCOPE.toml`，其中 `nn.py` 是 mixed-origin。[SDK LICENSE](https://github.com/alerad/leancert-python/blob/a4309c8f9faaed55c27c2da347fd0ea3eaf71e3a/LICENSE)、[文件级范围](https://github.com/alerad/leancert-python/blob/a4309c8f9faaed55c27c2da347fd0ea3eaf71e3a/LICENSE_SCOPE.toml)

安装文档有版本滞后：Core 网站仍有“1.0 wheel 自带 Bridge”描述，SDK 当前 README 则说明纯 Python wheel 在第一次 checked 调用时由 `lean-runtime` 下载匹配程序。部署应以所固定 SDK 的 README、元数据和 `leancert doctor` 输出为准，不能将二者混成同一发布承诺。[SDK 当前安装和运行时说明](https://github.com/alerad/leancert-python/blob/a4309c8f9faaed55c27c2da347fd0ea3eaf71e3a/README.md)、[网站兼容页](https://docs.leancert.io/python/reference/compatibility/)

#### 已证明的范围与容易误读的名字

核心有 `Layer.mem_forwardInterval`、`TwoLayerNet.mem_forwardInterval`，在维度良构、输入逐坐标属于区间等假设下，证明真实输出属于传播得到的区间；还包含 ReLU/sigmoid 的 enclosure 与 DeepPoly 风格松弛定理。**这使“小型 Lean 4 神经网络可信核从零开始”的前提不成立。**[网络模块说明](https://docs.leancert.io/ml/neural-networks/)

但同一文档非常明确：Attention 的 `mem_scaledDotProductAttention` 当前只证明输出长度关系，尚非完整逐元素 enclosure；`QuantizedLayer.forwardQuantized_sound` 只证明计算的下端点不超过上端点。不能因为函数名含 `mem` 或 `sound`，就声称完整 Transformer、量化运行时或端到端网络已获语义保证。[精确 theorem coverage 表](https://github.com/alerad/leancert/blob/7f91b6eb3567437f6cfac03ed279706603ee22f4/docs/ml/neural-networks.md)

Python 的 `forward_interval` 当前是 Dyadic sequential ReLU 路径；转换可接两层/顺序 MLP 及部分 Transformer 结构，但转换本身不可信。`TransformerBlock` 的 Python 模型是无 attention 的简化 encoder feed-forward 部分。`verify_nn_bounds` 返回便捷布尔值，而不是 v1 `ProofResult`；有审计需求时要保存原 enclosure。[Python ML 支持边界](https://docs.leancert.io/python/ml/)

#### Python 最小探针（API 已核对，未执行）

```python
import numpy as np
import leancert as lc
from leancert.nn import Layer, TwoLayerReLUNetwork

hidden = Layer.from_numpy(
    weights=np.array([[2.0, -2.0], [-2.0, 2.0]]),
    bias=np.zeros(2), activation="relu",
)
output = Layer.from_numpy(
    weights=np.array([[1.0, 1.0]]),
    bias=np.zeros(1), activation="none",
)
network = TwoLayerReLUNetwork(hidden, output, input_names=["x0", "x1"])
enclosures = lc.forward_interval(
    network, {"x0": (-1, 1), "x1": (-1, 1)}, precision=-80,
)
print(enclosures)
```

接口来自 [官方 ML 示例](https://github.com/alerad/leancert/blob/7f91b6eb3567437f6cfac03ed279706603ee22f4/docs/python/ml/index.md)，参数转换见 [`Layer.from_numpy`](https://github.com/alerad/leancert-python/blob/a4309c8f9faaed55c27c2da347fd0ea3eaf71e3a/leancert/nn.py#L112)。此例整数权重避免一般浮点有理化歧义；任意训练权重则需要记录有理化策略及误差。该网络数学上是 `2|x0-x1|`，在输入盒中真实最大值为 4；普通独立区间传播可能给到 8，这是关联丢失的示例，不是本次运行结果。

#### kernel replay 与 NN 模型导出是不同产品能力

Core 允许 `kernel/native/auto` 信任模式：kernel 路径做 kernel reduction，native 路径额外信任编译器/运行时。算术使用 Rational、Dyadic 还是 Affine 与这一轴独立。[Core trust model](https://docs.leancert.io/architecture/trust-model/)

SDK checked Bridge 的 `compiled_checker` 结果与导出后独立 kernel rebuild 是两个事件；后者须重放固定输入并应用 soundness theorem。网站列出的稳定独立导出家族主要是界、根、eventual bounds、积分，**不能推导 NN 便捷 bool 自动提供同样 artifact**。[Python trust boundary](https://docs.leancert.io/python/evidence/trust/)、[独立导出支持家族](https://docs.leancert.io/python/evidence/export/)

`network.export_lean()` 输出网络定义；其本身不是关于原 PyTorch 模型语义等价或安全性的证明。应编译生成定义、陈述实际性质、用适用 enclosure 定理或 checker 完成证明。不要与通用 `Verified.export_lean_project()` 混用。[NN source export 的明确边界](https://docs.leancert.io/python/ml/export/)

本次没有找到 LeanCert 的现成 **α,β-CROWN 分支/松弛证书导入器、Marabou UNSAT/Alethe 导入器或任意 ONNX 的完整认证翻译器**。因此它可复用为可信核/数学组件，但“替换 Python 搜索为 LeanCert checker”仍需定义证书结构、建模对应关系、写适配器并验证其覆盖。

### 5. Vehicle：最新 2026 进展主要解决组合与接口问题

核查默认分支 [`6312434`](https://github.com/vehicle-lang/vehicle/commit/6312434dfc109a800c618c4c6a43089b116b7c42)（2026-09-30），最近查到发布 [v0.28.0](https://github.com/vehicle-lang/vehicle/releases/tag/v0.28.0)（2026-09-10）。核心为 Haskell，有 Python 使用入口，验证后端可调用 Marabou；LICENSE 为三条款 BSD 文本。[仓库](https://github.com/vehicle-lang/vehicle)、[许可](https://github.com/vehicle-lang/vehicle/blob/6312434dfc109a800c618c4c6a43089b116b7c42/LICENSE)

应优先读 2026 论文 *Compositional Neural-Cyber-Physical System Verification in the Interactive Theorem Prover of Your Choice*，而不只停留在 FSCD 2025。它将规格编译与 Agda、Rocq、Isabelle、Imandra 的组合验证展开，例子把神经网络局部规格用于更大系统的无限时间安全证明。[2026 论文](https://arxiv.org/abs/2605.02790)

但该论文描述的 `checkVehicleProperty` 仍调用 Vehicle 检查验证缓存，并用模型路径/hash 保护对应关系；神经网络作为抽象组件接入。模型 hash 可防止旧结果悄悄用于新模型，不能独立证明外部 verifier 的数值推理。论文也承认外部编译带来的语义一致性问题。因此“在 ITP 中完成系统证明”不意味着整个具体网络和求解器都已缩进目标 ITP 的 kernel。[2026 全文 §2.2](https://arxiv.org/html/2605.02790v1)

RDS 最值得照搬的组织方式是：同一性质 AST 同时驱动训练/验证/定理接口；验证结果绑定模型、规格、转换版本和输入域；缓存失效有显式规则。当前仓库 ITP backend 目录中有上述四种后端；本次未确认正式 Lean 后端，不能因论文讨论 Lean 的类型系统就声称已支持 Lean。[ITP 后端目录](https://github.com/vehicle-lang/vehicle/tree/6312434dfc109a800c618c4c6a43089b116b7c42/vehicle/src/Vehicle/Backend/ITP)

### 6. 次优候选：VeriNet 与 NNV

**VeriNet**：核查快照 [`9207c2f`](https://github.com/vas-group-imperial/VeriNet/commit/9207c2f737d9b397167c17d4be9716fc363ff165)（2023-07-02）。提供符号区间传播、分支搜索、ONNX/PyTorch 接入；依赖 Pipenv 和 Xpress，README 提醒较大问题需要 Xpress 许可证。本次未找到逐次验证证书的独立导出/Lean 重放接口。[官方 README](https://github.com/vas-group-imperial/VeriNet/blob/main/readme.md)

其许可需要特别注意：根目录 `LICENSE.DOCX` 的文本规定非商业范围、一年期限，并限制改造、合并、后台使用等；其中学术性能比较有特定例外。不能因 GitHub 公开源码就将其视作通用宽松开源后端。本次只读取许可文本，没有对具体 RDS 用法作法律适用结论。[官方许可证](https://github.com/vas-group-imperial/VeriNet/blob/main/LICENSE.DOCX)

**NNV**：核查快照 [`376568b`](https://github.com/verivital/nnv/commit/376568b449535a779f751dd2def774a0ed94ead8)（2026-06-29）。当前 NNV 3.0 相关材料覆盖 Star/ImageStar 等 reachable-set 分析及神经控制系统；核心代码 [MIT](https://github.com/verivital/nnv/blob/376568b449535a779f751dd2def774a0ed94ead8/code/LICENSE)。工具实际依赖 MathWorks MATLAB 及多项 toolbox，并有 Python ONNX 转换辅助；这不是 Matplotlib，也不是一个独立纯 Python checker。本次未确认输出集合已有 Lean kernel replay。[官方 README 与环境要求](https://github.com/verivital/nnv/tree/376568b449535a779f751dd2def774a0ed94ead8)、[Python 转换工具](https://github.com/verivital/nnv/tree/376568b449535a779f751dd2def774a0ed94ead8/code/nnv/tools/onnx2nnv_python)

### 补充：有理证书的理论设计

Gokavarapu 的 *Proof-Carrying Verification for ReLU Networks via Rational Certificates* 最新为 v2（2026-01-12）。它针对 ReLU 网络和线性安全规格，给出 Farkas 不可行性与线性蕴含检查算法，并讨论证书归一化、组合和稀疏性。文中的“proof kernel”指精确有理运算检查算法；正文未报告 Lean 形式化，摘要页与全文未提供作者代码仓库，证据主要是数学证明与显式算例。可参考其证书接口设计，尚不能视作可直接复用的 Lean checker，也没有据此确认运行性能。[版本记录](https://arxiv.org/abs/2512.24339)、[原文](https://arxiv.org/html/2512.24339v2)

### 7. RDS 最小可复用验收设计

以下是建议的下一步实验，不是已完成实现或时间实测。

1. **统一精确 toy model**：采用上面的 `2|x0-x1|`，固定整数权重、输入盒、输出命题和哈希。先免除浮点有理化误差与复杂算子转换的干扰。
2. **三份结果单独记录**：Python verifier 的状态/界；LeanCert checked enclosure；具体 Lean 定理的 kernel 验收。若只有其中一项成功，结果报告必须如实保留，不能升级证据等级。
3. **做否定探针**：篡改一个权重、一个输入界或证书系数，kernel 路径应拒绝不成立的命题；更换模型后旧结果身份不应继续适用。这个检验比重复正确样本更能发现接口误接。
4. **再加紧界挑战**：真实上界为 4，但 naive interval 可能只给 8；因此分别测 `y ≤ 8` 与 `y ≤ 4` 的覆盖能力。失败可能是 enclosure 不够紧，不应自动诊断为模型不安全。
5. **仅在需要时消费外部证书**：优先为 affine+ReLU 的一小类 Marabou 证据定义精确语义和 Farkas/tree checker。Alethe 规则覆盖、预处理语义、委派叶节点、浮点到有理数转换是验收条件，不能隐含跳过。

最低 provenance 建议包含：模型原始文件/精确权重 digest、转换器版本、算子/维度约束、输入域与预处理、规格及其否定方向、求解器提交/配置/超时、数值格式与舍入、证书 digest、checker 提交、Lean/Mathlib 提交、实际 trust route。该字段集是本片段提出的接口建议。

#### 计算成本与投入边界

| 路径 | 可合理预期的成本来源 | 当前可作的结论 |
|---|---|---|
| auto_LiRPA 小型 CPU probe | PyTorch 安装、图转换、一次界传播 | 适合作快速接入探针；本次无秒数 |
| α,β-CROWN 完整验证 | bound 优化、BaB 节点数、GPU 显存、算子复杂度 | 超时可返回 unknown；竞赛成绩不能外推到 RDS |
| Marabou proof mode | LP、case split、证明记录、外部检查 | 证书生产会增加工作；没有针对本项目的开销比例 |
| LeanCert Core/Bridge | Lean/Mathlib 依赖、精确数膨胀、区间松弛、kernel/native 路径差异 | 小核先行；不能凭优化模块名字推断大模型吞吐 |
| Vehicle | 外部编译、规格检查、求解器成本及缓存维护 | 缓存适合避免重复验证，但不提高已有证明的信任等级 |
| NNV / ERAN / VeriNet | 专有平台或旧依赖栈、求解器许可/兼容、分析算法 | 首轮集成摩擦更高；先作为对照项 |

复杂验证通常可能长时间运行；若后续确需跨会话实验，按空投的约定使用 Windows Task Scheduler 托管，保存明确的输入、版本、日志与终止预算。本次只做文献/源码核查，没有启动后台任务。

### 8. 检索边界与仍未核实事项

- 已查官方 α,β-CROWN/auto_LiRPA README、当前安装元数据、高层 API；Marabou README、proof 选项、Engine、Alethe writer、普通证书支持集合；ERAN README/Python 入口；LeanCert ML/trust/export 文档、Core/SDK 版本和 SDK 许可；Vehicle 2026 论文及 backend 目录；VeriNet README/许可；NNV README/许可/转换工具入口。
- Web 补查使用了 `Lean4 CROWN certificate checker`、`Marabou Lean checker` 等查询，并发现 TorchLean 是直接相关结果；**TorchLean 应与本片段联合比较**，不因本片段聚焦外部 DL 工具而忽略它。没有对全 GitHub 所有分支/私有仓库进行穷尽检索。
- “未找到现成适配器”限定为上述官方源码/文档与有界搜索；不声称世界上没有任何 Lean 实现。未把论文中的“certification”自动解释为 proof assistant kernel 证明。
- 未实测：所有安装矩阵、模型转换一致性、API 示例、Lean 编译、Marabou Alethe 外部 checker 兼容性、完整网络 theorem coverage、RDS 的时间/内存成本。最新源码功能也未自动归属于旧 release 或本机已安装 wheel。
- 需后续特别验收：最新 SDK 的运行时下载与 Core/Bridge pin；NN checked bool 能否在选定版本导出所需独立 artifact；外部证书的 schema 与规则覆盖；PyTorch/ONNX 浮点实现与 Lean 实数模型之间的误差关系。

## 7. Mathlib、SciLean 与交互式定理证明成果

核查日期：2026-10-01。兼容基线：RDS `formal/lean-toolchain = leanprover/lean4:v4.33.1`，本地 Mathlib revision `0df444a360eaa60ab8c11dca51a86af692955474`，对应 `v4.33.1`。本片段完成了本地源码与上游主仓源码/元数据核查；**没有安装、构建或执行这些外部项目，以下示例不是编译通过的证据**。

建议先使用现有 Mathlib 实现统计前提与决策消费者之间的连接；现有基线已经具有 Hoeffding、Azuma–Hoeffding、Markov 及 Doob，不需要为了取得它们而升级工具链。SciLean 适合另设科学计算原型，暂不进入 RDS 的可信决策路径；神经网络方向优先复用 Mathlib 的算子与收缩理论，以及 TorchLean 中小而明确的实数语义定理。这里的选择依据是可关闭的证明义务与 RDS 需要的决策，不是库名称或运行速度。

### 1. 当前版本、许可证与兼容性

| 项目 | 本次检索的版本 | 工具链 / 依赖 | 许可证与判断 |
|---|---|---|---|
| Mathlib4：RDS 基线 | `0df444a360eaa60ab8c11dca51a86af692955474` / `v4.33.1` | Lean `v4.33.1` | Apache-2.0；下节的概率 API 均在本地基线中找到 |
| Mathlib4：上游 master | `2a885768dae569d938bb9ff3474da6a8753bb90a`，2026-09-30 20:39:31 UTC | Lean `v4.35.0-rc3` | 已查最新源码以避免把旧缺口误判为当前缺口；不建议在本轮连带升级 |
| SciLean 主仓 | `95f8119a2884e9c41f82136523bd5568ea7075c5`，2026-02-18 09:43:16 UTC | Lean `v4.28.0-rc1`；LeanBLAS `926cd897a7d2f403d6a0e2c5600adcf573e22b42`；传递 Mathlib `5352afccd6866369be9de43f5b7ec47203555f44` | Apache-2.0；固定工具链与 RDS 不同，直接兼容未验证；存在实质逻辑占位符 |
| formal-martingales | `1e49307ce983fe472b35400a79052bb607298123`，2026-06-14 | Lean `v4.30.0-rc2`；Mathlib `25b7ac7d0cf8eef34ced5525f4a62b7613ad649b` | Apache-2.0；Ville 的聚焦移植有价值，整库兼容未验证 |
| TorchLean 主仓 | `b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36`，2026-09-30 19:55:43 UTC | Lean `v4.34.0`；Mathlib `5ed2965256430c3649e86755f9576b54eca72435`；FloatLib `5f8218dc571c01d6f8bd070c65bcd0de3a40b3c5` | MIT；实数定理可挑选，不能宣称当前 RDS 能直接 import 全库 |
| Isabelle AFP：Neural_Networks | 条目发布 2025-11-09；2026-10-01 查阅 current 文档 | Isabelle/HOL / AFP session，非 Lean 包 | BSD-3-Clause；适合规格与导入边界的参考，不提供 Lake 依赖 |

版本依据：[Mathlib 当前工具链](https://github.com/leanprover-community/mathlib4/blob/2a885768dae569d938bb9ff3474da6a8753bb90a/lean-toolchain)、[Mathlib 基线许可证](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/LICENSE)、[SciLean 工具链](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/lean-toolchain)、[SciLean manifest](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/lake-manifest.json)、[SciLean LICENSE](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/LICENSE)、[formal-martingales 工具链](https://github.com/Robby955/formal-martingales/blob/1e49307ce983fe472b35400a79052bb607298123/lean-toolchain)、[TorchLean 工具链](https://github.com/lean-dojo/TorchLean/blob/b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36/lean-toolchain)、[TorchLean manifest](https://github.com/lean-dojo/TorchLean/blob/b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36/lake-manifest.json)、[TorchLean LICENSE](https://github.com/lean-dojo/TorchLean/blob/b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36/LICENSE)、[AFP 条目](https://isa-afp.org/entries/Neural_Networks.html)。Git SHA 和提交时间通过主仓 GitHub API 读取；AFP 的 current 文档没有在本次核查中转换为固定 repository SHA，因此不能当成完全冻结的复现实例。

### 2. Mathlib 概率统计：实际可 import 的接口

基线 Lake 配置无需新增概率库：

```lean
import Lake
open Lake DSL

package Formal where

require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git" @
  "0df444a360eaa60ab8c11dca51a86af692955474"

@[default_target]
lean_lib Formal
```

实际 RDS Lakefile 使用 tag `v4.33.1`；上面的完整 SHA 写法仅示范冻结依赖，不要求改动已经锁定的 manifest。`lean-toolchain` 仍为 `leanprover/lean4:v4.33.1`。

```lean
import Mathlib.Probability.Moments.SubGaussian
import Mathlib.MeasureTheory.Integral.Lebesgue.Markov
import Mathlib.Probability.Martingale.OptionalStopping

#check ProbabilityTheory.HasSubgaussianMGF.measure_sum_ge_le_of_iIndepFun
#check ProbabilityTheory.HasSubgaussianMGF.measure_sum_range_ge_le_of_iIndepFun
#check ProbabilityTheory.hasSubgaussianMGF_of_mem_Icc_of_integral_eq_zero
#check ProbabilityTheory.hasSubgaussianMGF_of_mem_Icc
#check ProbabilityTheory.measure_sum_ge_le_of_hasCondSubgaussianMGF
#check MeasureTheory.mul_meas_ge_le_lintegral₀
#check MeasureTheory.meas_ge_le_lintegral_div
#check MeasureTheory.maximal_ineq
```

这些名称通过阅读基线声明核对；本片段没有运行这段 `#check`。

#### 2.1 Hoeffding：独立性与有界性必须来自实验模型

`ProbabilityTheory.HasSubgaussianMGF.measure_sum_ge_le_of_iIndepFun` 的核心输入是：有限指标集 `s`，联合独立 `iIndepFun X μ`，每个 `X i` 具有参数 `c i : ℝ≥0` 的 `HasSubgaussianMGF`，以及 `0 ≤ ε`。输出为

\[
\mu\{\varepsilon\leq\sum_{i\in s}X_i\}
\leq \exp\!\left(-\frac{\varepsilon^2}{2\sum_{i\in s}c_i}\right).
\]

`measure_sum_range_ge_le_of_iIndepFun` 是前 `n` 项、共同参数 `c` 的版本，分母为 `2*n*c`。[基线声明，L780–792](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/Probability/Moments/SubGaussian.lean#L780)

有界随机变量的入口已经存在：`hasSubgaussianMGF_of_mem_Icc_of_integral_eq_zero` 要求概率测度、`AEMeasurable X μ`、几乎处处 `X∈[a,b]`、`μ[X]=0`；所得参数是 `((‖b-a‖₊)/2)^2`。`hasSubgaussianMGF_of_mem_Icc` 自动对 `X-μ[X]` 中心化。[Hoeffding lemma 与中心化入口，L839–866](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/Probability/Moments/SubGaussian.lean#L839)

据此可推导常见 `exp(-2 ε² / Σ(bᵢ-aᵢ)²)` 形式；对样本均值需把总和门槛换成 `n*ε` 并处理 `n>0`。双侧界需要对正负偏差分别应用后作并集界。不能把一个实测最大值充当几乎处处边界，也不能从不同 seed 的整数编号自动推导随机变量独立。

RDS 可消费的位置：预注册固定样本量的 bounded score、成对差值置信区间、固定预算筛选。若每对差值在 `[-1,1]`，该差值的区间宽度为 2；不能错误沿用单个 `[0,1]` score 的宽度 1。共同 seed 可改善差值方差，但独立性应针对不同配对之间的采样单元建模。运行中反复查看后提前停止，不能继续把固定时刻 Hoeffding 当作无需修正的整体错误率。

#### 2.2 Azuma–Hoeffding：现有 API 是条件次高斯增量的固定时刻界

同一 import 中，准确名称是小写 `hasCond`：

```lean
ProbabilityTheory.measure_sum_ge_le_of_hasCondSubgaussianMGF
```

该节要求 `StandardBorelSpace Ω`；定理要求 `IsZeroOrProbabilityMeasure μ`、`StronglyAdapted ℱ Y`、初项 `HasSubgaussianMGF (Y 0) (cY 0) μ`，以及对 `i<n-1` 的条件 MGF 性质

```lean
HasCondSubgaussianMGF (ℱ i) (ℱ.le i) (Y (i + 1)) (cY (i + 1)) μ
```

结论为前 `n` 个增量和的指数尾界，参数为 `Σ i∈range n, cY i`。旧的 `measure_sum_ge_le_of_HasCondSubgaussianMGF` 只是自 2026-01-27 起弃用的 alias。[基线节与定理，L870–942](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/Probability/Moments/SubGaussian.lean#L870)

RDS 可消费的位置：适应历史的实验策略，在明确 filtration 下建模条件中心化、条件有界/次高斯增量。主要工作是证明这些条件；“训练过程是 SGD”“有 Markov 性”“记录了历史”都不自动给出它们。该声明也没有直接提供 `∃n` 越界概率；需要把它扩展成合法的序贯过程或使用预先分配的时刻错误预算。

#### 2.3 Markov 尾界与 DPI 的 Markov 条件不是同一接口

`MeasureTheory.mul_meas_ge_le_lintegral₀` 对 `f : Ω → ℝ≥0∞`、`AEMeasurable f μ` 给出乘法形式 `ε * μ{ε≤f} ≤ ∫⁻f`。`MeasureTheory.meas_ge_le_lintegral_div` 另要求 `ε≠0` 且 `ε≠∞`，输出 `μ{ε≤f} ≤ (∫⁻f)/ε`。它不要求独立、同分布或鞅；有限且有用的期望上界须另行提供。[Markov 声明](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/MeasureTheory/Integral/Lebesgue/Markov.lean#L50)、[除法形式](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/MeasureTheory/Integral/Lebesgue/Markov.lean#L103)

可用于单时刻 e-value 检验：若非负统计量的零假设期望不超过 1，则超过 `1/α` 的概率不超过 `α`。要在任意停止时刻都有效，需要合法 e-process 或其他额外结构。

DPI 中的 Markov 链/条件通道通常表达条件独立或概率核分解。它既不是上面的尾界，也不自动建立“每次损失差值为鞅差”。RDS 的字段名与 Lean 接口应分别叫 `MarkovTailBound` 和 `MarkovKernel/ConditionalIndependence` 等，避免用一个模糊的 `markov_verified` 复用两种含义。这是接口建议，不是已经存在于 RDS 的字段。

#### 2.4 Doob 与 Ville：需要区分 submartingale / supermartingale

Mathlib 的 `MeasureTheory.maximal_ineq` 要求有限测度、**非负 submartingale**、非负门槛 `ε`、固定 horizon `n`。右边是越界集合上 `f n` 的积分，不是初始期望。[OptionalStopping，L149–159](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/Probability/Martingale/OptionalStopping.lean#L149)

因此不能简单取负把它变成非负 supermartingale 的 Ville：取负后非负前提已经消失。本次对本地概率相关源码及最新 OptionalStopping 的检索未找到可直接替代下列 Ville 声明的接口；这是有范围的检索结果，不宣称整个 Mathlib 永远没有别的推导路线。

`formal-martingales` 已有可审阅的实现：

```lean
import FormalMartingales.Martingale.Ville
import FormalMartingales.Sequential.EProcess

-- namespace FormalMartingales
#check FormalMartingales.ville_inequality
#check FormalMartingales.ville_inequality_of_integral_le_one
#check FormalMartingales.eprocess_sequential_test_typeI
```

`ville_inequality` 要求有限测度、`SigmaFiniteFiltration`、`Supermartingale f ℱ μ`、点态 `0≤f`，结论为 `ε * μ{ω | ∃n, ε≤f n ω} ≤ ENNReal.ofReal (μ[f 0])`。归一化版本另要求 `μ[f 0]≤1`、`α:NNReal`、`0<α`，得到跨可数时刻越过 `α⁻¹` 的概率至多 `α`。证明使用 hitting time、optional stopping 和递增并集，而非直接求负。[Ville 源码](https://github.com/Robby955/formal-martingales/blob/1e49307ce983fe472b35400a79052bb607298123/FormalMartingales/Martingale/Ville.lean)、[EProcess 源码](https://github.com/Robby955/formal-martingales/blob/1e49307ce983fe472b35400a79052bb607298123/FormalMartingales/Sequential/EProcess.lean)

值得特别防止名称造成过强结论：最新 `Concentration.lean` 的 `freedman_exponential_supermartingale_crossing` 把指数过程是 `EProcess` 作为**输入假设**，再换写越界事件；它没有在该定理里从任意有界增量和经验方差自动构造这个过程。不能据名称把“标准 Freedman 所有前提已完成”写入报告。[Concentration，L35–41](https://github.com/Robby955/formal-martingales/blob/1e49307ce983fe472b35400a79052bb607298123/FormalMartingales/Martingale/Concentration.lean#L35)

RDS 的优先接入对象是已经聚焦移植的 Ville 层和其消费者：对零假设、过滤、下注规则、初始归一化、每步条件期望建立证明，然后由同一规则产生的事件控制提前停止。若当前已移植对应版本，应继续复用该副本并记录来源，不再同时接入另一套旧工具链。

### 3. SciLean：科学计算能力与信任问题需同时说明

#### 3.1 目前能复用的 API

SciLean 的 `revFDeriv K f x` 返回 `(f x, pullback)`；逻辑定义用 Mathlib 的 Fréchet 导数及伴随。`fgradient f x` 是 pullback 作用于 1。组合规则 `SciLean.revFDeriv.comp_rule` 要求内外函数分别 `Differentiable K`，在结果中保留正向中间值再组合反向映射。[`SciLean/AD/RevFDeriv.lean`，L13–31、L81 起](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/SciLean/AD/RevFDeriv.lean)

```lean
import SciLean.AD.RevFDeriv
import SciLean.Tactic.Autodiff

#check SciLean.revFDeriv
#check SciLean.fgradient
#check SciLean.revFDeriv.comp_rule
```

`fun_trans` 及 `autodiff` 用微分规则变换程序；官方教程强调 `autodiff` 对 let 绑定的处理，适用于导数表达式与计算图的推导。它不是“任意现有 Python/PyTorch 代码自动变成内核证明”的入口。[官方自动微分教程](https://lecopivo.github.io/scientific-computing-lean/Differentiation/Automatic-Differentiation/)、[Autodiff tactic 源码](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/SciLean/Tactic/Autodiff.lean)

#### 3.2 核心阻碍不只是版本老

该固定 revision 的 `SciLean/Util/SorryProof.lean` 明确包含：

```lean
namespace SciLean
axiom sorryProofAxiom {P : Prop} : P
axiom sorryDataAxiom {α : Type _} : α
```

`sorry_proof`、`sorry_data` 宏分别展开到这些公理。对正式消费者只禁止标准 `sorryAx` 会漏检。必须对最终 theorem 的传递依赖做 `#print axioms` 并采用明确允许集合，拒绝 `SciLean.sorryProofAxiom`、`SciLean.sorryDataAxiom` 以及其他未批准公理。[准确声明与宏](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/SciLean/Util/SorryProof.lean)

`SciLean/Analysis/FloatAsReal.lean` 中以占位证明给 Float 建立 Field、NormedField、CompleteSpace、RCLike 等结构。此路线不能被表述为真实 IEEE 浮点数拥有实数代数性质，也不提供浮点舍入误差证明。部分 AD 规则同样存在 `sorry_proof`；故源文件能被 Lean 接受，并不足以表明目标声明已经无占位完成。另一方面，不应因此把整个项目的所有定理一概判无用：是否可进入证明链取决于实际使用声明的依赖闭包。[FloatAsReal](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/SciLean/Analysis/FloatAsReal.lean)、[AD 源文件](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/SciLean/AD/RevFDeriv.lean)

#### 3.3 Lake、FFI 与主机成本

仅在独立目录评估其匹配的旧工具链时，可用如下配置草案：

```lean
import Lake
open Lake DSL
package SciLeanProbe where
require scilean from git
  "https://github.com/lecopivo/SciLean.git" @
  "95f8119a2884e9c41f82136523bd5568ea7075c5"
@[default_target]
lean_lib SciLeanProbe
```

对应 `lean-toolchain` 为 `leanprover/lean4:v4.28.0-rc1`。还需确认解析后的 manifest 保留上表的 LeanBLAS / Mathlib SHA，不能仅靠顶层 SciLean SHA 假设动态 `@ master` 依赖永不漂移。[Lakefile](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/lakefile.lean)

Lakefile 包含 C 源码编译和 BLAS 链接；`SciLean.FFI` 使用预编译模块。README 的安装示例仍提较旧 Lean 版本，且说明 Windows 不受支持；当前 Lakefile 中 Windows 的链接参数为空并不构成 Windows 已测试支持的证据。RDS 当前是 Windows 环境，因此完整运行层的集成成本包括工具链隔离、外部库、编译器和 FFI 验证，不能用“添加一行 require”估算。[当前 README](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/README.md)、[FFI/Float](https://github.com/lecopivo/SciLean/blob/95f8119a2884e9c41f82136523bd5568ea7075c5/SciLean/FFI/Float.lean)

RDS 采用建议：允许 SciLean 产生候选数学表达式或 AD 原型；将需要的干净定理逐条审计后在当前 Mathlib 基线上小范围移植。不能让含上述占位依赖的声明直接产生 `certified` 决策。该建议不要求本轮安装 SciLean。

### 4. 最有复用价值的三条 ITP 路线

#### 4.1 Mathlib 的 Lipschitz、连续线性算子和收缩映射

这条路线版本摩擦最小，适合 RDS 已经表达为算子范数、残差迭代、停止误差的数学对象。

```lean
import Mathlib.Analysis.Normed.Operator.Basic
import Mathlib.Topology.MetricSpace.Contracting
import Mathlib.LinearAlgebra.Matrix.Gershgorin

#check ContinuousLinearMap.lipschitzWith_of_opNorm_le
#check ContractingWith.dist_le_of_fixedPoint
#check ContractingWith.dist_fixedPoint_le
#check ContractingWith.aposteriori_dist_iterate_fixedPoint_le
#check ContractingWith.apriori_dist_iterate_fixedPoint_le
#check ContractingWith.fixedPoint_lipschitz_in_map
```

`lipschitzWith_of_opNorm_le` 把算子范数上界连接到 Lipschitz 常数。`ContractingWith` 包含 `K<1` 的要求；已有不动点时，`dist_le_of_fixedPoint` 给出 `dist x x* ≤ dist x (f x)/(1-K)`；构造不动点及相应全局收敛结论时需要完备性等类型类前提。`aposteriori_dist_iterate_fixedPoint_le` 用连续两次迭代间距给停止误差界；`fixedPoint_lipschitz_in_map` 给两个收缩映射的一致扰动下不动点距离界。[算子接口](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/Analysis/Normed/Operator/Basic.lean#L343)、[收缩接口](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/Topology/MetricSpace/Contracting.lean#L254)

RDS 的直接消费者可以是“已证收缩的迭代达到目标误差后停止”和“部署的参数扰动是否仍在允许误差内”。矩阵版本必须明确实际迭代映射。例如残差更新 `x↦x+Ax+b` 的线性部分是 `I+A`，只证明 `‖A‖<1` 并不能证明该更新收缩。局部区域证明还需区域不变性，不能把一个采样点附近的局部结论改写为全局收敛。

`Mathlib.LinearAlgebra.Matrix.Gershgorin` 的 `eigenvalue_mem_ball` 给特征值所在的闭圆盘：存在行 `k`，中心 `A k k`、半径 `Σ j≠k, ‖A k j‖`。它适合谱约束证书的组成部分，但一般矩阵的谱半径界不是欧氏算子范数界；非正规矩阵尤其不能省略两者之间的证明。[Gershgorin 声明](https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/LinearAlgebra/Matrix/Gershgorin.lean#L27)

#### 4.2 TorchLean：优先挑选实数 Tensor 的 Lipschitz 与分类间隔定理

最新版论文是 *TorchLean: Formalizing Neural Networks in Lean*，arXiv `2602.22631`，2026-05-24 更新到 v2。主仓 2026-09-30 的源码已比论文时间更新；本节以固定主仓 revision 的实际接口为准。[论文](https://arxiv.org/abs/2602.22631)、[作者项目页](https://leandojo.org/torchlean.html)

```lean
import NN.Proofs.Analysis.Lipschitz.Network
import NN.MLTheory.Proofs.Verification.Robustness.LipschitzCertified

#check Proofs.linear_op_norm_bound
#check Proofs.lipschitz_composition
#check Proofs.relu_linear_lipschitz
#check NN.MLTheory.Proofs.Verification.Robustness.HasLogitMargin
#check NN.MLTheory.Proofs.Verification.Robustness.is_certified_robust_of_lipschitz_of_logitMargin
#check NN.MLTheory.Proofs.Verification.Robustness.is_certified_robust_of_l2_lipschitz_of_logitMargin
```

关键声明的准确含义：

| 声明 | 输入/输出 | RDS 可以消费什么 |
|---|---|---|
| `Proofs.linear_op_norm_bound` | `W : Tensor ℝ [m,n]`；输出 `tensorL2Dist(Wx,Wy) ≤ matrixFrobeniusNorm W * tensorL2Dist(x,y)` | 从精确实数权重的 Frobenius 范数界生成保守层 Lipschitz 证书 |
| `Proofs.relu_linear_lipschitz` | 上述线性映射再接 ReLU；相同 Frobenius 上界 | ReLU 网络层的组合式稳定性界 |
| `Proofs.lipschitz_composition` | 已有 `f`、`g` 的距离界与 `0≤Lg`；输出乘积 `Lg*Lf` | 网络级界；可能随深度变松，宽松上界不代表实验性能差 |
| `…is_certified_robust_of_lipschitz_of_logitMargin` | `0≤L`、输出 ℓ∞ 的 Lipschitz 假设、`0≤ε`、正 margin `m`、每个竞争 logit 落后至少 `m`、`2*(L*ε)<m` | 证明给定输入球内 argmax 分类不变 |
| `…is_certified_robust_of_l2_lipschitz_of_logitMargin` | 用输出 ℓ2 Lipschitz 前提替代 ℓ∞ 前提 | 通过范数比较取得同一分类稳定结论 |

来源：[Network.lean，L193–258](https://github.com/lean-dojo/TorchLean/blob/b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36/NN/Proofs/Analysis/Lipschitz/Network.lean#L193)、[LipschitzCertified.lean，L96、L193–247](https://github.com/lean-dojo/TorchLean/blob/b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36/NN/MLTheory/Proofs/Verification/Robustness/LipschitzCertified.lean#L193)。这里的实数距离稳定性和 argmax 稳定性是两种不同强度的结论，不能只引用前者却声称标签已稳定。

单独探针的 Lake 草案如下，工具链为 `leanprover/lean4:v4.34.0`：

```lean
import Lake
open Lake DSL
package TorchLeanProbe where
require TorchLean from git
  "https://github.com/lean-dojo/TorchLean.git" @
  "b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36"
@[default_target]
lean_lib TorchLeanProbe
```

完整包默认不要求 LibTorch/CUDA SDK，但仍含本机 C 运行时构建；启用 CUDA 则另有 LibTorch/CMake 路线。即使只想要数学定理，也要检查包级本机动态库配置，而不能假设细粒度 import 会完全避开构建依赖。[Lakefile 的默认后端与 C 构建](https://github.com/lean-dojo/TorchLean/blob/b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36/lakefile.lean#L32)

最新官方信任边界文档自述没有自定义 Lean axioms，并明确区分定理、可执行检查器、Prop 合约、FFI 运行时、外部证书生产者。它也说明 `checkedCuda` 的 `checked` 不意味着 LibTorch 位于内核信任域。本文仅核对了所选源码与该文档，没有全仓运行 axiom audit。RDS 若采用，应对最终定理独立打印公理，并把精确权重/图/范数/输入域与模型 hash 绑定。`ℝ` 语义证明不能直接覆盖任意 PyTorch 导出、Float 舍入、GPU reduction 或原生内存实现。[TRUST_BOUNDARIES.md](https://github.com/lean-dojo/TorchLean/blob/b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36/docs/TRUST_BOUNDARIES.md)

因此 TorchLean 的近期最佳用途是一个可界定的小型鲁棒性证书消费者，或选定定理的兼容移植；其深度学习运行时不是为了复用这几条定理必须整体接入的范围。

#### 4.3 Isabelle/HOL AFP：语义等价与导入边界的可靠参考

Brucker 与 Stell 的 2023 FM 工作后续形成 2025-11-09 的 AFP `Neural_Networks` 条目，不能只停留在 2023 论文。它提供 digraph、层列表/矩阵等前馈网络模型及语义等价，并包含 TensorFlow.js 模型导入工具。核心价值是明确区分模型表示、求值语义与模型导入。[最新 AFP 条目](https://isa-afp.org/entries/Neural_Networks.html)、[FM 2023 原论文](https://doi.org/10.1007/978-3-031-27481-7_24)

实际 `NN_Lipschitz_Continuous` 提供 `relu_lipschitz`、`relu_lipschitz_fv`、`softplus_lipschitz`、`dense_layer_lipschitz_on`、`foldl_layer_lipschitz_on`、`layers_lipschitz_from_components`。例如 dense 层定理要求权重范数界和相应仿射像上的激活 Lipschitz 性；组合定理 `foldl_layer_lipschitz_on` 显式要求每层保持域 `U` 不变。其最终形式之一是存在网络 Lipschitz 常数，不能误读成自动产出最紧数值常数。[AFP 理论源](https://isa-afp.org/browser_info/current/AFP/Neural_Networks/NN_Lipschitz_Continuous.html)

该路线没有 Lean import；直接引入将增加另一种证明助手、模型规格与构建链。RDS 更适合复用“导入数据必须对应明确语义、局部域必须闭合”的设计，以及少量必要的数学 lemma。源码头标注 BSD-3-Clause，可按相应许可证保留版权后移植；从定理语义重新在 Mathlib 证明仍须本地检验。模型导入工具存在不等于原始 TensorFlow/PyTorch 程序全部语义已验证。

### 5. `decide_cbv` 与 `native_decide`：Lean 4.33.1 的实际边界

Lean 4.33.1 已包含 `decide_cbv`。本地该版本的 `Init/Tactics.lean` 文档说明它由 `cbv` 产生证明项，不把编译器正确性加入信任基；`Lean/Elab/Tactic/Cbv.lean` 的实现先使用 `of_decide_eq_true` 再执行 `cbvDecideGoal`。它适合可判定的有限证书谓词，不会自动证明概率独立性、期望不等式或外部程序对应关系。[4.33.1 tactic 文档](https://github.com/leanprover/lean4/blob/v4.33.1/src/Init/Tactics.lean#L2394)、[实现](https://github.com/leanprover/lean4/blob/v4.33.1/src/Lean/Elab/Tactic/Cbv.lean)

同一版本 `native_decide` 走 `decide +native` 路径；`Lean/Meta/Native.lean` 的 `nativeEqTrue` 编译并执行布尔判定，然后引入 `_native.<tactic>.ax` 形式的 axiom declaration。因此在这个版本仅搜索旧文献中的某个固定 axiom 名称并不充分。它扩展的信任包括 native compilation 和 executable replacement 的行为。[`native_decide` 文档](https://github.com/leanprover/lean4/blob/v4.33.1/src/Init/Tactics.lean#L1390)、[Native 实现](https://github.com/leanprover/lean4/blob/v4.33.1/src/Lean/Meta/Native.lean)

RDS 可优先探索“外部产生候选证书 → Lean 内有限 checker → soundness theorem”的边界：小型封闭实例用 `decide_cbv`，大型实例先测证明大小与耗时。若用 `native_decide`，应在证书元数据中明确 native trust 并保留独立证据；不把 `#eval` 的 true 等同于定理。无论选哪种 tactic，都必须审计最终 theorem 的全部公理；`decide_cbv` 不会消除之前导入的 `sorryProofAxiom`。

### 6. 建议的接入顺序与完成判据

| 顺序 | 最小交付物 | 真实决策消费者 | 仍需关闭的义务 |
|---|---|---|---|
| 1 | 在现有 Mathlib 基线上封装固定样本 Hoeffding 接口 | 固定计划的差值阈值与置信界 | 采样单元、独立性、理论边界、中心化、样本量 |
| 2 | 将已有 Ville 移植与一个明确 e-process 连接 | 合法提前停止 / 错误率控制 | 零假设、filtration、适应性、非负性、条件期望、起点 |
| 3 | 收缩常数与残差误差证书 | 收缩迭代的停止误差、扰动容限 | 实际更新算子、范数、域不变性、模型参数身份 |
| 4 | TorchLean 选定实数鲁棒性引理的隔离探针或移植 | 特定模型和输入域的标签稳定证书 | 权重导入、Lipschitz 上界、margin、Float 对应、axiom audit |
| 5 | SciLean AD 小原型 | 数学表达式/候选梯度生成 | 自定义占位符清除、版本/FFI/平台问题；未关闭前不作可信放行 |

这里的顺序表示证明义务与当前消费者的匹配程度；不是按单次运行更便宜进行科学优先级排序。一个候选若无法形成有意义的科学问题或实际决策，即使能轻易证明也不应优先。

本片段证据状态：**SOURCE_REVIEW_ONLY**。不包含运行成功、完整构建、全仓无 sorry、GPU 语义验证或统计假设已经由真实数据满足的声明。后续验证应分别产出编译记录、`#print axioms`、固定输入证书的接受结果、以及该证书确实触发所声称 RDS 决策的集成证据；各层不能相互替代。

### 附录：RDS 科学价值、成本偏序与并行预算的窄范围只读审查

审查对象：`RDS-resource-aware-20261001` 中 HEAD `ba1db17c8791d687db2d2b657d746b0a6a3b6a2d` 的 search、reference runner、project runner 和成本汇总逻辑。其他参与者正在修改该工作树，本附录记录的是修改前的这些源码边界；未改代码、未运行实验。

1. **现有 Pareto 规则可以让便宜而科学价值较低的任务支配更重要的任务。** `rds_advisor_search.py:274` 从结果里的 `next_decision` 字符串生成集合，`:377–394` 以集合包含关系和较低单一成本建立 dominance。准确说这是 label 集合包含关系，不是直接计数。`discrimination` 缺失时，甚至不检查竞争解释或科学 scope 是否相同；有 discrimination 时才要求同 scope、相同解释集合及判别对的超集。`tests/test_rds_advisor_search.py:86–90` 固化了仅依据相同 decision labels 与较小成本选出 fast 的行为。最小修复是：缺乏明确科学比较依据时保留不可比；成本仅在同一科学问题、等效科学产出或显式科学偏序已建立的组内打破平局。增加一个 label 不应产生额外科学价值。

2. **未发现执行 kernel 全局强制串行。** Reference runner 的 `cmd_run` 在 `rds_cli.py:481–514` 结束状态事务，然后在 `:525` 调用子进程。`:382–383` 的活动运行检查只用于冻结 confirmation 前的探索结束，不是禁止一般并发。Project runner 用短事务保留预算、输出路径和一次执行身份；实际进程运行时没有占住整个数据库写事务（`rds_project.py:356–370`、`:420–432`、`:465–477`）。多个独立 run 可以由独立 worker / Windows Task Scheduler 并发。当前缺的是自动构造兼容批次及设备容量、显存、设备身份、依赖与共享瓶颈的规划/预留；不能把“缺少调度层”诊断为“kernel 有一个全局串行锁”。

3. **累计运行时间预算不能解释成截止时间。** Reference runner 只有 `runtime_ms`、`runs` 两种资源，每次分配最多 60 秒（`rds_cli.py:28`、`:91–98`、`:376`）；它是受限标量 reference protocol。Project runner 接受资源向量，但 `wall_seconds` 对每个 run 分别预留并相加结算（`rds_project.py:280–283`、`:334–337`、`:360–369`、`:577–578`）。因此它的现有语义是累计 run wall time：4 GPU 各跑 1 小时的独立任务，批次 elapsed time 可约 1 小时，但现有账本需要约 4 小时累计运行额度。最小改法是在规划层另设 deadline / batch makespan 和 device-time / 边际费用，不悄悄改写旧账本字段含义，也不把可用 4 GPU 折成“只够串行 1 个任务”。

4. **实际测量与来源标注要保留区分。** Project runner 在 `rds_project.py:539–544` 只自动实测 `wall_seconds`，其他资源维度结算为 charged estimate / unknown；成本汇总在 `rds_costs.py:123–150` 保持这些区别。Search 的 `_cost` 接受带 source 的 `INPUT_REPORTED` 记录，但 dominance 的 basis 文案称 observed，证据强度不一致。最小修复是将文案改为 sourced/reported，或仅在确有测量来源时使用 observed。GPU 总量、空闲量、运行估计、已测 device-time 和费用不应互相冒充。

以上支持“科学推进与到决策的时间优先，成本是约束和等效比较时的权衡”的实现方向。对空闲 3 张 GPU，应解释当前是否有独立且有价值的可执行工作；既不自动让最便宜任务获胜，也不为提高利用率启动重复或无关实验。

## 8. Lean 交互、CLI 与证明搜索基础设施

核查日期：2026-10-01（Asia/Shanghai）。范围：官方仓库、官方 Lean 文档和原始论文；读取了固定 commit 的源文件与 GitHub refs。没有安装这些工具、下载模型、运行 GPU 或进行本地兼容性/性能测试。以下“可接入”表示有公开接口与明确路径，不表示 RDS 已完成集成或证明了科研收益。

### 决策结论

RDS 当前最值得复用的基础设施是 **Lean community REPL 的持久进程与环境复用**；Python 包装优先评估 **LeanInteract**，确有高并发验证需求再评估 **Kimina**，确有分支级 tactic 搜索需求再评估 **Pantograph**。**LeanCopilot 是候选证明生成器，最终验收仍需对锁定命题独立重放。** 原版 LeanDojo 已弃用，LeanDojo-v2 的训练和数据库体系对当前 CPU 双步闭环明显更重，应按独立研究需求选择模块。

这些工具的直接价值是：在同一形式化预算内更快检查候选的数学前提，给 Advisor 返回可定位的失败或未完成原因，再改变实验优先级；增加工具数、通过证明数或推理吞吐本身，不能替代 RDS 的决策改变度验收。

用户已允许升级 Lean。官方 `releases/latest` 在本次查询返回 **Lean v4.34.1，2026-09-24 发布，非 prerelease**。REPL、LeanCopilot 与 mathlib4 的 `v4.34.0` 标签都存在，且其 `lean-toolchain` 均为 `v4.34.0`。因此，升级到 4.34.1 是明确的候选路线，但仍需在 RDS 分支验证三者的 patch 兼容性；不能把这些 `v4.34.0` 标签写成已实测支持 4.34.1。REPL 的当前 master 使用 `v4.35.0-rc3`，也不能把 master 当作当前稳定依赖。[Lean 4.34.1 release](https://github.com/leanprover/lean4/releases/tag/v4.34.1)、[mathlib 工具链](https://github.com/leanprover-community/mathlib4/blob/v4.34.0/lean-toolchain)、[REPL 工具链](https://github.com/leanprover-community/repl/blob/193cf4bb9a22bb3fc6d25774f0fe6a70db1fd6ee/lean-toolchain)、[LeanCopilot 工具链](https://github.com/lean-dojo/LeanCopilot/blob/5af8991b700271d4221bdd303aacdcd4fa29f167/lean-toolchain)。

### 固定版本、许可与接口矩阵

| 工具 | 本次固定来源与许可 | 核心接口/可解决卡点 | 对 RDS 的接入判断 |
|---|---|---|---|
| [Lean community REPL](https://github.com/leanprover-community/repl) | master `c88b976ff1e5d72875545de1868c43537138aba0`，提交 2026-09-28；Apache-2.0。已核实 `v4.33.0 = bbeedf38e0898869fc3b7c009e1ea877b46204e4`、`v4.34.0 = 193cf4bb9a22bb3fc6d25774f0fe6a70db1fd6ee` | stdin/stdout JSON，空行分隔；command、file、experimental tactic mode；`env`/`proofState` 复用、回退、pickle | **近期首选。** 保留现有 CLI 最终复核，先复用证明探索时的进程和 import。当前 4.33.1 精确 tag API 为 404；4.34.1 也须实际构建确认。 |
| [LeanInteract](https://github.com/augustepoiroux/LeanInteract) | `976edd7d38a99e1ea4c2dfabeb8ad98baffca3c8`，2026-07-16；Python 包 **0.11.5**，Python >=3.10；MIT | `LeanREPLConfig`、`LocalProject`、`LeanServer.run`、`AutoLeanServer`、session cache、server pool；包装 REPL 的持久子进程 | **先做适配探针。** README 公开上限为 4.32.0-rc1，但实际默认 fork 已有 4.33.0-rc1 tag，说明 README 落后；没有 4.33.1/4.34.1 已验证证据。可指定自建的 `local_repl_path`，必须验证协议。 |
| [PyPantograph](https://github.com/stanford-centaur/PyPantograph) / [Pantograph](https://github.com/leanprover/Pantograph) | Py `f8aee320ee5550ea2677e414534618a61e7e1497`，2026-06-30；**0.3.15**，Python >=3.11；Apache-2.0。实际 `src` submodule 为 `842c0fe6e76b0771cc7f7939604c7a0b90e17433`，Lean **4.29.1** | `Server.goal_start`、`goal_tactic`、耦合 metavariable 管理、whole-file specification conformity 检查；Python 层使用持久子进程的行协议 | **需要多分支证明搜索时再适配。** 不能把 standalone mirror main 的 4.18.0 当作当前 Python 包工具链，也不能把 4.29.1 wheel 当作兼容 4.34.1。已读 CI 仅为 Ubuntu。 |
| [LeanCopilot](https://github.com/lean-dojo/LeanCopilot) | main `a303359eedb1104276cdf3c4495c305c482ebadb`，2026-09-18，Lean4.34.0；已核实 `v4.34.0 = 5af8991b700271d4221bdd303aacdcd4fa29f167`；MIT | Lake 包；`suggest_tactics`、`search_proof`、`select_premises`；CTranslate2 原生 FFI 推理或外部模型 HTTP API | **可选证明搜索侧车。** 本身不解决 RDS 实验价值判断；引入模型及 C++ 构建/动态库成本。优先记录生成的证明脚本，再用现有 checker 重放。 |
| [LeanDojo](https://github.com/lean-dojo/LeanDojo) / [LeanDojo-v2](https://github.com/lean-dojo/LeanDojo-v2) | 旧库 README 明确 deprecated。v2 `baed5eae6e87a65a446d9f54af07aab2154e7599`，2026-08-10，包 **1.0.9**，Python >=3.11；**LICENSE 为 Apache-2.0，但 README/pyproject 声称 MIT，存在冲突** | 仓库 tracing、数据集/动态数据库、检索、训练、Pantograph prover、外部推理 API | **当前暂缓整体引入。** 优先复用需要的 tracing/prover 概念；其 PyTorch/DeepSpeed/Ray 等依赖不是一次局部 checker 调用所必需。许可冲突须在正式再分发前查清。 |
| [Kimina Lean Server](https://github.com/project-numina/kimina-lean-server) | `fb2393de3461db35eda4c714e3fd21187e92ec90`，2026-01-11；client **0.2.1**，Python >=3.9；MIT。README server 镜像示例2.0.0、默认 Lean4.26.0 | FastAPI + REPL 进程池 + import LRU 复用；REST API、sync/async Python SDK；批量校验与 tactic 信息提取 | **出现并发吞吐瓶颈再用。** 需将 server project_dir 指到目标 formal 项目，并换成匹配版本 REPL；默认镜像不能直接代表 4.34.1 兼容性。Windows 内存限制差异要检查。 |

固定来源：[REPL v4.33.0 README](https://github.com/leanprover-community/repl/blob/bbeedf38e0898869fc3b7c009e1ea877b46204e4/README.md)、[REPL LICENSE](https://github.com/leanprover-community/repl/blob/bbeedf38e0898869fc3b7c009e1ea877b46204e4/LICENSE)、[LeanInteract metadata](https://github.com/augustepoiroux/LeanInteract/blob/976edd7d38a99e1ea4c2dfabeb8ad98baffca3c8/pyproject.toml)、[LeanInteract 支持范围](https://github.com/augustepoiroux/LeanInteract/blob/976edd7d38a99e1ea4c2dfabeb8ad98baffca3c8/README.md)、[实际 fork 4.33.0-rc1 tag](https://github.com/augustepoiroux/repl/tree/v1.3.18_lean-toolchain-v4.33.0-rc1)、[PyPantograph metadata](https://github.com/stanford-centaur/PyPantograph/blob/f8aee320ee5550ea2677e414534618a61e7e1497/pyproject.toml)、[其 submodule 工具链](https://github.com/leanprover/Pantograph/blob/842c0fe6e76b0771cc7f7939604c7a0b90e17433/lean-toolchain)、[其 CI](https://github.com/stanford-centaur/PyPantograph/blob/f8aee320ee5550ea2677e414534618a61e7e1497/.github/workflows/test.yaml)、[LeanCopilot LICENSE](https://github.com/lean-dojo/LeanCopilot/blob/5e00f2dc0bbc31f7d90d7cde40c72a884e933ed9/LICENSE)、[LeanDojo 弃用声明](https://github.com/lean-dojo/LeanDojo/blob/main/README.md)、[v2 metadata](https://github.com/lean-dojo/LeanDojo-v2/blob/baed5eae6e87a65a446d9f54af07aab2154e7599/pyproject.toml)、[v2 实际 LICENSE](https://github.com/lean-dojo/LeanDojo-v2/blob/baed5eae6e87a65a446d9f54af07aab2154e7599/LICENSE)、[Kimina metadata](https://github.com/project-numina/kimina-lean-server/blob/fb2393de3461db35eda4c714e3fd21187e92ec90/pyproject.toml)、[Kimina README](https://github.com/project-numina/kimina-lean-server/blob/fb2393de3461db35eda4c714e3fd21187e92ec90/README.md)。

### 可复用的最小接入方式

下述示例是依据已读 API 写出的接入说明，**未在本机执行，不是验收脚本**。外部仓库、toolchain 与 mathlib commit 应作为同一个锁定组合记录；升级不能只改一处字符串。

#### 1. REPL：低依赖的持续交互

在一个与 RDS toolchain 匹配、已经 `lake build` 的 REPL checkout 上，从 RDS 的 `formal` 工作目录启动：

```powershell
lake env C:/deps/repl/.lake/build/bin/repl.exe
```

通过该进程的 stdin 发送 JSON，**每条消息后有空行**：

```json
{"cmd":"import Mathlib"}

{"cmd":"example (n : Nat) : n = n := by rfl","env":0}

```

第二条中的 `0` 是示意值，实际必须取第一条响应的 `env`。复用旧 `env` 可以开独立分支；带 `env` 的后续请求不能再带 `import`。用户代码报错并不等于进程退出；要读 `messages` 和 `sorries`，不能只读 exit code。[官方协议](https://github.com/leanprover-community/repl/blob/bbeedf38e0898869fc3b7c009e1ea877b46204e4/README.md)。

用这种方式可保持 REPL checkout 与正式数学依赖分开，减少主 `formal/lakefile.lean` 的无关依赖。官方支持从另一个项目用 `lake env <repl-path>` 运行；这不是新造的 socket 协议。

#### 2. LeanInteract：复用 Python 封装

对已经匹配版本并构建好的本地 REPL，可接入如下；`local_repl_path` 是 **REPL checkout 目录**，不是 executable 路径。

```python
from lean_interact import Command, LeanREPLConfig, LeanServer, LocalProject

config = LeanREPLConfig(
    project=LocalProject(directory="C:/work/research-direction-selector/formal"),
    local_repl_path="C:/deps/repl",
)
server = LeanServer(config)
try:
    imported = server.run(Command(cmd="import Mathlib"), timeout=60)
    env = getattr(imported, "env", None)
    if env is None:
        raise RuntimeError(f"Import did not produce an environment: {imported}")
    result = server.run(
        Command(cmd="example (n : Nat) : n = n := by rfl", env=env),
        timeout=10,
    )
    print(result)
finally:
    server.kill()
```

此例展示接口与超时，不把 `env` 存在当作证明通过；RDS 仍须检查错误、sorry 和目标命题。`LeanREPLConfig` 默认从作者 fork 下载/构建 REPL，而 `local_repl_path` 可绕开其默认版本选择。当前 Python 模型和上游 community REPL 的协议是否完全一致，需要一个小规模兼容测试；必要时可用公开的 `run_dict` 接口处理自定义 REPL 响应。[config API](https://github.com/augustepoiroux/LeanInteract/blob/976edd7d38a99e1ea4c2dfabeb8ad98baffca3c8/src/lean_interact/config.py)、[server API](https://github.com/augustepoiroux/LeanInteract/blob/976edd7d38a99e1ea4c2dfabeb8ad98baffca3c8/src/lean_interact/server.py)。

#### 3. LeanCopilot：确有搜索需要时加入 Lake

以下是上游 v4.34.0 组合的配置写法；用于最新 Lean4.34.1 之前要做 patch 兼容验证，不自动宣称通过：

```lean
import Lake
open Lake DSL

package rdsSearch where
  moreLinkArgs := #[
    "-L./.lake/packages/LeanCopilot/.lake/build/lib",
    "-lctranslate2"
  ]

require LeanCopilot from git
  "https://github.com/lean-dojo/LeanCopilot.git" @
  "5af8991b700271d4221bdd303aacdcd4fa29f167"
```

```lean
import LeanCopilot

example (a b : Nat) : a + b = b + a := by
  search_proof
```

构建依赖和模型下载是实质成本；本次未执行 `lake exe LeanCopilot/download`。该包支持 `NativeGenerator`（CTranslate2 FFI）、`ExternalGenerator`（外部模型 API）与自定义 `TextToText` 实例。`select_premises` 使用固定快照，升级 mathlib 后不能默认为完整覆盖当前定理库。Windows 需确保动态库搜索路径；Linux executable target 另有 libstdc++ 链接注意事项。[官方安装/接口](https://github.com/lean-dojo/LeanCopilot/blob/a303359eedb1104276cdf3c4495c305c482ebadb/README.md)、[外部模型 API schema](https://github.com/lean-dojo/LeanCopilot/blob/a303359eedb1104276cdf3c4495c305c482ebadb/external_model_api.yaml)。

#### 4. Pantograph：把 tactic 分支管理交给成熟接口

下面与已读官方例子相同的接口，可以作为其自身固定 toolchain 下的 smoke test；**并非 4.34.1 兼容代码声明**：

```python
from pantograph.server import Server

server = Server(imports=["Init"], timeout=30)
state0 = server.goal_start("forall (p q : Prop), Or p q -> Or q p")
state1 = server.goal_tactic(state0, tactic="intro")
print(state1)
```

若要关联目标项目可传 `project_path=...`；但目标 `.olean` 必须与 Pantograph 绑定的 Lean 一致。其 Python 层用 `asyncio.create_subprocess_exec` 与 stdin/stdout，不等于直接 Python FFI。standalone Pantograph 另外公开共享库 FFI 接口；两者不能混称，接口也不是一一对应。[示例](https://github.com/stanford-centaur/PyPantograph/blob/f8aee320ee5550ea2677e414534618a61e7e1497/examples/simple.py)、[Python transport](https://github.com/stanford-centaur/PyPantograph/blob/f8aee320ee5550ea2677e414534618a61e7e1497/pantograph/server.py)、[底层库入口](https://github.com/leanprover/Pantograph/blob/main/README.md)。

#### 5. Kimina：有批量需求时的服务边界

对已经部署且 toolchain/project/REPL 均锁定的本地 Kimina server：

```python
from kimina_client import KiminaClient

client = KiminaClient(
    api_url="http://127.0.0.1:8000",
    http_timeout=60,
    n_retries=0,
)
response = client.check(
    "example (n : Nat) : n = n := by rfl",
    timeout=15,
    reuse=True,
    max_workers=1,
    show_progress=False,
)
print(response)
```

显式指定本地 URL，避免配置继承和不同 README 版本的默认值造成混淆；当前 `base.py` 默认是 `LEAN_SERVER_API_URL` 或 localhost:8000，而 `README-client.md` 仍描述旧的远端默认值。当前 sync SDK 内部用 `/api/check`；主 README 的 `/verify` 是另一接口示例，不应混用 schema。区分服务端证明 `timeout`、客户端 `http_timeout`、排队等待和自动重试；自动重试次数也计入 RDS 的总验证预算。[base.py](https://github.com/project-numina/kimina-lean-server/blob/fb2393de3461db35eda4c714e3fd21187e92ec90/client/kimina_client/base.py)、[sync_client.py](https://github.com/project-numina/kimina-lean-server/blob/fb2393de3461db35eda4c714e3fd21187e92ec90/client/kimina_client/sync_client.py)。

配置接入点是 `LEAN_SERVER_PROJECT_DIR`、`LEAN_SERVER_REPL_PATH`、`LEAN_SERVER_MAX_REPLS`、`LEAN_SERVER_MAX_WAIT`、`LEAN_SERVER_MAX_REPL_USES`。README 中每进程硬内存限制为 Linux-only；Windows 不应依赖同名配置就认为限制生效。其 `gc:true` 会清理环境，不能将返回状态无条件当作长期保留的会话。[server 配置说明](https://github.com/project-numina/kimina-lean-server/blob/fb2393de3461db35eda4c714e3fd21187e92ec90/README.md)。

#### 6. LeanDojo-v2：只在明确需要时使用外部 prover

已读官方文档中的最小整体证明生成入口如下；它会调用外部推理，**这里只作 API 说明，本次未运行**：

```python
from lean_dojo_v2.prover import ExternalProver

prover = ExternalProver()
proof = prover.generate_whole_proof(
    "theorem my_and_comm : forall {p q : Prop}, And p q -> And q p := by"
)
```

这一步返回候选，不是 RDS 的科研主线决策器，也不能替代 Lean 验证。官方完整 quick start 包含 tracing、训练和模型权重，成本远高于单一 REPL。若当前只缺检验接口，不应把整套训练栈、动态数据库和新生命周期带入主线。[v2 官方接口与依赖](https://github.com/lean-dojo/LeanDojo-v2/blob/baed5eae6e87a65a446d9f54af07aab2154e7599/README.md)。

### 性能、可信边界与失败恢复

#### 持久进程的收益应准确表述

**复用进程/环境可摊薄 process startup、Lake environment setup 和重复 import 的成本；它不会消除 JSON 编解码、IPC、elaboration、tactic 执行或 kernel checking。** LeanInteract/PyPantograph 的实际源码都使用管道子进程；Kimina 还增加 HTTP、排队与调度。是否净加速，取决于 RDS 请求数量、import 大小、cache hit rate、证明本身耗时和内存，必须本机测量。[LeanInteract transport](https://github.com/augustepoiroux/LeanInteract/blob/976edd7d38a99e1ea4c2dfabeb8ad98baffca3c8/src/lean_interact/server.py)、[PyPantograph transport](https://github.com/stanford-centaur/PyPantograph/blob/f8aee320ee5550ea2677e414534618a61e7e1497/pantograph/server.py)、[Kimina 原始论文](https://arxiv.org/abs/2504.21230)。

上游论文测到的加速不能直接记为 RDS 已节省的算力。推荐只在真实 LeanFormal 代表请求上比较冷启动、热进程、不同 import header 三种情形，记录 p50/p95、总验证 walltime、峰值内存和失败率。只有同预算下确实多排除了错误候选、或更早改变下一实验，才计入 RDS 的业务收益。这是本报告的工程判断，未做本地实验。

#### “Lake Socket”不是已核实的通用产品接口

官方 Lake 文档给出的入口是 `lake serve`，它在项目环境中运行 Lean language server；标准 Lean LSP/扩展 RPC 与某个自定义 TCP socket wrapper 是不同层。官方 LSP IPC 文档显示 stdin/stdout 管道；Lean 扩展 RPC 的引用绑定打开文件与 session，需要 connect/keepAlive/release。对当前仅需提交完整证书的 RDS，自写 LSP 生命周期通常比复用 REPL 成本高；若要编辑器快照和位置级交互再考虑。[Lake serve](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/)、[LSP IPC](https://lean-lang.org/doc/api/Lean/Data/Lsp/Ipc.html)、[Lean RPC session](https://lean-lang.org/doc/api/Lean/Server/Rpc/Basic.html)、[RPC 引用释放](https://lean-lang.org/doc/api/Lean/Data/Lsp/Extra.html)。

#### 搜索器与 checker 分工

1. LLM、LeanCopilot、LeanDojo、外部求解器负责寻找候选证明/证书，允许失败和超时。
2. REPL/Pantograph/Kimina 负责交互与执行反馈，不自动保证自然语言研究问题被正确形式化。
3. 最终产物必须恢复为锁定命题的完整 Lean 声明，在 RDS 固定 toolchain、imports、允许公理集合下重放；保存 theorem source、声明类型、依赖版本、日志和证书哈希。
4. **`goals=[]` 不是整个工程已经无 sorry 的保证。** community REPL 明确允许 tactic mode 中的 sorry，并说明完成 proof state 尚不能自动回填原始 declaration。不能仅凭空目标列表放行。[REPL tactic mode](https://github.com/leanprover-community/repl/blob/bbeedf38e0898869fc3b7c009e1ea877b46204e4/README.md)。
5. “外部高速求解 + Lean checker”应说明 checker 的 soundness 定理、输入语义和算术语义。`native_decide` / `decide +native` 会把 compiler/相关实现加入信任边界；不能写为与纯内核归约完全同一可信基。普通 proof-term/kernel replay、`decide` 与 native evaluation 要分别记录。[官方 tactic reference](https://lean-lang.org/doc/reference/latest/Tactic-Proofs/Tactic-Reference/)。

#### 状态与超时的具体边界

| 场景 | 已核实机制 | RDS 应记录/采取的动作（工程建议） |
|---|---|---|
| LeanInteract 请求超时 | `LeanServer` kill REPL；`AutoLeanServer` 可重启，用用户选择的 session cache 重建环境 | 返回 `UNKNOWN/TIMEOUT`，不能判数学失败；将 session generation 与 env id 一起绑定，原始未缓存状态不可继续使用 |
| LeanInteract 自动恢复 | 默认 `ReplaySessionCache`；缓存项以负 ID 表示；实例删除后不持久；另有 pickle 方案 | 明确重放成本与重试上限；持久化源请求/版本而不是只存整数 ID |
| PyPantograph 超时/非法 JSON | 关闭进程并抛 `ServerError`；ready 失败可能是版本不匹配或 timeout | 重启后重建 imports/goal；丢弃旧 state id；保存原因而非“proof rejected” |
| REPL pickle | 可存环境/proof state，恢复返回新 ID；README 指出 scoped environment extension 的 pickle 限制 | 仅同 toolchain/imports 下恢复；优先源代码重放作为恢复基线；`.olean` 不当成跨版本通用证书 |
| Kimina worker 池 | 同时多个 REPL，import cache、gc、worker 数与生命周期配置 | 不把一次 HTTP 成功或无错误日志当作 proof acceptance；总预算包含队列和重试 |

对应代码来源：[LeanInteract 恢复实现](https://github.com/augustepoiroux/LeanInteract/blob/976edd7d38a99e1ea4c2dfabeb8ad98baffca3c8/src/lean_interact/server.py)、[Pantograph 超时实现](https://github.com/stanford-centaur/PyPantograph/blob/f8aee320ee5550ea2677e414534618a61e7e1497/pantograph/server.py)、[REPL pickle 限制](https://github.com/leanprover-community/repl/blob/bbeedf38e0898869fc3b7c009e1ea877b46204e4/README.md)。

### 前沿证据、反证与未验证事项

- **Pantograph 原论文**：Aniva 等，*Pantograph: A Machine-to-Machine Interaction Interface for Advanced Theorem Proving, High Level Reasoning, and Data Extraction in Lean 4*，arXiv:2410.16429，v2 为 2025-01-31。支持对高级证明搜索/推理状态接口的定位，不支持任何 RDS 实验决策提升结论。[原文](https://arxiv.org/abs/2410.16429v2)。
- **LeanCopilot 原论文**：Song、Yang、Anandkumar，*Lean Copilot: Large Language Models as Copilots for Theorem Proving in Lean*，arXiv:2404.12534。工具侧重点是 tactic 建议、证明搜索和 premise selection；适合作为可替换 proposer。[原文](https://arxiv.org/abs/2404.12534)。
- **Kimina 原论文**：*Kimina Lean Server: A High-Performance Lean Server for Large-Scale Verification*，arXiv:2504.21230。其机制是多个进程与 imports 复用；支持摊薄初始化成本，而非“无进程开销”。[原文](https://arxiv.org/abs/2504.21230)。
- **2026 年状态快照方向**：Shen、Shi，*Keep the Proof State Live: Snapshotting for Efficient Tactic Search in Lean 4*，arXiv:2605.25556v2（2026-05-27），指出 import cache 与 theorem-body proof-state snapshot 是不同优化层。论文报告在其 48 个 miniF2F-v2 题目设置下加速，但这不是 RDS 测量。作者声明未来开源；其文内 `A2DR1/Lean_Snapshot` 仓库在本次 GitHub 页面与 API 核查均为 404，因此本报告不把它列为现成可拿来用的依赖。[论文](https://arxiv.org/abs/2605.25556v2)、[文内仓库](https://github.com/A2DR1/Lean_Snapshot)。

最强反向证据是**版本耦合和工作负载差异**：PyPantograph 当前绑定4.29.1，LeanInteract README 与 fork tag 不一致；完整 theorem server 可能加重只有少量请求的 CPU 闭环。证明搜索效率、形式化命题正确性、实验主张正确性，是三个不同验收层次。

仍未验证：RDS 当前4.33.1以及获授权升级的4.34.1对各组件的实际编译/运行兼容性、Windows 进程取消与内存上限、LeanInteract 与最新版 community REPL 的完整协议兼容、实际 startup/import 成本、LLM证明建议能否减少 RDS 无效实验。以上均不得在主报告写为“已实现/已验证”。

## 9. 证据状态与尚待验证的事项

这份调研已完成源码和文献核查，不等于将这些工具全部集成进 RDS。没有获得某接口的官方适配证据，表示本次限定范围未找到，不能推断该接口绝不存在。所有本地构建、真实吞吐与最终交付状态以 [协作账本](collaboration-ledger.md) 的后续验收快照为准。

当前最重要的未知是：4.34.1 对所选附属包的实际兼容性；LeanCert 某一具体导出/检查路径的完整 kernel 证据；大求解器证书到 Lean 的支持子集；神经网络实数语义与部署浮点实现的桥接；以及这些工具是否在公平完整轨迹上提高研究进展。逐一针对具体问题补证据，避免把生态清单变成无边界实施清单。

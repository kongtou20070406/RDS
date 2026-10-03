# 张量算子等价性的形式化路线

研究核查日期：2026-10-02；工具链策略更新日期：2026-10-03。本文为 RDS 当前有限精确张量执行器提出可逐步验收的扩展路线。文献或上游代码已有的能力、RDS 尚未实现的能力，以及建议的边界分别说明；本文不代表新的验证后端已经上线。

## 建议

按“Lean 中的通用符号语义与定理 → E-Graph 候选搜索和证明见证 → Lean 内核重放 → 具体框架/硬件语义桥接”的次序扩展。先限定有限维、形状索引、实数语义的张量代数；不把具体有理数求值、实数定理、IEEE 浮点执行和模型导出视为同一语义。黎曼几何及无限维算子复用同一个可信证明核心，但作为有各自类型与前提的后续理论域，不塞入第一版数组 DSL。

RDS 跟进配套的 Lean/Mathlib 最新稳定版，当前为 **4.34.1**，按[成对升级流程](lean-toolchain-upgrades.md)维护。每个验收提交仍记录确切版本与 SHA，用来重放证明和绑定证书；4.33.1 不再作为依赖评估的长期上限。升级须重新构建、审计公理并重放原生证明。仓库根目录运行 `python -B scripts/update_lean_toolchain.py --check` 查询最新稳定配对，`--apply` 同步更新配置，`--check-lock` 离线核对一致性，再按流程构建和验收。

## 已有基础与差距

RDS 的 `rds_tensor_verify.py` 对有界秩和元素数的具体行优先张量执行精确有理数加法、缩放、转置及非广播批量矩阵乘法；它检查给定输入值，不证明对所有张量成立的符号恒等式。RDS 固定模板 Lean 适配器也不接受任意 Lean 源码或用户 tactics。现有边界见[形式化验证指南](formal-verification.zh-CN.md)和[Lean 生态综述](lean4-ecosystem-survey.md)。

有可直接利用的外部工作，但职责不同：

| 工作 | 已发表/上游能力 | 建议在 RDS 中的角色与限制 |
| --- | --- | --- |
| [TensorRight，POPL 2025](https://doi.org/10.1145/3704865) | 对任意秩、任意尺寸张量图重写，利用聚合轴把无界问题归约为有限个有界义务并交给 SMT；论文报告验证了 XLA algebraic simplifier 的 175 条规则中的 115 条。 | 作为规则语义、形状前提和独立差分基准的首选参照；其 SMT 验证结果不等于 Lean 内核证明，也不是可直接 import 的 RDS Lean 依赖。 |
| [TENSAT，MLSys 2021](https://proceedings.mlsys.org/paper_files/paper/2021/file/cc427d934a7f6c0663e5923f49eba531-Paper.pdf) 与 [egg](https://popl21.sigplan.org/details/POPL-2021-research-papers/23/egg-Fast-and-Extensible-Equality-Saturation) | E-Graph 等价饱和用于探索张量图重写并选择低代价实现。 | 负责找候选等价路径和提取优化图。正确性仍以每条规则 sound 为前提；饱和成功、代价更低或测试通过都不构成证明。 |
| [Lean 中的 equality saturation，POPL 2026](https://doi.org/10.1145/3776667) | 将 Lean 定理作为带条件重写规则，记录 E-Graph 解释，再重建由 Lean 检查的证明；条件成为待证明义务。 | 最贴合“搜索可扩展、裁决由内核完成”的桥接研究。引入前应固定上游 commit，审查 Lean 版本、规则条件处理、重建证明和许可证，并在 RDS 当前验收的稳定配对上做独立兼容探针；必要时成对升级。 |
| [TorchLean](https://github.com/lean-dojo/TorchLean) 与[论文](https://arxiv.org/abs/2602.22631) | 以形状携带类型的张量、网络语义、图变换和证书验证为目标；项目当前覆盖实数及 IEEE 浮点语义等路径。 | 是最相关的 Lean 深度学习参考/候选依赖。2026-10-03 核查的上游 commit `b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36` 使用 Lean/Mathlib 4.34.0，本次 RDS 使用 4.34.1。先在隔离 Lake workspace 中按 RDS 当前稳定配对重建并测试，不能混用 `.olean`；再根据兼容证据决定移植少量定理或维护单独版本子项目。运行时/FFI 的存在本身不证明该实现与数学语义相符。 |
| [Mathlib 张量积](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Analysis/InnerProductSpace/TensorProduct.html)、[连续线性算子](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Analysis/Normed/Operator/ContinuousLinearMap.html) | 提供内积空间张量积、算子映射及连续线性映射等抽象基础。 | Mathlib 已是当前 RDS Lean 依赖，优先薄封装并在当前验收的稳定配对上实际编译。有限族的 projective tensor product 不代表所有 Hilbert 完成张量积都已覆盖。 |
| [Mathlib Riemannian 基础](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Geometry/Manifold/Riemannian/Basic.html) 与 [Levi-Civita](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Geometry/Manifold/VectorBundle/CovariantDerivative/LeviCivita.html) | Riemannian 流形基本结构；当前 Levi-Civita 文件明确针对有限维流形。 | 后续几何模块可复用。流形上的张量场是丛截面，依赖切丛/余切丛、光滑性、度量及坐标变换；它不是把数组 AST 换个名字。不要推断 Mathlib 已覆盖无限维黎曼几何。 |

TensorRight 的价值是给“任意维度规则如何归约为有限义务”一个现成对照，Lean equality saturation 工作则提供由内核认证重写轨迹的方向。两者可以组成独立候选生成/检查器与 Lean 证明的分层，但需要显式桥接相同的 DSL 和语义。

## 分阶段工程路线

### 1. 有限维符号张量（优先）

在现有 Mathlib pin 下，定义带 `Shape : List Nat` 的张量表达式及解释函数。类型构造子至少区分元素域、形状、布局和算术语义。第一批覆盖同形加法、标量乘、轴置换/转置、矩阵乘法与收缩；广播、reshape、归约、动态维度及稀疏结构逐项增加，只有语义和边界写清楚后才加规则。

恒等式定理对任意合法形状和任意输入张量量化；维度相等、索引范围、非空归约等条件显式出现在类型或定理前提中。编译图导入层另负责证明/检查导入节点确实对应该解释函数。示例目标是矩阵乘法结合律与转置-乘法关系，随后覆盖批维规则和边界形状。

### 2. E-Graph 只搜索，Lean 负责裁决

规则注册表只列有 Lean 定理支撑的命名规则、方向、替换变量、前提和版本。E-Graph 不接收用户任意可执行规则作为可信事实。每条提取路径输出规则 ID、方向、匹配位置、替换及条件证明义务；独立重建器按原始输入 AST 重放并让 Lean kernel 检查目标等式。证明者只可建议证明项，不能改写待检命题或语义定义。

证书绑定规范化 AST、形状/布局、元素语义、规则库 hash、Lean/Mathlib pin、导入模型 hash 和 checker 版本。闭合证明得到 PASS；经支持语义检查的反例才是 FAIL；无规则、条件未解决、超时、预算耗尽或语义桥缺失返回 UNKNOWN。饱和或抽取出更低成本图本身不能改变状态。

### 3. 数值与模型边界

把数学实数上的等价和执行实现等价拆开。`ℝ` 上的 reassociation 一般不能无条件迁移到 Float32/Float64；舍入、溢出、NaN、次正规数、FMA、并行 reduction 次序及设备 kernel 都可能改变结果。浮点结论须绑定 IEEE 操作语义和明确误差/观察关系，再证明图导入或 exporter 与目标运行时对应。TorchLean 可作候选依赖/参照实现，先在隔离子项目中测试当前稳定配对；必要时允许 RDS 工具链成对升级，并通过仓库构建与证明重放验收。

### 4. 黎曼与无限维理论（独立里程碑）

几何模块从有限维黎曼流形开始：切/余切张量、张量丛映射、度量诱导的升降指标、协变导数、曲率及等变变换。每个结论说明光滑性、维数、坐标图及非退化度量假设。对优化器状态或参数流形应用时，另证明实际算法与所建几何对象之间的映射。

无限维模块先确定对象类别，而非笼统增加“高阶张量”：Banach/Hilbert 空间上的有界线性算子、连续多线性映射、代数张量积、projective/injective 张量范数及 Hilbert tensor completion 是不同定义。算子范数界、连续延拓、稠密子集上的相等何时可扩展、算子定义域/闭性，都要写入前提。Mathlib 某个有限族张量积接口能处理无限维因子，不等于已提供所有完成张量积或无限维流形定理。

## 防符号博弈的验收门槛

| 用例 | 预期结果 |
| --- | --- |
| 对任意合法维度的矩阵结合律，提供正确重写路径 | Lean kernel 重放后 PASS，并显示最终定理与公理依赖。 |
| 移除矩阵乘法收缩维度相等前提 | 不能通过形状检查或产生可检查的失败；不得静默广播。 |
| 注入错误重写，例如交换非交换矩阵的乘法次序 | Lean 无法证明时 UNKNOWN；不得因 E-Graph 合并而 PASS。 |
| 条件规则的前提未证，或 E-Graph 达到节点/时间预算 | UNKNOWN，保留未解决义务与资源记录。 |
| 在真实浮点语义下重结合会改结果 | 不能复用 `ℝ` 定理给出 PASS；应返回反例或 UNKNOWN。 |
| 修改图、ops-set/版本、形状、权重或运行语义 | 旧证书因输入绑定不匹配而拒绝。 |
| 在流形图册或无限维算子定理中缺少正则性/有界性假设 | 定理前提不得被有限数组规则隐含补齐。 |

因此建议先实现一个可独立构建的 Lean 符号张量定理探针和证书格式，再评估 Lean-E-Graph 与 TorchLean 的隔离依赖。只有证明重放、错误规则拒绝、形状失败和语义区分全通过后，才把它登记为 RDS 后端。工具链升级流程已另行落实；本张量设计不声称已完成候选依赖引入或通用张量后端。

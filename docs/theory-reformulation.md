# 理论改写：拓宽路线，保留原问题

当代理指标通过而任务仍停滞，或研究者明确要求更宽的方法时，先分清原命题、当前模型、实际更新和最终验收。寻找新表述，不先假定旧理论无效或某个“母理论”必然更优。图已经可达也可以提出改写；没有数值残差时不编造失败率或结构性天花板。

## 让模型提出有区别的下一步

这里的 jump 是工作方式：保持原研究目标，重新提出可检验的解释、表示或计算路线。它可以是删除一个多余假设、寻找有限归约或增加必要状态；没有从参数到几何再到 SSM 的通用优越性阶梯。从手推到计算机辅助证明通常改变算法与证书形式，并没有更换数学公理。

Advisor 从已有的 `selection_review` 与同作用域 checkpoint 审查生成 `next_move`。目标未知、当前可用路线缺少预测前提或历史损坏时先补证据；已记录重复否决、目标未达到或预测无区分度时，给出重表述或判别检查建议。已过滤的旧路线及无关候选缺陷不打断可用的新路线；健康的单条证明义务不强制编造竞争假说。`--brief` 只返回动作名，完整理由、来源与提示保存在原 CAS；选择记录沿用同一 ledger。无记录的讨论及任意自然语言同义改写仍不能由程序可靠判同。

消费这条建议时，模型应完成一个短的实际提案，而不是复述警报：

1. **指出卡住的假设。** 分开用户的目标/方法约束与模型自行引入的假设；未知测量、实现错误和真正反例分别处理。
2. **提出不同后果。** 与最小修补相比，候选改变了什么前提、状态表示、干预或证明归约？如果改变成立，哪项同作用域观测或证明义务会不同？先接受有来源的待检验候选，不要求创意诞生时已有完整证明。
3. **选择一个会改变决定的检查。** 可用精确小例、反例搜索、真实模型的受控干预或固定假设的模拟。先估算成本并绑定实际入口；五秒和十秒不是通用可行性要求。玩具模型和想象情景提出问题，不独立证实真实系统。
4. **根据结果选择。** 保留原目标、停止条件与投入授权；失败只排除证据覆盖的条件，改变假设后可重开。新方法不因更复杂而获优先级，也不因暂未改善最终指标而自动永久淘汰。

这些是候选生成与检验的接口，不是已实现的通用科学创造力。程序能定位显式缺口、检索工具和检查提案结构；具体解释仍由研究者/模型提出，适用性依赖独立证据。不得把两轮平台、某个漂移比值或多次讨论自动升级为理论不可能性，更不能由其自动获得 GPU 或改题授权。

### 论文启发与边界（核查于 2026-10-01）

[Zahavy 的 ICML 2026 立场论文](https://proceedings.mlr.press/v306/zahavy26a.html)提出，从经验构造解释性前提是与演绎验证不同的瓶颈。作者的[最新范围澄清](https://www.tomzahavy.com/projects/llms-cant-jump)明确没有否认 LLM 系统能做科学发现；其关注的是特定的、以物理直觉为基础的概念跃迁。本文不能作为“任意 LLM 结构上永不可能提出新假设”的证明，也不要求 RDS 先拥有通用世界模型。

近期的 [HALO v2（2026-07-22）](https://arxiv.org/abs/2607.18564v2)通过候选观察、策略识别和策略组合辅助药物假说生成，其研究涉及 10 位药物化学专家，不能外推为无人通用发现。[主动溯因探针（2026-08-04）](https://arxiv.org/abs/2608.03388v1)报告自选证据可能支持当前解释却不足以区分替代解释。这支持检查“下一次观测能改变什么决定”，不支持固定轮数封锁。

## 按需查预载工具与可运行算子脚手架

八张有适用条件的工具卡预载在[目录](../references/theory-tools.json)，按当前信号查一至三张摘要，再按 ID 读取需要的一张：

```text
python -B scripts/rds_theory_tools.py --signals trajectory_degradation local_global_gap --limit 3
python -B scripts/rds_theory_tools.py --id <returned-card-id>
```

核心卡片提供标准库可运行的算子模板（[scripts/rds_operators.py](../scripts/rds_operators.py)），用于固定合成示例和后续集成参考。导出使用与内置算子相同的实现，并包含正反例断言：

```text
python -B scripts/rds_theory_tools.py --list-operators
python -B scripts/rds_theory_tools.py --test-operator state_space_refinement
python -B scripts/rds_theory_tools.py --scaffold state_space_refinement --out operator.py
```

- `--list-operators`：列出理论卡、主信号与检查范围；元数据不验证当前研究的适用性。
- `--test-operator <card-id>`：完整运行固定合成示例诊断，输出 JSON 中的 `test_result`。退出码对应科学检查状态：`PASS=0`、`FAIL=1`、`UNKNOWN=2`。状态空间示例正常完成有限诊断后仍为 UNKNOWN、退出 2；自动化应读取报告，区分执行故障和未解决的科学断言。
- `--scaffold <card-id> [--out <path>]`：导出独立 Python 模板。直接运行模板会执行正反例断言，输出独立的 `self_test_status`；自检成功不提升其中的科学检查状态。`--out` 仅适用于该模式，默认独占创建新文件，拒绝覆盖已有文件；省略时在 JSON 中返回代码。

状态空间的有限 NFE 比较属于数值诊断：`diagnostic_pass=true` 可以与 `status=UNKNOWN` 同时成立，有限差值和玩具输入不能证明渐近收敛或步长不变性。收缩分析分别报告严格范数条件、工程余量、不动点数值求解与目标偏置；未知目标或求解失败不能记为零偏置。多项式区间 PASS 需要覆盖声明区间的精确有理包围界；精确点可以构成反例，只有有限采样或未得到包围证明时仍为 UNKNOWN。

基础算子库包含 22 项确定性、闭环物理、概率统计与通用第一性原理算子：

### 通用第一性原理算子（放之四海皆准）
- 量纲齐次性与超越函数无量纲检验（`dimensional_homogeneity`）：基于 Buckingham $\pi$ 定理与国际单位制（SI）7 基本物理量纲指数向量 `[L, M, T, I, Theta, N, J]`，在加法项之间进行严格的量纲一致性匹配，并强制要求超越函数（$\exp, \ln, \sin$ 等）的输入必须完全无量纲，从根本上杜绝“米加秒”或“以带单位物理量作为指数”的非物理理论推演。
- 因果前序与时间超前泄漏拦截（`causal_dag_no_leakage`）：基于严格时间箭头（$t_{\text{cause}} \le t_{\text{effect}}$）与有向无环图（DAG）拓扑排序，检验因果流向与特征工程是否存在将未来标签反向输入给过去状态的 look-ahead 泄漏，并拦截任何循环因果闭环。
- 数据处理不等式与信息单调性（`data_processing_inequality`）：基于香农信息论马尔可夫链 $X \to Y \to Z$ 互信息单调不增定理（$I(X; Z) \le I(X; Y)$），拦截任何下游后处理阶段凭空伪造互信息增益的幻觉。
- 连续性方程与守恒流平衡（`conservation_flow_balance`）：基于物理连续性方程与基尔霍夫节点定律（$\text{流入} - \text{流出} = \text{累积变化}$），对物理质量、能量、电荷或算力 Token 网络的节点流平衡进行零泄漏确定性审计。
- 柯尔莫哥洛夫概率公理与归一化（`kolmogorov_probability_axioms`）：基于概率论柯尔莫哥洛夫公理体系，验证事件概率非负性（$p_i \ge 0$）、全概率空间测度归一性（$\sum p_i = 1.0$）及分布合法性，提供精确的反例数值坐标证人。

### 统计学、概率学与动力学算子
- 盖尔圆盘谱界分析（`gershgorin_spectral_bound`）：基于 Lean 4 Mathlib Gershgorin 圆盘定理（`Mathlib.LinearAlgebra.Matrix.Gershgorin`），在离散收缩谱半径、非奇异性（严格对角占优）与连续 Hurwitz 稳定性间提供精确有理数证书，越界时提取圆盘与违背行作为反例证人。
- 复合层 Lipschitz 界（`lipschitz_layer_bound`）：基于 TorchLean 与 Mathlib 连续线性算子范数界，给出逐层 Frobenius 与无穷范数积，验证输入扰动输出容差上界，超出裕度时提供超标比率反例。
- 次高斯 Hoeffding 集中界（`hoeffding_sample_bound`）：基于 Mathlib 次高斯矩尾界（`ProbabilityTheory.HasSubgaussianMGF`），计算有限样本置信半径与所需样本量，阻断小样本随机方差被误判为科学增益的统计幻觉。
- 2D 有理 Voronoi 域覆盖（`rational_voronoi_partition`）：验证离散几何紧覆盖，精确检测未覆盖空洞并输出未覆盖点坐标。
- 多步 Lyapunov 能量耗散（`multi_step_energy_dissipation`）：沿多步轨迹跟踪二次 Lyapunov 能量单调下降，在出现能量放大的步数输出发散步与增量凭据。
- 马尔可夫与切比雪夫非参数尾部界（`markov_chebyshev_bound`）：根据一阶矩（均值）与二阶矩（方差），在无分布先验下计算单侧及双侧概率尾部极值上界，提供无偏风险证人。
- 假发现率多重假设检验控制（`false_discovery_rate_bh`）：提供独立假设下的 Benjamini-Hochberg (BH) 与任意相关依赖下的 Benjamini-Yekutieli (BY) 严格 $q$ 值阈值控制，剔除伪假说。
- 随时有效 Ville 检验与超鞅停机（`sequential_ville_eprocess`）：基于 Ville 超鞅不等式（$P(\sup_{t} E_t \ge 1/\alpha) \le \alpha$），构建抵御任意可择停机偏差（optional stopping）的序列证据积累算子。
- 经验伯恩斯坦方差自适应集中界（`empirical_bernstein_bound`）：基于样本经验方差动态收缩置信区间，在大样本低方差工况下给出远优于最坏情况 Hoeffding 界的紧致误差半径。
- 辛几何哈密顿能量守恒（`symplectic_energy_conservation`）：在相空间 $(q, p)$ 中跟踪哈密顿总能量 $H(q, p)$ 的数值漂移，区分数值伪耗散/伪发散与真实动力学守恒。
- 控制屏障函数离散前向不变性（`control_barrier_invariance`）：基于离散 Control Barrier Function (CBF)，对状态轨迹进入并保持在安全集合 $h(x) \ge 0$ 的前向不变性提供严格充要证书。
- 庞加莱横截面极限环收缩（`poincare_section_return`）：在多维非线性动力系统中建立余维为 1 的局部横截超平面，检测轨迹穿越点序列的返回映射收缩因子与周期极限环轨道稳定性。
- 刘维尔定理相空间体积演化（`liouville_phase_volume`）：计算流场 Jacobian 矩阵迹（散度），严格界定相空间体积连续演化率，认证体积保持流（保守系统）或耗散吸引子收缩率。

摘要保留 `id/title/reason/matched_tags/required_inputs/locator/runnable_operator` 和目录 SHA；`selection=TAG_MATCH_ONLY`、`prerequisites=NOT_ASSESSED`。标签命中只提供工具线索，不验证前提、排名科学价值或授权执行。`goal.reformulation.signals` 可以附同一短名单，历史 `as_of` 必须允许该目录日期。Skill 只给入口，不加载整个库；没有匹配时保留未匹配数量，不硬塞无关工具。

## 最小契约

在原 Frontier goal 添加以下片段；这是字段说明，不是完整可运行输入：

```json
{"reformulation": {
  "current_model": "current-model-node",
  "reason": "局部条件已检查，但尚未建立到原目标的适用桥梁",
  "source": {"path": "original-comparison.json", "locator": "/scope"},
  "available_on": "2026-10-01"
}}
```

程序保留原 `target/decision`，产生 `THEORY_REFORMULATION`。回复沿用 proposal 的 `relations/assumptions/test/next_if_positive/next_if_negative`，`theory_bridge` 只需候选、映射和来源，避免重复填写原问题：

| 字段 | 内容与默认值 |
| --- | --- |
| `candidate_model/mapping` | 必填：已定义候选节点和具体对应；候选须在通向原目标的提案路径上 |
| `source_model` | 可省略，复用 gap 的当前模型 |
| `kind` | 可省略，默认 `unspecified`；如 `exact_reduction/approximation/analogy/alternative` 或其他短标签，仅帮助表达，不是必选分类 |
| `preserved_claim` | 可省略，默认原目标且保留性未验证；主张确切等价时需写明实际命题 |
| `changed_assumptions/applicability_conditions` | 可省略，前者为空，后者复用 proposal 的 `assumptions`；只补真正不同的前提 |
| `source/available_on` | 来源定位必填；`as_of` 下可用日期必填，新节点相同；无 cutoff 时缺日期也不能冒称已核实时间 |
| `domain/error_bound` | `approximation` 额外需要的有效域和误差声明；声明不是已核验误差界 |

下面是回复中的桥接和证明检查片段；模型 ID 须由同一 pack 的既有节点或有来源的新节点定义，另填关系、假设与正负下一决定：

```json
{"theory_bridge": {
  "candidate_model": "discrete-state-model",
  "mapping": "h=x, f(h,u)=T_u(h), observation=identity; same initialization and discrete index",
  "source": {"locator": "explicit synthetic identity-embedding example"},
  "available_on": "2026-10-01"
},
"test": {
  "kind": "proof_check", "outcomes": ["verified", "counterexample", "unresolved"],
  "protocol": "Compare both updates under the declared mapping",
  "measurement": "Equality of the same finite-index sequence",
  "stop_condition": "Keep unresolved if the update or premises are unavailable"
}}
```

经验检查给出同作用域的不同预测和观测。证明检查保留三个结果：已验证/反例对应正负后续决定，未解决保持停止条件；无需编造 rival 理论。必须核对证明是否对应同一映射、命题和前提；证明一个无关的小不等式不能认证整条改写路线。

缺定义为 `NEEDS_DEFINITION`；结构完整为 `NEEDS_EVIDENCE`。输出保留 UNKNOWN 适用性、PROPOSED 关系和未授权执行；理论改写不会自动进入可执行候选池。来源 URL、日期或自签 PASS 都不会升级证据。`as_of` 下缺日期及未来来源不参与历史路线；沿用最多 16 proposals、每条 16 新节点/32 关系、128 KiB pack 等边界。只检查显式候选，不枚举一个无限理论格。

## 四个自包含反例

以下直接代数例是教学反例，不是对真实模型的测量，也不声称已由 Lean 验证。

1. **局部放大不推出轨迹发散。** `T(x)=min(2x,1)` 在 `[0,1]`：`x0=0` 保持零，任意 `x0>0` 有限步到 1。靠近零的斜率为 2，仍每条轨迹收敛；它不具有唯一全域吸引不动点。不能把“存在扩张区间”写成发散证明。
2. **收缩不必抹去目标细节。** 固定输入 `y` 与任意详细目标 `F(y)`，`T_y(x)=0.5x+0.5F(y)` 对状态是收缩，唯一不动点就是 `F(y)`。状态扰动衰减和输入信息丢失不是同一命题。
3. **稳定可能稳定地偏离真值。** `T_y(x)=0.5x+0.5(F(y)+b)` 收敛到偏置目标；若从 `F(y)` 出发，误差为 `(1−2^-k)b`，随步数增大。稳定性须与固定点身份、目标误差分开检查。
4. **连续稳定不保证 Euler 稳定。** `x'=-3x` 的精确一步流为 `e^-3 x`，显式 Euler 在 `h=1` 时为 `−2x`。同一生成矩阵的数值更新可能发散；时间跨度、步长、离散化与实际代码必须绑定。连续/离散状态空间及稳定性框架参见作者公开的 [Åström–Murray 教材](https://www.cds.caltech.edu/~murray/books/AM08/pdf/am08-complete_20Feb10.pdf)。

## 状态空间是候选，不是默认答案

一般非线性离散状态模型 `h_(k+1)=f(h_k,u_k)` 以 `h=x`、`f=T`、观测恒等映射即可表示递归。这是对所声明序列的恒等嵌入，不推出某个结构化线性/选择性 SSM 包含任意不动点映射。任意 ODE 的时间 1 流也不等于其一步 Euler 更新。

[Mamba 原论文 §2](https://arxiv.org/html/2312.00752v2)区分广义 state-space 与其特指的结构化 SSM，并显式说明离散化与输入选择机制。最新核查还包括官方仓库中的 [Mamba-2/SSD 与 Mamba-3](https://github.com/state-spaces/mamba)，以及 [Mamba-3 原论文](https://arxiv.org/abs/2603.15569)：这些是序列建模的公开成果，不是 ReFRM 长链去雾质量、高频保持或任意 NFE 的保证。精度、运行实现和任务适用性仍须检查。

对 SSM 路线，可以分别检查状态/观测解耦、输入驱动、有限时域重参数化或离散化，每项保持有来源的假设和会改变下一决定的检查。MSE、score matching、optimal transport 则先明确损失、分布与对象之间的具体关系；需要时再命名关系，不能排成未经证明的包含链。

## 冻结快照的有界诊断

对导出矩阵与固定时域的 refinement 值，使用[快照检查器](../scripts/rds_dynamics_probe.py)：

```json
{
  "schema": 1,
  "source": "explicit synthetic snapshot; no model measurement",
  "declared_scope": "one local scalar update and one fixed-horizon comparison",
  "residual": [[1, 0], [0, 0.1]],
  "jacobian": [[-2]],
  "refinement": {"time_horizon": 1, "levels": [
    {"steps": 8, "value": [0.04]}, {"steps": 16, "value": [0.048]}
  ]}
}
```

将此教学输入保存为 `snapshot.json` 后，执行 `python -B scripts/rds_dynamics_probe.py --input snapshot.json --output probe.json`；真实检查须换成原始导出值与来源身份。`source_identity` 可声明运行/模型/参数等字符串身份，仍是 INPUT_REPORTED。输入不超过 1 MiB，残差矩阵最多 128×64，Jacobian 最多 64×64，refinement 为同一正时域、2–16 个严格递增步数及等长输出向量。矩阵 SVD/特征值需可选 NumPy；缺失时该部分 UNAVAILABLE，refinement 仍可用标准库。

CLI 默认只打印简短估计与各部分状态；`--output probe.json` 保存完整数据。摘要和完整输出都保留原始输入文件的 `input_file_sha256`，不能覆盖输入文件。残差能量比例按尺度归一化计算；非零残差的总平方能量若下溢，报告 `total_squared_energy=null`、`total_squared_energy_status=UNDERFLOW`，不把不可表示的总量当成零残差。

能量集中不推出最小隐状态维数；离平衡点的局部 Jacobian 不证明极限环或全局发散；步长差值变小不证明连续极限。输出保持 `global_stability/causal/task_gain=UNKNOWN`。检查器不读取或执行任意模型、不发现模型真值、不认证完整训练/部署。转向新架构或正式训练仍需原授权范围、比较预算和任务验收。改变 scope 可以重开，未答复的建议不能变成批准。

重复的代码身份映射可先用[上下文压缩入口](agent-entry.md#review-the-research-choice)移到保留完整原始数据的共享 manifest；随后审查新上下文身份，不改写旧冻结记录。只加载当前检查所需的来源与工具卡。

## 失败轨迹怎样改变下一步

先复用已保存的原始产物与收据，避免为重建一个摘要再跑训练。把进程是否成功、测量是否有效、目标是否达成分别记录；有效局部观测可以来自失败进程，成功管线也可能没有任务收益。

| 档案中的问题 | 下一步检查 |
| --- | --- |
| 局部代理通过，实际长链退化 | 绑定同一更新、checkpoint、输入域、时域与主指标，先核对局部到任务的迁移；不要只重复调代理系数 |
| 不清楚训练或测量了哪个系统 | 从真实 CLI/runner 入口读配置与代码身份，核对 hook、时间编码、裁剪/拼接和实际更新；替代脚本不能认证原入口 |
| 稳定却收敛到错误目标 | 检查不动点偏置与输入/观测映射，再决定是否改目标、状态表示或驱动；收缩证明不能替代质量测量 |
| 步数增加时结果恶化 | 区分固定步长延长时间与固定时域细化；先用冻结快照/真实更新诊断，再决定是否需要新架构 |
| 连续若干变体没有改变判断 | 保留共享失败证据，按新信息选择预载工具与一个决定性检查；没有新 scope/证据时不重新包装同一尝试 |

GPU 实验启动前须使用项目实际配置的 runner 做 preflight，核对容量、占用与可执行工作，再走原授权/预算准入。原档案的“空闲”描述不代替当前检查，入口与参数从现有配置读取。公共文档不复制私人路径或原始指标。

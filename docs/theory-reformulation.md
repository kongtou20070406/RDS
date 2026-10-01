# 理论改写：拓宽路线，保留原问题

当代理指标通过而任务仍停滞，或研究者明确要求更宽的方法时，先分清原命题、当前模型、实际更新和最终验收。寻找新表述，不先假定旧理论无效或某个“母理论”必然更优。图已经可达也可以提出改写；没有数值残差时不编造失败率或结构性天花板。

## 按需查预载工具

八张有适用条件的工具卡预载在[目录](../references/theory-tools.json)，按当前信号查一至三张摘要，再按 ID 读取需要的一张：

```text
python -B scripts/rds_theory_tools.py --signals trajectory_degradation local_global_gap --limit 3
python -B scripts/rds_theory_tools.py --id <returned-card-id>
```

摘要保留 `id/title/reason/matched_tags/required_inputs/locator` 和目录 SHA；`selection=TAG_MATCH_ONLY`、`prerequisites=NOT_ASSESSED`。标签命中只提供工具线索，不验证前提、排名科学价值或授权执行。`goal.reformulation.signals` 可以附同一短名单，历史 `as_of` 必须允许该目录日期。Skill 只给入口，不加载整个库；没有匹配时保留未匹配数量，不硬塞无关工具。

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

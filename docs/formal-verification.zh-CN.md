# 形式化验证：声明、检查与范围

[English](formal-verification.md) · [文档导航](README.zh-CN.md) · [科研工作流](research-workflow.zh-CN.md) · [术语表](terminology.zh-CN.md)

RDS 将数学命题与检验实用收益或机制的实验分开。验证器依据明确语义检查显式性质；科研运行器另行检查执行约束，记录实际发生的事情。

## 实现状态

当前 `main` 已包含 [PR #2](https://github.com/kongtou20070406/RDS/pull/2) 在 `995e8eb` 引入的数学实现，以及 Advisor／工作台集成。下表保留较早的 `f020b2c` 基础版本作为历史对照。使用接口前核对实际 ref；路线图条目不是安装后已有的能力。

| 范围 | 历史基础版本（`f020b2c`） | 当前 `main`（数学实现来自 `995e8eb`） | 后续工作 |
| --- | --- | --- | --- |
| 普通标量执行 | 受限有理 AST 与配对 MSE；准入为 `AST_ONLY`。 | 保留。 | 与数学验证分别处理。 |
| 显式标量边界 | 可选 SymPy，依据为 `SYMBOLIC_CHECKED`；不支持的情况返回 `UNKNOWN`。 | 显式命题类型、精确仿射有理证书生成器和独立检查器。 | 扩展覆盖，保留命题与证据绑定。 |
| 证书复用 | 没有独立证书检查路径。 | 绑定的标量证书及可重建的通用证明缓存，命中后仍独立检查；求解位于短暂的资源预留写事务之外。 | 扩展适配器时保留依赖绑定。 |
| 网络性质 | 没有网络验证器。 | 已注册有理 Linear/ReLU 的界、间隔和正尺度等变性。 | 更多算子及显式的导出／运行对应关系。 |
| 矩阵与动力学性质 | `dynamics` 不支持，返回 `UNKNOWN`。 | 已注册有理仿射收缩／固定点检查，以及有范围的谱半径检查。 | 更多动力学与范数，并配备独立可靠检查器。 |
| 原生 Lean | 没有原生 Lean 适配器。 | 已注册固定模板的闭合 Rat `eq`／`lt`／`le` 义务，调用显式配置的 Lean4 程序检查。 | mathlib 与带量词的模型／性质适配器。 |
| 框架、张量与模型导出 | 没有通用定理命令或模型导出。 | `formal` CLI、有限定理模块、具体精确张量检查，以及受限 Python 模型导出 API。 | 通用符号张量与更多经过检查的翻译。 |

下述接口已包含在 `main` 中。[固定版本实现契约](https://github.com/kongtou20070406/RDS/blob/995e8eb98f75697ef1ce43a9991f0686e5c29caa/references/formal_framework.md) 记录其来源版本；运行时使用已安装版本的注册和测试。PR 初始提交 `8eadae9` 只覆盖标量证书路径，不是本页描述的接口快照。

## 声明与独立检查

`main` 中的实现使用 `scripts/rds_verify.py` 和 `formal` CLI，接受有限 schema-1 声明。可信注册表包含 12 个原子数学 kind 与有限定理模块组合，区别于 23 节点方法论目录。JSON 不能注册可执行规则或用户公理。原子声明通过 `kind` 选择规则；命名模块声明使用 `by.rule`，没有顶层 `rule_id` 字段。

| 声明 kind | 框架规则／支持的义务 |
| --- | --- |
| `scalar_threshold` | `scalar.threshold_separation`：闭区间上有定义的对照界与有理干预见证。 |
| `lean_obligation` | `lean.rational_relation`：调用原生 Lean 检查固定模板的闭合有理数 `eq`、`lt` 或 `le` 命题。 |
| `affine_contraction` / `affine_fixed_point` / `affine_dynamics` | `matrix.infinity_contraction` / `matrix.fixed_point` / `dynamics.affine`：诱导无穷范数、指定固定点，或两者。 |
| `matrix_spectral_bound` / `matrix_spectral_exact` | `matrix.gershgorin` / `matrix.spectral_radius`：三角矩阵可精确判定；其他矩阵在前者使用充分界，在后者保持 `UNKNOWN`。充分界无法确定时保持 `UNKNOWN`。 |
| `scale_equivariance` | `network.positive_homogeneity`：支持的 Linear/ReLU 模型所声明的正尺度恒等式，与尺度不变性不同。 |
| `network_bounds` / `network_margin` | `network.interval_bounds` / `network.interval_margin`：输入箱上的声明界或间隔；失败需要实际经过检查的反例。 |
| `tensor_identity` / `tensor_bounds` | `tensor.exact_identity` / `tensor.exact_bounds`：具体有限张量计算，不是任意符号张量恒等式。 |
| `theorem_module` | 用 `logic.and_intro` 组合有限命名声明，不是新 Lean 语言。 |

`verify(spec)` 生成证据并独立检查，`check_certificate(spec, certificate)` 检查证书是否有效，`checked_result` 重建结论。有效的 **FAIL** 证书也能通过证书有效性检查：证据有效不等于命题成立。结果包含 `status`、`assurance`、`backend`、`semantics`、`spec_sha256`、`verifier_sha256`，得到确定结论时附证书。CLI `check` 接受框架证书或包含它的完整框架结果，重新构造结论，不信任结果中报告的状态。CLI 对 PASS／FAIL／UNKNOWN 的退出码分别是 0／1／2。这些命令不需要已初始化的科研契约。

在包含示例文件的当前 `main` 或 v5.5.0-rc.2 checkout 中运行以下命令：

```powershell
python -B scripts/rds_cli.py --root . formal rules
python -B scripts/rds_cli.py --root . formal verify --spec examples/formal/affine_dynamics.json --output proof.json --no-cache
python -B scripts/rds_cli.py --root . formal check --spec examples/formal/affine_dynamics.json --certificate proof.json
```

参考运行器的数学侧条件声明形如：

```json
{"formal":{"kind":"declarative","statement":{"schema":1,"kind":"affine_dynamics","model":{"matrix":[["1/2"]],"bias":["1/2"]},"threshold":"1","point":["1"]}}}
```

收据标注 `claim_relation: declared_side_condition_only` 和 `observed_status: NOT_APPLICABLE`；评估分别记录 `formal_status`、`formal_assurance`，其中 `manipulation: NOT_APPLICABLE`、`mechanism: NOT_TESTED`。这不会自动证明数学 JSON 模型等价于实际训练图；参考训练比较仍为标量。

### 原生 Lean：已实现的窄接口

已注册的 `lean_obligation` 适配器只接受 `schema`、`kind`、`relation`、`left`、`right` 这五个字段。`schema` 为 1，`relation` 为 `eq`、`lt` 或 `le`，左右两侧为精确有理数常量；拒绝 JSON 浮点数。[现有示例](https://github.com/kongtou20070406/RDS/blob/995e8eb98f75697ef1ce43a9991f0686e5c29caa/examples/formal/lean_obligation.json)为：

```json
{"schema":1,"kind":"lean_obligation","relation":"lt","left":"1/2","right":"3/4"}
```

将 `RDS_LEAN_EXECUTABLE` 设为已有原生工具链程序的绝对路径，替换下面的示例路径。适配器不会下载 Lean，拒绝 elan 和 `.elan/bin` shim。

```powershell
$env:RDS_LEAN_EXECUTABLE = 'C:\path\to\native-toolchain\bin\lean.exe'
python -B scripts/rds_cli.py --root . formal verify --spec examples/formal/lean_obligation.json --output lean-proof.json --tactics lean4
python -B scripts/rds_cli.py --root . formal check --spec examples/formal/lean_obligation.json --certificate lean-proof.json
```

适配器使用 Lean 的 Rat 定义和 `by decide` 渲染固定的 `RDS.obligation` 定理，以 `--trust=0` 调用原生程序，并要求完全匹配的空公理审计结果。独立检查重新渲染期望源码，再次调用 Lean，核对声明／源码绑定、程序指纹和版本。这是对生成模板再次进行原生检查，不是重放已保存的 `.olean` 证明对象，也不信任缓存 stdout。

经过检查的原子结果报告 `LEAN_KERNEL_CHECKED`、`backend: lean4_closed_rational` 和 `semantics: closed_Lean_Rat_relation`。该适配器当前只产生 PASS 或 UNKNOWN：假命题、工具不可用、编译失败和资源限制均为 UNKNOWN，不是已检查的反驳。含原生义务的定理模块外层仍为 `CERTIFICATE_CHECKED`，不表示所有叶子都由 Lean 检查。任意 Lean 文本、用户 tactics、通用 mathlib 翻译，以及实际训练图的证明仍不支持。

有界 tactic 名称为 `rule`、`gershgorin`、`spectral_radius`、`scale_invariance`、`lean4`、`interval`。`rule` 选择已注册后端，`lean4` 仅适用于 `lean_obligation`；其他名称选择各自兼容的 kind。空链或重复链被拒绝，不兼容 tactic 为 UNKNOWN；显式 `--tactics` 绕过默认磁盘缓存。

### 历史 prototype：独立的实验性路径

另一份本地 `scripts/rds_probe.py` 中的历史实验性实现曾加入 `FormalRuleRegistry` 与一个同名 `LeanFormalEngine` 类，加载 23 个方法论节点和五个数学检查，接收规则 ID 或 tactic 列表并输出轨迹。它不是当前的 `rds_verify.py` 分派器，其标识不能继承该框架的复核保证。以下审计只针对这条历史路径。

在该 prototype 中，`kind: causal_rule` 加 `rule_id` 只检查注册规则的 `discriminator`、`primary_gate`、`falsifier` 是否非空，并不检查提案或图中新补充的义务。因此，`RULE_ALIGNED` 只表示注册元数据结构符合要求；还须满足的证据见 [23 节点义务映射](rule-obligations.zh-CN.md)。

该 prototype 的 tactic 路径没有将每步结论绑定到声明定理；空 tactics、`intro`、未核对的 `exact`、`sorry` 和部分算术输入，可能在没有证明目标时产生 `PASS`，聚合后甚至标为 `LEAN_TACTIC_PROVED`。原始 Lean 文件成功退出，也可能在没有核对目标定理或公理时得到 `LEAN4_CERTIFIED`。这些是已经观察到的 prototype 限制，不能当作有效证明依据或升级科学结论。

声明中的残差引理也需要修正：当 alpha 非负时，`Lip(F)<=K` 和 `alpha*K<1` 可约束缩放映射 `alpha*F`，不能证明 `I+alpha*F` 收缩。例如 `F(x)=x`、`K=1`、`alpha=1/2` 时，残差映射的 Lipschitz 常数是 `3/2`。谱半径检查同样不能代替谱范数检查。后续检查器必须绑定准确算子与范数，拒绝不支持的目标。

### 验证流程

现已包含在 `main` 的注册接口遵循下述结构；扩展数学覆盖仍是后续开发里程碑。

```mermaid
flowchart LR
    A[显式命题与模型语义] --> B[支持的规则或后端]
    B --> C[生成证书或候选见证]
    C --> D[独立证书检查器]
    D --> E[status、assurance 与证据]
    E --> F[运行器准入与执行约束]
    F --> G[实际执行观测与科学评估]
```

证明搜索可能昂贵，也可能不完备；检查器应依据绑定输入验证准确的声明义务。复用证书时，代码或模型、完整声明、数值语义和验证器版本必须匹配，并重放检查器。数学证据复用不能跳过当前预算和数据暴露检查。

这套架构由 Python 编排。多数领域证书使用精确 Python 检查，支持的原生 Rat 义务则按上述方式使用真正的 Lean 检查器。精确实数模型证书或闭合 Rat 证明，都不能证明浮点训练实现满足同一命题。

## 标量契约与显式命题类型

当前标量实现将声明放在 `hypothesis.formal`：

```json
{
  "formal": {
    "kind": "contraction_boundary",
    "statement": "threshold_necessity",
    "quantity": "scalar_property",
    "domain": ["0", "100"],
    "threshold": "1",
    "max_loss": "1"
  }
}
```

这只是一个假说的数学部分，不是完整假说或计划。其余必填字段以运行 checkout 的[可执行契约](../references/l3-state-machine.md)为准。精确标量声明使用有限整数、十进制字符串或有理数字符串。

| 字段或命题 | 当前标量适配器的含义 |
| --- | --- |
| `kind` | 路由标量性质；边界适配器包含 `strict_algebraic_threshold` 和 `contraction_boundary`，保留显式旧名称 `threshold_necessity`。名称本身不能证明一般收缩。 |
| `quantity: scalar_property` | 执行对象是可测标量性质，须说明它如何对应研究声明。 |
| `domain` / `threshold` | 闭区间上的义务与预声明边界；即使符号化简消去分母，原始分母仍须有定义。 |
| `statement: threshold_separation` | 两臂有定义，对照在整个定义域低于阈值，干预至少存在一个跨越见证；这是当前边界声明的默认命题。 |
| `statement: threshold_necessity` | 当执行跨越满足两臂损失上限时，允许单独解释为对有范围的必要性命题的反例。 |
| `max_loss` | 标量必要性证伪条件预声明的损失上限；数学见证本身不是实际执行的低损失反例。 |

历史基础版本 `f020b2c` 尚未实施显式命题类型的区分，在旧版本中加入 `statement` 字段不会获得当前语义。使用当前 `main` 时，必要性意图须显式声明；引擎绑定改变后使用新契约。

精确检查器在有界算术下覆盖支持的仿射有理式；不支持的表达式可能回退到可选 SymPy。未声明数学性质的普通运行使用 AST 检查和精确有理执行；省略声明不能证明科研提案没有数学义务。

## 检查状态、验证依据与执行观测

| `status` | 含义 |
| --- | --- |
| `PASS` | 所选检查器在其文档范围内接受了声明义务。 |
| `FAIL` | 义务在该后端的失败语义下未成立；须说明依据是已检查反例，还是其他检查失败。 |
| `UNKNOWN` | 没有结论：不支持输入、缺依赖、达到资源上限或方法无法确定；既不是通过，也不是反驳。 |

显式形式准入要求 `PASS`，`FAIL` 和 `UNKNOWN` 都阻止准入。非法输入抛出的异常应作为错误报告，附版本与命令，不能改称科学反驳。

`assurance` 描述检查方式；这些标识不是置信度分数，也不能自动排序：

| 标识 | 含义与可用范围 |
| --- | --- |
| `AST_ONLY` | 受限语法检查，没有声明数学性质；`main` 可用。 |
| `SYMBOLIC_CHECKED` | 可选符号检查结果，没有独立证书；`main` 可用。 |
| `CERTIFICATE_CHECKED` | 独立检查已绑定的精确领域证书或有限模块；`main` 可用，模块可以组合 Python 与原生 Lean 叶子。 |
| `LEAN_KERNEL_CHECKED` | 已注册的原子闭合 Rat 模板再次通过原生 Lean 检查和空公理审计；在 `main` 配置原生工具链后可用，不是通用模型验证。 |
| `EXACT_OBSERVATION_CHECKED` | 精确检查实际执行的标量样本；`main` 可用，与准入证书分别记录。 |
| `EXACT_COUNTEREXAMPLE_CHECKED` | 直接调用网络适配器时，其精确前向见证反驳声明模型性质；通用框架将已检查的 FAIL 包装为 `CERTIFICATE_CHECKED`。 |
| `NONE` | 没有数学验证依据。 |

准入见证可能不在本次执行所选样本中。因此，当前实现分别记录 `admission_status` / `admission_assurance` 与 `observed_status` / `execution_assurance`。没有观察到跨越，不能推翻先前的存在性证书；执行者失败，也不能反驳数学或科学声明。

验证器输出与 `run_status`、`assessment.task_gain`、`assessment.mechanism` 分别记录。`PASS` 不证明任务性能提升、因果隔离、总体泛化或 L4 策略改进。

## 多维适配器范围

以下数学 kind 已在当前 `main` 中注册，来源实现为 PR #2 `995e8eb`。受限模型导出是 Python API，不是另一种 `formal` CLI kind。使用所选版本的契约和限制；不能将标量 `hypothesis.formal` 字段强加给每个后端。

| 适配器 | 声明模型与义务 | 解释边界 |
| --- | --- | --- |
| `network_bounds` / `network_margin` | 有理参数的 Dense Linear/ReLU 模型、有界输入箱、输出范围或目标输出间隔。 | 区间包络可给出充分界；包络过宽意味着不确定，只有经过精确检查的见证才建立反例。不认证准确率或任意 PyTorch 执行。 |
| `affine_contraction` | 有限维有理映射 `x ↦ A·x+b`，全局诱导无穷范数严格小于声明阈值。 | 这是无穷范数义务，不是谱范数或谱半径命题。 |
| `affine_fixed_point` | 声明点精确满足 `A·x+b=x`。 | 固定点检查本身不证明收缩或收敛。 |
| `affine_dynamics` | 同时检查仿射收缩与固定点义务。 | 范围是仿射离散映射，不是一般非线性 ODE 或训练过程。 |
| `matrix_spectral_bound` / `matrix_spectral_exact` | 用 Gershgorin 充分界或三角矩阵精确谱检查 `rho(A)<threshold`。 | 谱半径不同于谱范数和单步收缩；充分界过宽为 UNKNOWN。 |
| `scale_equivariance` | 声明正尺度 `F(s*x)=s*F(x)`，适用于零偏置 Linear/ReLU 模型；scale 为 1 时是恒等特例。 | 不说明损失尺度不变性、归一化或训练行为。 |
| `tensor_identity` / `tensor_bounds` | 具体精确张量表达式，检查值／形状一致或闭合界。 | 有界的 literal/add/scale/transpose/matmul 计算，不是通用符号张量定理，不支持一般 broadcasting。 |
| 受限模型导出 | 将支持的评估模式 `Sequential`、Linear/ReLU 叶子导出为精确有理参数。 | 二进制参数值形成模型快照，不产生前向执行或检查点安全声明；导出成功不保证验证器能接受其规模。 |

后端的大小限制、schema 和错误行为须以所选版本为准。上述声明不覆盖通用符号张量、任意层、浮点舍入、autograd、随机优化或泛化。本次发布回归因未配置工具链跳过两项原生 Lean 检查，因未安装 PyTorch 跳过两项 PyTorch 检查；该次运行未验证这些可选路径。

## 怎样提交有用的验证贡献

提供实现 ref、完整声明、准确命题与量词、模型或代码映射、数值语义、后端及版本、最小公开输入、命令和实际输出。按后端范围包含成立、不成立和不确定的案例；支持证书时，应独立调用检查器，并检查被修改的绑定和候选见证。

准入、实际执行和科学解释分别报告。证据与 PR 要求见[贡献指南](../CONTRIBUTING.zh-CN.md)。

## Lean 兼容与可选 C++ 适配

RDS 的主体是自动化辅助人类科研。当前 `main` 提供上述窄范围原生 Rat 接口；更广的 Lean4/mathlib 兼容应针对合适的数学子问题，复用真正的证明器与检查器，详见[当前接口与后续接入契约](lean-integration.zh-CN.md)。RDS 翻译支持的性质，将证明证据绑定到实验；Python 继续编排，C++ 可用于已经测量的适配瓶颈。这些接口不建立延迟保证。

接入 Lean 时，应独立固定期望定理和定义，核查包含 `sorryAx` 在内的公理依赖，并复核证明对象。编译一个无关文件成功不够。这些要求依据 Lean 的[官方证明验证指南](https://lean-lang.org/doc/reference/latest/ValidatingProofs/)；其[内核类型检查器源码](https://github.com/leanprover/lean4/blob/master/src/kernel/type_checker.cpp)也是具体的 C++ 参考。实现语言本身不能建立可靠性。

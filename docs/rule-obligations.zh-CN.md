# 判断规则的证明义务：全部 23 个节点

[English](rule-obligations.md) · [形式化验证](formal-verification.zh-CN.md) · [研究工作流](research-workflow.zh-CN.md) · [规则源文件](../references/judgment-graph.yaml)

本指南翻译规则源文件中的 `proof_obligations`。其中的表达式是可读的义务说明，不是通用证明器可直接执行的语法。每条规则仍受原有适用范围约束，声明的输入必须绑定原始产物；文档谓词不表示已有自动解析器或证明。

`by_rule` 的结构性检查不等于规则、计划或因果关系已被证实。实验性的 `LeanFormalEngine` 可用 `kind: causal_rule` 和 `rule_id` 定位节点；当前仅检查 `discriminator`、`primary_gate` 和 `falsifier` 元数据非空，不读取或强制新增的 `proof_obligations`。所有节点的 `runtime_enforced: false` 都表示这些义务尚未在运行时强制执行；`RULE_ALIGNED` 仅表示结构元数据对齐。

`tactic_candidates` 只列出可能用于局部算术义务的候选 tactic，不表示已接入或已完成整条规则的证明。精确模型内的数学检查、实际源码与执行观测、数据来源和实证比较各需对应证据；实证义务不能由数学检查、评分或自签成功字段替代。提出科学声明前，必须独立核查相关范围内的这些义务。以下每条证据要求还共同包含：保留原始来源标识、版本和实际输出，不以自签成功字段替代。

记号：`s` 对最大化指标取 +1，对最小化指标取 -1；`H` 为指定内容哈希。`empty`、`subseteq`、`intersect`、`does_not_imply`、`iff` 是数学谓词。确认性比较还需要声明的范围、有效独立数据，以及预先承诺的选择和评估规则。

## locked-test-selection

- **前置门禁：**确认前记录全部候选选择与数据暴露；绑定相同评估器、对照和预先声明的最低有用增益。
- **可行域表达式：**

```text
clean(T) and selection_data intersect T = empty; Delta_T = s*(M_T(treatment)-M_T(control))
```
- **变量定义：**`T` 为冻结的确认样本群；`selection_data` 为影响选择的所有样本及关联样本群；`clean` 为记录中未暴露的来源链；`M_T` 为预先声明的指标；`s` 为指标方向。
- **证伪条件：**冻结的独立比较不支持预先声明的有用增益，或确认数据来源链已经暴露。
- **证据要求：**预先规定在开发数据上选择 checkpoint，在未触碰的测试数据上确认一次；记录每个候选及选择决策，使用锁定测试指标与公平对照。
- **验证边界：**`protocol_and_empirical`（协议与实证）；注册 ID 为 `locked-test-selection`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## deployment-information

- **前置门禁：**声明部署时可见的输入及其来源链；审计所有实际推理路径，包括预处理。
- **可行域表达式：**

```text
inputs(deployed_model) subseteq I_deploy; inputs(deployed_model) intersect I_target_only = empty
```
- **变量定义：**`I_deploy` 为部署时可用的输入；`I_target_only` 为标签、从目标派生的值及逐样本 oracle 信息。
- **证伪条件：**部署路径需要仅目标侧可得的信息；此类 oracle 结果应报告为上界，不作为已实现性能。
- **证据要求：**追踪每个推理输入；分别报告仅使用部署输入的模型与 oracle；正式任务指标只使用部署可见输入。
- **验证边界：**`source_and_empirical`（源码与实证）；注册 ID 为 `deployment-information`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## preserve-quantifiers

- **前置门禁：**写清每个量词、策略类和可用信息；区分固定动作、oracle 与学得的条件策略。
- **可行域表达式：**

```text
not(forall f, P(a0,f)) does_not_imply not(exists g in G_deploy, forall f, P(g(f),f))
```
- **变量定义：**`a0` 为一个已测试的固定动作；`f` 为部署可见输入；`P` 为声明的成功谓词；`G_deploy` 为声明的、使用部署输入的可学习策略类。
- **证伪条件：**没有覆盖量化策略类的证据，却把已测试动作或策略的失败推广到所有条件策略。
- **证据要求：**在留出集上比较固定动作、逐样本 oracle 上界与使用部署可见 `f` 的策略；用正式留出任务指标评估学得的条件策略。
- **验证边界：**`logic_and_empirical`（逻辑与实证）；注册 ID 为 `preserve-quantifiers`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## computation-graph-identity

- **前置门禁：**绑定实际张量图与 checkpoint；指出分支信息必须保持可用的位置。
- **可行域表达式：**

```text
pool(z1)=pool(z2) implies h(pool(z1))=h(pool(z2)) for the same h
```
- **变量定义：**`z1,z2` 为不同分支配置；`pool` 为实际聚合；`h` 为固定下游计算；等号使用声明的数值语义。
- **证伪条件：**交换后的配置在所声称的分支敏感路线之前已聚合为同一结果；不能将收益归因于该路线。
- **证据要求：**完整重训前检查张量路径、固定权重的分支交换或消融；与同预算对照比较正式指标，并进行机制敏感诊断。
- **验证边界：**`source_and_execution`（源码与执行）；注册 ID 为 `computation-graph-identity`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## proxy-primary-bridge

- **前置门禁：**预先声明任务门禁与独立的机制敏感诊断；核对路线干预是否保留预期比较条件。
- **可行域表达式：**

```text
Delta_task = s*(M_T-M_C); Delta_route = s*(M_route_on-M_route_off); these are separate propositions
```
- **变量定义：**`M` 为预先声明的任务指标；`T,C` 为匹配的干预与对照；`route_on/off` 为匹配的机制干预；`s` 为指标方向。
- **证伪条件：**移除路线后任务收益仍存在，或诊断改变了无关因素；只保留证据支持的工程收益。
- **证据要求：**在同预算下消融或关闭声明的路线，并保留其他条件；预先声明的任务指标决定效用，机制诊断决定机制归因。
- **验证边界：**`intervention_and_empirical`（干预与实证）；注册 ID 为 `proxy-primary-bridge`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## short-budget-fidelity

- **前置门禁：**在每个预算下匹配样本工作量、训练日程和实现；测量有代表性的完整终点后，才能把早期排序视为预测依据。
- **可行域表达式：**

```text
sign(M_A(t_short)-M_B(t_short)) = sign(M_A(t_full)-M_B(t_full)) on measured representative pairs
```
- **变量定义：**`A,B` 为已测候选；`t_short,t_full` 为匹配的短跑与完整预算；`M` 使用同一终点指标及选择协议。
- **证伪条件：**排序逆转或无法验证代理排序；短跑仅作为可行性诊断，不能作为终点证明。
- **证据要求：**比较代表性候选的早期与较长匹配预算排序；计入步数乘批量、训练日程及实现变化；候选数量足够时才报告排序相关或首选保留情况；使用同配方的完整预算正式终点。
- **验证边界：**`empirical`（实证）；注册 ID 为 `short-budget-fidelity`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## method-recipe-variance

- **前置门禁：**先审计已有记录，优先使用同 seed 的匹配对照；只有已观察到的 seed 不稳定会影响当前决策、且额外比较在明确授权预算内，才追加 seed；预先规定不确定性的处理方法。
- **可行域表达式：**

```text
Delta_i = s*(M_T(seed_i)-M_C(seed_i)); extra_seed_runs require observed seed instability and decision impact within authorized budget
```
- **变量定义：**`seed_i` 为配对 seed；`T,C` 为匹配方法；`M` 为主指标；`s` 为指标方向；`uncertainty` 为声明的估计器及其假设。
- **证伪条件：**收益可由配方或实现解释，或未满足适用范围内的不确定性标准；收窄方法声明。
- **证据要求：**先查已有记录并做同 seed 公平比较；追加 seed 必须同时满足已观察的不稳定影响决策及授权预算约束；使用匹配配方与成本协议下预先声明的主指标，如实说明实际 seed 范围和已有不确定性证据。
- **验证边界：**`empirical`（实证）；注册 ID 为 `method-recipe-variance`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## realized-boundary-not-knob

- **前置门禁：**在精确实数／有理数语义下绑定执行的归一化方程、有限定义域与 `rho>=0`；匹配初始化和配方，测量实际有效质量，另行审计浮点差异。
- **可行域表达式：**

```text
S=sum_j abs(raw_j)>=0; rho>=0; m=rho*S/(1+S); rho=1 and finite S implies m<1; rho>1 implies (m>=1 iff S>=1/(rho-1))
```
- **变量定义：**`raw_j` 为实际行系数；`S` 为其有限绝对值之和；`rho` 为声明的有限缩放；`m` 为执行后的有效行质量。
- **证伪条件：**源码采用不同方程，或实际执行的质量未达到声明的边界；撤回严格边界推断。
- **证据要求：**使用能实际达到或跨过边界的归一化对照，记录越界，并尽量匹配起始算子和训练；只比较两个未越界的上限只能检验余量；匹配任务指标和预算，分开任务收益与更窄的机制结论。
- **验证边界：**`algebra_and_execution`（代数与执行）；注册 ID 为 `realized-boundary-not-knob`；局部 tactic 候选为 `linarith`、`interval_check`。需独立核查适用范围内的证据；`runtime_enforced: false`。

## depth-versus-trajectory

- **前置门禁：**使用同一个固定 checkpoint 和相同评估样本；各步之间不重训，记录逐步指标与计算成本。
- **可行域表达式：**

```text
theta_k=theta_star and X_k=X_star; M_k=M(F_theta_star^k(X_star),Y_star)
```
- **变量定义：**`theta_star` 为一个固定 checkpoint；`X_star,Y_star` 为相同评估样本；`k` 为所评估的递归步；`F` 为执行的递推。
- **证伪条件：**用分别训练的 checkpoint 代替同一 checkpoint 的轨迹；不能据此声称后续步骤退化。
- **证据要求：**在相同图像上评估同一固定 checkpoint 的中间步骤；记录逐步正式指标及计算成本。
- **验证边界：**`execution_and_empirical`（执行与实证）；注册 ID 为 `depth-versus-trajectory`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## reuse-baseline-control

- **前置门禁：**要求包含逐样本对照结果的成功引擎收据；随机或扩展适配器必须核对所有会影响结果的身份信息。
- **可行域表达式：**

```text
H(control_AST_new)=H(control_AST_receipt) and H(data_new)=H(data_receipt)
```
- **变量定义：**`H` 按适用情况对规范 AST 或精确数据字节计算 SHA-256；`receipt` 为原始成功对照评估；随机运行身份还包含适配器相关的 seed、checkpoint、配方和数值语义。
- **证伪条件：**任何会影响结果的绑定发生变化，或缺少收据证据；使复用失效，但不恢复已暴露数据的确认资格。
- **证据要求：**对照原收据核对计算身份与数据集 SHA-256；扩展适配器还需完整核对随机和数值身份；只有不能改变声明对照结果的主机变化才可忽略；缓存逐样本输出须绑定锁定基线及精确数据分区。
- **验证边界：**`provenance_and_execution`（来源与执行）；注册 ID 为 `reuse-baseline-control`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## trained-anchor-not-method-win

- **前置门禁：**记录已训练比较锚点的配方、终点和完整成本；声称优越性前取得适当的匹配基线。
- **可行域表达式：**

```text
feasible(anchor) does_not_imply Delta=s*(M_treatment-M_matched_control)>delta_min
```
- **变量定义：**`anchor` 为首个实测终点；`matched_control` 使用相同载体、数据、配方和选择规则；`delta_min` 为预先声明的有用增益；`s` 为方向。
- **证伪条件：**仅锚点完成，或匹配比较未支持优势；保留可行性结论，暂不声称比较优势。
- **证据要求：**记录锚点配方、资源使用和逐样本终点；在相同载体、数据、选择和评估规则下比较仅替换混合器的版本；按声明的质量与资源预算比较主任务指标。
- **验证边界：**`empirical`（实证）；注册 ID 为 `trained-anchor-not-method-win`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## resource-canary-before-campaign

- **前置门禁：**测量计划使用的批量、裁剪、精度、加载与评估配置；启动前声明并发方式、显存红线和开销余量。
- **可行域表达式：**

```text
memory_peak<=memory_limit and makespan(schedule,measured_step_times)+T_io+T_eval+T_contingency<=B_remaining
```
- **变量定义：**`schedule` 为可行并发与步数安排；`times/memory_peak` 为目标配置的实测时间与峰值显存；`B_remaining` 为授权剩余总墙钟时间。
- **证伪条件：**短时探测或实测开销使整组实验不可行；启动前修改计划或重新分配。
- **证据要求：**用目标配置进行有界短时探测，测量峰值显存与步耗时，核对数据加载和评估开销，再计算匹配实验总成本；可复现比较必须满足显式显存红线和总预算上限。
- **验证边界：**`measurement_and_budget`（测量与预算）；注册 ID 为 `resource-canary-before-campaign`；局部 tactic 候选为 `linarith`、`interval_check`。需独立核查适用范围内的证据；`runtime_enforced: false`。

## bundled-change-needs-component-control

- **前置门禁：**声明针对特定分量的干预及可行的保留容差；分别审计实际作用路径与路由能量路径。
- **可行域表达式：**

```text
changed_factors={target_component}; preserved_factors include carrier,routing_interface,initial_operator,recipe
```
- **变量定义：**`changed/preserved_factors` 为执行的干预清单；`target_component` 为正在检验的归因分量；`include` 表示需在声明容差内保持相同的因素。
- **证伪条件：**多个有效分量同时变化；只保留组合层面的证据，不能推断各分量必要性。
- **证据要求：**预先声明一个分量干预，尽量保留载体、路由接口、可训练容量、起始算子和训练配方；检查实际作用与路由能量路径；按匹配预算比较固定终点主指标，并单独记录剩余不匹配因素。
- **验证边界：**`intervention_and_empirical`（干预与实证）；注册 ID 为 `bundled-change-needs-component-control`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## ablation-is-intervention-specific

- **前置门禁：**绑定实际执行的精确消融，不依赖非正式名称；记录全部保留和替换的计算路径。
- **可行域表达式：**

```text
manifest_executed=manifest_declared; conclusion_scope subseteq tested_intervention_scope
```
- **变量定义：**`manifest` 为实际槽位、增益、作用和路由变化；`tested_intervention_scope` 为精确替换方式、任务及配方。
- **证伪条件：**执行组与声明不同，或把一次替换失败推广到所有消融；修订解释。
- **证据要求：**核对执行组的干预清单、保留槽位、增益、作用路径和路由输入；结论限定于该组；匹配终点和资源比较，复用开发图像只支持局部模型选择，不提供泛化确认。
- **验证边界：**`source_and_empirical`（源码与实证）；注册 ID 为 `ablation-is-intervention-specific`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## transfer-requires-matched-protocol

- **前置门禁：**执行明确的任务转向并核算目标任务比较成本；使用相关强对照，匹配载体、终点和评估；追加 seed 必须基于已观察的不稳定及其决策影响。
- **可行域表达式：**

```text
Delta_target=s*(M_target(treatment)-M_target(matched_control)); cost_T and cost_C follow the same declared budget
```
- **变量定义：**`target` 为请求的目标任务或样本群；`M_target` 为其终点指标；`s` 为方向；`cost` 为匹配的训练、调参与评估资源协议。
- **证伪条件：**在匹配目标协议下收益消失；只撤回该范围内的迁移声明。
- **证据要求：**先查已有记录并优先同 seed 公平对照；按已核算成本进行目标任务比较，固定载体、终点和评估，包含相关强对照；只有已观察的不稳定可能改变当前决策、且新增比较符合授权预算，才追加 seed；记录每个完成组和产物身份，如实报告主指标及配对不确定性证据。
- **验证边界：**`empirical`（实证）；注册 ID 为 `transfer-requires-matched-protocol`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## protocol-versioned-evidence

- **前置门禁：**将每行报告绑定完整协议及产物身份；核对预期比较与历史版本差异。
- **可行域表达式：**

```text
signature=(H(data),H(model),H(checkpoint),seed,budget,selection,evaluator); compare only matched signatures except the declared intervention
```
- **变量定义：**`H` 为内容摘要；`signature` 为包括影响结果设置的完整任务与评估身份；`intervention` 为明确允许的比较差异。
- **证伪条件：**各行无法形成有效的匹配比较；暂不作比较结论，不能只选择更高分数。
- **证据要求：**每行绑定数据集哈希、模型和 checkpoint 身份、seed、训练预算、终点选择和评估设置；比较同类版本或明确重跑匹配比较；主指标表的协议身份可审计，比较组由同一规则评估。
- **验证边界：**`provenance`（来源）；注册 ID 为 `protocol-versioned-evidence`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## normalization-removal-confound

- **前置门禁：**检验特定边界声明时保留归一化路线；匹配起始算子和配方，测量幅度与优化变化。
- **可行域表达式：**

```text
normalized_i=rho*raw_i/(1+sum_j abs(raw_j)); removed_i=raw_i; varying the equation changes more than a cap
```
- **变量定义：**`raw_i` 为执行的系数；`rho` 为缩放；`normalized/removed` 为精确比较的算子；初始化和梯度为额外需测量的混杂因素。
- **证伪条件：**幅度、初始化或优化变化仍与边界混杂；仅保留更窄的结论。
- **证据要求：**改变所声称的边界时保留归一化，并匹配起始算子和训练配方；测量实际幅度与优化差异；匹配任务质量并核实边界干预，分开任务效用与严格边界归因。
- **验证边界：**`algebra_and_empirical`（代数与实证）；注册 ID 为 `normalization-removal-confound`；局部 tactic 候选为 `interval_check`。需独立核查适用范围内的证据；`runtime_enforced: false`。

## executed-manipulation-validity

- **前置门禁：**昂贵执行前从已绑定源码推导可达性质；分开数学存在性、实际观测到的干预和任务结果。
- **可行域表达式：**

```text
exists x in D: P_treatment(x)!=P_control(x); boundary variant requires exists x_observed in D: P_treatment(x_observed)>=tau
```
- **变量定义：**`D` 为已承诺的可行定义域；`P` 为实际建模性质；`tau` 为声明的阈值；`observed` 为执行样本；不等式使用声明的干预方向。
- **证伪条件：**没有实际干预则机制未被检验；有效且范围明确的反例只反驳声明的必要性命题。
- **证据要求：**训练前推导执行方程的可达范围，再记录已承诺数据上的实际越界或路线活动；分别检查可行性、实际干预和任务结果；机制归因前必须实际改变声明性质，任务质量仍用预先声明的匹配指标和预算。
- **验证边界：**`algebra_and_execution`（代数与执行）；注册 ID 为 `executed-manipulation-validity`；局部 tactic 候选为 `interval_check`、`linarith`。需独立核查适用范围内的证据；`runtime_enforced: false`。

## learned-support-not-allowed-support

- **前置门禁：**检查拟合后的有效性质，不能只看允许的参数范围；使用匹配的固定与学得对照，源码变化后重复检查。
- **可行域表达式：**

```text
allowed_support=Theta; realized_support={theta_hat(x):x in D_observed}; boundary claim needs max_x P(theta_hat(x))>=tau
```
- **变量定义：**`Theta` 为声明的参数域；`theta_hat` 为拟合参数；`P` 为实际有效算子的性质；`D_observed` 为已承诺的观测；`tau` 为边界。
- **证伪条件：**拟合后的有效算子仍处在原有一侧；撤回越界归因，但保留范围明确的适应性证据。
- **证据要求：**在声明数据上检查实际有效算子与拟合参数范围；比较匹配的固定和学得对照，同时报告边界活动与质量；用同一配方及选择规则区分主指标效用和边界声明。
- **验证边界：**`execution_and_empirical`（执行与实证）；注册 ID 为 `learned-support-not-allowed-support`；局部 tactic 候选为 `interval_check`。需独立核查适用范围内的证据；`runtime_enforced: false`。

## hard-budget-reallocation

- **前置门禁：**核算已花费与排队工作、并发、评估和预备开销；新准入前释放被替代的预留，并保护确认预算。
- **可行域表达式：**

```text
B_spent+B_reserved+B_new+B_overhead<=B_total; B_exploration<=B_total-B_confirmation_floor
```
- **变量定义：**`B` 为使用统一声明单位的非负分配；`reserved` 为显式释放被替代且未启动计划后的预留；`overhead` 为整组实验的保守开销估计。
- **证伪条件：**匹配比较超过实测剩余预算；启动前缩减计划或取得新的预算决定。
- **证据要求：**根据逐组步耗时、步数和可行并发推导墙钟时间，计入数据、评估与预备开销；核算匹配比较并在准入前释放被替代分配；预期能改变决策的证据仍须处于授权上限及受保护确认预算内。
- **验证边界：**`budget_and_empirical`（预算与实证）；注册 ID 为 `hard-budget-reallocation`；局部 tactic 候选为 `linarith`、`interval_check`。需独立核查适用范围内的证据；`runtime_enforced: false`。

## adaptive-test-reuse

- **前置门禁：**记录每次暴露及其影响的决策；真正独立确认前冻结候选和评估器。
- **可行域表达式：**

```text
used_for_choice(T) implies exploratory(T); independent_confirmation(T_new) requires unexposed_lineage(T_new) and frozen_selection
```
- **变量定义：**`T` 为已暴露分区；`T_new` 为新的确认样本群；`lineage` 包括字节、样本和样本群重叠，以及系统外暴露声明。
- **证伪条件：**把先前暴露或来源重叠的数据称为独立；撤回独立标签，而非实测探索得分。
- **证据要求：**记录暴露及其影响的全部决策；冻结候选和评估规则后，在真正未暴露的样本群上测试一次，否则明确限定为探索性能；确认收益需独立确认，已暴露测试仍是声明协议下有效的探索终点。
- **验证边界：**`provenance_and_empirical`（来源与实证）；注册 ID 为 `adaptive-test-reuse`；无算术 tactic 候选。需独立核查适用范围内的证据；`runtime_enforced: false`。

## implementation-equivalence-before-speedup

- **前置门禁：**声明数值语义、输入、前向与梯度路径及容差；在同一有版本记录的匹配协议下测量质量和资源使用。
- **可行域表达式：**

```text
max_x norm(f_new(x)-f_old(x))<=eps_f and max_x norm(grad_new(x)-grad_old(x))<=eps_g on X_declared
```
- **变量定义：**`X_declared` 为审计过的输入集或定义域；`norm` 为预先声明的范数；`eps_f,eps_g` 为声明的数值容差；`grad` 为相关导数；`model` 为已绑定实现。
- **证伪条件：**输出或梯度差异超过容差，或遗漏了改变的路径；将加速代码作为不同实现处理。
- **证据要求：**在代表性输入和声明容差下比较前向输出及相关梯度，保留版本哈希，匹配组使用同一核实过的实现协议；先检查声明输入和容差范围内的等价性，再按记录协议比较主任务质量与实际资源使用。
- **验证边界：**`numerical_and_execution`（数值与执行）；注册 ID 为 `implementation-equivalence-before-speedup`；局部 tactic 候选为 `interval_check`。需独立核查适用范围内的证据；`runtime_enforced: false`。

## source-aware-evaluator-check

- **前置门禁：**将研究声明、执行方程和干预清单绑定到源码审计；决策时审计不读取封存的后续结果，并保留原始评分。
- **可行域表达式：**

```text
feasible_claim = exists x in D: declared_distinction(executed_source,x); judge_score does_not_imply feasible_claim
```
- **变量定义：**`D` 为实际源码推导的定义域；`declared_distinction` 为声称的干预差异；`judge_score` 为协议量表得分，不是证明证据。
- **证伪条件：**源码使声明的差异不可达；修订方案，但不能由已知案例的修复声称评审器普遍可靠。
- **证据要求：**向独立审计者提供声明、执行方程和干预清单；不看封存后续结果而推导可达性质，保留原评分及修正；评分用于支持机制推断或昂贵启动前，先取得可复现、基于源码的判别有效性证据。
- **验证边界：**`source_and_empirical`（源码与实证）；注册 ID 为 `source-aware-evaluator-check`；局部 tactic 候选为 `linarith`、`interval_check`。需独立核查适用范围内的证据；`runtime_enforced: false`。

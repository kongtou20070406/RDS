# Advisor：由事实、规则和有限干预生成建议

核验日期：2026-09-30。本文是有界设计补充，沿用 [Advisor 证据报告](advisor-evidence.md) 的文献边界与低成本要求。本次补查四个 primary 来源，没有运行科研实验、训练预测模型或测量 Advisor 的省算力幅度。下文“建议实现”是工程方案，不能当作当前代码已经具备的能力。

推荐把判断图用作可审查的证据与约束图，再由程序生成有限候选和比较依据：`有类型的事实 → 三值前提 → 干预模板 → 替代解释与判别条件 → 成本约束下的偏序建议`。这样，LLM 可以帮助理解问题、提出待审查解释和写清建议；候选是否可用、证据是否齐全、能比较什么、为什么没有淘汰某项，则由显式数据和程序决定。

## 最小 prior-art 与迁移边界

以下只核验与当前设计最接近的原文及其限制；不是穷尽综述。“最新”指本次检索中找到并核验的 2026 进展。

| 来源与原文定位 | 能够支持的主张 | 对 RDS 的采用与限制 |
|---|---|---|
| Sina Akbari、Jalal Etesami、Negar Kiyavash，*Minimum Cost Intervention Design for Causal Effect Identification*，ICML 2022，PMLR 162:258–289，[正式页面](https://proceedings.mlr.press/v162/akbari22a.html)、[论文](https://proceedings.mlr.press/v162/akbari22a/akbari22a.pdf)，问题定义与复杂度/算法部分 | 给定因果图，寻找足以识别指定效应的低成本干预；一般问题困难，与加权 hitting set 有联系。 | 借鉴“先规定目标，再规定可用干预与成本”。本地小候选集可枚举；判断图的文字规则和路径没有自动获得论文所需的因果图身份。 |
| Panagiotis Tigas、Yashas Annadani、Andrew Jesson、Bernhard Schölkopf、Yarin Gal、Stefan Bauer，*Interventions, Where and How? Experimental Design for Causal Models at Scale*，NeurIPS 2022，[arXiv v3，2022-10-21](https://arxiv.org/html/2203.02016v3)，§1 Assumptions、§3.1、Algorithm 3 | CBED 以 SCM/DAG 后验及干预结果模型估计互信息；原文明确假设无隐藏混杂、可观测变量、加性 Gaussian 噪声、单目标干预等。 | 真实 EIG 需要后验与结果似然。当前 RDS 的规则图、遥测摘要和论文引用不满足这些条件；不能用节点度、随机游走或 LLM confidence 替代该估计。 |
| Sepehr Elahi、Sina Akbari、Jalal Etesami、Negar Kiyavash、Patrick Thiran，*Fast Proxy Experiment Design for Causal Effect Identification*，NeurIPS 2024，[正式页面](https://proceedings.neurips.cc/paper_files/paper/2024/hash/5bd9fbb3a5a985f80c16ddd0ec1dfc43-Abstract.html)、[arXiv v1](https://arxiv.org/html/2407.05330v1)，问题设置与方法部分 | 已知因果图下的最低成本 proxy 干预设计，可化为 weighted MaxSAT/ILP，并提出较快 heuristic。 | 支持把合法性和可识别性写成约束后再优化成本。小规模 Advisor 不必引入求解器；有限枚举足够时用标准库。原文没有验证训练故障模板或本地科研收益。 |
| Erdun Gao、Liang Zhang、Jake Fawkes、Aoqi Zuo、Wenqin Liu、Haoxuan Li、Mingming Gong、Dino Sejdinovic，*Observationally Informed Adaptive Causal Experimental Design*，[arXiv v1，2026-03-04](https://arxiv.org/html/2603.03785v1)，§2.2 Assumption 1、§3–4、Appendix E/F；预印本 | R-Design 用 observational 模型与实验残差，针对目标效应/策略而非无关参数不确定性获取数据。要求受控分配、positivity、跨来源效应不变及目标支持覆盖等。 | 采用“测量会改变当前决策的未知量”的设计原则。原文 Appendix E 中不确定性较不可靠的 tree 模型，主动获取增益有限或缺失；Appendix F 的弱先验也会妨碍冻结先验方法。不能把其模型概率、样本效率或 CATE 结果迁移成 RDS 保证。 |

四个来源共同提醒：约束可计算、目标明确，不等于因果已可识别。2026 原文中的负面结果还说明，主动设计的效果依赖模型和不确定性质量。本次工程方案因此先使用透明的条件与集合比较；概率模型是以后有任务证据时才可增加的能力。

## 数据契约：事实与图各自负责什么

现有 `rds_meta.py` 的规则含 `id/scope/trigger/correction/alternatives/discriminator/primary_gate/falsifier/sources`，其中 trigger 等是自然语言字符串。它们适合保存和审查经验。若要让程序可靠运行规则，需要少量经审查的机器绑定；不能直接执行这些字符串，也不能把 LLM 解析结果无审查升级成 predicate。

建议沿用当前规则 ID、来源和 state，不另建知识平台。只为可执行规则登记一个白名单条件与有限模板。没有机器绑定的规则仍可提供带引用的提示，输出应标记其机器判定状态为 `UNBOUND`。

事实至少保存下列信息：

| 字段 | 用途 |
|---|---|
| `name/value/type/unit` | 区分 loss 值、比例、步数、时间、Boolean；缺失值不补成零。 |
| `split/reduction/mode/window` | 指明 train/validation、mean/sum、train/eval 与采样区间；不可比量不得形成同一个差值。 |
| `run_id/seed/config_fingerprint/budget` | 将观察绑定到实际训练路径与预算；“配置写了 warmup”和“实际 LR 轨迹有 warmup”是不同事实。 |
| `origin/locator/review_state` | 指向日志、代码位置、收据或原文；保存未审查摘录身份。 |
| `status/derivation` | `OBSERVED`、`DECLARED`、`DERIVED`、`UNKNOWN`；推导须有输入 ID 和计算方法。状态名本身不证明来源可信。 |

图边可明确标为 `requires`、`supports`、`contradicts`、`derived_from`、`depends_on`。这些是证据或规则关系。`supports` 表示某条有范围的主张获得支持，不能沿路径传递为“原因已确认”。真正因果边若在特定任务中建立，还须另外保存变量、干预定义、识别假设和验证范围；不要默认整个经验图是 causal DAG。

## 程序可落地的五步

### 1. 对齐事实并计算三值前提

用白名单谓词处理类型与来源，例如 `has_observed_update`、`same_metric_protocol`、`budget_comparable`、`intervention_realized`。每个谓词输出 `PASS/FAIL/UNKNOWN` 和所用 fact IDs。只对有明确任务定义的比较使用阈值，不加入通用 loss 或梯度阈值。

条件合取中，已知矛盾给 `FAIL`，全部明确通过才给 `PASS`，其余给 `UNKNOWN`。条件失败的模板退出本次候选，保留失败理由；未知条件转为“读取/测量缺失事实”的候选，或保持待定。未知不会自动支持默认诊断，失败也不会反向确诊另一机制。

### 2. 从审查过的有限模板枚举干预

一个模板包含：规则 ID/版本、适用范围、机器前提、允许改变的一个因素及有限取值、所需 control、已有证据复用条件、测量项目、替代解释、可能结果模式、反驳条件、成本区间和来源。结果模式是显式模型假设，不能写成论文担保的必然结果。

用 `dict/list/set` 与 `itertools.product` 枚举已经登记的有限取值。先保留单因素、兼容控制组的候选，按 intervention fingerprint 去重；需要多个改变的方案应说明为何不可分离以及其归因限制。枚举上限属于资源契约，达到上限时报告截断，不能假装搜索完整。LLM 新提案可以进入待审查模板队列，不绕过这些前提直接进入排名。

### 3. 明确测试能够区分哪些替代解释

有界图搜索现已提供可选的 `action.discrimination` 声明和条件判别对输出，详见[输入契约与软件示例](advisor-discrimination.md)。这一步依据调用者提供的预测集合计算；预测核验、真实测量协议及科研收益仍需要任务证据。

设当前候选解释为有限集合 `H`。每个候选测试 `a` 为每个解释保存允许的观察集合 `O(h,a)`，以及这些预测的依据和适用条件。只有两种预测在声明条件下不重叠、且所需测量可实现，才登记该条件下的可判别对 `(h_i,h_j)`。预测未知或重叠时保留模糊性。

建议分别输出 `conditional_distinguishing_pairs` 和 `unresolved_pairs`；前者仍然依赖预测模型成立，不是已获得信息。单纯知道论文“有时有效”不能登记为硬排除某解释的观察条件。测试完成后，执行验收内核先确认改动确实发生，再核对观察；未实现干预记为未测试，结果落在多个预测范围内则保留多个解释。

不在不同规则列出的任意解释之间比较“覆盖数量”：解释范围和粒度必须相同，否则把一个解释拆成十个会人为抬高分数。未知解释没有穷尽保证，输出范围须保留 `other/unmodeled`。

### 4. 计算增量成本与兼容复用

先检查已有日志、控制结果和 checkpoint。复用 fingerprint 至少核对代码/数据/划分、metric 定义、初始状态、seed、sample-work、schedule 与 checkpoint 恢复方式；某项不能确认即记录不兼容或未知。对改变架构、随机数调用顺序或 batch 的实验，相同 seed 标签不保证相同随机路径。

成本记录 CPU/人工/GPU 等所需资源和可比较的区间，包含测量、恢复和重新建立 control 的增量成本；没有估计时标未知，不设为零。先建议读取已有记录，只有它不能回答会改变当前决策的未知量时才提出新探针。用户当前偏好是同 seed 配对与兼容控制复用，不默认增加多 seed；已有 seed 不稳定证据且确会改变决策时再讨论其投入。

### 5. 先过滤约束，再给偏序而非伪精确分数

把 `primary_gate`、预算上限、允许改动、证据要求和执行风险作为显式约束。对同一目标、同一解释集合与同样有效前提的候选，保留 Pareto frontier：只有 A 的条件判别集合包含 B、所有比较的成本/风险维度不更差、且至少一维严格更好，才将 B 记为被 A 支配。若成本是区间，只有 `upper_cost(A) <= lower_cost(B)` 才能据此确认成本不更差；区间重叠或未知保留不可比。

“潜在覆盖”不用于压倒有验证条件的覆盖；两个不同的测量目标也不能仅凭一个集合大小相互淘汰。没有任务验证的 utility、confidence 或权重时，不把它们加成一个总分。frontier 内可依用户已声明的投入偏好选择；无法决定时输出差别与缺失事实。展示顺序可按稳定 ID 保持复现，它不代表科学优先级。

标准库实现的边界流程可表达为：

```text
facts = normalize_and_validate_sources(state, receipts)
for rule in reviewed_rules:
    binding = lookup_predicates_and_templates(rule.id, rule.version)
    if binding is absent: record_unbound_rule(rule); continue
    preconditions = evaluate_three_valued(binding.predicates, facts)
    if any FAIL: record_rejection(rule, preconditions); continue
    if any UNKNOWN: emit_needed_observations(rule, preconditions); continue
    for candidate in enumerate_finite_templates(binding, facts):
        attach_control_reuse_check(candidate)
        attach_conditional_predictions_and_unresolved_alternatives(candidate)
        attach_incremental_cost_interval(candidate)
        candidates.add_by_fingerprint(candidate)
feasible = enforce_declared_scope_budget_and_primary_gate(candidates)
return pareto_frontier_with_reasons(feasible), rejected, missing, unbound
```

该流程生成的是候选建议与可审查理由。它没有自动发起训练的语义。图读取、白名单谓词、集合包含、指纹与区间比较均可由标准库实现；无须新增图数据库、向量服务或通用规划器。

## EIG、VOI 和不确定性的明确边界

判别对集合是当前声明模型下的结构性比较，不是 entropy、预计信息增益或成功概率。只有解释后验 `P(h|D)` 和测试结果模型 `P(o|h,a,D)` 均有适用范围与校准证据，才有条件计算 Bayesian EIG。CBED 的估计过程实际用到后验采样和似然；引用该论文不会给 RDS 补齐这些输入。

VOI 还需要可用的决策 utility、候选行动与成本，而非仅判断哪项实验最有信息。工程定义可写为：

`VOI(a) = E_o[max_d E[U(d,h) | D,o,a]] - max_d E[U(d,h) | D] - cost(a)`。

这里的成本须与 utility 使用可比较的单位，或保留多维成本决策；不能随意换算。“信息很多”也可能不会改变下一行动。没有这些概率与 utility 的当前场景，只输出条件判别覆盖、预算可行性与未解决项，不输出伪精确 VOI。可以采用的低成本决策规则是：如果在所有当前允许观察下，下一可执行行动都相同，且测量没有独立科研目标，则暂不为该决策追加实验。它仍依赖当前候选模型，不是对未知世界的保证。

## 一个训练停滞示例

输入只有“loss 平台期”时，优化步未实际更新、LR/schedule 不合适、表达能力不足及数据/目标问题都可以保留；不能从一个现象确诊一个原因。有限模板可先列为：读取现有 update/梯度/实际 LR 记录；固定数据与初始状态的小范围 LR 配对探针；机制敏感的容量/路径检查。每项须说明会改变的因素与它仍区分不了什么。

若现有代码与更新记录共同表明宣称训练的参数不在实际 optimizer 更新路径中，先修正路径并验收；LR/容量改动对“更新路径是否缺失”没有必要判别价值。若记录表明更新存在，只能排除这项机械故障，不能因此确认 LR 或容量解释。LR 小探针表现改善也仍可能受 batch 顺序、恢复方式、schedule 或统计噪声影响，保留相关替代解释。

这个例子的先后次序来自可用事实和当前决策目标，不是写死“所有停滞先调 LR”。同 seed 配对控制可提高局部比较的可比性；一条路径上的 gain 不证明跨 seed、实现、数据或任务的普遍效应。执行成功、hash 一致、满足 metric gate，与机制因果得到支持是不同验收事项。

## 在五个组件中的位置

| 组件 | 责任与可交付证据 |
|---|---|
| Skill | 定义用户目标、允许改动、预算与阶段流程；指明何时用 Advisor。 |
| 执行验收内核 | 绑定 plan、代码/配置与实测结果；检查干预实现、control 兼容、任务指标与声明范围。 |
| 状态记忆 | 保存原始观察、来源、失败、未决项与版本；提供 Obelisk 历史记录检索和复用入口。 |
| Advisor | 计算规则前提，枚举候选，比较条件判别力与增量成本；输出建议、被拒理由与缺证据。 |
| RSI | 提出和审查规则/模板修改，记录旧版本与反例；候选反思不得仅凭一次成功自动变成普适规则。 |

各组件仍围绕人类科研目标运作。Lean 等形式化工具只在适用数学子任务中提供特定检查；该工具或一般执行收据自身不会完成科研效果验收。

## 首轮验收与剩余风险

可先用现有离线记录和小 fixture 检查：缺字段走 `UNKNOWN`；自然语言未绑定规则不会被执行；不可比 loss/预算不形成诊断；来源与 predicate 版本可追溯；模板枚举有限且重复不增加排名；预测重叠保留解释；复用不兼容有明确理由；成本未知不按零处理；无严格支配时保留 frontier；相同输入产生相同结构化候选与理由。此类检查验证计算行为，没有验证建议的科研成功率。

真实质量还取决于模板是否遗漏关键解释、观察预测是否可迁移、成本估计是否可信。既有历史案例如果用于形成规则，就不能再次当作独立效果评估集。以后仅在有合适记录且会影响采纳时，做保留案例上的回放或同 seed 对照；记录误排除、错误支配与新增成本。数据不足时保留未决结论，不用流畅叙述、规则命中次数或图结构替代因果证据。

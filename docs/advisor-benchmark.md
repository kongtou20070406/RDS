# Advisor 公开任务改编组件挑战

2026-09-30 在本地真实调用 Advisor 与图搜索：**8/8 个改编案例、28/28 条预先声明的合同检查通过**。处理这些案例并组装结果耗时 83.0743 ms；没有 GPU、付费 API、模型训练或多 seed。该数字是小型组件挑战的通过数，**不是 ScienceAgentBench、CORE-Bench 的原始 benchmark 分数，也不是科研质量或省算力效果的测量**。

完整输入与定位见 [source-facts.json](../benchmark/advisor-public/source-facts.json)，可重跑脚本见 [run.py](../benchmark/advisor-public/run.py)，逐项条件、理由和原始 API 输出见 [results.json](../benchmark/advisor-public/results.json)。本报告不修改现有历史 benchmark manifest，也不把历史案例加入分母。

## 选型与最新版本

优先查验 primary benchmark 项目及任务元数据，而非转述 leaderboard。ScienceAgentBench 在 2026-04-30 发布 verified 版本以减少评价 false negatives，本次使用公开 `verified` viewer 的 instance 2。完整任务执行与评价需要科学数据和环境，部分输出使用 API visual judge；这次没有下载完整科学数据或运行其官方 harness。[ScienceAgentBench 官方项目](https://github.com/OSU-NLP-Group/ScienceAgentBench)、[verified 数据卡与任务](https://huggingface.co/datasets/osunlp/ScienceAgentBench)

CORE-Bench 用科学代码复现任务及输出问题评估代理，当前官方 README 推荐 HAL harness；完整执行会下载 capsule 并使用隔离环境。本次仅人工核对公开 train 元数据中两项 task 的工作流与一个 reference scalar，未执行 capsule，也未回答原题以获取官方分数。[CORE-Bench 官方项目](https://github.com/siegelz/core-bench)、[公开任务元数据](https://github.com/siegelz/core-bench/blob/main/benchmark/dataset/core_train.json)

同时查验了 2026-06 的 SciAgentArena primary 发布页。它加入科研任务有效性、工作流、工具与版本约束等检查，契合 Advisor 的约束意识；本轮选择无需额外环境的 SAB/CORE 元数据切片，而未迁入其完整科研执行任务。[SciAgentArena](https://sciagentarena.github.io/)、[论文](https://arxiv.org/abs/2606.12736)

## 来源与改编的分界

| 原任务 | 从 primary 人工核对的事实 | 本次测试所用改编 |
|---|---|---|
| SAB verified instance 2 | 基于 composition 生成材料 diffusion features，以 SHAP 选 20 项并写 CSV；公开记录给出输入、源 notebook 与输出文件。 | 两个有限检查模板分别对应 20 与 10 项合同；原合同、改成 10、删来源、成本未知形成四组对照。它们不会生成真实 SHAP features。 |
| CORE `capsule-7038571` | 指定 `main.py`、`config/uci.json` 与 CTGCN-C，工作流为 preprocessing、embedding、link-pred。 | 将两项前置完成条件接到一个有界元数据检查；完成标记是明确标注的 synthetic state，检验缺证据、零预算和不同 capsule ID。 |
| CORE `capsule-5286757` | 公开 reference 记录含 epoch 9 的单项 train loss，选用值 `0.04598272387846722`。 | 将这个已归属的参考标量传给动态 Advisor；不提供 validation 轨迹或训练 protocol，检查其是否保持缺证据。该数值不是本地 RDS 训练结果。 |

这些事实在 snapshot 中保留原题 ID、URL、字段定位与改编说明；真实任务事实、published reference、synthetic completion flags 和人为约束扰动分别标注。SAB selected viewer row 于 2026-09-30 核对；其数据卡 commit 仅用于定位 verified 发布说明，没有声称将 row 数据按那个 commit 下载。CORE 来源是当日读取的 mutable `main`；本地 snapshot SHA256 锁定的是人工提取物，不认证远程版本。

没有复制未公开 evaluator、完整 benchmark 数据或 gold programs。SAB 短事实归属其 CC BY 4.0 数据卡及 OSU NLP Group；CORE 仅保存带定位的少量事实/参考值。完整科研结果仍需相应原任务的执行和评价。

## 实际调用与预先声明的 oracle

脚本直接加载 integration 的 `RDSAdvisor.advise_on_loss_dynamics` 和 `rds_advisor_search.search_directions`，传入来源标记事实与人工适配的 dict graph。它不会重新实现一个 Advisor 来代替实际模块。判定合同在 `source-facts.json` 的 `cases[].expected` 中预先写定；判断依赖题面及显式扰动，不读取运行输出再改正确答案。

这些 oracle 的意义是：原合同要求 20，则 10 的检查不可就绪；人类明确改合同后建议应随之改变；无来源事实保持 UNKNOWN；未知成本不认证可承担；指定工作流未证明完成时不能直接当作就绪；错 source identity 阻止复现归属。其它正确处理三值条件、来源和预算的实现也可以满足它们。规则 ID 是 fixture 标识，不是原 benchmark gold policy。

执行结果：

| Case | 对照或扰动 | 预期与实测结果 | 结果 |
|---|---|---|---|
| C1 | 公开单 train scalar，无配对曲线 | `INSUFFICIENT_EVIDENCE`，未升级为收敛/容量诊断 | 通过 |
| C2 | 原 SHAP 20 项合同 | 20 项检查 `READY`，10 项检查 `BLOCKED_PREREQUISITE` | 通过 |
| C3 | 人为把需求改为 10 项 | 候选交换：10 项 `READY`，20 项被阻止；此时已非原 SAB 任务 | 通过 |
| C4 | 值仍为 20，删除其 source | 两项检查均 `NEEDS_EVIDENCE`，相关 truth 为 UNKNOWN，产生只读查询 | 通过 |
| C5 | 删除 20 项检查的 cost | 检查条件就绪，但 cost 和 budget status 均 UNKNOWN | 通过 |
| C6 | preprocessing 有 synthetic 完成标记；embedding 缺失 | `NEEDS_EVIDENCE`；遍历两层 prerequisite 边并请求 embedding 证据 | 通过 |
| C7 | 已声明前置完成；可用预算为 0 | 正的本地元数据检查 cost 导致 `BLOCKED_BUDGET`，没有就绪替代项 | 通过 |
| C8 | 锁定 7038571，却提供真实但不同的 5286757 capsule ID | identity predicate 为 FALSE，阻止该复现 source 的后续检查 | 通过 |

C8 只测来源 capsule 身份条件，**没有测量**训练 control cache 的 AST、数据 SHA、recipe 或 checkpoint 复用验证。C6 的边是题面改编的工作流依赖，**不是**由数据发现的因果边。C2–C8 测的是手工绑定的条件和候选组合；没有测量系统能否从自由文本自动提取正确 graph 或自行生成新科学方法。

## 成本、版本与重跑

本次单次读取/解析小型 `source-facts.json` 的实测开销为 **0.3766 ms**。graph cost 引用这个本地元数据检查观测；正常 fixture budget 为它的十倍，零预算/未知 cost 是显式扰动。这个 cost 只用于已说明的元数据检查，不能转换为 SHAP、training、capsule 执行或完整 artifact 验证成本。查缺失 receipt 的总成本未提供，相关组合保持 UNKNOWN。

在 repository root 运行：

```powershell
python benchmark/advisor-public/run.py
```

也可指定其它含相同 API 的 checkout：

```powershell
python benchmark/advisor-public/run.py --root C:\path\to\research-direction-selector --output benchmark/advisor-public/results-rerun.json
```

仅 Python 标准库；不安装 dependencies、不联网、不启动原任务。默认覆盖该目录中的 `results.json`，保留原运行可另设 output。计时随机器变化；检查的期待行为固定。输出包含完整 adapted graph/context、每条 criterion、module 和 runner/input SHA256：

| 锁定对象 | 本次 SHA256 |
|---|---|
| `source-facts.json` | `41e40fc86b3e561cafb8443848062e3dcdf499e3a268de443b05a148151ee00e` |
| `run.py` | `a93aeae3790112914f15b80907fa3e9c1bc6bf64005f60716237f5623d36f409` |
| `rds_advisor.py` | `b70b480d46493ba1eecd00221657d61790fb5051f7808ce643e40c916f53b820` |
| `rds_advisor_search.py` | `ca68505c3a94035e25b2b1b6accc940815ae09e838b3d0bbc6f93a0314241369` |

## 结论的适用边界

这次结果支持：在这组显式配置和小规模输入中，程序建议确实随事实来源、合同、依赖和预算改变，并保留未知。不能由 8/8 得到诊断准确率、research-quality、原 benchmark success rate、概率校准或实际 GPU 节省比例。

案例是公开、手工选择的 development fixtures，不是 blind holdout；适配图也由人写定。source 字段仍是 caller-reported，engine 没有访问 URL 或独立验证 receipt 的真实性。本轮只读原 metadata，不证明 synthetic 完成标记为真。两个显式 outcome labels 让程序可检查候选格式，但不能证明这些观察分支科学上确有判别力；真实任务还须验证其测量模型和替代解释。

本轮直接传 dict graph，未覆盖 CLI、真实 YAML 解析、全部静态判断图或长期记忆检索路径；这些由其它回归单独覆盖。进一步测试应在合适的公开执行环境可用且投入被授权时，评估原任务的真实 artifact、工作流完成和评价程序；继续保留组件 guardrail 与原科学任务分数之间的分界。

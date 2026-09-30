# 科研 benchmark 选型资料与暂缓的比较方案

核对日期：2026-09-30。**横向比较已暂缓，没有排期，也没有运行实验。** 下文九次 attempt 是此前提出、尚未执行的存档方案，不会自动启动。本页保留选型资料，没有产生新的能力分数，也没有启动模型 API、GPU 或付费实验。

**当前优先体验和实用：先把一个真实项目的完整 L2 科研辅助流程用顺。** 从目标、已有记录、假说与下一步，到执行准备、真实证据、结果解释和继续决定，让人能清楚审阅、跨会话接续，少重复解释、找记录和纠正 AI。只使用项目中已有或已授权的工作，不为刷分增加实验；实际能力仍以实现和记录为准。

目前的 208 项组件回归包含 204 项通过、4 项可选依赖跳过；公开任务改编挑战为 8/8 案例、28/28 条合同检查通过。它们检验特定实现与已配置规则，不能当端到端科研能力、原 benchmark 分数或优于其他 skill 的证据。见 [已测结果与边界](advisor-benchmark.md)。

## 保留的 benchmark 选型资料

| 候选及核对版本 | 测什么、实际条件与未来参考用途 |
|---|---|
| **SkillsBench v1.1；固定仓库提交为 2026-07-23** | 87 个任务、8 个领域，原任务有执行环境和验收；此前选了三个 CPU 科研任务作为比较候选，现已暂缓。它覆盖实际分析与交付，但不是完整开放式科研发现。[版本](https://github.com/benchflow-ai/skillsbench/releases/tag/v1.1) [论文 v4，2026-06-14](https://arxiv.org/abs/2602.12670) |
| **ResearchGym v2，2026-03-11** | 5 个任务、39 个子任务，隐藏论文方法，评估提出方法、实验和迭代成果；最接近科研闭环。原实验单 A100 80GB，基本 12h/$10 API，Codex 等专有框架 24h/$20；确定预算和环境后才跑。[论文](https://arxiv.org/html/2602.15112v2) [官方代码](https://github.com/Anikethh/ResearchGym) |
| **MLRC-Bench v3，2025-10-24** | 7 个研究竞赛任务，最佳开发快照在隐藏测试集评分，基线=0、顶尖人类=100；测方法实现收益。单 16/48GB GPU，普通 launcher 上限 5h/$10，后续预算项。[论文](https://arxiv.org/html/2504.09702v3) [预算脚本](https://github.com/yunx-z/MLRC-Bench/blob/main/launch.sh) |
| **RE-Bench v2，2025-05-27** | 7 个研究工程环境，起点=0、强参考解=1；能测优化与资源分配，但多数需 H100。唯一无 GPU 的 Rust 任务原设 20 核/100GB/$500 API，也不是廉价首测。[论文](https://arxiv.org/html/2411.15114v2) [官方代码](https://github.com/METR/RE-Bench) |
| **InnovatorBench，ICLR 2026** | 20 个 LLM 研究任务，方法设计与实验迭代，2–36h，多机/GPU及评测 API 随任务变化；部署和训练投入较大，留待后续。[论文](https://arxiv.org/abs/2510.27598) [官方代码与数据准备](https://github.com/GAIR-NLP/InnovatorBench) |
| **Autoresearch Bench，2026-09-01** | 4h 实验反馈循环，许多任务有外部隐藏测试；很贴合下一步选择。当前官方仓库只有 README，未发布任务/harness，统一费用未确认，不能列为准备就绪。[官方说明](https://www.autoresearch-bench.com/) [代码发布状态](https://github.com/Emulated-Labs/autoresearch-bench) |
| **SciAgentArena，2026-06** | 关注科研任务有效性、工作流及工具约束；数据访问要求分享联系信息并接受条款，本轮未接受、未取得完整环境，不能直接启动。[官方发布页](https://sciagentarena.github.io/) [数据访问条件](https://huggingface.co/datasets/iLOVE2D/SciAgentArena) |
| **BixBench 当前公开版本** | 生物数据的多步分析与解释，支持自定义代理；官方全套脚本为多副本、多模型，24–48h 且 API 费用明显，先不运行默认套件。零样本问答不能替代端到端分析。[官方执行说明](https://github.com/Future-House/BixBench/blob/main/README.md) |

这些资料按核对日期记录公开版本与执行条件，今后恢复比较时须重新核验。不同模型、框架和预算下的已发表分数，只能作背景，不能拿来证明 RDS 的增益。SkillsBench 网站有更多框架/模型配置，论文与网站统计口径不同；存档方案选用 v1.1 任务，不借用其排行榜作为我们的成绩。[官方项目](https://www.skillsbench.ai/)

## 存档方案：固定版本与三个条件

以下版本是此前候选方案的定位记录，并非当前执行安排。将来恢复时重新确认模型、skill、任务、环境和预算，不能直接沿用过时配置。

| 对象 | 固定内容 |
|---|---|
| 任务 | SkillsBench v1.1，提交 `9a1f4dd5f7659f75707435da3ce854b6e48321d1`；执行前记录 release、任务、环境镜像和 grader 的实际哈希 |
| A：无额外科研 skill | 同一底座模型与基础代理；不给额外科研 skill，保留相同任务题面和基础通用工具 |
| B：K-Dense 科研包 | 提交 `65d6e786832e2c52832713117bbbf5096b56f77f`；启用 hypothesis-generation v2.2、scientific-critical-thinking v1.3，MIT；包含两个 skill 的实际程序能力，不能裁成纯提示词 |
| C：RDS | v5.5.0-rc.2，提交 `b0689fd618cba67414ea2de2ad380242d8bacf23`；启用科研规程、执行与验收、研究状态与记忆、Advisor、RSI 中实际已实现的接口 |
| 方向建议参考 | Orchestra 提交 `773a52944ba4747a18bd4ae9ade53fff041adcbc` 的 brainstorming-research-ideas；适用于方向建议子测，不作为完整实验流水线基线，不加入存档的九次候选执行 |

B 使用原始 [hypothesis-generation](https://github.com/K-Dense-AI/scientific-agent-skills/blob/65d6e786832e2c52832713117bbbf5096b56f77f/skills/hypothesis-generation/SKILL.md) 与 [scientific-critical-thinking](https://github.com/K-Dense-AI/scientific-agent-skills/blob/65d6e786832e2c52832713117bbbf5096b56f77f/skills/scientific-critical-thinking/SKILL.md)。其配套共有 7 个 CLI，执行前逐项登记入口、依赖和实际调用；保留完整包才能比较真实使用效果。其 [最新论文 v2，2026-09-02](https://arxiv.org/abs/2609.00065) 未提供任务级能力评测，不能据此推定胜负。Orchestra 的适用范围见 [固定版本 skill](https://github.com/Orchestra-Research/AI-Research-SKILLs/blob/773a52944ba4747a18bd4ae9ade53fff041adcbc/21-research-ideation/brainstorming-research-ideas/SKILL.md)。

如果未来恢复，比较对象是**科研 skill 完整工具包**。三组应固定同一模型版本、推理设置、基础运行框架、题面、数据、通用工具、网络权限、执行依赖与资源上限；skill 自带程序的差异逐项披露。全部模型、CLI、检索、实验、诊断和验收费用计入相同总预算。不能把包级效果解释为纯提示词效果，不默认增加消融组合。

## 存档方案：三个原任务、九次候选执行

| SkillsBench 原任务 | 选择理由 | 此前提出的执行数（未运行） |
|---|---|---|
| [econ-detrending-correlation](https://github.com/benchflow-ai/skillsbench/blob/9a1f4dd5f7659f75707435da3ce854b6e48321d1/tasks/econ-detrending-correlation/task.md) | 检查趋势处理与相关分析，观察程序分析和结果解释是否对齐 | A、B、C 各一次 |
| [citation-check](https://github.com/benchflow-ai/skillsbench/blob/9a1f4dd5f7659f75707435da3ce854b6e48321d1/tasks/citation-check/task.md) | 检查引用是否真的支持主张，观察查证与未知处理 | A、B、C 各一次 |
| [lake-warming-attribution](https://github.com/benchflow-ai/skillsbench/blob/9a1f4dd5f7659f75707435da3ce854b6e48321d1/tasks/lake-warming-attribution/task.md) | 科研数据分析与归因解释，观察证据、竞争解释和交付物 | A、B、C 各一次 |

此前候选方案共 **3 × 3 = 9 次 attempt**，每个条件/任务只有一次，没有安排重复采样、多 seed 或 GPU，实际执行数为零。若将来恢复，不同条件应从相同干净任务状态开始，不共享另一个条件的输出、建议或记忆；条件顺序、模型设置和预算须预先记录。若任务本身要求随机种子，固定并披露这一执行配置。

即使未来完成，这也只是三个选定任务的配对试测，**不是完整 87 任务的官方分数**。单次结果不能证明统计稳定胜出；发现会改变结论的实际不稳定性后，再决定是否值得增加执行。预算不足、工具不适配或任务不能执行时如实报告，不能改题或改 grader 使成绩通过。

## 存档：未来恢复比较时的准备事项

此前核对时本机 PATH 未发现 Docker，模型/API 预算和运行资源尚未确认。**这不构成当前安装、准备或执行任务。** 将来重新决定恢复比较后，先核实版本、环境与总预算；本页不授予新的付费、GPU 或条款接受权限。

1. 拉取固定任务版本，逐项确认 CPU 环境、数据规模、许可、网络边界、依赖与原始 grader；记录镜像 digest 和实际执行命令。
2. 准备可用的隔离执行环境。若需 Docker/WSL、远程资源或调整任务条件，先明确安装/资源范围；不把改编环境冒充官方协议。
3. 固定三组同一模型、框架版本和工具权限，登记两个基线 skill 的 CLI 与 RDS 的入口。清空跨条件记忆，禁止运行中更新 skill/规则。
4. 在执行清单写明每次 attempt 的时间、token/API、CPU/RAM、磁盘和验收开销上限，以及九次合计预算；先核实限制能实际生效，再启动。
5. 由独立评测侧保管隐藏测试、参考答案和 oracle；代理只能读原题允许的数据与公开反馈。不能将隐藏答案、测试逻辑或另一组轨迹放进上下文。
6. 在看结果前锁定原题评分与附加证据审核表，记录任务选取、历史暴露和已知环境问题；任何后续变更都留下原因与版本。

## 存档：恢复比较后如何报告成绩

**原任务验收与附加证据审核分别报告**，不发明一个“综合科研能力分”。原 grader 保留其成功/失败和任务原生指标，逐题展示 A/B/C 的交付物与评分；只明确标注这三个任务的结果，不外推全领域能力。

附加审核检查：引用是否支持主张；配置、代码、数据与结果能否对上；结论是否超出证据；缺失证据是否保持未知；竞争解释是否保留；建议是否根据实际观测更新。审核不是凭文风给创新分，也不要求命中 RDS 自己的规则名称。开始前公开标准，评测侧尽量隐藏条件身份；需要人工判断的项单列判断依据和分歧。

同时单列：

- **成本与时间**：模型/API、skill CLI、检索、环境准备、执行、诊断与验收；共享准备费用说明分摊方式。
- **失败与干预**：所有 attempt 都登记；区分基础设施失败、预算耗尽、无效产物和原 grader 未通过。排除规则预先声明，失败的支出保留，人工纠正次数与时间另报。
- **完整记录**：固定版本、命令、工具调用、原始日志、运行配置、产物哈希、评分输出与人工审核；轨迹保存原文，敏感凭据不写进公开材料。

公开结果时同时提供负结果和限制：是否只有单次、是否选定子集、是否改环境、是否使用人工帮助、有哪些跳过项。原始轨迹是复核依据；成功交付不等于新机制成立，科研分析得分也不等于 RDS 已实现自主科研。

## 当前推进条件：先确认体验与实用

先在一个真实项目中贯通 L2 的全部环节，检查人是否能直接找到当前目标、已有证据、下一步及其理由，是否能换会话继续，以及是否少了重复解释、翻找记录和纠正 AI 的负担。用真实任务的记录、失败和人工纠正说明改善在哪里；没有观察到改善就修复具体体验问题，不制造科研效果分数。

真实任务体验稳定、确有需要衡量的问题后，才考虑恢复同条件比较，并重新确认预算、版本与评分协议。ResearchGym 等真实闭环 benchmark 仍是备选资料，不能自动升级为实验。人类负担、长期记忆、RSI 改进与数学证明有效性各有自己的证据；一个项目的顺畅体验不能一并证明这些能力。参见 [未来计划](roadmap.md) 与 [研究自主性边界](research-autonomy.md)。

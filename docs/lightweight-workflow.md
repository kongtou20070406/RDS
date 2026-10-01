# 轻量科研工作流

2026-10-01 的单机操作路径验收：本地弱图检查的暖样本中位耗时为 **0.225 秒**，Obelisk 有界历史审查加同一检查为 **2.123 秒**，减少 **89.40%**；两侧均计入 CLI 启动，主要防打转提示相同。样本为 3 个本地点与 2 个增强暖点，精度与工作量不同；这是该配置下的路径时延，完整 AI 回复时延、历史恢复精度和科研效用仍未测量，不能推广成所有项目都快 50%。

使用者给出当前问题和可用记录即可。AI 从现有目标、代码、观测和预算提炼下一决定，内部考虑至少三条因果上不同的路线，通常只呈现一个推荐与一个必要备选，并推进已有授权内的工作。无需逐轮填表或加载全部后端。当前实做以机器学习研究为主；其他学科需要自己的执行接口和证据协议。

## 本地弱方向图用于防打转

项目的单一 `RESEARCH.md` 保存 AI 整理的紧凑有类型决策记录：目标版本、稳定 idea/decision ID、状态、停下原因、实际干预、重开条件及下一决定。weak direction graph 的用途是防止重复提案、A–B 摇摆和讨论没有下一步，**不是来源检索**。源指针仅用于审计与核对原始证据，不形成来源索引、聊天镜像、embedding store 或第二套状态机。

```powershell
python -B scripts/rds_cli.py advise --research-note RESEARCH.md
```

CLI 读取一个完整的 `rds-research` JSON 围栏，`schema_version=1`，包含 `goal`、有序 `events` 和可选 `config`。goal 绑定 revision、metric 名称/单位、direction、budget 及来源；events 的类型为 proposal、decision、discussion、result 或 goal_change。记录由 AI 从实际任务整理，使用者不用填 schema。目标或预算尚未明确时保持待定，不为了过校验虚构冻结值。

Proposal 使用稳定 `idea_id/question_id/goal_revision`、scope、typed intervention、source，以及正负结果对应的下一 decision ID。Decision 另记录 `decision_id`、`outcome` 与 `reason`。摘要保留原始证据定位；没有真实接受记录就维持 proposed/pending，不能自行写 accepted。手写 accepted、verified 或 plan_locked 都不会产生执行授权。

纯 note-only 路径不加载整张判断图、principle library 或 SQLite，不依赖 Obelisk，也不调用它。`--research-note` 可与 `--artifacts`、`--frontier` 组合；不能混用 literature、document 或 fit 模式。需要导入真实观测或探索图断口时，才调用对应功能。

## Proposal review 的边界

相同稳定 ID，或相同 scope 和有类型干预再次出现，程序可检查已记录否决：没有显式变化提示 `REPEAT_REJECTED_IDEA`；新证据指针、范围或干预变化提示 `REOPEN_REVIEW`，保留旧否决供复核，不能自动宣告旧结果失效。正负结果导向同一下一决定会提示无效实验；连续讨论无锁定计划只建议收敛，不强制选择未知目标。

这些都是 `INPUT_REPORTED` 的弱记账检查。它不理解任意同义改写，不保证录入完整，不认证来源或科研结果，也不恢复精准聊天历史。源指针和新证据标签需要实际核对；不能仅凭新增标签重开并宣称科学支持。摘要与实时文件或收据冲突时，核对原始材料和当前状态。

讨论停滞时，先推进最小有效决定或可逆证据检查。新证据、作用域或实际干预改变旧否决依据，可以重开并解释变化；同一证据下反复换措辞不构成新方向。推荐与未回复均不等于用户接受，记录不能扩大现有授权。

## Obelisk 是可选精确历史增强

需要过去原话、精确参数或数值且现场记录不足时，可选择已有 [Obelisk bridge](../references/obelisk.md) 查询相关原始历史。bridge 只是公共 CLI 的调用包装，不要求另配服务。使用增强模式前可检查：

```powershell
python -B scripts/rds_cli.py history preflight
```

preflight 仅检查 CLI 可运行和版本；`required_for=enhanced_history`、`optional=true`。索引、agent skill 加载和当前项目覆盖仍是 `NOT_CHECKED`。缺 CLI、权限错误或超时只表示增强不可用，本地防打转仍可工作；不能谎称已查询 Obelisk、没有历史或精确恢复完成。

需要该增强时按[官方安装说明](https://github.com/tommy0103/obelisk#install)配置 Node.js >=22.13，并运行 `npm install --global @obelisk-apps/cli`、`obelisk --version`、`obelisk install`。Node 和 Obelisk 都不是本地弱方向图的必需依赖。查询保持项目范围、可见性、原始身份与数据暴露边界，不直读数据库或复制全部聊天。

## 响应时间目标与未测状态

50% 指**响应时间减少至少 50%**，不是科研效果达到增强版的一半。应比较同一防打转任务、相同信息粒度和判断要求下，本地 guard 与增强 retrieval+guard 的完整路径：`1 - T_local / T_enhanced >= 0.5`。记录环境、任务规模、冷/热状态、响应波动以及是否产生相同的有效复核决定。

未完成这样的测量前，目标为 `UNMEASURED`。单次操作路径延迟不能证明科研效用；本地只看 tags 与外部恢复完整历史属于不同工作，不能据此宣称效果等同或达到速度目标。同任务接续和重复提案检查的有效效果也须另测，目前新科研收益仍为 `UNMEASURED`。

## 按需加载细节

[短 SKILL](../SKILL.md)保留核心纪律；[research discipline](../references/research-discipline.md)保留详细目标、伪代码、证据、人类介入、输出、CLI 与形式验证契约。相关规则才读其日期、范围、条件和反例；外部执行用 [project 工作流](development-loop.md)，数学义务用 [formal framework](../references/formal_framework.md)，科研收益用 [advancement 协议](advisor-advancement.md)。

Runner、Lean、Advisor 和 RSI 能力与验收门继续保留。科研偏好仅明确 opt-in 才记录或沿用；[可选偏好](../references/optional-preferences.md)不授予资源权限。软件回归、形式性质或历史案例命中不能替代独立科研验证。

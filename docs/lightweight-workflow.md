# 本地决策与防打转

使用者给出当前问题和可用记录，AI 从目标、代码、观测和预算整理下一决定，推进已有授权内的工作。无需逐轮填表。五个组件继续分工：Skill 组织研究，执行内核运行与验收，状态记忆保存账本，Advisor 建议下一步，RSI 评估规则修改。

## 使用已有账本

本地防打转内聚在 `scripts/rds_advisor.py`，复用已初始化项目的 `.rds/project.sqlite3` 或参考内核的 `.rds/state.sqlite3`。独立 `--research-note RESEARCH.md` 入口已退出；旧调用会返回迁移提示，不把裸文本标签当成可信历史。

AI 将实际生成的结构化候选原样放入 `decision.json`，同时记录 `question_id`、`goal_revision`、`scope`、`outcome` 和当时的 `evidence`。`outcome` 为 `rejected`、`accepted`、`plan_locked` 或 `deferred`；`evidence` 使用对应 research context 的 facts。没有真实接受记录时不能自行填写 accepted。已有 checkpoint 命令负责事务写入、哈希身份与契约绑定：

```powershell
python -B scripts/rds_cli.py --root <project> checkpoint save --id <checkpoint-id> --decision <decision.json>
python -B scripts/rds_cli.py --root <project> advise --research-context <context.json>
```

`context.json` 的 `decision` 对象包含 `id`（对应 `question_id`）、`goal_revision` 与 `scope`，`facts` 包含当前事实。AI 整理这些内部字段，使用者不必维护 schema。目标或预算尚未明确时保留未知，不为了通过校验虚构值。

## Advisor 如何使用历史

Advisor 在只读事务中核对 checkpoint 哈希与当前契约，使用匹配问题的结构化决定；声明了相同验收谓词的同一目标，还会读取改名问题的记录（见下文）。相同路线在相同目标、范围、事实和前提下已被否决时，从可用候选中剪除，并保留 `REPEAT_REJECTED_ROUTE` 及原 checkpoint 身份。比较的是实际干预结构，显示 ID 不作为路线身份；程序不理解任意同义改写。

`decision.goal_conditions`（不计顺序）与 `goal_revision` 相同时，即使 `question_id` 改名，也视为同一目标：范围与事实都未变的被否决路线照样剪除，标记中给出原 `recorded_question_id`；范围或事实改变时照常 `REOPEN_REVIEW`。无论记录在哪个问题下，都按 checkpoint 顺序以最近一次适用的决定为准：回到旧问题既不能绕过后来的否决，也不会让已被取代的否决继续生效。就绪候选只改了某条被否决路线的参数（该路线在同一目标、当前范围下最近一次记录仍为否决，且记录时的审查事实与现在相同）时，提示 `GOAL_ROUTES_REJECTED`；目标仍为 `UNKNOWN` 或 `FALSE` 时 `next_move` 为 `REFORMULATE`：先把一个改变前提、表示或方法的方案与最小修补比较，再决定是否继续加参数。首次尚未测量的尝试、改变了操作或干预的路线、范围明确的证明义务检查和已有可判别对照不受打断；参数变体本身不被阻止；范围或相关事实已改变时不给变体提示，因为新的范围或证据尚未失败。描述、竞争解释和结果标签与路线身份一样只作显示；没有结构化 target、intervention 或 operation 的动作不归入参数变体。其他问题的格式错误记录不阻断本问题：Advisor 提示 `GOAL_HISTORY_SKIPPED`，只用本问题的记录。验收谓词或修订号不同、未声明谓词时不共享历史；参数域否决与 A→B→A 摇摆仍只看本问题；不同项目根目录仍不共享账本。

相关事实、前提、测量、范围或目标改变时保留候选并提示 `REOPEN_REVIEW`；新干预按其实际结构比较。A→B→A 提示 `DECISION_OSCILLATION`，供人核对摇摆原因，不直接禁止执行。发现损坏或契约冲突时报告 `LOOP_HISTORY_REVIEW_ERROR`，不能用部分损坏历史剪枝。

这些记录的 assurance 是 `RECORDED_INPUT_NOT_SCIENTIFIC_VERIFICATION`。哈希只核对记录身份；记录的否决不是科学定理，事实改变也不自动成为新证据。重复提案检查不能替代原始观测、独立确认、形式证明或执行准入。建议与未回复不等于接受，实时预算、收据和授权继续由现有内核管理。

## Obelisk 是选配的长程原话检索

本地账本可以独立防打转。现场记录缺少过去原话、精确参数或数值时，才使用已有 [Obelisk 接口](../references/obelisk.md) 检索项目范围内的原始历史，无需新增 bridge 服务。

```powershell
python -B scripts/rds_cli.py history preflight
```

Preflight 只检查 CLI 可运行和版本，不证明索引新鲜、skill 已加载或项目覆盖完整。增强检索不可用不妨碍本地账本复核；不能把查询失败说成没有历史。需要增强时参考 [Obelisk 安装说明](https://github.com/tommy0103/obelisk#install)。不直读其数据库，不复制完整聊天。

原独立 note 路径的速度数字不适用于现有账本路径，已撤下。软件回归通过不等于科研效用提高；科研收益仍需独立评测。

细节按需阅读：[Skill](../SKILL.md)、[科研纪律](../references/research-discipline.md)、[项目与开发循环](development-loop.md)、[形式检查](../references/formal_framework.md)和 [RSI 证据](../references/rsi-evidence.md)。科研偏好仅明确 opt-in 才记录或沿用。

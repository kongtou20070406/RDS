# 由程序维护依赖关系

**简体中文** · [English](truth-maintenance.md)

给工具简短声明和变更即可。程序生成内部 AND/OR 表、选择支持证人、审查结构并重算闭包与目标阻断项。AI 无需维护另一张支持表，也无需把推导后的状态复制回输入。

现有 `hypergraph` 命令同时接受原格式与简短输入：

```json
{
  "claims": {"premise": {"status": "supported", "source": "observation.json"}},
  "rules": [{"from": "premise", "to": "target", "status": "supported", "source": "implication.json"}],
  "goal": "target"
}
```

程序把 `target` 自动建为 `UNKNOWN`，生成规则 ID，再计算声明闭包。AI 只需提交一次支持关系的含义。同一规则的前提是 AND；多条规则通向同一结论是 OR。工具无法从任意散文中发现科学蕴涵。

## 宽容输入

能确定含义的格式修正由程序完成，并保存在 `input_review`：

- 接受整个 JSON 代码块和字符串外的尾逗号。
- 接受 `claims`/`nodes`、`rules`/`hyperedges`、`goal`/`goals`、`state`/`status`，以及规则的 `from`/`premises`/`if`、`to`/`conclusion`/`then`。
- 节点可以按 ID 写成对象；单个前提或目标可以直接给字符串。自动修整 ID 空白和状态大小写，去掉重复 AND 前提。
- 未给节点状态时默认 `UNKNOWN`，未给规则状态时默认 `PROPOSED`。自动补出被引用节点和规则 ID。缺来源时生成仅指向输入声明的定位符，无来源的 `SUPPORTED` 声明保留为 `UNKNOWN` 或 `PROPOSED`。
- 已给文件/哈希的来源会补定位符并保留原字段；哈希组合无效仍明确报错。完全相同的重复变化复用快照，新的变更来源继续留在历史中。

别名冲突、重复 ID、缺规则端点、未知变更目标会一起报告；存在这些歧义时不应用变更。退出码 2 表示输入需要澄清或计算达到上限。科学义务尚未解决仍可继续使用，不会成为格式拒绝。重复 JSON 键与非有限数字仍无效。导入的代码只作为数据，不会执行。

## 在 agent loop 中只提交变更

```powershell
python -B scripts/rds_cli.py --root ../tms-demo hypergraph -i examples/tms-input.json
```

根目录需要已存在。程序将当前图保存在现有 `.rds/project.sqlite3` 与 CAS 中，下一轮自动读取该项目的当前状态，AI 无需传整张表或上一轮的 `record` 路径：

```powershell
python -B scripts/rds_cli.py --root ../tms-demo hypergraph --retract-node premise --change-source later-observation.json
python -B scripts/rds_cli.py --root ../tms-demo hypergraph --update one-change.json
python -B scripts/rds_cli.py --root ../tms-demo hypergraph --trace-cone target
```

`one-change.json` 可以只有 `{"claims":{"premise":{"status":"supported","source":"new-observation.json"}}}`；`--declare '<简短 JSON>'` 也可直接提交，省去写文件的一次往返。一次最多合并八份增量，引用不会覆盖已有观测；明确冲突的 scope/revision 或计算上限需显式导入新图。ID、声明来源和派生状态表由程序生成，科学关系的含义仍需调用方给出。

默认输出至多三个目标状态、有界变化摘要、一个下一步与供按需查看的 CAS 定位符。同一次工具调用完成编译、更新、重算、保存。撤回节点支持变为 `UNKNOWN`，撤回规则支持变为 `PROPOSED`；`--refute-node` / `--refute-rule` 记录 `CONTRADICTED`。原始证据来源留在记录上，变更来源与此前的状态/来源保存在只追加历史中。需要详情时可用 `--output <new-file>` 与 `--json`。

普通闭包、目标状态、阻断集合与报告行统一来自修订后的图。独立 OR 路线会保留，无锚定的环不能自证。旧快照不可变；`--input <旧记录路径>` 可显式恢复。歧义不会改写当前图，并发更新会返回 `CONFLICT`，不会覆盖他人更新或把旧结论当作当前结果。退出码 2 的不同原因由 `status`/`next_step` 区分：需澄清的 `UNKNOWN`、达到计算上限的 `INCOMPLETE`、并发的 `CONFLICT`；语法、存储或完整性错误仍走退出码 1。

`advise --saved-dependencies --context context.json --graph graph.json` 在程序侧向现有 Advisor 注入该根目录的当前图；前瞻执行 `exec --saved-dependencies --context context.json --graph graph.json --ledger <归属账本>` 在准入前也会从归属账本重新加载。上下文文件无需放依赖表。原有 `dependency_map` 输入仍可使用简短声明或程序完整快照，内部标准表保留严格验证。不要同时通过两条路提供图；收据、目标门禁、预算与授权继续由现有组件负责。

自定义工具可用 `rds_tms_store.tms_tool(root, declaration=..., retract_nodes=...)`。宿主从本地上下文绑定根目录，模型只见小参数和短结果。Codex/Pi 已可通过 shell 工具使用 CLI；原生自定义工具的包装属于集成示例，没有自动安装插件。只在证据、依赖变化或需要解释下一步时调用，不强制每轮运行，也不挂无限继续钩子。调查来源与字节对照见 [Codex/Pi agent loop 设计](agent-loop-tms.md)。

## 证据范围

保证级别仍为 `INPUT_REPORTED_DEPENDENCY_ANALYSIS_NOT_PROOF`。来源定位符、声明的 `SUPPORTED`、文件哈希、执行收据或有限本地用例都不能确立科学结论。文件审计只检查字节。程序维护依赖影响、建议下一项检查，不产生执行授权或普适能力认证。

可复用候选的执行继续使用 `rsi extract/validate/register/use`。绑定原任务的应用、独立预期答案和限定范围复用继续在 #43/#45 中推进；收据到反驳的集成继续在 #49/#36 中推进。本接口不引入能力 registry 或强制三级流程。

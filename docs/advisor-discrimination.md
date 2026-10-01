# Advisor：显式预测下的条件判别

`action.discrimination` 是有界搜索的可选配置。它登记每个候选解释允许哪些观察，再用有限集合交集计算当前条件下可区分的解释对。预测与来源由调用者声明；程序不生成预测，也不验证来源中的科学主张。

## 输入契约

在现有 `executable.action` 中增加：

```json
"discrimination": {
  "scope_id": "synthetic-update-path-v1",
  "source": "synthetic fixture; not measured research evidence",
  "predictions": {
    "optimizer_step_omitted": ["step-not-recorded"],
    "zero_lr": ["step-recorded"],
    "incorrect_targets": ["step-recorded"]
  },
  "conditions": [{"fact": "protocol_matched", "op": "eq", "value": true}]
}
```

| 字段 | 约束与含义 |
|---|---|
| `scope_id` | 显式、非空的比较范围 ID；支配比较还必须使用完全相同的解释 ID 集合。 |
| `source` | 预测依据的来源定位，沿用现有 source 格式与可靠性规则。提供定位不等于来源已核验；显式标为不可靠的声明不提供支持。 |
| `predictions` | 键须匹配 `action.competing_explanations` 中的解释 ID；值为非空的允许观察标签数组。标签须来自 `action.outcomes[].observation`。 |
| `conditions` | 可省略；沿用现有有界事实谓词与三值求值，如 `eq/ne/in/lt/lte/gt/gte`。不执行自然语言或任意代码。 |

解释列表、每个预测标签列表及条件列表各以 32 项为界。opt-in 声明的必要字段缺失或结构无效时，保守地将全部解释对保留为未决，不用部分残缺声明认证判别支持。

解释 ID 是稳定身份，不宜用临时改写的描述来代表同一解释。观察标签只是有限模型的结果类别；测量协议和类别边界仍须由任务定义。

## 判别与未决项

对解释对 `(a, b)`，只有预测支持有效、有来源、双方允许观察集合均非空，且所有适用条件为 `TRUE` 时，两个集合不相交才进入 `conditional_distinguishing_pairs`。这里的“条件可判别”依赖所声明预测成立，尚未观察到结果。

预测集合重叠、缺失预测、未知标签、无有效来源或适用条件为 `UNKNOWN/FALSE` 时，保留 `unresolved_pairs` 和原因。条件求值仍区分缺证据与已知矛盾；两者都不提供判别支持。缺失或不可用的预测不能通过空集合获得虚假的判别力。

每个 opt-in 候选的 `candidate.discrimination` 保存以下字段：

| 输出 | 含义 |
|---|---|
| `scope_id/source/evidence_status` | 声明范围、来源与来源身份；调用者 JSON 保持 `INPUT_REPORTED`。 |
| `conditions/applicability` | 每个条件的事实求值轨迹与合取结果 `TRUE/FALSE/UNKNOWN`。 |
| `valid_prediction_support/issues` | 预测支持有效与否，以及声明问题。完整但重叠的预测可以是有效支持。 |
| `conditional_distinguishing_pairs` | 形如 `["incorrect_targets", "optimizer_step_omitted"]` 的解释 ID 对。 |
| `unresolved_pairs` | 形如 `{"pair": ["incorrect_targets", "zero_lr"], "reason": "..."}` 的未决对与原因。 |

候选原有的动作前提、预算和决策覆盖仍分别检查。预测适用条件失败不代表某个解释已被反驳，也不代替动作本身的前提。

该输出不含解释概率、熵、预计信息增益或 VOI；集合数量不是成功率。模型未列出的解释仍可能成立。

## 对支配关系的影响

两项动作都未配置 `discrimination` 时，沿用已有决策覆盖与可比增量成本的偏序。任一动作 opt-in 后，支配比较还要求双方显式使用同一 `scope_id`、完全相同的解释 ID 集合、有效预测支持，并且各自至少有一个获得支持的条件可判别对；较优动作的条件可判别对集合须包含另一项的集合。全部预测重叠的声明可以结构有效，但没有获得支持的判别对，因此不能支持支配关系。一个 opt-in 动作与一个 legacy 动作不能靠旧的覆盖数量相互淘汰。

其余已有要求仍适用：候选状态相同、资源/单位/比较组可比、决策覆盖不缩小、成本不更高，并至少在一个比较维度严格更好。在成本相同且其他要求满足时，严格增加条件可判别对覆盖即可提供这一严格 Pareto 改善。不同范围、无有效预测支持或覆盖互不包含时保留不可比；不把不同粒度的解释对数量加成总分。

## 运行软件示例

[discrimination-example.json](../examples/advisor-search/discrimination-example.json) 同时包含 `graph` 与 `context`。在仓库根目录运行：

```powershell
python -c "import json,sys; from pathlib import Path; sys.path.insert(0,'scripts'); from rds_advisor_search import search_directions; x=json.loads(Path('examples/advisor-search/discrimination-example.json').read_text(encoding='utf-8')); print(json.dumps(search_directions(x['graph'],x['context']),ensure_ascii=False,indent=2))"
```

示例有三个合成解释：遗漏 `optimizer.step` 调用（`optimizer_step_omitted`）、学习率为零（`zero_lr`）、目标参数错误（`incorrect_targets`）。廉价 `update-count` 检查读取 `optimizer.step` 调用计数，可以区分“遗漏调用”与其余两个解释，仍无法区分后两者；调用计数不代表参数实际改变，零学习率仍可记录调用。较贵的 `target-identity` 检查可以区分“目标参数错误”与其余两个解释。两项分别覆盖两对，但互不包含，因此都保留在 frontier。较低成本不能补足缺失的判别覆盖。

将 `context.facts.protocol_matched.value` 改为 `false`，或移除该事实来源，判别对应转为未决，不应凭较低成本认定判别支配。同一范围下，若一项有效覆盖另一项全部解释对、其余比较条件也满足，才可能形成支配关系。

所有事实、预测、来源与成本都是标明身份的软件 fixture。运行只检查有限计算行为，不执行实验、调度任务或训练模型，也没有验证诊断准确率、科研收益、测量可实现性、因果识别或预测校准。设计背景见 [Advisor 判断图设计](advisor-graph-design.md)。

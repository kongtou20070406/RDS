# 参与 RDS 贡献

[English contribution guide](CONTRIBUTING.md) · **简体中文**

中文导引：先说明改动层次与所用版本，再按改动类型验证并提交 PR。形式声明遵循所选 adapter 的契约，分别报告 status 与 assurance。

日本語ガイド：fork と作業ブランチを作成し、変更に応じた確認を行って PR を送ってください。共通のコマンド、対応範囲、証拠の扱いは [日本語 README](README.ja-JP.md) と他の言語で揃えてください。

RDS 包含科研决策技能与有界标量参考内核。贡献应让具体的研究决定或程序行为更容易检查。保持改动聚焦，说明证据与适用边界。

从[文档索引](docs/README.zh-CN.md)、[科研工作流](docs/research-workflow.zh-CN.md)与[术语说明](docs/terminology.zh-CN.md)开始。涉及数学命题时，请阅读[形式验证指南](docs/formal-verification.zh-CN.md)。

## Fork、建分支、验证与提交 PR

先将 [kongtou20070406/RDS](https://github.com/kongtou20070406/RDS/fork) fork 到自己的账号。以下示例使用 PowerShell、Git，以及可选的已登录 GitHub CLI。将 `YOUR_GITHUB_NAME` 替换为你的账号名；本例演示修改 README。

```powershell
git clone https://github.com/YOUR_GITHUB_NAME/RDS.git
Set-Location RDS
git remote add upstream https://github.com/kongtou20070406/RDS.git
git fetch upstream
git switch -c docs/clarify-evidence upstream/main

# Edit the files, then perform the checks for your change type below.
python -B scripts/rds_cli.py --version
git diff --check
git diff -- README.md README.zh-CN.md README.ja-JP.md

git add README.md README.zh-CN.md README.ja-JP.md
git commit -m "docs: clarify evidence boundaries"
git push -u origin docs/clarify-evidence
gh pr create --repo kongtou20070406/RDS --base main --head YOUR_GITHUB_NAME:docs/clarify-evidence --web
```

根据实际改动选择分支名和暂存文件。没有 `gh` 时，推送后打开 fork 的 **Compare & pull request** 页面。PR 中说明问题、改动后的行为、已运行检查及仍存在的限制。

## 不同贡献所需的证据

| 改动 | 准入与证据要求 |
| --- | --- |
| 文档与翻译 | 与当前程序行为一致，链接指向已有文件。共享命令、版本事实、支持范围和证据边界应在 [README.md](README.md)、[README.zh-CN.md](README.zh-CN.md)、[README.ja-JP.md](README.ja-JP.md) 中保持一致。纯措辞修正可以只影响一种语言；说明其他版本为何无需修改。 |
| 有适用范围的规则与证据 | 提供适用范围、触发条件、竞争解释、区分性实验、主要指标门禁、证伪条件和注明日期的原始来源，参见 [judgment-graph.yaml](references/judgment-graph.yaml)。借鉴研究结果前检查更新的第一手证据。区分论文报告、当地探索性收益、确认收益与机制证据。科研策略提升需比较等总成本的研究轨迹。 |
| 内核、验证器或历史适配器 | 提供最小端到端复现、预期的前后行为，以及对应需求的相关测试。说明 adapter、版本/ref、支持输入和失败或不确定行为，并遵循下方形式声明清单。保留[执行契约](references/l3-state-machine.md)。历史改动须保留来源身份、范围、分页与明确失败；检索文本不产生新授权。遵循 [Obelisk bridge](references/obelisk.md)。 |
| 新研究案例 | 按[评测协议](benchmark/README.md)提供决策时可见的 prompt、来源与截止时间、评分标准和可复现检查。将后续结果与提案者输入分开，披露缺失的原始产物。标明合成标量输入和回顾性会话报告分数。开发中使用过的案例属于回归证据；独立评估需要此前未使用的案例、模型/技能版本记录、受控信息暴露与匹配预算。 |

运行验证的声明必须来自实际执行的检查和收据。不要添加 `manipulation_verified` 等自签字段让计划通过。通过门禁只说明对应程序约束满足，不会自动建立因果关系、外部训练性能或自主科研质量。哈希绑定产物，不认证其科学解释。

说明改动影响的是技能协议、runner、verifier，还是实验性策略工具。L1–L4 描述工作职责，不是行业标准，也不是可执行状态机的四个状态。面向 L4 的工具可以用普通回归测试验证；若声称它提升科研策略，则需要独立、前瞻、等总成本的研究轨迹比较，并保留负结果。

## 形式声明与发布范围

区分**目标 base ref 上已发布的行为**、**本 PR 新增的行为**与**开发候选**。[PR #2](https://github.com/kongtou20070406/RDS/pull/2) 中的 typed scalar certificate 工作尚未合并到 `main`。更通用的网络、矩阵和动力学后端，在接入公开接口、完成测试并形成文档前，仍是开发候选。不能把本地类、分支或测试输入写成已发布支持承诺。

涉及数学命题的贡献请提供：

- **声明与代码对应关系：**按所选 adapter 的 schema 提供精确命题、假设、参数、定义域或维度范围。`kind`、`statement`、`quantity`、`domain` 属于 typed scalar 契约，不是所有多维 spec 的强制字段。说明所声明模型或性质如何对应被检查的代码。
- **可公开复现：**最小公开或合成输入、准确命令、RDS 版本与 commit/ref、adapter/backend 版本，以及实际输出。接口若输出证书/checker 身份或产物哈希，也一并记录。仅检查独立声明、未执行实验时应明确说明。
- **结果：**存在准入与执行两个阶段时，分开报告。保留实际 `status`、`assurance`、reason，以及返回的反例或观测；不要从一个字段推断另一个。

| Status | 报告方式 |
| --- | --- |
| `PASS` | 声明的检查在文档所述假设与范围内通过。实际执行证据与科学确认仍需分别提供。 |
| `FAIL` | 声明的检查失败。说明违反的条件或反例，不要将其扩展为范围之外的科学反驳。 |
| `UNKNOWN` | checker 尚未建立结论，例如输入不支持、依赖缺失或求解未得结论。保留原因与实际门禁行为。 |

`assurance` 描述检查方式，与 status 分开。例如，`AST_ONLY` 是语法路径，`SYMBOLIC_CHECKED` 本身不等于独立核验的证明证书。证书声明须遵循对应文档的 checker 与绑定要求。这些标签都不能单独建立任务收益、因果机制支持或 L4 科研策略提升。

## 与改动相称的验证

小型文档或翻译改动只需检查本地链接、命令准确性、语言同步和 `git diff --check`。除非改动了需要验证的可执行示例或行为声明，否则无需运行完整测试。

程序改动应运行相关测试；已有检查不能覆盖变化的需求时，添加聚焦的回归。例如，历史适配器有以下定向检查：

```powershell
python -B -m unittest discover -s tests -p test_rds_l3.py -k obelisk -v
```

围绕修改的需求选择测试，也覆盖失败路径。跨越内核或评测协议的改动，请运行下方完整检查。普通标量执行使用标准库；完整测试与 benchmark 检查需要安装可选形式依赖：

```powershell
python -m pip install -r requirements-formal.txt
python -B -m unittest discover -s tests -v
python -B benchmark/run.py
python -B benchmark/redteam/runner.py
```

[CI](.github/workflows/test.yml) 当前在 Windows、Ubuntu 及 Python 3.11、3.13 上运行单元测试和历史回放。报告实际运行的命令与观察到的结果；说明跳过的检查。合成回归用于检查协议行为，不能替代独立科学评估或真实 GPU 实验。

共享命令和边界应在三版 README、中英贡献指南及受影响的指南之间同步。纯措辞修改可以不改变其他版本；在 PR 中简要说明即可。

## 公开证据与许可证

使用最小公开或合成输入。不要提交 `.rds/` 运行状态、私人会话导出或日志、私人数据集、凭据或 token。通过公开引用或脱敏来源身份保留必要出处，只分享有权公开的材料。

发布许可仍待确定：本仓库当前没有 `LICENSE` 文件，不应假定拥有复用许可。以后添加文件时，以仓库实际 `LICENSE` 为准；徽章、路线计划或其他项目的许可证不会建立本仓库的许可条款。

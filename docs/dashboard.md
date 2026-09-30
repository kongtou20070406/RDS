# RDS 本地科研工作台 / Local research dashboard

这个界面将 RDS 的实际项目记录导出成一个可离线打开的 HTML 文件。主线是自动化辅助人类科研：目标 → 调查证据 → 选择实验 → 执行与验收 → 复盘与接续。它提供中文/英文切换、浅色/深色主题和当前页记录搜索。

## 快速开始

在仓库目录运行，`--root` 指向已经初始化 RDS 的项目目录：

```powershell
python -B scripts/rds_dashboard.py --root C:\research\project --output dist\dashboard.html
```

用浏览器打开生成的 HTML。无需服务器、网络连接、CDN 或前端依赖。项目记录改变后重新执行导出，页面本身不会轮询或运行实验。

没有状态库时，生成的页面显示空状态，不会初始化 `.rds`、填入假数字或展示模拟曲线。用下面的命令查看明确标记的介绍示例；示例只有未检验假设，没有运行结果或虚构预算：

```powershell
python -B scripts/rds_dashboard.py --demo --output dist\dashboard-demo.html
```

## 可展示的记录

| 页面 | 实际来源 |
| --- | --- |
| 项目总览 | `state.contract`、`state.budget`、当前分支与记录数量 |
| 假设与证据 | `state.hypotheses`，分别显示 `task_gain`、`mechanism`、`search_policy` |
| 实验计划 | `state.plans`、运行状态、用途、数据分区、预算与验收 |
| 执行收据 | `receipts` 表中的运行状态、实际收益字段、计费、复用与绑定 |
| 研究分支 | `state.branches` 中的理由、干预维度、父分支和停滞计数 |
| 诊断与建议 | `--advisor` 导入的结构化 JSON；作为建议保留原字段 |
| 复盘记录 | `events` 表最近 100 条事件及事件总数 |
| 快速开始 | 科研流程、CLI 导航与能力边界 |

`project init/create/execute` 项目读取 `.rds/project.sqlite3` 的现有 `ProjectStore.snapshot`：展示原 `runs`、资源预算向量和实际收据；参考 runner 项目读取 `.rds/state.sqlite3`。两种账本不会混合，页面与导出 JSON 标明 `PROJECT` / `REFERENCE`；同时存在时优先项目账本。没有假设或研究分支的项目保持这些页面为空。

项目预算分别展示实测用量、预估记账、预留和剩余，保留原单位。收据里未知的 CPU/GPU 用量保持未知，墙钟不会换算成 CPU 时间。收据原件定位指向实际数据库的 `receipts` 表与 `run_id`，产物路径来自该收据，不生成额外收据镜像。

运行成功、任务收益和机制支持是不同判断。收据里的 `gain` 仅按原记录展示，不会自动升级成确认结论。未记录字段显示 `—` 或“未记录”；缺少预算时没有资源进度。Lean / mathlib 是适用于数学子任务的协作能力。

## 载入诊断

可以传入 advisor 返回的 JSON 对象或对象数组：

```powershell
python -B scripts/rds_dashboard.py --root C:\research\project --advisor advice.json --output dist\dashboard.html
```

例如：

```json
{
  "diagnosis": "竞争解释尚未被区分",
  "minimal_experiment": {"intervention": "固定预算，只改变目标机制", "stop_condition": "干预没有改变被测属性"},
  "evidence_refs": [{"source": "run-log.json", "observation": "当前两组属性相同"}],
  "next_if_positive": "保留机制分支",
  "next_if_negative": "修订机制解释"
}
```

这些内容不会写回账本，不会生成计划或执行收据。界面保留来源和不确定性；没有已有 seed 不稳定性的证据时，不主动要求多 seed 实验。

## 只读和验证

导出器用 Python 标准库。项目状态复用 `ProjectStore.snapshot(check_bindings=False)` 的只读接口；参考状态与近期事件通过 SQLite `mode=ro`、`query_only` 和短读事务读取。它不调用会写入或迁移状态的 `cmd_status`，不为显示重新 hash 输入文件，不读取执行 artifact 的二进制内容。输出必须是 `.rds` 目录以外的 `.html` 文件。HTML 和 CLI JSON 输出均为 UTF8，包括 Windows 中文路径。

所有数据以转义 JSON 嵌入，界面使用 `textContent` 渲染用户字段；没有将用户文本作为 HTML 的路径。页面 CSP 禁用网络连接。浏览器本地存储只保存语言和主题偏好。HTML 包含项目中的契约、收据和路径，分享该文件就会分享这些内容。

```powershell
python -B -m unittest discover -s tests -p test_rds_dashboard.py
```

测试覆盖真实 CPU 项目的成功与失败收据、未知资源与预估记账、两类账本选择、导出不 hash 输入或改变账本、UTF8 输出、无数据库时不创建状态、独立证据轴、脚本注入转义、示例不伪造结果，以及错误数据库与危险输出路径的拒绝。

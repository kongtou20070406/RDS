# 从实际文件进入 Advisor

这个小型本地样例检查 RDS 能否读取原文件、保留证据来源，并在缺失或身份冲突时要求补证据。数值是测试夹具，不是科研效果或 benchmark 分数；配置中的研究身份仍属于声明。

在仓库根目录执行：

```powershell
python -B examples/artifact-import/inspect.py
```

只导入文件的 CLI 命令需要明确项目根目录：

```powershell
python -B scripts/rds_cli.py --root examples/artifact-import artifacts import --manifest examples/artifact-import/manifest.json
```

脚本实际调用 `ingest_manifest` 和 `search_directions`，将完整结果写入 `development-check.json`。文件齐全时可解释记录；缺文件或运行身份冲突时产生只读查询。脚本不运行训练，也不改写四个原始输入。

`manifest.json` 固定源文件 SHA256，并为每项事实选择 JSON pointer、CSV 行列或明确日志键。`OBSERVED` 只说明读到了记录值；`DECLARED` 用于配置声明；有限均值、差值计算为 `DERIVED`；缺失、冲突和手写验证标记保留 `UNKNOWN`。这些字段不能让外部 JSON 自行获得导入器的内存来源身份。

外部运行收据使用 `run_id`、`run_status`、`protocol`、`resources`、`artifacts` 和去除自身字段后计算的 `sha256`。成本只读取终态、身份完整且哈希一致的收据，失败和诊断也计入；分配额度不冒充实测 CPU/GPU/API 开销。通过 `cost_bindings` 显式选择某次运行的一项资源，才能给指定行动提供历史成本；历史值不保证新运行开销。

对照复用还要求 code/config/data/split/init/seed/checkpoint/schedule/sample_work/numeric_protocol 都明确相同、运行 `SUCCEEDED`、输入绑定未变化、原产物哈希一致。相同 seed 单独不足以复用。此版本读取有文件大小和行数上限，大型产物应在后续工作中接入单独的有界验证方法。

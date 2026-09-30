<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/rds-hero-dark.svg">
  <img src=".github/assets/rds-hero-light.svg" alt="Research Direction Selector" width="100%">
</picture>

# Research Direction Selector

[![stars](https://img.shields.io/github/stars/kongtou20070406/research-direction-selector?style=flat-square)](https://github.com/kongtou20070406/research-direction-selector/stargazers)
[![version](https://img.shields.io/github/v/tag/kongtou20070406/research-direction-selector?label=version&style=flat-square)](https://github.com/kongtou20070406/research-direction-selector/releases)
[![license](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![tests](https://img.shields.io/badge/tests-passing-brightgreen.svg?style=flat-square)](tests/)

Turn a research question, existing evidence, and a limited budget into a decision-changing experiment -- driven by your agent, verified by your kernel.

**English** · [简体中文](README.zh-CN.md) · [日本語](README.ja-JP.md)

</div>

<br />

## Two sides of the research loop

RDS has two sides that share one research state:

**Agent side** — the `research-direction-selector` agent skill (`SKILL.md`) teaches coding agents (Codex, Claude Code, etc.) how to understand research goals, frame falsifiable hypotheses, design fair controls, and turn gate feedback into structured next-step plans. The agent converses in plain language and plans experiments.

**Kernel side** — the local reference engine (`scripts/rds_cli.py`) manages transactional SQLite budgets, AST and Lean4-inspired formal gates, baseline caching, telemetry compression, and an evidence-grounded advisor.

Both read from and write to the same `.rds/` state store and `references/judgment-graph.yaml` causal rules.

---

## 5 Core Functional Components

按职责拆分，RDS 严格归纳为 **5 个关键组件**（3 个基础组件 + 2 个增强组件）：

| 关键组件 | 主要职责 | 它回答的问题 |
| :--- | :--- | :--- |
| **① 科研规程：Skill** | 引导 AI 理解目标、提出假说、设计对照、组织下一步计划 | **这轮研究应该怎样思考和推进？** |
| **② 执行与验收内核** | 管理实验状态、调用运行工具、收集结果，执行预算和证据检查 | **实验怎么跑？结果符合哪些预定条件？** |
| **③ 研究状态与记忆** | 保存目标、配置、结果、失败条件和决策依据，支持跨会话恢复 | **我们已经做过什么、知道什么，为什么走到这里？** |
| **④ Advisor 建议引擎** | 根据当前观测、历史经验和规则，提出诊断线索与候选行动 | **现在遇到这个情况，下一步可以怎么做？** |
| **⑤ 自改进模块：RSI** | 提出规则或策略修改，经过评测后决定是否采用 | **RDS 自己哪些判断和做法需要改进？** |

```mermaid
flowchart TD
    subgraph 基础闭环
        S["① Skill (科研规程)"] --> K["② 执行与验收内核"]
        K --> M["③ 研究状态与记忆"]
        M --> S
    end
    subgraph 增强引擎
        M -. 历史记录与规则图 .-> A["④ Advisor 建议引擎"]
        A -. 候选探索建议 .-> S
        M -. 失败记录与反例 .-> R["⑤ RSI 自改进模块"]
        R -. 改进规则与策略 .-> M
    end
```

### 最容易混淆的是这三组关系

- **Skill 和 Advisor：** Skill 规定研究的基本做法，例如要求公平对照、区分指标与机制；Advisor 针对当前情况提供具体建议，例如先检查训练是否充分，或尝试另一条候选路线。
- **记忆和 Advisor：** 记忆保存“发生过什么、有什么依据”；Advisor 利用这些记录判断“接下来值得检查什么”。
- **Advisor 和 RSI：** Advisor 帮你改进正在研究的模型或实验；RSI 尝试改进 **RDS 自身的规则和决策策略**。

### 其他名字算在哪里？

- **预算控制、基线缓存、日志提取、探针、形式化检查**：主要属于 **② 执行与验收内核** 的底层子模块。
- **`.rds/` 项目记录、Obelisk 历史接口、判断图谱（`judgment-graph.yaml`）**：主要归入 **③ 研究状态与记忆**，供其他组件读取。
- **L1／L4**：是讨论中的能力层级，不能另算组件。

**前 3 个组件支撑基本科研闭环；Advisor 增加主动建议；RSI 增加对工具自身的改进。** 最清晰的系统构成是：**3 个基础组件＋2 个增强组件，共 5 个。**

---

## Skill: agent-first research guidance

You can use RDS in your agent like:

```text
/rds 指标不再提升了，用现有日志区分训练问题和容量限制
/rds 这两个消融同时改了好几件事，设计一个最小公平比较来区分解释
/rds 继续这个项目，先检查剩余预算和已完成运行，再提出新工作
/rds 帮我评估当前的收缩性假说，并生成形式化验证证明
```

### Install

#### Let your agent install it (recommended)

Give this setup instruction directly to Codex, Claude Code, or any agent with shell access:

```text
Install Research Direction Selector from
https://github.com/kongtou20070406/research-direction-selector
as the research-direction-selector agent Skill.
Keep the whole repository, including scripts, references, and examples.
Use this project's .agents/skills directory and verify the CLI version.
Then read SKILL.md and help me start from my actual research question.
```

#### Manual install

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE/.agents/skills" -Force | Out-Null
git clone https://github.com/kongtou20070406/research-direction-selector.git "$env:USERPROFILE/.agents/skills/research-direction-selector"
```

---

## Deterministic Execution & Acceptance Kernel

The kernel (`scripts/rds_cli.py`) runs on pure Python 3.11+ standard library:

```powershell
# 1. Initialize research state from contract
python -B scripts/rds_cli.py --root ./my-project project init --contract ./my-project/contract.json

# 2. Create and execute plan with transactional budget
python -B scripts/rds_cli.py --root ./my-project project create --manifest ./my-project/treatment.json
python -B scripts/rds_cli.py --root ./my-project project execute --id treatment

# 3. Check costs and status
python -B scripts/rds_cli.py --root ./my-project project costs
python -B scripts/rds_cli.py --root ./my-project project status
```

---

## Lean4-style Declarative Formal Verification

`scripts/rds_probe.py` unifies mathematical bounds and causal rules into a modular **Tactic Proof Engine** inspired by Lean 4 / Mathlib:

- **FormalRuleRegistry** — Pre-loads 28 rules & mathematical lemmas (`lemma.gershgorin`, `lemma.spectral_radius`, `lemma.residual_contraction`, `lemma.scale_invariance`, `lemma.parameter_box`).
- **Tactic Proof Dispatcher** — Discharges obligations declaratively with tactics:
  `tactics: [gershgorin, spectral_radius, lipschitz_scaling, scale_invariance, interval_check, linarith, by_rule, lean4]`
- **Native Lean 4 & 2.0s Circuit Breaker** — Binds to local `lean.exe` when raw Lean source is provided; bounded timeouts prevent solver deadlocks.

```python
from rds_probe import LeanFormalEngine

cert = LeanFormalEngine({
    "kind": "theorem",
    "theorem": "contraction_boundary",
    "tactics": [
        {"tactic": "gershgorin", "matrix": [[0.4, 0.1], [0.1, 0.4]]},
        {"tactic": "linarith", "claim": "0.5 < 1.0"}
    ]
}).verify()
# Output: {"status": "PASS", "assurance": "LEAN_TACTIC_PROVED", "proof_trace": [...]}
```

---

## Advisor: Evidence-Grounded Suggestions

`scripts/rds_advisor.py` replaces arbitrary heuristics with causal rigor:
- **Refuses Ungrounded Pseudo-Diagnoses** — Single loss values never trigger "overfitting" or "underfitting" verdicts; requires paired train/validation curves with declared `trend_tolerance`.
- **Localization-First Anomaly Handling** — On NaN/Inf, guides root-cause localization of the first nonfinite tensor and FP32 replaying rather than blindly masking issues with `eps`.
- **Topological Candidate Generation** — Traverses the causal judgment graph to recommend Pareto-optimal, orthogonal exploration branches.

```powershell
python -B scripts/rds_cli.py --root ./my-project advise
```

---

## Obelisk History Integration

RDS connects with [Obelisk](https://github.com/tommy0103/obelisk) to retrieve past session history without duplicating vector stores:

```powershell
python -B scripts/rds_cli.py history prepare --project-path 'C:\research\project' --terms 'C7' --output 'query.mjs'
python -B scripts/rds_cli.py history query --query 'query.mjs'
```

---

## Verification & Tests

```powershell
# Run the complete test suite
python -m unittest discover -s tests -p "test_*.py" -v

# Run historical case replays
python benchmark/run.py

# Run adversarial red-team stress tests
python benchmark/redteam/runner.py
```

---

## Repository layout

```text
SKILL.md                         Agent collaboration protocol (Component ①)
scripts/rds_cli.py               Execution kernel & transactional budget ledger (Component ②)
scripts/rds_probe.py             AST sandbox & Lean4 tactic proof engine (Component ②)
scripts/rds_compress.py          Telemetry log compression & spike monitor (Component ②)
references/judgment-graph.yaml   28-node causal judgment graph & lemmas (Component ③)
references/                      State machine contracts & RSI evidence (Component ③)
scripts/rds_obelisk.py           Obelisk session history bridge (Component ③)
scripts/rds_advisor.py           Evidence-grounded Advisor engine (Component ④)
scripts/rds_meta.py              RSI rule reflection & graph mutation (Component ⑤)
scripts/rds_adversary.py         RSI adversarial fuzzing & auto-repair (Component ⑤)
benchmark/                       Historical decision packets & red-team benchmarks
tests/                           Full regression test suite
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/rds-hero-dark.svg">
  <img src=".github/assets/rds-hero-light.svg" alt="Research Direction Selector" width="100%">
</picture>

# Research Direction Selector

[![stars](https://img.shields.io/github/stars/kongtou20070406/research-direction-selector?style=flat-square)](https://github.com/kongtou20070406/research-direction-selector/stargazers)
[![version](https://img.shields.io/github/v/tag/kongtou20070406/research-direction-selector?label=version&style=flat-square)](https://github.com/kongtou20070406/research-direction-selector/releases)
[![license](https://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat-square)](LICENSE)
[![tests](https://github.com/kongtou20070406/research-direction-selector/actions/workflows/test.yml/badge.svg)](https://github.com/kongtou20070406/research-direction-selector/actions/workflows/test.yml)

研究の問い、既存の証拠、限られた予算から、判断を変える実験へ。あなたの Agent が進め、ローカルカーネルが検証します。

[English](README.md) · [简体中文](README.zh-CN.md) · **日本語**

</div>

<br />

## 研究ループの二つの側面

RDS の二つの側面は、同じ研究状態を共有します。

**Agent 側** — `research-direction-selector` Agent Skill（`SKILL.md`）は、コーディング Agent（Codex、Claude Code など）に、研究目標の理解、反証可能な仮説の設定、公平な対照の設計、ゲートのフィードバックを構造化した次の計画に変える方法を教えます。Agent は自然言語で対話し、実験を計画します。

**カーネル側** — ローカル参照エンジン（`scripts/rds_cli.py`）は、トランザクションで管理する SQLite 予算、AST と範囲を限定した宣言型の形式ゲート、ベースラインのキャッシュ、テレメトリの圧縮、証拠に基づく Advisor を管理します。

両者は同じ `.rds/` 状態ストアと `references/judgment-graph.yaml` の因果ルールを読み書きします。

---

## 5 つの主要機能コンポーネント

責務ごとに整理すると、RDS は **5 つの主要コンポーネント**で構成されます。基盤となる 3 つと、機能を拡張する 2 つです。

| 主要コンポーネント | 主な責務 | 答える問い |
| :--- | :--- | :--- |
| **① 研究プロトコル：Skill** | Agent に目標の理解、仮説の設定、対照の設計、次の計画を導く | **この研究をどう考え、進めるべきか？** |
| **② 実行・受け入れカーネル** | 実験状態の管理、実行ツールの呼び出し、結果の収集、予算と証拠の検査 | **実験をどう実行するか？結果は事前に定めたどの条件を満たすか？** |
| **③ 研究状態と記憶** | 目標、設定、結果、失敗条件、判断の証拠をセッションをまたいで保持する | **何を実施し、何がわかり、なぜこの地点に至ったか？** |
| **④ Advisor エンジン** | 観測、履歴、ルールから診断の手がかりと行動候補を提案する | **現在の状況で、次に何を試せるか？** |
| **⑤ 自己改善モジュール：RSI** | ルールや方針の変更を提案し、採用前に評価する | **RDS 自身のどの判断や実践を改善すべきか？** |

```mermaid
flowchart TD
    subgraph Foundational_loop[基盤となるループ]
        S["① Skill（研究プロトコル）"] --> K["② 実行・受け入れカーネル"]
        K --> M["③ 研究状態と記憶"]
        M --> S
    end
    subgraph Enhancement_engines[拡張エンジン]
        M -. 履歴とルールグラフ .-> A["④ Advisor エンジン"]
        A -. 探索候補の提案 .-> S
        M -. 失敗記録と反例 .-> R["⑤ RSI 自己改善モジュール"]
        R -. 改訂したルールと方針 .-> M
    end
```

### 混同しやすい三つの関係

- **Skill と Advisor：** Skill は公平な対照や指標と機構の区別など、研究の実践を定めます。Advisor は、学習が十分か確認する、別の候補を試すなど、現在の状況に応じた行動を提案します。
- **記憶と Advisor：** 記憶は何が起きたかとその証拠を保持します。Advisor はその記録を使い、次に何を確認する価値があるかを提案します。
- **Advisor と RSI：** Advisor は研究対象のモデルや実験の改善を支援します。RSI は **RDS 自身のルールと判断方針**の改善を試みます。

### その他の名称はどこに属するか？

- **予算管理、ベースラインのキャッシュ、ログ抽出、プローブ、形式検査**は、主に **② 実行・受け入れカーネル**の内部モジュールに属します。
- **`.rds/` のプロジェクト記録、Obelisk の履歴インターフェース、判断グラフ（`judgment-graph.yaml`）**は、主に **③ 研究状態と記憶**に属し、他のコンポーネントから参照されます。
- **L1–L5** は研究フレームワークで議論する[能力レベル](docs/research-autonomy.md)であり、追加のコンポーネントではありません。

**最初の 3 つが基本的な研究ループを支え、Advisor は能動的な提案を、RSI はツール自体の改善を加えます。** システムは **基盤 3 つ + 拡張 2 つ、計 5 つのコンポーネント**で構成されます。

---

## Skill：Agent を入口とする研究支援

Agent で、次のように RDS を使えます。

```text
RDS を使って、指標が改善しなくなった理由を調べてください。既存のログから学習の問題と容量の限界を区別してください。
RDS を使って、複数の要素を同時に変えた二つのアブレーションを検討してください。異なる説明を区別できる最小の公平な比較を設計してください。
RDS を使って、このプロジェクトを続けてください。新しい作業を提案する前に、残りの予算と完了した実行を確認してください。
RDS を使って、現在の収縮性の仮説を評価し、対応する形式的な命題について検査済みの証拠を生成してください。
```

### インストール

#### Agent にインストールしてもらう（推奨）

端末にアクセスできる Codex、Claude Code、その他の Agent に、次の設定指示を直接渡してください。

```text
次のリポジトリから Research Direction Selector をインストールしてください。
https://github.com/kongtou20070406/research-direction-selector
research-direction-selector Agent Skill として配置してください。
scripts、references、examples を含むリポジトリ全体を保持してください。
現在のプロジェクトの .agents/skills ディレクトリを使い、CLI のバージョンを確認してください。
その後 SKILL.md を読み、私の実際の研究課題から協働を始めてください。
```

#### 手動インストール

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE/.agents/skills" -Force | Out-Null
git clone https://github.com/kongtou20070406/research-direction-selector.git "$env:USERPROFILE/.agents/skills/research-direction-selector"
```

---

## 決定的な実行・受け入れカーネル

カーネル（`scripts/rds_cli.py`）は Python 3.11+ の標準ライブラリのみで動作します。

リポジトリのルートから、新しい空の `./my-project` ディレクトリを使って、以下の CPU デモを実行してください。準備ステップは、対照群と処置群の両方について、実ファイルに結び付いた契約とマニフェストを作成します。このデモは科学的な確認を示すものではありません。実行とレシートの詳細は[プロジェクト実行器の例](examples/project-runner/README.md)を参照してください。

```powershell
# 0. 例の契約、データ、マニフェストを準備
python -B examples/project-runner/prepare.py --root ./my-project

# 1. 契約から研究状態を初期化
python -B scripts/rds_cli.py --root ./my-project project init --contract ./my-project/contract.json

# 2. トランザクションによる予算管理のもとで両群を作成・実行
python -B scripts/rds_cli.py --root ./my-project project create --manifest ./my-project/control.json
python -B scripts/rds_cli.py --root ./my-project project execute --id control
python -B scripts/rds_cli.py --root ./my-project project create --manifest ./my-project/treatment.json
python -B scripts/rds_cli.py --root ./my-project project execute --id treatment

# 3. コストと状態を確認
python -B scripts/rds_cli.py --root ./my-project project costs
python -B scripts/rds_cli.py --root ./my-project project status
```

カーネルは記録された台帳状態からキャンペーンの次の一手を導出します。いつでも
`python -B scripts/rds_cli.py --root ./my-project project next` を実行すると、
今すべき一つのアクション（登録・実行・復旧・比較・決定の記録）とその実行可能な
コマンドが出力されます。エージェントはこの手順を繰り返すだけでループ全体を
推進でき、上のコマンド列を暗記する必要はありません。

---

## Lean4 スタイルの宣言型形式検証

`scripts/rds_verify.py` は、有限の宣言的命題、登録済みの領域ルール、独立した証明書検査を提供します。範囲を限定したタクティックインターフェースは Lean スタイルの証明ワークフローに着想を得ています。汎用の Lean や Mathlib の証明器ではありません。

- **信頼するルールの登録簿** — 有理数スカラーの閾値、アフィン力学、適用範囲を定めた行列スペクトル検査、対応する Linear/ReLU の性質、具体的なテンソル、正確な単位円板の幾何被覆、ネイティブ Lean の証明義務（閉じた有理数関係と範囲を限定した統計義務）を扱う 15 個の原子的数学ルールを登録しています。有限の定理モジュールはこれらの命題を組み合わせます。この登録簿は、23 ノードの方法論判断グラフとは別です。
- **範囲を限定したタクティックのディスパッチャー** — `LeanFormalEngine().verify(spec, tactics)` は `rule`、`gershgorin`、`spectral_radius`、`scale_invariance`、`interval`、`lean4` を受け付けます。タクティックは互換性のある登録済み検査を選び、未対応または結論を出せない入力には `UNKNOWN` を返します。
- **ネイティブ Lean 4 アダプター** — ネイティブ Lean 実行ファイルを設定すると、固定テンプレートの閉じた有理数の `eq`、`lt`、`le` 証明義務は、ネイティブ再検査と公理が空であることの監査後に `LEAN_KERNEL_CHECKED` を受け取ります。任意の Lean ソースやユーザーのタクティックは受け付けません。

リポジトリのルートから、次の Python 例を実行してください。

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from rds_verify import LeanFormalEngine, check_certificate

spec = json.loads(Path("examples/formal/theorem_module.json").read_text(encoding="utf-8"))
result = LeanFormalEngine().verify(spec, tactics=("rule",))
assert result["status"] == "PASS"
assert result["assurance"] == "CERTIFICATE_CHECKED"
assert check_certificate(spec, result["certificate"])
```

同じ宣言を CLI から検証することもできます。

```powershell
python -B scripts/rds_cli.py --root . formal verify --spec examples/formal/theorem_module.json --output proof.json --no-cache
python -B scripts/rds_cli.py --root . formal check --spec examples/formal/theorem_module.json --certificate proof.json
```

検査済みの数学的命題だけでは、タスク性能、因果的な切り分け、実際に実行された学習グラフとの対応は示せません。スキーマ、保証レベルのラベル、対応範囲は[形式検証](docs/formal-verification.md)を参照してください。

---

## Advisor：証拠に基づく提案

`scripts/rds_advisor.py` は記録された証拠と方法論グラフから、次の手順を提案します。
- **診断の前に証拠を確認** — 単一の loss 値では過学習や学習不足の診断を支えられません。対になった曲線や比較可能な観測が、説明候補の背景を与えます。
- **介入の前に発生箇所を特定** — NaN/Inf に対しては、数値的な保護策を変える前に、最初の非有限値を特定し、精度や更新経路を確認する提案を優先します。
- **グラフに基づく候補** — 方法論ルールが診断の手がかりと探索候補を整理します。その順位付けは、因果効果、パレート最適性、実験がすべてのルール義務を満たすことを証明しません。

```powershell
python -B scripts/rds_cli.py --root ./my-project advise
```

---

## Obelisk 履歴との連携

推奨する任意の記憶拡張：[Obelisk](https://github.com/tommy0103/obelisk)。軽量な決定グラフは研究の堂々巡りを防ぎ、過去のセッションの正確な情報が必要なときは Obelisk を使います。履歴ストアを重複して構築する必要はありません。

```powershell
python -B scripts/rds_cli.py history prepare --project-path 'C:\research\project' --terms 'C7' --output 'C:\queries\obq-c7-unique-token.mjs'
python -B scripts/rds_cli.py history query --query 'C:\queries\obq-c7-unique-token.mjs'
```

---

## 検証とテスト

```powershell
# 全テストスイートを実行
python -m unittest discover -s tests -p "test_*.py" -v

# 過去のケースをリプレイ
python benchmark/run.py

# 対抗的なレッドチームのストレステストを実行
python benchmark/redteam/runner.py
```

---

## リポジトリ構成

```text
SKILL.md                         Agent の協働プロトコル（コンポーネント ①）
scripts/rds_cli.py               実行カーネルとトランザクション予算台帳（コンポーネント ②）
scripts/rds_probe.py             制限された AST とスカラーの形式的受け入れ検査（コンポーネント ②）
scripts/rds_verify.py            宣言型ルール、限定タクティック、証明書検査（コンポーネント ②）
scripts/rds_compress.py          テレメトリログ圧縮とスパイク監視（コンポーネント ②）
references/judgment-graph.yaml   23 ノードの方法論判断グラフ（コンポーネント ③）
references/                      状態機械の契約と RSI の証拠（コンポーネント ③）
scripts/rds_obelisk.py           Obelisk セッション履歴ブリッジ（コンポーネント ③）
scripts/rds_advisor.py           証拠に基づく Advisor エンジン（コンポーネント ④）
scripts/rds_meta.py              RSI のルール振り返りとグラフ変更（コンポーネント ⑤）
scripts/rds_adversary.py         RSI の対抗的な変種と評価候補（コンポーネント ⑤）
benchmark/                       過去の判断パケットとレッドチームベンチマーク
tests/                           全回帰テストスイート
```

---

## Star の推移

<a href="https://www.star-history.com/#kongtou20070406/research-direction-selector&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=kongtou20070406/research-direction-selector&type=Date&theme=dark">
    <img alt="Star の推移" src="https://api.star-history.com/svg?repos=kongtou20070406/research-direction-selector&type=Date" width="600">
  </picture>
</a>

このチャートは公開の Star History サービスから読み込まれ、GitHub star の推移のみを反映します。研究上の意味はありません。

---

## ライセンス

Apache License 2.0。詳細は [LICENSE](LICENSE) を参照してください。

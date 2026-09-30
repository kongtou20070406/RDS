# Contributing to RDS

**English** · [简体中文贡献指南](CONTRIBUTING.zh-CN.md)

中文导引：完整流程见[中文贡献指南](CONTRIBUTING.zh-CN.md)。先说明改动层次与所用版本；形式声明遵循所选 adapter 的契约，分别报告 status 与 assurance。

日本語ガイド：fork と作業ブランチを作成し、変更に応じた確認を行って PR を送ってください。共通のコマンド、対応範囲、証拠の扱いは [日本語 README](README.ja-JP.md) と他の言語で揃えてください。

RDS combines a research decision skill with a bounded scalar reference kernel. Contributions should make a concrete decision or executable behavior easier to inspect. Keep the change focused and describe its evidence and limits.

Start with the [documentation index](docs/README.md), [research workflow](docs/research-workflow.md), and [terminology](docs/terminology.md). For mathematical claims, read the [formal verification guide](docs/formal-verification.md).

## Fork, branch, validate, and open a PR

Fork [kongtou20070406/research-direction-selector](https://github.com/kongtou20070406/research-direction-selector/fork) into your account. The example below uses PowerShell, Git, and an optional authenticated GitHub CLI. Replace `YOUR_GITHUB_NAME` with your account name, then edit the README files for this example.

```powershell
git clone https://github.com/YOUR_GITHUB_NAME/research-direction-selector.git
Set-Location research-direction-selector
git remote add upstream https://github.com/kongtou20070406/research-direction-selector.git
git fetch upstream
git switch -c docs/clarify-evidence upstream/main

# Edit the files, then perform the checks for your change type below.
python -B scripts/rds_cli.py --version
git diff --check
git diff -- README.md README.zh-CN.md README.ja-JP.md

git add README.md README.zh-CN.md README.ja-JP.md
git commit -m "docs: clarify evidence boundaries"
git push -u origin docs/clarify-evidence
gh pr create --repo kongtou20070406/research-direction-selector --base main --head YOUR_GITHUB_NAME:docs/clarify-evidence --web
```

Choose a branch name and staged files that fit your actual change. Without `gh`, open the fork's **Compare & pull request** page after pushing. State the problem, resulting behavior, checks run, and remaining limits in the PR.

## What a contribution needs

| Change | Admission and evidence |
| --- | --- |
| Documentation and translations | Match the current executable behavior and link to existing files. Keep shared commands, version facts, supported scope, and evidence boundaries consistent across [README.md](README.md), [README.zh-CN.md](README.zh-CN.md), and [README.ja-JP.md](README.ja-JP.md). A wording-only correction may affect one language; say when the others need no change. |
| Scoped rules and evidence | Include scope, trigger, competing explanations, a discriminating test, primary metric gate, falsifier, and dated original sources; see [judgment-graph.yaml](references/judgment-graph.yaml). Check newer primary evidence before borrowing a research result. Separate paper-reported results, local exploratory gains, confirmed gains, and mechanism evidence. A search-policy claim needs research trajectories compared at equal total cost. |
| Kernel, verifier, or history adapter | Give a minimal end-to-end reproducer and expected before/after behavior, plus relevant tests tied to the stated requirement. Specify the adapter, version/ref, supported inputs, and failure or inconclusive behavior; follow the formal-claim checklist below. Preserve the [execution contract](references/l3-state-machine.md). History changes must preserve source identity, scope, pagination, and explicit failures; retrieved text grants no new authorization. Follow the [Obelisk bridge](references/obelisk.md). |
| New research cases | Provide the decision-time prompt, source provenance and cutoff, rubric, and reproducible checks under the [benchmark protocol](benchmark/README.md). Keep later outcomes separate from proposer inputs and disclose missing original artifacts. Label synthetic scalar fixtures and retrospective session-reported scores. Cases used during development are regression evidence; an independent evaluation needs previously unused cases, recorded model/skill versions, controlled information exposure, and matched budgets. |

Runtime-verified claims must come from the executed checks and their receipts. Do not add self-signed fields such as `manipulation_verified` to make a plan pass. Passing a gate establishes its stated program constraint; it does not by itself establish causality, external training performance, or autonomous research quality. Hashes bind artifacts and do not certify their scientific interpretation.

Identify whether the change affects the skill protocol, runner, verifier, or an experimental policy tool. RDS adopts Kramer et al. (2026)'s original L0–L5 scientific-discovery framework; see [autonomy scope](docs/research-autonomy.md). Existing L3 runner identifiers and the former L4-RSI label are historical engineering names, not claims of external levels. Restrict an autonomy claim to the demonstrated task and automation scope. RSI improvement is a separate claim requiring independent, prospective trajectories on unused cases at equal total cost, including negative results.

## Formal claims and release scope

Distinguish **released behavior on the target base ref**, **behavior introduced by this PR**, and **development candidates**. Current `main` includes [PR #2](https://github.com/kongtou20070406/research-direction-selector/pull/2): typed scalar certificates, registered rational Linear/ReLU bounds, margins and positive-scale equivariance, scoped affine contraction/fixed-point and spectral checks, concrete tensor checks, and a narrow configured native Lean interface. General networks, symbolic tensors and arbitrary dynamics remain outside that support; use the [backend scope](docs/formal-verification.md) and installed registrations. Do not turn a local class, branch, or fixture into a released support promise.

For a contribution involving a mathematical claim, provide:

- **Declaration and binding:** the exact proposition, assumptions, parameters, and domain or dimensional scope, using the selected adapter's schema. `kind`, `statement`, `quantity`, and `domain` belong to the typed scalar contract; they are not mandatory fields for every multidimensional specification. Explain how the declared model or property corresponds to the code being checked.
- **Public reproduction:** a minimal public or synthetic input, exact commands, RDS version and commit/ref, adapter/backend versions, and the observed output. Include certificate/checker identity or artifact hashes when the interface emits them. State when only a standalone declaration was checked and no experiment was executed.
- **Results:** report admission and execution separately when both exist. Copy the actual `status`, `assurance`, reason, and any returned counterexample or observation; do not infer one field from another.

| Status | How to report it |
| --- | --- |
| `PASS` | The declared check passed within its documented assumptions and scope. Execution evidence and scientific confirmation remain separate requirements. |
| `FAIL` | The declared check failed. State the violated condition or counterexample; do not generalize it into a scientific refutation beyond that scope. |
| `UNKNOWN` | The checker did not establish a result, for example because the input is unsupported, a dependency is absent, or solving is inconclusive. Preserve the reason and actual gate behavior. |

`assurance` describes the kind of checking, independently of status. For example, `AST_ONLY` is a syntax path, and `SYMBOLIC_CHECKED` alone is not an independently checked proof certificate. A certificate claim must follow its documented checker and binding requirements. None of these labels establishes task gain, causal mechanism support, a scientific-discovery autonomy level, or RSI policy improvement.

## Validation proportional to the change

For a small documentation or translation change, check local links, command accuracy, language synchronization, and `git diff --check`. A full test run is unnecessary unless the edit changes an executable example or behavior claim that needs verification.

For executable changes, run the relevant tests. Add a focused regression when existing checks do not cover the changed requirement. For example, the history adapter has a focused check:

```powershell
python -B -m unittest discover -s tests -p test_rds_l3.py -k obelisk -v
```

Select tests for the requirement you changed, including the failure path. For changes spanning the kernel or evaluation protocol, run the full checks below. Ordinary scalar execution uses the standard library, but the full tests and benchmark checks require the optional formal dependencies:

```powershell
python -m pip install -r requirements-formal.txt
python -B -m unittest discover -s tests -v
python -B benchmark/run.py
python -B benchmark/redteam/runner.py
```

[CI](.github/workflows/test.yml) currently runs the unit suite and historical replay on Windows and Ubuntu with Python 3.11 and 3.13. Report the commands and outcomes you actually observed; explain skipped checks. Synthetic regressions test protocol behavior and do not substitute for an independent scientific evaluation or a real GPU experiment.

Synchronize shared commands and boundaries across the three READMEs, the English/Chinese contribution guides, and any guide affected by the change. Pure wording fixes may leave other versions unchanged; explain that briefly in the PR.

## Public evidence and licensing

Use minimal public or synthetic fixtures. Do not commit `.rds/` runtime state, private session exports or logs, private datasets, credentials, or tokens. Preserve useful provenance with public references or sanitized source identities, and only share material you have permission to publish.

Distribution licensing is pending: this repository currently has no `LICENSE` file. Do not assume reuse permission. Check the repository's actual `LICENSE` if one is added; a badge, roadmap, or license in another project does not establish terms here.

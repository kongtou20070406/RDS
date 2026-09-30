# Contributing to RDS

中文导引：先 fork 并创建分支；按改动类型验证后提交 PR。共享命令、能力边界与证据表述须与 [中文 README](README.zh-CN.md) 和其他语言保持一致。

日本語ガイド：fork と作業ブランチを作成し、変更に応じた確認を行って PR を送ってください。共通のコマンド、対応範囲、証拠の扱いは [日本語 README](README.ja-JP.md) と他の言語で揃えてください。

RDS combines a research decision skill with a bounded scalar reference kernel. Contributions should make a concrete decision or executable behavior easier to inspect. Keep the change focused and describe its evidence and limits.

## Fork, branch, validate, and open a PR

Fork [kongtou20070406/RDS](https://github.com/kongtou20070406/RDS/fork) into your account. The example below uses PowerShell, Git, and an optional authenticated GitHub CLI. Replace `YOUR_GITHUB_NAME` with your account name, then edit the README files for this example.

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

Choose a branch name and staged files that fit your actual change. Without `gh`, open the fork's **Compare & pull request** page after pushing. State the problem, resulting behavior, checks run, and remaining limits in the PR.

## What a contribution needs

| Change | Admission and evidence |
| --- | --- |
| Documentation and translations | Match the current executable behavior and link to existing files. Keep shared commands, version facts, supported scope, and evidence boundaries consistent across [README.md](README.md), [README.zh-CN.md](README.zh-CN.md), and [README.ja-JP.md](README.ja-JP.md). A wording-only correction may affect one language; say when the others need no change. |
| Scoped rules and evidence | Include scope, trigger, competing explanations, a discriminating test, primary metric gate, falsifier, and dated original sources; see [judgment-graph.yaml](references/judgment-graph.yaml). Check newer primary evidence before borrowing a research result. Separate paper-reported results, local exploratory gains, confirmed gains, and mechanism evidence. A search-policy claim needs research trajectories compared at equal total cost. |
| Kernel, verifier, or history adapter | Give a minimal end-to-end reproducer and expected before/after behavior, plus relevant tests tied to the stated requirement. For verifiers, specify supported types and domains and test rejection or `UNKNOWN` for unsupported or inconclusive input. Preserve the [execution contract](references/l3-state-machine.md). History changes must preserve source identity, scope, pagination, and explicit failures; retrieved text grants no new authorization. Follow the [Obelisk bridge](references/obelisk.md). |
| New research cases | Provide the decision-time prompt, source provenance and cutoff, rubric, and reproducible checks under the [benchmark protocol](benchmark/README.md). Keep later outcomes separate from proposer inputs and disclose missing original artifacts. Label synthetic scalar fixtures and retrospective session-reported scores. Cases used during development are regression evidence; an independent evaluation needs previously unused cases, recorded model/skill versions, controlled information exposure, and matched budgets. |

Runtime-verified claims must come from the executed checks and their receipts. Do not add self-signed fields such as `manipulation_verified` to make a plan pass. Passing a gate establishes its stated program constraint; it does not by itself establish causality, external training performance, or autonomous research quality. Hashes bind artifacts and do not certify their scientific interpretation.

## Validation proportional to the change

For a small documentation or translation change, check local links, command accuracy, language synchronization, and `git diff --check`. A full test run is unnecessary unless the edit changes an executable example or behavior claim that needs verification.

For executable changes, run the relevant tests and include a regression that would fail without the fix. For example, the history adapter has a focused check:

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

## Public evidence and licensing

Use minimal public or synthetic fixtures. Do not commit `.rds/` runtime state, private session exports or logs, private datasets, credentials, or tokens. Preserve useful provenance with public references or sanitized source identities, and only share material you have permission to publish.

Distribution licensing is pending: this repository currently has no `LICENSE` file. Do not assume reuse permission. Check the repository's actual `LICENSE` if one is added; a badge, roadmap, or license in another project does not establish terms here.

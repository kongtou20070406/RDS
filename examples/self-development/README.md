# Develop RDS with RDS

This CPU example uses the actual CLI and project runner to check RDS's development changes. It copies public repository inputs to a new workspace outside the checkout, locks the copied program and tests, reserves a budget, executes the checks and retains their original output.

From the repository root:

```powershell
python -B examples/self-development/run.py --workspace C:\rds-development\iteration-1
```

Add `--all-tests` to run every public test module. The copied workspace includes the benchmark support package required by the full suite; its test inputs are bound at admission along with the program.

Choose a new, empty directory outside the repository. The example rejects an existing or nested directory. It uses the current Python executable and standard-library process runner; the selected tests may use the repository's optional formal dependencies.

The saved workflow includes:

1. A project contract, manifest and pre-execution decision checkpoint.
2. The actual process exit, test results, logs, receipt and resource costs, including failures.
3. Restored live state, imported test observations and an Advisor recommendation to inspect failures or review the next change.
4. A replay of the finite [RSI example](../rsi/), followed by adoption on a separate graph only when execution succeeds and the case gate accepts it.
5. A recorded rollback of that isolated graph. The repository's judgment graph is not changed by the example.

To inspect a failed attempt using the current tool:

```powershell
python -B scripts/rds_cli.py --root C:\rds-development\iteration-1 meta reflect
```

Reflection emits an execution-review candidate tied to the registered run, attempt and receipt. Inspect the existing failure and repair its cause before another authorized iteration; the candidate is not automatically installed as a scientific rule.

For v5.6.0-rc.1 on 2026-09-30, the first actual iteration ran 49 checks and recorded two failures. They exposed an incomplete control fixture and a test that searched explanatory prose for the word `probability` rather than checking output fields. After these fixes and additional acceptance coverage, the second iteration ran 65 checks with no failures or skips. Artifact import, Advisor output, four finite rule cases, isolated adoption and rollback all completed. The case replay passed 1/4 baseline cases and 4/4 candidate cases, with two improvements on its declared held-out cases and no regressions.

The iterations use different test sets; this is a development feedback record, not a controlled research-policy comparison. Its held-out cases are declared software fixtures, not sealed external scientific evaluations. `task_gain` and `mechanism` remain `UNKNOWN`; no GPU run, paid model call or multi-seed experiment is launched. Runtime records stay in the selected workspace and should not be committed with private paths or data.

The subsequent public-CLI audit exposed control identity, continuation, failure-exit and dashboard integration bugs. The first attempt at the full suite also found a missing benchmark support package in this copied workspace. After repairs, `--all-tests` ran all 286 cases: 282 passed, four optional-dependency checks skipped, and no failures. The same workflow imported those counts, produced advice and completed the isolated rule replay, adoption and rollback.

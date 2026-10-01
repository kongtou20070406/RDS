# Low-friction research entry

Programmatic completion supplies file hashes, protocol identities, timestamps, receipts and previously recorded question/scope fields. It does not invent a research objective, budget, seed, hidden input, proof, causal explanation or scientific rejection. The normal frozen ProjectStore and append-only checkpoints remain authoritative.

## Wrap a command

```powershell
python -B scripts/rds_cli.py --root <source-directory> exec --name probe-001 --timeout 30 -- python -B probe.py
```

One call freezes inputs, constructs the contract/protocol/manifest, reserves the explicit wall allowance, executes and records the real receipt. No handwritten protocol JSON is needed. The default cap is 60 seconds; supply the appropriate bounded cap. Jobs that must outlive the conversation use `--background`, the existing Windows Task Scheduler runner. Jobs longer than 3600 seconds use the regular project runner.

The command runs in `<source-directory>/.rds/exec/probe-001`, a frozen copy. Existing file arguments and static local Python imports are copied, including package initializers. Add implicit inputs with `--bind data=relative/file.json` (also `code`, `config`, `evaluator`). Dynamic imports, external packages, environment access and remote inputs are not completely discovered. Keep these limitations explicit; this trusted-code runner is not an OS sandbox. Non-Python/inline commands require an explicit code binding. Commands cannot invoke a shell.

Use `--output outputs/result.json` to require an output in the job copy; its parent directories are created after runner validation. Read original stdout/stderr and declared outputs through the receipt's artifact paths. Omit `--name` to derive a stable name from the frozen request: an identical call reuses its receipt and changed inputs produce a new identity. Explicit names remain immutable. Failure/timeout logs and spent costs survive. Exit code 0 means operational completion; mathematical or policy success remains unknown.

For an existing local Python file, the shortest form is `python -B scripts/rds_cli.py exec -t 10 probe.py`. The entry supplies the current Python executable and infers the child boundary. Once the child starts, all its arguments remain untouched, including `--help` and `--root`. Use explicit `--` for commands whose boundary is unclear.

## Select before executing

Maintain the semantic `context.json` and structured graph for the actual next decision. The tool supplies repetitive bookkeeping around these inputs; it cannot derive the right mathematical question from arbitrary prose.

```powershell
python -B scripts/rds_cli.py --root <existing-ledger> advise --context context.json --graph graph.json --record next-choice --brief
python -B scripts/rds_cli.py --root <source-directory> exec --name probe-002 --timeout 30 --context context.json --graph graph.json --ledger <existing-ledger> -- python -B probe.py
```

If exactly one `READY` candidate remains, its identity is completed automatically. Otherwise supply `--choose <candidate-id>` from the advice. This records the caller's planned route, not scientific acceptance. The prospective `exec` reviews the current ledger, records the choice **before execution**, then records the execution identity afterward in that same ledger. Unchanged rejected routes are unavailable; changed relevant facts, premises or scope can reopen review. Unknown prerequisites, ambiguity or corrupt history cannot authorize a quick research run. An `exec` without context/ledger is explicitly an operational wrapper and does not claim direction selection.

Prospective child jobs consume a conservative wall allowance in that same parent ledger before launch; unspent allowance is not refunded. Changing a job name or creating a fresh child directory cannot replenish it. Quick execution requires a wall-only parent budget; multi-resource work needs an explicit project manifest. The original human deadline and authorization still apply.

## Clarify method limits

Treat candidate construction, verification of a fixed candidate, and proof of a universal claim as separate purposes. An algorithm name alone does not identify its purpose: branch and bound can search heuristically or exhaustively exclude a rigorously bounded domain. Floating point with proved enclosures can support a certificate; exact arithmetic can still be used for forbidden heuristic search. A coverage certificate proves a construction upper bound, not a matching unrestricted lower bound or global optimum.

Consider certifying computation during direction selection when it can close the next mathematical obligation within the authorized budget. Use the existing graph/Advisor fields: state the exact obligation and quantified domain; expose domain completeness and each pruning lemma as prerequisite facts with real evidence; require the bound certificate, remaining unresolved branches and independent replay as observables; let verified completion versus a counterexample or unresolved branch change the next decision. Missing prerequisites should produce a concrete bridge lemma or smaller valid sub-obligation. Record the prospective choice before execution and consume its actual result in the next selection, instead of wrapping a finished proof only for archival. A reusable domain adapter must provide these mathematical obligations and a real checker; the generic scope checker supplies no universal branch-and-bound solver.

When a user's instruction has materially different plausible scopes, ask one short question before the affected step. Keep that question pending and continue work that does not depend on the answer. Neither silence nor a quoted proposal resolves it. External contest rules can describe admissible evidence but do not override the user's method, CPU/GPU, budget or deadline restrictions. Do not extrapolate a small-case runtime into an unmeasured promise for larger cases.

Opt in through the **existing** Advisor context, without another database or command. Retain the original wording and its locator; after actual clarification, retain that wording and source as well. For example, after a human confirms that strict assisted proof is allowed and heuristic candidate search is forbidden:

```json
{
  "method_constraints": [{
    "id": "candidate-search",
    "quote": "不要数值搜索",
    "source": "user:original-message",
    "status": "CONFIRMED",
    "confirmation": {
      "quote": "允许严格辅助证明，禁止启发式数值找候选",
      "source": "user:clarification-message"
    },
    "when": {"purpose": "candidate_search"},
    "forbid": {"technique": "heuristic"}
  }]
}
```

This is a schema example, not an authorization. Each clause needs a unique `id`, original `quote`, `source` and `status` (`CONFIRMED` or `UNRESOLVED`). A confirmed clause has exactly one nonempty `forbid` or `require` predicate. `when` limits its scope; an omitted/empty `when` applies to all described steps. An unresolved clause may supply a short `question`. Unknown scope must remain unknown rather than being guessed from keywords. A clarification's `confirmation` records actual `quote` and `source`; use the latest genuine instruction while retaining the earlier wording.

Actions and templates declare `methods` as one flat string dictionary or a list of steps, for example `{"purpose":"proof","technique":"certifying_branch_bound","arithmetic":"certified","device":"cpu"}`. Include each stage in a mixed search/verification/proof workflow. Names are exact caller-defined values, not fuzzy aliases. Predicates are bounded to eight string fields; contexts contain at most 32 clauses and workflows at most 32 distinct method steps. If these fields are missing, describe the actual operation from its code/protocol; do not ask the human to fill a form.

Advisor reports compatible, conflicting or unknown scopes. Conflicts block that candidate; unresolved wording produces clarification questions; missing descriptions remain unknown. Other compatible candidates remain available. Constraint-aware experiment composition retains every declared stage and keeps distinct method descriptions separate even for otherwise identical intervention aliases. Quick prospective execution rechecks the supplied context before launch or parent-budget charge, then retains the clauses and review in its ordinary checkpoint; the frozen request binds the entire research context. A supplied `READY` or compatibility label cannot bypass that check. Old contexts without `method_constraints` retain their behavior.

This checks caller-reported declarations, not natural-language meaning, the authenticity of a source locator, or whether code implements its declared method. `INPUT_REPORTED` compatibility grants no execution authority, validates no theorem and replenishes no budget. At continuation boundaries, carry forward the recorded clauses and clarification; dropping them from a new context is not permission to lift a restriction. Read the actual program, authorization, receipt and appropriate proof evidence separately.

## Record a scoped rejection

```powershell
python -B scripts/rds_cli.py --root <existing-ledger> reject --reason "declared scoped counterexample" --evidence witness.json
```

The latest matching checkpoint supplies the question ID, goal revision, scope, candidate and contemporaneous facts. `--route` can verify the expected candidate. The tool retains the original witness bytes and hash, reason and previous checkpoint identity. Missing context produces an actionable error. It never infers a mathematical counterexample from a failed process or permanently bans a route outside its recorded scope.

Inside Python, the same entry is available from the skill's `scripts` directory:

```python
from rds_quick import record_falsification
record_falsification(ledger_root, witness=bad_example_dict, reason="why this scoped claim fails")
```

This records caller-declared falsification with `RECORDED_INPUT_NOT_SCIENTIFIC_VERIFICATION` assurance. Run the appropriate exact checker separately when required.

## Output and tolerant spelling

New `exec`/`reject` commands return a compact digest by default; `--json` returns their full report. `advise`, `project status`, `status`, `formal verify` and `formal check` support `--brief`/`--digest`. Full JSON is retained in `.rds/cas/<sha256>.json`; original execution logs remain intact in the runner's artifact directory. Counts are local ledger counts, not proof of scientific use or autonomy.

At meaningful advances or blockers, the agent gives one short factual line, for example `RDS｜选路✓→执行✓｜证明?｜<sha8>` followed by the concrete advance or next step when useful. Show only evidenced stages and an actual receipt/certificate/saved-record hash prefix; use `?` for unknown and `—` for inapplicable stages. The proof marker concerns the reported claim and its premises, not a process exit or a narrower lemma. Do not report every internal invocation or add display calls. Complete receipts remain available for audit; actual backend, assurance and application scope remain distinct.

Exact commands take priority, followed by explicit aliases and unique command prefixes. Examples: `advisor`/`review` → `advise`, `proj` → `project`, `cp` → `checkpoint`, `execute` → `exec`, `deny` → `reject`, `calls` → `usage`; Chinese aliases include `审查`, `执行`, `否决`, `检查点`, `项目`, `调用`, `状态`. `--workspace` and `--project-root` alias `--root`, including after the subcommand; `--context` aliases `--research-context`. Ambiguous `adv` reports `advise, advancement`; a typo receives repair suggestions. Values, budgets, paths, witness contents and the wrapped argv after `--` are never fuzzy-normalized.

Additional aliases include `test`/`eval`/`start`/`测试` → `exec`, `suggest`/`route`/`规划` → `advise`, and `falsify`/`counterexample`/`证伪` → `reject`. `verify`/`prove`/`证明` expand to `formal verify`; `check`/`核查` to `formal check`; `snapshot`/`存档` to `checkpoint save`. Existing `run` and `plan` keep their original meanings. Root supports `-w`, `-d`, `--dir`; exec supports `-t`, `-o`, `-c`, `-l`; reject supports `-m`, `-e`. Suggestions do not authorize execution.

Use `hypergraph --input proof-graph.json` for the existing bounded AND/OR dependency analysis. `--audit-files` checks declared file hashes; neither graph reachability nor a `SUPPORTED` label proves mathematics. Full results are retained; `--json` exposes them. Truncation returns exit code 2.

An optional `exec --guard policy.json` checks comparable metrics or replays frozen milestones before allowing promotion. `reject --domain domain.json` records only explicitly justified parameter exclusions. Both use existing artifacts and checkpoints; see [regression guards](regression-guards.md).

## Performance and design provenance

Pure Frontier queries skip the unrelated judgment graph and ML recommendations. No persistent cached proof or scientific truth is introduced. Measure real local timings and output bytes before making speed/token claims; desktop/network reconnection time is outside this CLI measurement.

The interface follows independently implemented standard practices also observable in Claude Code: ranked command/alias suggestions, exact matches taking precedence, and definitions loaded when needed. The [official MCP guide](https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search) documents deferred tool discovery. The [official exact-match bug report](https://github.com/anthropics/claude-code/issues/19259) illustrates the need to separate fuzzy suggestions from execution. A bounded inspection of a third-party 2.1.88 source-map reconstruction informed the comparison; it is an old snapshot, not an authenticated current Anthropic source commit. No reconstructed code or dependency was copied into RDS.

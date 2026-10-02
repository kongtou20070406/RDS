# Program-owned dependency maintenance

**English** · [简体中文](truth-maintenance.zh-CN.md)

Give the tool small declarations and changes. The program builds the internal AND/OR table, selects justification witnesses, checks the structure and recomputes the closure and goal blockers. An agent does not maintain a second support table or copy derived statuses back into its input.

The existing `hypergraph` command accepts its original schema and compact input:

```json
{
  "claims": {"premise": {"status": "supported", "source": "observation.json"}},
  "rules": [{"from": "premise", "to": "target", "status": "supported", "source": "implication.json"}],
  "goal": "target"
}
```

Here the program creates the `target` node as `UNKNOWN`, assigns the rule ID and derives the reported closure. The agent supplies the meaning of the support relation once. All premises of one rule are AND; separate rules concluding the same node are OR. The tool cannot discover a scientific implication from arbitrary prose.

## Input tolerance

Unambiguous formatting repairs are automatic and retained in `input_review`:

- A whole JSON code fence and trailing commas outside strings are accepted.
- `claims`/`nodes`, `rules`/`hyperedges`, `goal`/`goals`, `state`/`status`, and rule `from`/`premises`/`if`, `to`/`conclusion`/`then` are accepted.
- Node records can be keyed by ID; a single premise or goal can be a string. Identifier whitespace and status case are normalized, and repeated AND premises are deduplicated.
- Missing node status defaults to `UNKNOWN`; missing rule status defaults to `PROPOSED`. Referenced nodes and rule IDs are generated. Missing sources get input-declaration locators, and a source-free `SUPPORTED` assertion is withheld as `UNKNOWN` or `PROPOSED`.

Conflicting aliases, duplicate IDs, missing rule endpoints and unknown change targets are reported together. No change is applied while these ambiguities remain. Exit 2 means input clarification or a computation limit; an open scientific obligation is still usable and does not cause a formatting rejection. Duplicate JSON keys and non-finite numbers remain invalid. Imported code is data and is never executed.

## Reuse snapshots, submit changes

```powershell
python -B scripts/rds_cli.py --root ../tms-demo hypergraph -i examples/tms-input.json
```

Default output contains at most three goal statuses, counts, one next step and the existing CAS `record` locator. The full result at that locator includes the program-generated `dependency_map`. Feed that **record path** directly to the next invocation:

```powershell
python -B scripts/rds_cli.py --root ../tms-demo hypergraph -i <previous-record-path> --retract-node premise
```

No table editing is required. Retraction withdraws a node's reported support (`UNKNOWN`) or a rule's reported support (`PROPOSED`). `--refute-node` / `--refute-rule` instead record `CONTRADICTED`. Repeat a flag for several targets; `--change-source <locator>` records the source of the declared change. `--trace-cone <node>` explains its selected current justification. `--output <new-file>` and `--json` expose the full result when needed.

The ordinary closure, goal statuses, blocker sets and reported rows all refer to the revised map. Independent valid OR alternatives survive; an unanchored cycle cannot prove itself. Earlier snapshots remain immutable. Reuse an earlier record to revisit its declarations instead of manually reconstructing a support table. Advisor accepts the generated snapshot in its existing `advisor_context.dependency_map` field and analyzes the same revised map. Existing receipt checks and authorization remain in their current owners.

## Evidence boundary

The assurance remains `INPUT_REPORTED_DEPENDENCY_ANALYSIS_NOT_PROOF`. A source locator, reported `SUPPORTED` label, file hash, execution receipt or finite local cases does not establish a scientific claim. File auditing checks bytes only. The program manages dependency consequences and offers a next check; it grants no execution authorization and declares no universal capability mastery.

Reusable candidate execution continues through `rsi extract/validate/register/use`. Goal-bound application, independent expected answers and scoped reuse remain the work described in #43/#45; receipt-to-refutation integration remains #49/#36. This interface introduces no capability registry or mandatory three-tier workflow.

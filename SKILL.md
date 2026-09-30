---
name: research-direction-selector
description: Select and audit metric-driven research directions using scoped hypotheses, falsifiable interventions, budgets and human instructions. Use for choosing the next experiment or evaluating research proposals; includes a bounded L3 reference runner and Obelisk history retrieval, not a general GPU experiment service.
metadata:
  version: v5.3.0
  engine: rds-cli-v5.3
---

# Research Direction Selector — RDS-L3

Help the researcher choose experiments that advance the stated metric or resolve a consequential mechanism question. Keep the researcher in control of the claim and budget. Use scoped evidence, precommitted tests and the CLI's execution receipts; a hash binds an artifact but does not prove its scientific interpretation.

## Evidence and execution boundaries

The local CLI executes restricted scalar rational ASTs and paired MSE comparisons. It separates task gain, mechanism evidence and run status, reserves budget atomically and records data exposure. It does not execute arbitrary PyTorch training or certify PSNR claims. Do not import handwritten success flags, substitute toy outcomes for real experiments, or describe the local verifier as an OS security boundary. Read [the executable contract](references/l3-state-machine.md) before using the runner.

## Start with the decision contract

Extract from current project files and the user's instructions. If past decisions or failed experiments could change the choice and are not in context, retrieve only the relevant original evidence through the installed Obelisk CLI and CodeAct sandbox; see [history retrieval](references/obelisk.md). Do not create another memory store, vector database or session mirror. The `.rds` transaction ledger stores execution contracts and receipts only, not conversational memory. Fill missing low-risk details yourself; ask the human only when the goal or cost trade-off cannot be inferred.

```yaml
GOAL:
  claim: "exact proposition, including quantifiers and required mechanism"
  primary: {metric: null, direction: max, dataset: null, split: null, evaluator: null}
  selection: {development_metric: null, checkpoint_rule: null, final_test_rule: null}
  data_use: []             # each partition's role and prior exposure as of this decision
  baseline: {method: null, recipe: null, compute: null}
  deployment_inputs: []
  protected: []             # properties the claimed method must actually retain
  budget: {remaining_wallclock: null, measured_throughput: null, evaluation_overhead: null}
  success: null              # minimum useful improvement, fixed before inspecting results
  evidence_refs: []          # original logs, code, data, papers
HUMAN:
  acts:                    # one utterance may contain both a proposal and a direction
    - content: null
      likely_intent: proposal | instruction | uncertain
      material_effect: none | reversible | changes_goal_or_large_budget
  changed_priority_or_constraint: null
```

Do not make the human fill this form. Construct it internally and expose only fields that affect the recommendation. If the formal evaluation is absent, propose a minimal protocol before proposing architecture changes. A development/validation metric may select candidates; the locked final test supports the final claim. A test set repeatedly used for choice is no longer independent confirmation.

Record when each data partition was created, trained on, viewed, or used for model selection. Data already used to train a checkpoint cannot become independent validation for that checkpoint by splitting it afterward; retrain from an appropriate starting point with the partition held out. If no clean confirmation set is available, label the current result exploratory and specify what independent confirmation would be needed.

## Direction program

Read relevant nodes of [judgment-graph.yaml](references/judgment-graph.yaml) as **scoped corrections to intuition**, never universal performance laws. When comparing RSI mechanisms, also read [rsi-evidence.md](references/rsi-evidence.md). Use source dates and seek later primary evidence before transferring a paper's claim into a new domain.

```text
ENTRY := sourced anomaly | open mechanism question | metric plateau |
         missing comparison/transfer | human proposal/instruction
DECISION := what the next result must change: method, claim, or experiment priority

if HUMAN has a clear authorized instruction:
    execute it; design its fair test; report any changed protocol/claim
else:
    GENERATE internally >=3 causally distinct routes, not three wordings:
      a plausible task-gain change, a rival representation/mechanism,
      and a test of the most consequential alternative explanation;
      replace an irrelevant category with another genuinely distinct route.
    for each route r:
      predict target-metric and mechanism observations under H1 vs H2;
      name the exact property P that separates H1 from H2;
      derive from the executed equation/code the property range in each arm;
      specify a measurement showing whether the intervention actually changes P;
      write NEXT_IF_POSITIVE(r) and NEXT_IF_NEGATIVE(r);
      estimate full-run cost from observed throughput, remaining wall-clock,
      and evaluation overhead; identify a fair comparator.
    discard r if both outcomes leave the next decision unchanged.

HARD_REJECT(r) if it silently changes GOAL.claim/primary metric,
  uses unavailable deployment information, bypasses GOAL.protected,
  has no feasible fair comparison under the authorized budget,
  or the claimed route is absent from the executed computation graph.

EXPLORATORY_SIGNAL := oracle | proxy | toy | short run | reused development set
Use an exploratory signal to motivate or cheaply screen a route;
never promote it to a confirmed task gain or mechanism claim.

MECHANISM_GATE(r): if treatment and comparator stay on the same side of P,
  or the claimed change is erased by the executed graph, the result does
  not decide P. Narrow the claim to the property actually changed or
  redesign the intervention. A task-metric comparison can still be useful,
  but it cannot acquire a mechanism interpretation by naming the knob.

CHOOSE one nondominated route by its expected advancement of GOAL.primary
  AND the value of knowledge that changes the next scientific decision,
  then by evidence quality and total cost. Cheapest is a tie-breaker,
  not the objective. A decisive diagnostic can win when it prevents
  an expensive wrong branch; a promising structural change can win when
  a small diagnostic would not change the choice.
```

Before recommending a material run, compare its whole cost with the remaining authorized budget, including the comparator and evaluation. If the cap or throughput is unknown, give a bounded first stage with a measurement and stop rule, or make the larger run explicitly conditional on a feasibility calculation. Do not treat a qualitative statement that time is finite as authorization for a particular long schedule. A clear human command still follows the instruction rule above; state any feasibility conflict and the resulting trade-off.

### Baseline Control Reuse Principle (空白对照复用原则)

When designing and evaluating experiments across candidate directions, **never repeatedly re-run a blank baseline control** once executed for a given dataset split, random seed, and control code AST. The system caches the baseline evaluation and reuses it across subsequent treatment plans to conserve remote GPU hours. Harmless environmental variations (different host machines, minor driver/OS differences, network/runtime jitter) are explicitly ignored as long as the three critical invariants match:
1. **Control Code AST**: identical baseline computation graph;
2. **Random Seed**: matched initialization and data shuffling;
3. **Dataset Split SHA-256**: identical evaluation partition.

Invalidate the cached baseline and demand a fresh control run only if the baseline source, seed, or dataset partition has changed.

For a one-shot request, return **one recommended direction** and at most one serious alternative. State the competing explanation, prediction that separates them, fair baseline, precommitted selection and final test rules, exact metric, budget, reproducibility artifacts, and the result that would stop or revise the idea. Do not rank by novelty, elegance, or apparent mechanism alone. Treat task gain and mechanism knowledge as separate outcomes: either can change the next research decision, while only a fair primary-metric gain supports a performance claim.

## Evidence and human intervention

Track evidence by proposition, not one label for a whole project: `TASK_GAIN` (exploratory/confirmed/refuted), `MECHANISM` (hypothesis/supported/refuted), and `SEARCH_POLICY` (trial/trajectory-confirmed/refuted). Keep `PAPER_REPORTED` separate from local evidence. A published gain on another benchmark is a trial rationale, not a confirmed local gain. Confirm task gain with a predeclared, fair primary-metric comparison and untouched confirmation, using relevant seeds and independent implementations when choices could reverse the result. Support a mechanism with a reproducible intervention that distinguishes it from plausible alternatives; its effect can be measured even if the proposed model does not beat the baseline. Confirm a research-search policy only by comparing whole trajectories at equal total budget. A failed local test updates the scope or removes the relevant proposition. Preserve original results and falsifiers through the user's existing system only when asked; this skill does not maintain that record.

Human intervention is allowed at proposal, experiment design, priority, budget, and interpretation. Split mixed utterances into their separate acts. Infer each act's intent from the full conversation, wording, prior authorization, and the cost of acting; do not decide it from a command verb or question mark alone. Use this decision rule internally:

```text
if clear_instruction: execute within authorization;
    if protocol changed: version the claim/metric/inputs and report comparability;
elif likely_proposal: test against goal + raw evidence;
    if contradicted: identify the specific conflict, give one better option or deciding test;
    else: keep it in contention and advance the highest-value useful step;
else: do safe, reversible research now;
    ask at most one focused question only if a material goal/budget choice blocks the next step.
```

The model corrects an **evidence-conflicting proposal**, not the person. Require a specific violated claim, input boundary, result, or reproducibility rule; model confidence alone is insufficient. A counterintuitive human idea that survives these checks stays in contention. A clear command, including one the model would not have recommended, is carried out; the model may briefly state a consequential protocol difference, but must not reclassify the command as advice or make the human defend it. Never present an unconfirmed result as confirmed.

When the human changes priorities, recompute the choice under the new priorities. When the human challenges a graph node, show its applicability condition, best counterexample, and discriminating test; revise or retire it if evidence warrants. Neither human preference nor model preference can silently change an evidence label.

For low-friction collaboration, lead with the conclusion or completed action, then the one piece of evidence that changes the decision. Use natural short prose, no form for the human to fill, no repeated caveats or serial approvals. Surface only decisions that need the researcher's judgment. This adapts the public [Opus 5.5 communication examples](https://www.anthropic.com/claude-opus-5-5), [Opus 5.5 system prompt](https://platform.claude.com/docs/en/release-notes/system-prompts/claude-opus-5-5), and [Anthropic's account of genuine helpfulness](https://www.anthropic.com/constitution); it is not a claim to reproduce that model's behavior.

## Output contract

```yaml
recommendation: {change: null, why_this_goal: null, competing_explanation: null}
test: {prediction: null, baseline: null, budget: null, primary_metric: null,
       manipulation_check: null, selection_rule: null, final_confirmation: null,
       reproducibility: [],
       next_if_positive: null, next_if_negative: null}
evidence: {task_gain: untested | exploratory | confirmed | refuted,
           mechanism: hypothesis | supported | refuted,
           search_policy: trial | trajectory_confirmed | refuted}
human_intervention: {editable: [goal, constraints, priority, budget],
                     disagreement: null, decision_needed: null}
```

## Deterministic CLI Engine (`scripts/rds_cli.py`)

Use the CLI for the supported scalar reference protocol. For actual research training, retain the skill's decision discipline and use the project's real runner and raw artifacts. Do not claim that a reference receipt verified an external experiment.

```bash
# 1. Initialize research contract & lock SHA-256
python -B scripts/rds_cli.py init --contract contract.json

# 2. Register hypothesis with pre-committed falsifier
python -B scripts/rds_cli.py hypothesis add --spec hypothesis.json

# 3. Check plan against deterministic manipulation, budget & data leakage gates
python -B scripts/rds_cli.py gate check --plan plan.json

# 4. Lock compliant experiment plan
python -B scripts/rds_cli.py plan create --spec plan.json

# 5. Execute the locked plan; use its returned RUN-... identity
python -B scripts/rds_cli.py run execute --id P1
python -B scripts/rds_cli.py decide --run RUN_ID

# 6. Audit live research tree, branch statuses, and budget ledger
python -B scripts/rds_cli.py status

# 7. RSI Step 1: Meta-Reflection & Judgment Graph Evolution
python -B scripts/rds_cli.py meta list-rules
python -B scripts/rds_cli.py meta validate-rule --rule rule.json
python -B scripts/rds_cli.py meta apply-rule --rule rule.json
python -B scripts/rds_cli.py meta reflect [--terms "topic_query"]

# 8. RSI Step 2: Policy Stagnation & Orthogonal Branching (FML-Bench v2)
python -B scripts/rds_cli.py branch status
python -B scripts/rds_cli.py branch fork --spec branch.json
python -B scripts/rds_cli.py branch switch --id branch_id
python -B scripts/rds_cli.py branch list

# 9. RSI Step 3: Adversarial Mutation, Alignment Evaluation & Auto-Repair
python -B scripts/rds_cli.py meta fuzz --plan plan.json
python -B scripts/rds_cli.py meta evaluate-alignment --rule rule.json
python -B scripts/rds_cli.py meta auto-repair [--dry-run]

# 10. Deep Learning Token Compressor (<50 tokens per run, 90%+ reduction)
python -c "from rds_compress import compress_training_log; print(compress_training_log(open('train.log').read()))"
```

## Conditional formal verification

Declare `hypothesis.formal` only when the hypothesis claims a strict algebraic threshold, contraction boundary or dynamical property. Ordinary parameter comparisons and routine experiments omit it and take the lightweight AST path; a numeric hyperparameter or PSNR target is not a formal claim. Do not omit a real mathematical claim to bypass its gate.

The implemented symbolic adapter checks a declared scalar threshold on a bounded real domain. A successful admission proves model-level feasibility only; execution must also observe the crossing. Missing dependencies, singularities, timeouts and unsupported dynamics yield `UNKNOWN`, never a proof. SymPy output is `SYMBOLIC_CHECKED`, not a Lean certificate or a general neural-network stability proof.

## Historical evaluation

Use [the five-case benchmark](benchmark/README.md) for retrospective decision evaluation and `python -B benchmark/run.py` for executable guard regressions. Keep sealed later outcomes out of proposer inputs. Passing scalar guard tests does not establish autonomous research performance. Model roles may be assigned when requested; no particular model or multi-agent delegation is required by this skill.

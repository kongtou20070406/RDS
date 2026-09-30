# Rule proof obligations: all 23 nodes

[简体中文](rule-obligations.zh-CN.md) · [Documentation](README.md) · [Formal verification](formal-verification.md)

Each node in [judgment-graph.yaml](../references/judgment-graph.yaml) retains its original scope, sources, discriminator and falsifier, and now documents preconditions, a feasible-domain expression, variables and required evidence. These expressions are readable specifications, not executable syntax for a universal prover.

The experimental `LeanFormalEngine` can address a node with `kind: causal_rule` and its `rule_id`. At this snapshot it only checks that registry metadata fields are present. It does not enforce `proof_obligations`; every node therefore records `runtime_enforced: false`. `RULE_ALIGNED` is structural metadata alignment, not plan compliance or causal proof.

Candidate tactics describe possible local arithmetic checks, not implemented discharges of the full rule. Exact model algebra, actual source and execution, data provenance, and empirical comparisons require their respective evidence. Missing evidence remains unresolved; no self-signed flag, tactic trace or score may substitute for it. The [research workflow](research-workflow.md) keeps these assessments separate.

Notation: `s` is +1 for a metric to maximize and -1 for one to minimize; `H` is the specified content hash. `empty`, `subseteq`, `intersect`, `does_not_imply` and `iff` are mathematical predicates. A comparison can be confirmatory only with the declared scope, valid independent data and a precommitted selection/evaluation rule.

## locked-test-selection

**Preconditions:** Record all candidate selection and exposure before confirmation. Bind the same evaluator, baseline and predeclared useful delta.

**Feasible-domain expression:**

```text
clean(T) and selection_data intersect T = empty; Delta_T = s*(M_T(treatment)-M_T(control))
```

**Variables:** T: frozen confirmation cohort; selection_data: all samples or linked cohorts influencing selection; clean: recorded unexposed lineage; M_T: predeclared metric; s: +1 maximize, -1 minimize

**Falsifier:** The frozen independent comparison does not support the predeclared useful gain, or confirmation lineage was already exposed.

**Required evidence:** predeclare checkpoint selection on development data; confirm the chosen model once on untouched test data project locked test metric and fair baseline, with every candidate and selection decision logged

**Verification boundary:** `protocol_and_empirical`; registry ID `locked-test-selection`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## deployment-information

**Preconditions:** Declare deployment-visible inputs and their lineage. Audit every actual inference path, including preprocessing.

**Feasible-domain expression:**

```text
inputs(deployed_model) subseteq I_deploy; inputs(deployed_model) intersect I_target_only = empty
```

**Variables:** I_deploy: inputs available at deployment; I_target_only: labels, target-derived values and per-example oracle information

**Falsifier:** The deployed path needs target-only information; report any oracle result as a bound instead of achieved performance.

**Required evidence:** trace every inference input; compare deployment-only model with oracle reported separately formal task metric using deployment-visible inputs only

**Verification boundary:** `source_and_empirical`; registry ID `deployment-information`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## preserve-quantifiers

**Preconditions:** State each quantifier, policy class and available information. Distinguish a fixed action, an oracle and a learned conditional policy.

**Feasible-domain expression:**

```text
not(forall f, P(a0,f)) does_not_imply not(exists g in G_deploy, forall f, P(g(f),f))
```

**Variables:** a0: one tested fixed action; f: deployment-visible input; P: stated success predicate; G_deploy: declared learnable policy class using deployment inputs

**Falsifier:** A failing tested action or policy is generalized to all conditional policies without evidence covering the quantified class.

**Required evidence:** compare fixed action, per-example oracle bound, and policy using deployment-visible f on a held-out set formal held-out task metric for the learned conditional policy

**Verification boundary:** `logic_and_empirical`; registry ID `preserve-quantifiers`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## computation-graph-identity

**Preconditions:** Bind the actual tensor graph and checkpoint. Identify where branch information must remain available.

**Feasible-domain expression:**

```text
pool(z1)=pool(z2) implies h(pool(z1))=h(pool(z2)) for the same h
```

**Variables:** z1,z2: distinct branch configurations; pool: actual aggregation; h: fixed downstream computation; equality: declared numerical semantics

**Falsifier:** Swaps collapse to the same aggregate before the claimed branch-sensitive route; withhold attribution to that route.

**Required evidence:** inspect tensor path and fixed-weight branch swaps or ablations before full retraining formal metric against same-budget baseline plus a mechanism-sensitive diagnostic

**Verification boundary:** `source_and_execution`; registry ID `computation-graph-identity`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## proxy-primary-bridge

**Preconditions:** Predeclare a task gate and a separate mechanism-sensitive diagnostic. Verify the route intervention preserves the intended comparison.

**Feasible-domain expression:**

```text
Delta_task = s*(M_T-M_C); Delta_route = s*(M_route_on-M_route_off); these are separate propositions
```

**Variables:** M: predeclared task metric; T,C: matched treatment/control; route_on/off: matched mechanism intervention; s: metric direction

**Falsifier:** The task gain survives route removal, or the diagnostic changes unrelated factors; retain only the supported engineering gain.

**Required evidence:** same-budget ablation or intervention that disables claimed route while preserving the rest predeclared task metric decides utility; mechanism diagnostic decides mechanism attribution

**Verification boundary:** `intervention_and_empirical`; registry ID `proxy-primary-bridge`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## short-budget-fidelity

**Preconditions:** Match sample-work, schedule and implementation at each budget. Measure representative full endpoints before treating an early rank as predictive.

**Feasible-domain expression:**

```text
sign(M_A(t_short)-M_B(t_short)) = sign(M_A(t_full)-M_B(t_full)) on measured representative pairs
```

**Variables:** A,B: measured candidates; t_short,t_full: matched short/full budgets; M: same endpoint metric and selection protocol

**Falsifier:** Ranks reverse or the surrogate cannot be validated; use short runs as feasibility diagnostics rather than endpoint proof.

**Required evidence:** compare early and longer matched-budget ranks on representative candidates; account for steps times batch size, schedule and implementation changes, and report rank correlation or top-choice retention only when enough candidates were measured full-budget formal endpoint under the same recipe

**Verification boundary:** `empirical`; registry ID `short-budget-fidelity`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## method-recipe-variance

**Preconditions:** First audit existing records and use the same seed for the matched control. Add seeds only after observed seed instability threatens the decision, within explicit budget; predeclare uncertainty treatment.

**Feasible-domain expression:**

```text
Delta_i = s*(M_T(seed_i)-M_C(seed_i)); extra_seed_runs require observed seed instability and decision impact within authorized budget
```

**Variables:** seed_i: paired seed; T,C: matched methods; M: primary metric; s: metric direction; uncertainty: declared estimator with its assumptions

**Falsifier:** The gain is explained by recipe/implementation or fails the scoped uncertainty criterion; narrow the method claim.

**Required evidence:** Audit existing records and make a matched same-seed contrast first; add seeds only when observed seed instability threatens the decision and the additional comparison fits the authorized budget. Predeclared primary metric under a matched recipe and cost protocol, with the actual seed scope and any available uncertainty evidence stated honestly.

**Verification boundary:** `empirical`; registry ID `method-recipe-variance`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## realized-boundary-not-knob

**Preconditions:** Bind the executed normalization equation, finite domain and rho>=0 under exact real/rational semantics. Match initialization and recipe, and measure actual effective mass; audit floating-point differences separately.

**Feasible-domain expression:**

```text
S=sum_j abs(raw_j)>=0; rho>=0; m=rho*S/(1+S); rho=1 and finite S implies m<1; rho>1 implies (m>=1 iff S>=1/(rho-1))
```

**Variables:** raw_j: actual row coefficients; S: their finite absolute sum; rho: finite declared scaling; m: executed effective row mass

**Falsifier:** The source uses a different equation or no executed mass reaches the claimed boundary; withdraw strict-bound inference.

**Required evidence:** to test the strict subunit predicate, use a normalized comparator that can realize m at or above one, measure actual crossings, and match starting operator and training as closely as feasible; a 0.95 versus 1.00 cap tests only the margin; for rho > 1 the original formula crosses only when S >= 1 / (rho - 1) matched restoration metric and budget; separate any task gain from the narrower mechanism conclusion

**Verification boundary:** `algebra_and_execution`; registry ID `realized-boundary-not-knob`. Local candidate tactics: `linarith`, `interval_check`. Independent scoped evidence is required; runtime enforcement is not implemented.

## depth-versus-trajectory

**Preconditions:** Use one fixed checkpoint and the same evaluation examples. Record each step metric and compute cost without retraining between steps.

**Feasible-domain expression:**

```text
theta_k=theta_star and X_k=X_star; M_k=M(F_theta_star^k(X_star),Y_star)
```

**Variables:** theta_star: one fixed checkpoint; X_star,Y_star: same evaluation examples; k: evaluated recurrent step; F: executed recurrence

**Falsifier:** Different trained checkpoints replace a within-checkpoint trajectory; withhold later-step degradation claims.

**Required evidence:** evaluate intermediate steps from one fixed checkpoint on the same images fixed-checkpoint stepwise formal metric with compute cost

**Verification boundary:** `execution_and_empirical`; registry ID `depth-versus-trajectory`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## reuse-baseline-control

**Preconditions:** Require a successful engine receipt with per-sample control results. Use full result-affecting identity for stochastic or extended adapters.

**Feasible-domain expression:**

```text
H(control_AST_new)=H(control_AST_receipt) and H(data_new)=H(data_receipt)
```

**Variables:** H: SHA-256 over canonical AST or exact data bytes as applicable; receipt: successful original control evaluation; stochastic identity: additional adapter-specific seed/checkpoint/recipe/semantics

**Falsifier:** Any result-affecting binding drifts or receipt evidence is missing; invalidate reuse without restoring exposed-data eligibility.

**Required evidence:** verify control identity and dataset SHA-256 against the original receipt; for an extended adapter verify its full stochastic and numerical identity before reuse; host changes are harmless only when they cannot change the declared control result cached per-sample control outputs must bind the locked baseline and exact dataset partition; a cache hit does not restore an exposed partition's confirmation eligibility

**Verification boundary:** `provenance_and_execution`; registry ID `reuse-baseline-control`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## trained-anchor-not-method-win

**Preconditions:** Record the trained anchor recipe, endpoint and complete cost. Obtain the appropriate matched baseline before claiming superiority.

**Feasible-domain expression:**

```text
feasible(anchor) does_not_imply Delta=s*(M_treatment-M_matched_control)>delta_min
```

**Variables:** anchor: first measured endpoint; matched_control: same carrier/data/recipe/selection; delta_min: predeclared useful gain; s: direction

**Falsifier:** Only the anchor completed, or the matched contrast fails; keep feasibility and withhold comparative superiority.

**Required evidence:** record the anchor's recipe, resource use and per-example endpoint; compare a mixer-only replacement with the baseline under the same carrier, data, selection and evaluation rules the project's primary task metric against the matched baseline at the declared quality-resource budget

**Verification boundary:** `empirical`; registry ID `trained-anchor-not-method-win`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## resource-canary-before-campaign

**Preconditions:** Measure the intended batch/crop/precision/loading/evaluation configuration. Declare concurrency, memory redline and overhead allowance before launch.

**Feasible-domain expression:**

```text
memory_peak<=memory_limit and makespan(schedule,measured_step_times)+T_io+T_eval+T_contingency<=B_remaining
```

**Variables:** schedule: feasible concurrency and step counts; times/memory_peak: measured intended configuration; B_remaining: authorized remaining campaign wall time

**Falsifier:** The canary or measured overhead makes the campaign infeasible; revise or reallocate before launching.

**Required evidence:** run a bounded canary at the intended configuration; measure peak memory and step time, verify data loading and evaluation overhead, then cost the matched campaign before launch a reproducible task comparison that fits the explicit memory redline and total campaign cap

**Verification boundary:** `measurement_and_budget`; registry ID `resource-canary-before-campaign`. Local candidate tactics: `linarith`, `interval_check`. Independent scoped evidence is required; runtime enforcement is not implemented.

## bundled-change-needs-component-control

**Preconditions:** Declare a component-specific intervention and feasible preservation tolerances. Audit physical action and routing-energy paths separately.

**Feasible-domain expression:**

```text
changed_factors={target_component}; preserved_factors include carrier,routing_interface,initial_operator,recipe
```

**Variables:** changed/preserved_factors: executed intervention manifest; target_component: the attribution being tested; include: required equality within declared tolerances

**Falsifier:** Multiple effective components change; retain only bundle-level evidence, not individual necessity.

**Required evidence:** predeclare one component intervention while retaining the carrier, routing interface, trainable capacity, starting operator and training recipe as closely as feasible; inspect both the physical action and its routing-energy path a fixed-endpoint primary metric under a matched budget, with remaining mismatches recorded separately from mechanism attribution

**Verification boundary:** `intervention_and_empirical`; registry ID `bundled-change-needs-component-control`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## ablation-is-intervention-specific

**Preconditions:** Bind the precise executed ablation rather than its informal name. Record all preserved and replaced computation paths.

**Feasible-domain expression:**

```text
manifest_executed=manifest_declared; conclusion_scope subseteq tested_intervention_scope
```

**Variables:** manifest: actual slot/gain/action/routing changes; tested_intervention_scope: exact replacement, task and recipe

**Falsifier:** The executed arm differs, or one replacement failure is generalized to all ablations; revise interpretation.

**Required evidence:** bind the executed arm to a precise intervention manifest; verify preserved slots, gains, action paths and routing inputs, and describe the conclusion for that exact arm matched endpoint and resource comparison for the executed intervention; reused development images support local model choice rather than generalization confirmation

**Verification boundary:** `source_and_empirical`; registry ID `ablation-is-intervention-specific`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## transfer-requires-matched-protocol

**Preconditions:** Honor the explicit task pivot and cost the target-task comparison. Match carrier, endpoints and evaluation using a relevant strong control; additional seeds require observed instability and decision impact.

**Feasible-domain expression:**

```text
Delta_target=s*(M_target(treatment)-M_target(matched_control)); cost_T and cost_C follow the same declared budget
```

**Variables:** target: requested target task/cohort; M_target: its endpoint metric; s: direction; cost: matched training/tuning/evaluation resource protocol

**Falsifier:** The gain disappears under the matched target protocol; withdraw only the scoped transfer claim.

**Required evidence:** Execute the requested task pivot with a costed matched target-task comparison; fix carrier, endpoints and evaluation, include a relevant strong control, and add seeds only after observed instability can change the decision within the authorized budget. target-task primary metric and paired uncertainty at the declared resource budget, with every completed arm and artifact identity recorded

**Verification boundary:** `empirical`; registry ID `transfer-requires-matched-protocol`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## protocol-versioned-evidence

**Preconditions:** Bind each reported row to complete protocol and artifact identity. Reconcile intended contrast and historical version differences.

**Feasible-domain expression:**

```text
signature=(H(data),H(model),H(checkpoint),seed,budget,selection,evaluator); compare only matched signatures except the declared intervention
```

**Variables:** H: content digest; signature: full task/evaluation identity with result-affecting settings; intervention: explicitly allowed contrast

**Falsifier:** Rows cannot be reconciled under a valid matched contrast; withhold the comparison instead of choosing a larger score.

**Required evidence:** bind each table row to dataset hash, model and checkpoint identity, seed, training budget, endpoint selection and evaluation settings; compare like versions or explicitly rerun the required matched contrast a primary-metric table with auditable protocol identity and comparators evaluated by the same rule

**Verification boundary:** `provenance`; registry ID `protocol-versioned-evidence`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## normalization-removal-confound

**Preconditions:** Keep the normalization route when testing a boundary-specific claim. Match the starting operator and recipe, and measure amplitude and optimization changes.

**Feasible-domain expression:**

```text
normalized_i=rho*raw_i/(1+sum_j abs(raw_j)); removed_i=raw_i; varying the equation changes more than a cap
```

**Variables:** raw_i: executed coefficient; rho: scaling; normalized/removed: exact compared operators; initialization and gradients: additional measured confounds

**Falsifier:** Amplitude, initialization or optimization changes remain confounded with the boundary; keep only the narrower conclusion.

**Required evidence:** retain normalization and match the starting operator and training recipe while varying the claimed boundary; measure realized amplitude and optimization differences rather than treating the knob value as the intervention matched task quality plus a verified boundary manipulation; task utility and strict-bound attribution are separate conclusions

**Verification boundary:** `algebra_and_empirical`; registry ID `normalization-removal-confound`. Local candidate tactics: `interval_check`. Independent scoped evidence is required; runtime enforcement is not implemented.

## executed-manipulation-validity

**Preconditions:** Derive the attainable property from bound source before expensive execution. Keep mathematical existence, observed manipulation and task outcome separate.

**Feasible-domain expression:**

```text
exists x in D: P_treatment(x)!=P_control(x); boundary variant requires exists x_observed in D: P_treatment(x_observed)>=tau
```

**Variables:** D: committed feasible domain; P: actual modeled property; tau: declared threshold; observed: executed samples; inequality: stated intervention direction

**Falsifier:** No realized manipulation leaves mechanism untested; a valid scoped counterexample refutes only the declared necessity statement.

**Required evidence:** derive the attainable range from the executed equation before expensive training, then log actual crossings or route activity on the committed data; keep feasibility, realized intervention and task outcome as separate checks the declared property must actually be manipulated before mechanism attribution; task quality still uses the predeclared matched metric and budget

**Verification boundary:** `algebra_and_execution`; registry ID `executed-manipulation-validity`. Local candidate tactics: `interval_check`, `linarith`. Independent scoped evidence is required; runtime enforcement is not implemented.

## learned-support-not-allowed-support

**Preconditions:** Inspect fitted effective properties, not only allowed parameter ranges. Use matched fixed/learned controls and repeat inspection after source changes.

**Feasible-domain expression:**

```text
allowed_support=Theta; realized_support={theta_hat(x):x in D_observed}; boundary claim needs max_x P(theta_hat(x))>=tau
```

**Variables:** Theta: declared parameter domain; theta_hat: fitted parameters; P: actual effective operator property; D_observed: committed observations; tau: boundary

**Falsifier:** Fitted effective operators remain on the original side; withdraw attribution to crossing while retaining scoped adaptation evidence.

**Required evidence:** inspect the executed effective operator and fitted parameter range across the declared data; compare matched fixed and learned controls and report boundary activity alongside quality primary metric for utility and observed effective-property crossings for the boundary claim, under the same recipe and selection rule

**Verification boundary:** `execution_and_empirical`; registry ID `learned-support-not-allowed-support`. Local candidate tactics: `interval_check`. Independent scoped evidence is required; runtime enforcement is not implemented.

## hard-budget-reallocation

**Preconditions:** Account for spent and queued work, concurrency, evaluation and contingency. Release displaced reservations and protect confirmation before new admission.

**Feasible-domain expression:**

```text
B_spent+B_reserved+B_new+B_overhead<=B_total; B_exploration<=B_total-B_confirmation_floor
```

**Variables:** B: nonnegative allocations in consistent declared units; reserved: after explicitly releasing displaced unstarted plans; overhead: conservative campaign estimate

**Falsifier:** The matched comparison exceeds measured remaining budget; reduce it or obtain a new budget decision before launch.

**Required evidence:** account for spent and reserved work; derive scheduled wall time from per-arm step times, step counts and feasible concurrency, including data and evaluation overhead and contingency; cost a matched pair and explicitly release displaced allocations before admission expected decision-changing primary-metric evidence within the authorized total cap and protected confirmation reserve

**Verification boundary:** `budget_and_empirical`; registry ID `hard-budget-reallocation`. Local candidate tactics: `linarith`, `interval_check`. Independent scoped evidence is required; runtime enforcement is not implemented.

## adaptive-test-reuse

**Preconditions:** Record each exposure and the decisions it influenced. Freeze the candidate and evaluator before genuinely independent confirmation.

**Feasible-domain expression:**

```text
used_for_choice(T) implies exploratory(T); independent_confirmation(T_new) requires unexposed_lineage(T_new) and frozen_selection
```

**Variables:** T: exposed partition; T_new: fresh confirmation cohort; lineage: bytes/sample/cohort overlap and off-system exposure declarations

**Falsifier:** Previously exposed or overlapping lineage is called independent; retract that label, not the measured exploratory score.

**Required evidence:** log the exposure and every decision it influenced; freeze the selected candidate and evaluation rule before testing once on a genuinely unexposed cohort, or explicitly limit the claim to exploratory performance independent confirmation for a confirmatory gain claim; the exposed test remains a valid measured exploratory endpoint under its stated protocol

**Verification boundary:** `provenance_and_empirical`; registry ID `adaptive-test-reuse`. No arithmetic tactic is assigned. Independent scoped evidence is required; runtime enforcement is not implemented.

## implementation-equivalence-before-speedup

**Preconditions:** Declare numerical semantics, inputs, forward/gradient paths and tolerances. Measure quality and resource use under one versioned matched protocol.

**Feasible-domain expression:**

```text
max_x norm(f_new(x)-f_old(x))<=eps_f and max_x norm(grad_new(x)-grad_old(x))<=eps_g on X_declared
```

**Variables:** X_declared: audited input set/domain; norm: predeclared norm; eps_f,eps_g: stated numerical tolerances; grad: relevant derivatives; model: bound implementations

**Falsifier:** Output/gradient discrepancies exceed tolerance or altered routes are omitted; treat accelerated code as a distinct implementation.

**Required evidence:** compare forward outputs and relevant gradients with the original implementation on representative inputs under a declared tolerance, retain version hashes, and use one verified implementation protocol for the matched arms equivalence checks within their declared input and tolerance scope, then primary quality and actual resource use under the recorded protocol

**Verification boundary:** `numerical_and_execution`; registry ID `implementation-equivalence-before-speedup`. Local candidate tactics: `interval_check`. Independent scoped evidence is required; runtime enforcement is not implemented.

## source-aware-evaluator-check

**Preconditions:** Bind the claim, executed equation and intervention manifest for source-aware audit. Keep sealed later outcomes out of decision-time audit and retain original scores.

**Feasible-domain expression:**

```text
feasible_claim = exists x in D: declared_distinction(executed_source,x); judge_score does_not_imply feasible_claim
```

**Variables:** D: actual source-derived domain; declared_distinction: claimed manipulation; judge_score: protocol rubric score, not proof evidence

**Falsifier:** The source makes the claimed distinction unattainable; revise the proposal, without claiming general evaluator reliability from a known-case repair.

**Required evidence:** provide an independent auditor the declared claim, executed equation and intervention manifest; derive the reachable property without the sealed later outcome, and preserve original scores alongside any correction reproducible source-grounded validity of the discriminator before a score is used to justify mechanism inference or an expensive launch

**Verification boundary:** `source_and_empirical`; registry ID `source-aware-evaluator-check`. Local candidate tactics: `linarith`, `interval_check`. Independent scoped evidence is required; runtime enforcement is not implemented.

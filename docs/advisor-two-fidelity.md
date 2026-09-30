# Experimental two-fidelity evidence planning

This optional Advisor adapter applies interval-based evidence planning to an explicitly supplied finite value tree. It is inspired by Chen and Chen's [2FFS paper, v2 (2026-09-29)](https://arxiv.org/abs/2606.01708v2), whose [algorithms and proofs](https://arxiv.org/html/2606.01708v2) distinguish cheap biased evaluations from expensive stochastic node evaluations.

It is an experimental planning tool. It does not yet implement the paper's complete scale certificates, recursive race budgets or asynchronous oracle driver. It is not an MCTS rollout service, and passing its software tests does not establish improved scientific advice, statistical calibration or the paper's cost bound.

## What the adapter does

- Retains lower/upper bounds for each node, including intersections over every prefix of supplied slow samples.
- Propagates MAX/MIN bounds, identifies a leader and challenger, and requests evidence on a critical endpoint witness.
- Proposes a cheap expansion or a slow evidence request when its declared future cost fits a comparable budget.
- Stops when the supplied bounds separate a root action within the requested epsilon. The result is conditional on the declared objective and oracle assumptions.
- Preserves missing evidence and costs, reports contradictory intervals, and leaves execution authority unchanged.

A condition-dependency graph is not automatically a numeric minimax tree. Declare the objective, units and scope separately, and bind root actions to current READY Advisor candidate IDs. A tree supplied for one objective does not rank directions for a different objective.

## Use

Add an optional `two_fidelity` object to the existing `--research-context` JSON. The normal graph search still supplies the candidates. Advisor adds `two_fidelity_selection` to the recommendation, which also appears in the offline dashboard.

```sh
python -B scripts/rds_cli.py --root <project> advise \
  --research-context <context.json> --graph <graph.json>
```

With `--artifacts <manifest.json>`, node observations can refer to imported fact IDs. The importer retains file locations and conflict/reliability status. The manual context retains its declared identity. A JSON `ARTIFACT_OBSERVED` field cannot manufacture the importer's provenance.

The schema is `rds-two-fidelity-v1`. Its objective defines `direction`, `metric`, `unit` and `scope`; its tree defines a root and MAX/MIN/LEAF nodes. Fast evaluations require a known bias bound. Slow records require explicit independence, a node-value target, a sub-Gaussian parameter and a known bias bound. These are model assumptions, not facts proven by a source label.

Future action costs require one named resource, unit and `comparison_group`, plus a source and an explicit estimate. A historical receipt measures past work; its `prediction_status: UNKNOWN` cannot become a known future cost. No CPU/GPU/API conversion is invented. Suggested work is not debited from the execution ledger.

## Evidence needed before claiming usefulness

The current historical and RSI fixtures support engineering checks. They do not supply independent scientific rollout rewards and calibrated fast/slow oracles. Simulated values or repeated model self-scores do not fill that gap.

A useful comparison must freeze the candidates, available observations and total budget before comparing the current finite-rule search, a simple deterministic selection baseline, and an eligible stochastic policy. Assess independent outcome labels, incorrect selections/claims, retained useful candidates, evidence requests and their total cost, including failures. Without independent labels, report only checked software behavior. Do not claim Monte Carlo adds value merely because this adapter passes tests.

No GPU, paid model call or additional seed campaign is required to check the adapter's interval, provenance, cost and stopping behavior. A real research-utility experiment remains conditional on having a suitable project, observable outcomes and an authorized budget.

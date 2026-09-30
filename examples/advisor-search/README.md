# Bounded Advisor search prototype

Run `python examples/advisor-search/run_example.py`. Every fact and cost in this
example is synthetic, and is labelled `INPUT_REPORTED`, never a verified receipt.
The example equation/range shows that the rho=1 arm cannot cross m>=1; the
program blocks the strict-crossing candidate and offers a narrower interpretation
plus a read of actual crossing logs. It does not solve arbitrary equations.

`search_directions(graph, context)` reads `decision`, source-anchored `facts`,
optional observed `costs`, and a sourced `budget`. RDS reads the same object from
`state.advisor_context`. Conditions use explicit fact names and comparison
operators; missing source or explicitly unreliable evidence is `UNKNOWN`.
Only `prerequisite_for` edges compose tests. Text rules stay review requests.

The output binds competing explanations, required observables and each outcome
to a next decision, then records fact → rule → prerequisite → action derivations.
Unknown prerequisites offer concrete read-only queries; false prerequisites
block the dependent experiment. There are depth/node/candidate bounds and cycle
reports. No experiment, new model, source check or filesystem mutation is run.

Ranking is a partial Pareto order over declared decision coverage and observed
incremental cost only when units and comparison groups match. Unknown costs have
no guessed rank. No multi-seed run is inserted: a separately configured candidate
would need sourced `seed_instability_observed=true` and `decision_sensitive=true`
preconditions before it could be considered.

# RDS native Lean library

Pinned toolchain: Lean **4.33.1**, mathlib **v4.33.1**, commit
`0df444a360eaa60ab8c11dca51a86af692955474` (also locked in `lake-manifest.json`).

From this directory:

```powershell
$env:MATHLIB_CACHE_DIR = Join-Path (Get-Location).Path '.lake/cache'
lake exe cache get
lake build
```

The library proves conditional mathematical statements. A kernel-checked import
does **not** verify that an actual dataset, training run or sampling procedure
satisfies their hypotheses.

| API | Mathematical assumptions and conclusion |
| --- | --- |
| `Formal.Probability.ville` | Finite measure, sigma-finite filtration, real-valued nonnegative supermartingale: infinite countable-time threshold-crossing bound by its initial expectation. |
| `Formal.Probability.ville_test` | Probability measure plus the above conditions, initial expectation at most one, positive level `α`: anytime crossing of `1/α` has probability at most `α`. |
| `Formal.Probability.hoeffding` | Probability measure, independent a.e. measurable random variables, specified a.e. intervals and zero expectations: finite-sum one-sided Hoeffding bound. |
| `Formal.Probability.hoeffding_centered` | The same independence, measurability and interval conditions; subtracts actual integrals, so raw variables need not have mean zero. |
| `Formal.Probability.hoeffding_subgaussian` | Explicit independent sub-Gaussian MGF conditions: finite-sum right-tail bound. |
| `Formal.Information.markov_dpi` | Probability source and two Markov kernels generating `X → Y → Z`: KL-defined joint-versus-product-marginal mutual information satisfies `I(X;Z) ≤ I(X;Y)`, including infinite values. |
| `Formal.Information.kl_markov_dpi` | Finite measures and a common Markov kernel: KL divergence contracts. |
| `Formal.gershgorin`, `Formal.eigenvalue_norm_lt_one` | Finite square normed-field matrix and a genuine eigenvalue; row norm bounds localize/bound eigenvalues, without claiming Euclidean operator norm. |
| `Formal.scaled_contraction`, `Formal.residual_lipschitz_bound` | A K-Lipschitz map: scaling contracts when `‖α‖K < 1`; residual `I+αF` only gets the bound `1+‖α‖K`. |
| `Formal.residual_contraction` | A continuous linear residual map with actual operator bound `‖I+A‖ ≤ q < 1` contracts. |
| `Formal.relu_homogeneous`, `Formal.linear_homogeneous`, `Formal.scale_invariance` | ReLU is positively homogeneous; bias-free real linear maps preserve scaling and positive-scale normalization. |

`Probability/Martingale.lean` adapts Rob Sneiderman's Apache-2.0 proof from
[`formal-martingales`, commit `1e49307ce983fe472b35400a79052bb607298123`](https://github.com/Robby955/formal-martingales/blob/1e49307ce983fe472b35400a79052bb607298123/FormalMartingales/Martingale/Ville.lean),
retaining copyright and attribution. The remaining mathematical results reuse
mathlib's Apache-2.0 library. See `LICENSE`.

No proof uses `sorry`, a custom axiom, or `native_decide`. The intended audit allows
only Lean's foundational `propext`, `Classical.choice`, and `Quot.sound` axioms.

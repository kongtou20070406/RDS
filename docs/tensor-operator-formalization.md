# Formalizing tensor-operator equivalence

Research checked: 2026-10-02; toolchain policy updated: 2026-10-03. This document proposes a staged extension of RDS's concrete exact-tensor evaluator. It distinguishes upstream capabilities, RDS implementation, and future engineering work; no new verifier backend is claimed here.

## Recommendation

Extend in this order: symbolic, shape-indexed tensor semantics and theorems in Lean; E-Graph candidate search with proof witnesses; replay in the Lean kernel; then bridges to concrete framework and hardware semantics. Start with finite-dimensional tensors over explicit real semantics. Keep concrete rational evaluation, real-valued theorems, IEEE floating-point execution, and model import as separate semantics. Reuse the proof core for later Riemannian and infinite-dimensional domains, but give those domains their own types and assumptions instead of folding them into the first array DSL.

RDS follows matching stable Lean/Mathlib releases, currently **4.34.1**, using the [paired upgrade procedure](lean-toolchain-upgrades.md). Exact versions and SHAs identify each accepted revision and its certificates; 4.33.1 is not a permanent constraint on dependency evaluation. Every upgrade needs a fresh build, axiom audit and native proof replay.

## Prior work and the gap

RDS's `rds_tensor_verify.py` evaluates bounded, concrete row-major tensors using exact rational addition, scaling, transpose, and non-broadcasting batched matrix multiplication. It checks supplied values; it does not prove symbolic identities for all tensors. The fixed-template Lean adapter likewise does not accept arbitrary Lean source or user tactics. See the [formal-verification guide](formal-verification.md) and [Lean ecosystem survey](lean4-ecosystem-survey.md).

| Work | Established capability | Role and limitation for RDS |
| --- | --- | --- |
| [TensorRight, POPL 2025](https://doi.org/10.1145/3704865) | Verifies tensor graph rewrites at arbitrary rank and size. Aggregated axes reduce unbounded cases to finitely many bounded SMT obligations. The paper reports proving 115 of 175 XLA algebraic simplifier rules in full generality. | Reference for rewrite semantics, shape preconditions, and differential benchmarks. SMT verification is not a Lean-kernel proof and is not an importable RDS Lean dependency. |
| [TENSAT, MLSys 2021](https://proceedings.mlsys.org/paper_files/paper/2021/file/cc427d934a7f6c0663e5923f49eba531-Paper.pdf) and [egg](https://popl21.sigplan.org/details/POPL-2021-research-papers/23/egg-Fast-and-Extensible-Equality-Saturation) | Equality saturation explores tensor rewrites and extracts a low-cost implementation. | Candidate search and graph extraction only. Correctness still depends on sound rules; saturation, lower cost, and tests do not constitute a proof. |
| [Equality saturation in Lean, POPL 2026](https://doi.org/10.1145/3776667) | Treats Lean theorems as conditional rewrite rules, records E-Graph explanations, reconstructs Lean-checked proofs, and leaves rule conditions as proof obligations. | Best fit for scalable search with kernel adjudication. Before adoption, pin and audit the upstream commit, Lean compatibility, condition handling, proof reconstruction, and license; probe against the current accepted stable pair, upgrading the pair when needed. |
| [TorchLean](https://github.com/lean-dojo/TorchLean) and [paper](https://arxiv.org/abs/2602.22631) | A Lean framework for shape-indexed tensors, network semantics, graph transformations, and certificate checking; current project sources include real and IEEE floating-point paths. | Closest deep-learning reference and dependency candidate. As checked on 2026-10-03, upstream commit `b062b9a3f0e4b10b1d06ff8231adc93d6c1caa36` pins Lean/Mathlib 4.34.0; this RDS revision uses 4.34.1. Rebuild and test the candidate against RDS's current stable pair in an isolated Lake workspace; do not mix `.olean` artifacts. Port selected theorems or maintain a separately versioned subproject only if compatibility evidence warrants it. Runtime/FFI existence does not prove correspondence with mathematical semantics. |
| [Mathlib tensor products](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Analysis/InnerProductSpace/TensorProduct.html) and [continuous linear maps](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Analysis/Normed/Operator/ContinuousLinearMap.html) | Abstract inner-product tensor products, operator maps, and continuous linear maps. | Mathlib is already an RDS dependency; prefer a thin wrapper and compile against the current accepted stable pair. A projective tensor product over a finite family does not imply coverage of every completed Hilbert tensor product. |
| [Mathlib Riemannian basics](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Geometry/Manifold/Riemannian/Basic.html) and [Levi-Civita connection](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Geometry/Manifold/VectorBundle/CovariantDerivative/LeviCivita.html) | Riemannian manifold basics; the current Levi-Civita file explicitly targets finite-dimensional manifolds. | Reuse in a later geometry module. Tensor fields are sections of bundles and require tangent/cotangent bundles, smoothness, metric, and chart transformations; they are not array ASTs under another name. Do not infer general infinite-dimensional Riemannian coverage. |

TensorRight supplies a concrete precedent for reducing arbitrary-dimension rule verification to finite obligations. Lean equality saturation supplies a way to kernel-check rewrite paths. Combining them requires an explicit bridge between their DSLs and semantics.

## Staged engineering plan

### 1. Symbolic finite-dimensional tensors

Define a tensor expression language in the existing Mathlib-pinned project, indexed by `Shape : List Nat`. Its types should distinguish scalar domain, shape, layout, and arithmetic semantics. Begin with same-shape addition, scalar multiplication, axis permutation/transpose, matrix multiplication, and contraction. Add broadcasting, reshape, reductions, dynamic dimensions, and sparse structures only after their semantics and edge cases are specified.

Theorems should quantify over every well-shaped input tensor. Dimension equality, index bounds, and nonempty-reduction assumptions must appear in types or theorem premises. A graph-import layer separately checks that imported nodes implement the denotation. Initial targets include matrix multiplication associativity and transpose/multiplication laws, followed by batched rules and edge shapes.

### 2. E-Graph searches; Lean decides

The rule registry should contain only named rules backed by Lean theorems, with direction, substitutions, premises, and version. E-Graph input must not turn arbitrary user-executable rules into trusted facts. Each extraction path emits rule IDs, directions, match locations, substitutions, and premise obligations. An independent replayer reconstructs the goal from the original AST and asks the Lean kernel to check it. A proof generator may suggest terms but cannot alter the goal or semantic definitions.

Bind certificates to canonical AST, shape/layout, scalar semantics, rule-registry hash, Lean/Mathlib pins, imported-model hash, and checker version. A closed proof yields PASS; only a counterexample checked under supported semantics yields FAIL; missing rules, open premises, timeouts, exhausted budgets, and missing semantic bridges yield UNKNOWN. Saturation or lower-cost extraction cannot change the status on its own.

### 3. Numeric and model boundaries

Separate equality over mathematical reals from implementation equivalence. Reassociation over `ℝ` is generally not unconditional for Float32/Float64: rounding, overflow, NaNs, subnormals, FMA, parallel reduction order, and device kernels can change results. A floating-point result must bind IEEE operations and an explicit error/observational relation, then prove that graph import or export corresponds to the target runtime. TorchLean is a candidate dependency/reference. Test it against the current stable pair in an isolated subproject; a paired RDS upgrade is allowed when needed and must pass the repository's build and replay checks.

### 4. Riemannian and infinite-dimensional domains

Start geometry with finite-dimensional Riemannian manifolds: tangent/cotangent tensors, bundle maps, metric-induced index raising/lowering, covariant derivative, curvature, and equivariant transformations. State smoothness, dimension, chart, and metric nondegeneracy assumptions for every theorem. Applications to optimizer state or parameter manifolds also need a mapping from the actual algorithm to the geometric objects.

For infinite-dimensional theory, first specify the object class rather than adding a generic “higher tensor”: bounded operators on Banach/Hilbert spaces, continuous multilinear maps, algebraic tensor products, projective/injective tensor norms, and Hilbert tensor completions are distinct. Operator norm bounds, continuous extension, equality on dense subsets, operator domains, and closedness belong in theorem premises. A Mathlib interface for tensor products of a finite family whose factors may be infinite-dimensional does not establish all completed tensor-product or infinite-dimensional manifold results.

## Anti-gaming acceptance criteria

| Case | Expected result |
| --- | --- |
| Correct matrix associativity rewrite for every legal dimension | PASS after Lean kernel replay, with theorem and axiom dependencies shown. |
| Omit the matrix multiplication contraction-dimension condition | Rejected by shape checking or a checked failure; never silently broadcast. |
| Inject an invalid rewrite, such as swapping noncommuting matrix factors | UNKNOWN when Lean cannot prove it; never PASS because E-Graph merged the nodes. |
| A conditional rule has an unproved premise, or E-Graph hits node/time limits | UNKNOWN with open obligations and resource record. |
| Reassociation changes the result under actual floating-point semantics | A real-number theorem cannot yield PASS; return a counterexample or UNKNOWN. |
| Graph, opset/version, shape, weights, or execution semantics change | Reject the old certificate because its input binding no longer matches. |
| A manifold or infinite-operator theorem lacks regularity/boundedness assumptions | Do not infer those premises from finite-array rules. |

The first implementation milestone should be a separately buildable Lean symbolic-tensor theorem probe and certificate format, followed by isolated dependency evaluations for Lean equality saturation and TorchLean. Register a production RDS backend only after proof replay, invalid-rule rejection, shape failures, and semantic distinctions pass. The toolchain upgrade procedure is implemented separately; this tensor design does not claim that the candidate dependencies or a general tensor backend have been integrated.

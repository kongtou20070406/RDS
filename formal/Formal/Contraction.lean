import Mathlib.Analysis.Normed.Operator.Basic
import Mathlib.Topology.MetricSpace.Contracting

open scoped NNReal

namespace Formal

/-- Scaling a K-Lipschitz map really gives a contraction when `‖α‖ * K < 1`. -/
theorem scaled_contraction {E : Type*} [NormedAddCommGroup E] [NormedSpace ℝ E]
    {f : E → E} {K : ℝ≥0} (hf : LipschitzWith K f) (α : ℝ)
    (hsmall : ‖α‖₊ * K < 1) :
    ContractingWith (‖α‖₊ * K) (fun x ↦ α • f x) :=
  ⟨hsmall, (lipschitzWith_smul α).comp hf⟩

/-- General residual blocks have this upper bound; `‖α‖ * K < 1` alone does not
make the residual block a contraction. -/
theorem residual_lipschitz_bound {E : Type*} [NormedAddCommGroup E] [NormedSpace ℝ E]
    {f : E → E} {K : ℝ≥0} (hf : LipschitzWith K f) (α : ℝ) :
    LipschitzWith (1 + ‖α‖₊ * K) (fun x ↦ x + α • f x) :=
  LipschitzWith.id.add ((lipschitzWith_smul α).comp hf)

/-- A linear residual update contracts when the norm of its actual update operator `I + A`
is bounded by a constant below one. Bounding `A` alone does not establish this condition. -/
theorem residual_contraction {E : Type*} [NormedAddCommGroup E] [NormedSpace ℝ E]
    (A : E →L[ℝ] E) {q : ℝ≥0} (hq : q < 1)
    (hoperator : ‖ContinuousLinearMap.id ℝ E + A‖ ≤ (q : ℝ)) :
    ContractingWith q (fun x : E ↦ x + A x) := by
  refine ⟨hq, ?_⟩
  apply LipschitzWith.of_dist_le_mul
  intro x y
  have heq : x + A x - (y + A y) = (ContinuousLinearMap.id ℝ E + A) (x - y) := by
    rw [map_sub]
    rfl
  rw [dist_eq_norm, dist_eq_norm, heq]
  exact (ContinuousLinearMap.id ℝ E + A).le_of_opNorm_le hoperator (x - y)

/-- The contraction statement gives the concrete pairwise residual-distance bound. -/
theorem residual_distance_bound {E : Type*} [NormedAddCommGroup E] [NormedSpace ℝ E]
    (A : E →L[ℝ] E) {q : ℝ≥0} (hq : q < 1)
    (hoperator : ‖ContinuousLinearMap.id ℝ E + A‖ ≤ (q : ℝ)) (x y : E) :
    dist (x + A x) (y + A y) ≤ q * dist x y :=
  (residual_contraction A hq hoperator).toLipschitzWith.dist_le_mul x y

end Formal

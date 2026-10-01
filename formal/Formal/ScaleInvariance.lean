import Mathlib.Analysis.Normed.Operator.Basic

namespace Formal

/-- Scalar ReLU, with its actual positive-homogeneity proof. -/
def relu (x : ℝ) : ℝ := max 0 x

theorem relu_homogeneous {c : ℝ} (hc : 0 ≤ c) (x : ℝ) :
    relu (c * x) = c * relu x := by
  rcases le_total 0 x with hx | hx
  · simp only [relu, max_eq_right hx, max_eq_right (mul_nonneg hc hx)]
  · simp only [relu, max_eq_left hx,
      max_eq_left (mul_nonpos_of_nonneg_of_nonpos hc hx), mul_zero]

/-- Bias-free real linear maps preserve scalar multiplication. -/
theorem linear_homogeneous {E F : Type*} [NormedAddCommGroup E] [NormedAddCommGroup F]
    [NormedSpace ℝ E] [NormedSpace ℝ F] (L : E →L[ℝ] F) (c : ℝ) (x : E) :
    L (c • x) = c • L x := L.map_smul c x

/-- Normalization removes every positive input scale for a bias-free linear map,
including zero output (whose normalization is defined as zero). -/
theorem scale_invariance {E F : Type*} [NormedAddCommGroup E] [NormedAddCommGroup F]
    [NormedSpace ℝ E] [NormedSpace ℝ F] (L : E →L[ℝ] F)
    {c : ℝ} (hc : 0 < c) (x : E) :
    ‖L (c • x)‖⁻¹ • L (c • x) = ‖L x‖⁻¹ • L x := by
  rw [linear_homogeneous, norm_smul, Real.norm_eq_abs, abs_of_pos hc, mul_inv,
    smul_smul]
  congr 1
  rw [mul_assoc, mul_comm ‖L x‖⁻¹ c, ← mul_assoc, inv_mul_cancel₀ hc.ne', one_mul]

end Formal

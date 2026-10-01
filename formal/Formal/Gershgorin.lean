import Mathlib.LinearAlgebra.Matrix.Gershgorin

namespace Formal

/-- Gershgorin localization of every eigenvalue of a finite square matrix. -/
theorem gershgorin {K n : Type*} [NormedField K] [Fintype n] [DecidableEq n]
    {A : Matrix n n K} {z : K}
    (hz : Module.End.HasEigenvalue (Matrix.toLin' A) z) :
    ∃ i, z ∈ Metric.closedBall (A i i) (∑ j ∈ Finset.univ.erase i, ‖A i j‖) :=
  eigenvalue_mem_ball hz

/-- A strict row-norm bound puts every eigenvalue strictly inside the unit disk.
This is a spectral conclusion, not a claim about a training graph or Euclidean operator norm. -/
theorem eigenvalue_norm_lt_one {K n : Type*} [NormedField K] [Fintype n] [DecidableEq n]
    {A : Matrix n n K} {z : K}
    (hz : Module.End.HasEigenvalue (Matrix.toLin' A) z)
    (hrows : ∀ i, ‖A i i‖ + ∑ j ∈ Finset.univ.erase i, ‖A i j‖ < 1) :
    ‖z‖ < 1 := by
  obtain ⟨i, hi⟩ := gershgorin hz
  have hball : ‖z - A i i‖ ≤ ∑ j ∈ Finset.univ.erase i, ‖A i j‖ := by
    simpa only [Metric.mem_closedBall, dist_eq_norm] using hi
  calc
    ‖z‖ = ‖(z - A i i) + A i i‖ := by rw [sub_add_cancel]
    _ ≤ ‖z - A i i‖ + ‖A i i‖ := norm_add_le _ _
    _ ≤ (∑ j ∈ Finset.univ.erase i, ‖A i j‖) + ‖A i i‖ := add_le_add hball le_rfl
    _ < 1 := by simpa only [add_comm] using hrows i

end Formal

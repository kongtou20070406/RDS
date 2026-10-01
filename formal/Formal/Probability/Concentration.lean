import Mathlib.Probability.Moments.SubGaussian

open MeasureTheory ProbabilityTheory
open scoped NNReal ENNReal

namespace Formal.Probability

/-- Hoeffding's right-tail bound with explicit sub-Gaussian MGF assumptions. -/
theorem hoeffding_subgaussian {Ω ι : Type*} [MeasurableSpace Ω]
    {μ : Measure Ω} {X : ι → Ω → ℝ} (hindep : iIndepFun X μ)
    {c : ι → ℝ≥0} {s : Finset ι}
    (hsub : ∀ i ∈ s, HasSubgaussianMGF (X i) (c i) μ)
    {ε : ℝ} (hε : 0 ≤ ε) :
    μ.real {ω | ε ≤ ∑ i ∈ s, X i ω} ≤
      Real.exp (-ε ^ 2 / (2 * ∑ i ∈ s, c i)) :=
  HasSubgaussianMGF.measure_sum_ge_le_of_iIndepFun hindep hsub hε

/-- Hoeffding for independent, a.e. measurable, bounded zero-mean variables.
The denominator is `2 * sum ((b_i-a_i)/2)^2`, i.e. the usual `sum (b_i-a_i)^2 / 2`.
This is a conditional distribution theorem, not verification of a sample's assumptions. -/
theorem hoeffding {Ω ι : Type*} [MeasurableSpace Ω]
    {μ : Measure Ω} [IsProbabilityMeasure μ] {X : ι → Ω → ℝ}
    (hindep : iIndepFun X μ) {s : Finset ι} {a b : ι → ℝ}
    (hmeas : ∀ i ∈ s, AEMeasurable (X i) μ)
    (hbounds : ∀ i ∈ s, ∀ᵐ ω ∂μ, X i ω ∈ Set.Icc (a i) (b i))
    (hmean : ∀ i ∈ s, ∫ ω, X i ω ∂μ = 0)
    {ε : ℝ} (hε : 0 ≤ ε) :
    μ.real {ω | ε ≤ ∑ i ∈ s, X i ω} ≤
      Real.exp (-ε ^ 2 / (2 * ∑ i ∈ s, (((‖b i - a i‖₊ / 2) ^ 2 : ℝ≥0) : ℝ))) := by
  simpa only [NNReal.coe_sum] using hoeffding_subgaussian hindep
    (fun i hi ↦ hasSubgaussianMGF_of_mem_Icc_of_integral_eq_zero
      (hmeas i hi) (hbounds i hi) (hmean i hi)) hε

/-- The usual centered Hoeffding bound requires no zero-mean assumption on the raw variables. -/
theorem hoeffding_centered {Ω ι : Type*} [MeasurableSpace Ω]
    {μ : Measure Ω} [IsProbabilityMeasure μ] {X : ι → Ω → ℝ}
    (hindep : iIndepFun X μ) {s : Finset ι} {a b : ι → ℝ}
    (hmeas : ∀ i ∈ s, AEMeasurable (X i) μ)
    (hbounds : ∀ i ∈ s, ∀ᵐ ω ∂μ, X i ω ∈ Set.Icc (a i) (b i))
    {ε : ℝ} (hε : 0 ≤ ε) :
    μ.real {ω | ε ≤ ∑ i ∈ s, (X i ω - ∫ z, X i z ∂μ)} ≤
      Real.exp (-ε ^ 2 / (2 * ∑ i ∈ s, (((‖b i - a i‖₊ / 2) ^ 2 : ℝ≥0) : ℝ))) := by
  simpa only [NNReal.coe_sum, Function.comp_apply] using hoeffding_subgaussian
    (hindep.comp (fun i x ↦ x - ∫ z, X i z ∂μ) (fun _ ↦ measurable_id.sub_const _))
    (fun i hi ↦ hasSubgaussianMGF_of_mem_Icc (hmeas i hi) (hbounds i hi)) hε

end Formal.Probability

"""Audit selected conditional probability theorems, never empirical assumptions.

The finite input language names a theorem from the bundled, pinned Formal
library. A kernel PASS proves that quantified conditional statement only;
independence, supermartingale structure and the data-to-model link remain open.
"""
import json
from pathlib import Path
import re
import tempfile

import rds_lean_verify as lean
from rds_verify_types import MAX_CERTIFICATE_BYTES, canonical, digest, require

BACKEND = "lean4_statistical_library"
VERSION = 1
SEMANTICS = "conditional_statistical_theorem"
MATHLIB_REV = "d13f23b723b8a846827a245b89c10fc7d3f11612"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
THEOREMS = {
    "ville": ("Formal.Probability.Martingale", "Formal.Probability.ville_test", [
        "probability_input_measure", "sigma_finite_declared_filtration",
        "nonnegative_adapted_integrable_process", "supermartingale_under_declared_filtration",
        "initial_expectation_at_most_one", "positive_significance_level"]),
    "hoeffding": ("Formal.Probability.Concentration", "Formal.Probability.hoeffding", [
        "probability_input_measure", "finite_independent_family", "almost_everywhere_measurable_variables",
        "almost_sure_declared_interval_bounds", "zero_means", "nonnegative_tail_parameter"]),
    "dpi": ("Formal.Information.DPI", "Formal.Information.markov_dpi", [
        "probability_input_measure", "measurable_markov_kernels",
        "joint_law_and_marginal_product_definition", "declared_channel_composition"]),
}
STATEMENTS = {
    "ville": """theorem obligation {Ω : Type*} {m : MeasurableSpace Ω} {μ : Measure Ω}
    {F : Filtration ℕ m} {f : ℕ → Ω → ℝ}
    [IsProbabilityMeasure μ] [SigmaFiniteFiltration μ F]
    (h : Supermartingale f F μ) (hnonneg : 0 ≤ f)
    (hstart : μ[f 0] ≤ 1) {α : ℝ≥0} (hα : 0 < α) :
    μ {ω | ∃ n : ℕ, ((α⁻¹ : ℝ≥0) : ℝ) ≤ f n ω} ≤ (α : ℝ≥0∞) :=
  Formal.Probability.ville_test h hnonneg hstart hα
""",
    "hoeffding": """theorem obligation {Ω ι : Type*} [MeasurableSpace Ω]
    {μ : Measure Ω} [IsProbabilityMeasure μ] {X : ι → Ω → ℝ}
    (hindep : iIndepFun X μ) {s : Finset ι} {a b : ι → ℝ}
    (hmeas : ∀ i ∈ s, AEMeasurable (X i) μ)
    (hbounds : ∀ i ∈ s, ∀ᵐ ω ∂μ, X i ω ∈ Set.Icc (a i) (b i))
    (hmean : ∀ i ∈ s, ∫ ω, X i ω ∂μ = 0)
    {ε : ℝ} (hε : 0 ≤ ε) :
    μ.real {ω | ε ≤ ∑ i ∈ s, X i ω} ≤
      Real.exp (-ε ^ 2 / (2 * ∑ i ∈ s, (((‖b i - a i‖₊ / 2) ^ 2 : ℝ≥0) : ℝ))) :=
  Formal.Probability.hoeffding hindep hmeas hbounds hmean hε
""",
    "dpi": """theorem obligation {X Y Z : Type*}
    [MeasurableSpace X] [MeasurableSpace Y] [MeasurableSpace Z]
    (μ : Measure X) [IsProbabilityMeasure μ]
    (κ : Kernel X Y) (η : Kernel Y Z) [IsMarkovKernel κ] [IsMarkovKernel η] :
    Formal.Information.mutualInformation μ (η ∘ₖ κ) ≤
      Formal.Information.mutualInformation μ κ :=
  Formal.Information.markov_dpi μ κ η
""",
}


def _metadata(spec):
    return {"conditional_statement": True, "application_status": "UNKNOWN",
            "assumptions_required": THEOREMS[spec["theorem"]][2] + ["empirical_model_correspondence"]}


def render_source(spec):
    require(isinstance(spec, dict), "Specification must be an object")
    require(len(canonical(spec).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Specification exceeds size limit")
    require(set(spec) == {"schema", "kind", "theorem"},
            "Statistical obligation requires exactly schema, kind and theorem; parameters/assumptions are unsupported")
    require(type(spec["schema"]) is int and spec["schema"] == 1, "Unsupported specification schema")
    require(spec["kind"] == "statistical_obligation", "Unsupported statistical obligation kind")
    require(isinstance(spec["theorem"], str) and spec["theorem"] in THEOREMS,
            "Supported statistical theorems are ville, hoeffding and dpi")
    module = THEOREMS[spec["theorem"]][0]
    return (f"import {module}\nset_option maxHeartbeats 200000\n"
            "open MeasureTheory ProbabilityTheory\n"
            "open scoped NNReal ENNReal BigOperators MeasureTheory ProbabilityTheory\nnamespace RDS\n"
            + STATEMENTS[spec["theorem"]] + "end RDS\n#print axioms RDS.obligation\n")


def _library(module):
    """Only existing package artifacts; discovery never builds or downloads."""
    root = lean.FORMAL_ROOT
    required = [root / name for name in ("lakefile.lean", "lean-toolchain", "lake-manifest.json")]
    require(all(path.is_file() for path in required), "Formal library is not configured; run lake build explicitly")
    manifest = json.loads(required[2].read_text(encoding="utf-8"))
    packages = manifest.get("packages")
    require(isinstance(packages, list), "Formal package manifest is invalid")
    paths = [root / ".lake" / "build" / "lib" / "lean"]
    names, revisions = set(), {}
    for package in packages:
        name = package.get("name")
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", name),
                "Formal dependency has an invalid package name")
        require(name not in names, "Duplicate Formal dependency")
        names.add(name)
        revisions[name] = package.get("rev")
        compiled_path = root / ".lake" / "packages" / name / ".lake" / "build" / "lib" / "lean"
        if name == "mathlib":
            require(compiled_path.is_dir(), "Formal mathlib artifacts are missing; run lake build explicitly")
        if compiled_path.is_dir():
            paths.append(compiled_path)
    require(revisions.get("mathlib") == MATHLIB_REV, "Formal mathlib dependency does not match its pinned revision")
    require(paths[0].is_dir(), "Formal library artifacts are missing; run lake build explicitly")
    compiled = paths[0] / Path(*module.split(".")).with_suffix(".olean")
    source = root / Path(*module.split(".")).with_suffix(".lean")
    require(compiled.is_file() and source.is_file(), "Selected Formal theorem has no compiled module")
    require(compiled.stat().st_mtime_ns >= source.stat().st_mtime_ns,
            "Selected Formal module is stale; run lake build explicitly")
    require((root / "Formal.lean").is_file(), "Formal library root source is missing")
    files = required + [root / "Formal.lean"] + sorted((root / "Formal").rglob("*.lean"))
    files += sorted((paths[0] / "Formal").rglob("*.olean"))
    if (paths[0] / "Formal.olean").is_file():
        files.append(paths[0] / "Formal.olean")
    binding = {"files": {path.relative_to(root).as_posix(): digest(path.read_bytes()) for path in files},
               "mathlib_revision": MATHLIB_REV}
    return paths, binding, required[1].read_text(encoding="utf-8").strip()


def _axioms(stdout):
    if stdout.strip() == lean.AXIOM_AUDIT:
        return []
    match = re.fullmatch(r"'RDS\.obligation' depends on axioms: \[([A-Za-z0-9_.,\s]+)\]\s*", stdout)
    require(match is not None, "Lean proof is missing its exact theorem axiom audit")
    axioms = [item.strip() for item in match[1].split(",")]
    require(len(set(axioms)) == len(axioms) and set(axioms) <= ALLOWED_AXIOMS,
            "Lean theorem depends on an unsupported axiom")
    return sorted(axioms)


def _native_check(spec, source):
    module = THEOREMS[spec["theorem"]][0]
    paths, binding, toolchain = _library(module)
    executable, fingerprint = lean._executable()
    with tempfile.TemporaryDirectory(prefix="rds-statistical-") as folder:
        code, version = lean._run([str(executable), "--version"], folder)
        require(code == 0 and re.fullmatch(r"Lean \(version 4\.[0-9]+\.[^\r\n]+\)\s*", version),
                "Executable did not identify itself as Lean 4")
        expected = re.fullmatch(r"leanprover/lean4:v(4\.[0-9]+\.[0-9]+)", toolchain)
        require(expected is not None and version.startswith("Lean (version " + expected[1] + ","),
                "Native Lean version does not match the Formal toolchain")
        path = Path(folder) / "Obligation.lean"
        path.write_text(source, encoding="utf-8")
        code, stdout = lean._run([str(executable), "--trust=0", "--memory=4096", "--threads=1", str(path)],
                                folder, lean_path=paths, timeout_seconds=60)
    require(code == 0, "Lean did not prove the selected conditional statistical theorem: " + stdout[:2048])
    axioms = _axioms(stdout)
    return {"lean_version": version.strip(), "lean_executable_sha256": fingerprint,
            "library": binding, "axioms": axioms, "stdout": stdout}


def _certificate(spec, source, checked):
    return {"schema": 1, "backend": BACKEND, "version": VERSION, "verdict": "PASS",
            "assurance": "LEAN_KERNEL_CHECKED", "semantics": SEMANTICS,
            "spec_sha256": digest(spec), "source": source, "source_sha256": digest(source.encode("utf-8")),
            "theorem": THEOREMS[spec["theorem"]][1], "axioms": checked["axioms"],
            "lean_version": checked["lean_version"], "lean_executable_sha256": checked["lean_executable_sha256"],
            "library": checked["library"], "library_sha256": digest(checked["library"]), **_metadata(spec)}


def verify(spec):
    try:
        source = render_source(spec)
        checked = _native_check(spec, source)
        return {"status": "PASS", "assurance": "LEAN_KERNEL_CHECKED", "backend": BACKEND,
                "semantics": SEMANTICS, "certificate": _certificate(spec, source, checked),
                "reason": "Conditional theorem checked; empirical application assumptions remain unverified",
                **_metadata(spec)}
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError, RecursionError, UnicodeError) as exc:
        metadata = _metadata(spec) if isinstance(spec, dict) and isinstance(spec.get("theorem"), str) and spec["theorem"] in THEOREMS else {}
        return {"status": "UNKNOWN", "assurance": "NONE", "backend": BACKEND,
                "semantics": SEMANTICS, "certificate": None, "reason": str(exc), **metadata}


def check_certificate(spec, certificate):
    """Re-render and replay the compiler; supplied Lean code is never executed."""
    try:
        require(isinstance(certificate, dict), "Certificate must be an object")
        require(len(canonical(certificate).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Certificate exceeds size limit")
        require(type(certificate.get("schema")) is int and certificate["schema"] == 1 and
                type(certificate.get("version")) is int and certificate["version"] == VERSION and
                certificate.get("conditional_statement") is True,
                "Unsupported statistical certificate schema or metadata")
        source = render_source(spec)
        require(certificate.get("source") == source and certificate.get("spec_sha256") == digest(spec) and
                certificate.get("source_sha256") == digest(source.encode("utf-8")), "Certificate binding mismatch")
        return certificate == _certificate(spec, source, _native_check(spec, source))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError, RecursionError, UnicodeError):
        return False

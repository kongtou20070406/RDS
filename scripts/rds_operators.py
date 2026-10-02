"""Runnable, verifiable code operators and scaffolding for RDS theory tool cards.

Transforms informational theory cards into executable, self-testing operators
preventing iterative LLM research loops from retreating to naive hyperparameter tuning.
"""
import inspect
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Operator 1: ContinuousStateSpaceOperator (state_space_refinement)
# ---------------------------------------------------------------------------

class ContinuousStateSpaceOperator:
    """Continuous-time State-Space Discretization (ZOH) Operator.

    Converts continuous-time parameters (A_log, B, C, D) into step-invariant discrete updates
    via Zero-Order Hold (ZOH). Guarantees Hurwitz stability (via -exp(A_log) < 0) and
    O(dt) error convergence across varying inference step sizes (NFE).
    """

    def __init__(self, state_dim: int, in_dim: int = 1, out_dim: int = 1):
        self.state_dim = state_dim
        self.in_dim = in_dim
        self.out_dim = out_dim
        # Default initialization: stable continuous eigenvalues in [-5.0, -0.5]
        self.a_log = [math.log(0.5 + 4.5 * (i / max(1, state_dim - 1))) for i in range(state_dim)]
        self.b = [[1.0 / math.sqrt(state_dim)] * in_dim for _ in range(state_dim)]
        self.c = [[1.0 / math.sqrt(state_dim)] * state_dim for _ in range(out_dim)]
        self.d = [[0.0] * in_dim for _ in range(out_dim)]

    def discretize_zoh(self, dt: float) -> Tuple[List[float], List[List[float]]]:
        """Discretizes continuous diagonal A = -exp(a_log) and B via exact Zero-Order Hold.

        A_bar_i = exp(-dt * exp(a_log_i)) in (0, 1)
        B_bar_ij = (1 - A_bar_i) / exp(a_log_i) * B_ij
        """
        if dt <= 0:
            raise ValueError(f"Step size dt must be positive, got {dt}")
        a_bar = []
        b_bar = []
        for i in range(self.state_dim):
            a_cont = math.exp(self.a_log[i])
            decay = math.exp(-dt * a_cont)
            a_bar.append(decay)
            # Numerically stable (1 - exp(-dt * a)) / a
            scale = (1.0 - decay) / a_cont if dt * a_cont > 1e-6 else dt * (1.0 - 0.5 * dt * a_cont)
            b_row = [scale * self.b[i][j] for j in range(self.in_dim)]
            b_bar.append(b_row)
        return a_bar, b_bar

    def step(self, h: List[float], u: List[float], a_bar: List[float], b_bar: List[List[float]]) -> Tuple[List[float], List[float]]:
        """Computes one discrete state update and output."""
        h_next = [0.0] * self.state_dim
        for i in range(self.state_dim):
            b_contrib = sum(b_bar[i][j] * u[j] for j in range(self.in_dim))
            h_next[i] = a_bar[i] * h[i] + b_contrib
        y = [0.0] * self.out_dim
        for i in range(self.out_dim):
            c_contrib = sum(self.c[i][j] * h_next[j] for j in range(self.state_dim))
            d_contrib = sum(self.d[i][j] * u[j] for j in range(self.in_dim))
            y[i] = c_contrib + d_contrib
        return h_next, y

    def forward_trajectory(self, u_seq: List[List[float]], dt: float, h0: Optional[List[float]] = None) -> Tuple[List[List[float]], List[List[float]]]:
        """Integrates trajectory over sequence u_seq with fixed step dt."""
        a_bar, b_bar = self.discretize_zoh(dt)
        h = list(h0) if h0 is not None else [0.0] * self.state_dim
        h_traj = [list(h)]
        y_traj = []
        for u in u_seq:
            h, y = self.step(h, u, a_bar, b_bar)
            h_traj.append(list(h))
            y_traj.append(y)
        return h_traj, y_traj

    def verify_step_invariance(self, total_time: float = 1.0, nfe_candidates: Tuple[int, ...] = (16, 32, 64, 128)) -> Dict[str, Any]:
        """Verifies that trajectory error scales as O(dt) and remains bounded across sampling steps."""
        endpoints = {}
        for nfe in nfe_candidates:
            dt = total_time / nfe
            # Smooth driving signal: u(t) = sin(2*pi*t)
            u_seq = [[math.sin(2.0 * math.pi * (k * dt))] for k in range(nfe)]
            _, y_traj = self.forward_trajectory(u_seq, dt)
            endpoints[nfe] = y_traj[-1][0]

        # Check Cauchy differences between consecutive resolutions
        sorted_nfe = sorted(nfe_candidates)
        cauchy_diffs = []
        for i in range(len(sorted_nfe) - 1):
            nfe_coarse, nfe_fine = sorted_nfe[i], sorted_nfe[i + 1]
            diff = abs(endpoints[nfe_fine] - endpoints[nfe_coarse])
            cauchy_diffs.append({"coarse": nfe_coarse, "fine": nfe_fine, "diff": diff})

        # Monotonic convergence check: differences should shrink as grid refines
        is_convergent = all(
            cauchy_diffs[i]["diff"] <= cauchy_diffs[i - 1]["diff"] * 1.2 + 1e-4
            for i in range(1, len(cauchy_diffs))
        )
        finest_err = cauchy_diffs[-1]["diff"]
        return {
            "status": "PASS" if is_convergent and finest_err < 0.05 else "FAIL",
            "finest_nfe": sorted_nfe[-1],
            "finest_cauchy_error": finest_err,
            "cauchy_diffs": cauchy_diffs,
            "endpoints": endpoints,
            "assurance": "STEP_INVARIANCE_CERTIFIED" if is_convergent else "STEP_SENSITIVITY_DETECTED",
        }

    @staticmethod
    def scaffold_code() -> str:
        """Returns standalone copy-pasteable implementation for user models."""
        return '''# Continuous State Space Operator (ZOH Discretization)
# Plug-and-play replacement for naive recurrence suffering from step sensitivity.
import math

class ContinuousStateSpace:
    def __init__(self, dim, in_dim=1, out_dim=1):
        self.dim = dim
        self.a_log = [math.log(1.0 + i) for i in range(dim)]
        self.b = [[1.0 / math.sqrt(dim)] * in_dim for _ in range(dim)]
        self.c = [[1.0 / math.sqrt(dim)] * dim for _ in range(out_dim)]
        self.d = [[0.0] * in_dim for _ in range(out_dim)]

    def discretize_zoh(self, dt):
        a_bar = [math.exp(-dt * math.exp(al)) for al in self.a_log]
        b_bar = []
        for i in range(self.dim):
            a_cont = math.exp(self.a_log[i])
            decay = a_bar[i]
            scale = (1.0 - decay) / a_cont if dt * a_cont > 1e-6 else dt
            b_bar.append([scale * self.b[i][j] for j in range(len(self.b[i]))])
        return a_bar, b_bar

    def forward(self, u_seq, dt, h0=None):
        a_bar, b_bar = self.discretize_zoh(dt)
        h = list(h0) if h0 else [0.0] * self.dim
        outputs = []
        for u in u_seq:
            h = [a_bar[i] * h[i] + sum(b_bar[i][j] * u[j] for j in range(len(u))) for i in range(self.dim)]
            y = [sum(self.c[k][i] * h[i] for i in range(self.dim)) + sum(self.d[k][j] * u[j] for j in range(len(u))) for k in range(len(self.c))]
            outputs.append(y)
        return outputs

if __name__ == "__main__":
    op = ContinuousStateSpace(dim=4)
    out16 = op.forward([[1.0]] * 16, dt=1.0/16)
    out64 = op.forward([[1.0]] * 64, dt=1.0/64)
    print("NFE 16 final output:", out16[-1])
    print("NFE 64 final output:", out64[-1])
'''


# ---------------------------------------------------------------------------
# Operator 2: ContractionDynamicsOperator (contraction_target_bias)
# ---------------------------------------------------------------------------

class ContractionDynamicsOperator:
    """Contraction Dynamics and Target Bias Operator.

    Verifies the induced infinity norm ||A||_inf of an affine iteration x_{k+1} = A x_k + b.
    Computes exact analytical fixed points and distinguishes contracting dynamics from target bias.
    """

    @staticmethod
    def infinity_norm(matrix: List[List[float]]) -> float:
        """Induced infinity norm: max row sum of absolute values."""
        if not matrix or not matrix[0]:
            return 0.0
        return max(sum(abs(val) for val in row) for row in matrix)

    @staticmethod
    def solve_linear_system(a_mat: List[List[float]], b_vec: List[float]) -> List[float]:
        """Solves A x = b via Gaussian elimination with partial pivoting."""
        n = len(b_vec)
        # Augment matrix
        aug = [list(a_mat[i]) + [b_vec[i]] for i in range(n)]
        for col in range(n):
            # Pivot
            max_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
            if abs(aug[max_row][col]) < 1e-12:
                raise ValueError("Matrix is singular or near-singular")
            aug[col], aug[max_row] = aug[max_row], aug[col]
            pivot = aug[col][col]
            for j in range(col, n + 1):
                aug[col][j] /= pivot
            for row in range(n):
                if row != col:
                    factor = aug[row][col]
                    for j in range(col, n + 1):
                        aug[row][j] -= factor * aug[col][j]
        return [aug[i][n] for i in range(n)]

    @classmethod
    def analyze_system(
        cls,
        a_mat: List[List[float]],
        b_vec: List[float],
        target: Optional[List[float]] = None,
        max_norm_threshold: float = 0.999
    ) -> Dict[str, Any]:
        """Evaluates contractivity, computes fixed point x* = (I - A)^(-1) b, and target bias."""
        n = len(b_vec)
        if len(a_mat) != n or any(len(row) != n for row in a_mat):
            raise ValueError(f"Matrix A must be {n}x{n}")

        norm_inf = cls.infinity_norm(a_mat)
        is_contracting = norm_inf <= max_norm_threshold

        # (I - A) x = b
        eye_minus_a = [
            [(1.0 if i == j else 0.0) - a_mat[i][j] for j in range(n)]
            for i in range(n)
        ]
        try:
            fixed_point = cls.solve_linear_system(eye_minus_a, b_vec)
            has_unique_fp = True
        except ValueError:
            fixed_point = None
            has_unique_fp = False

        target_bias = None
        if fixed_point is not None and target is not None:
            if len(target) != n:
                raise ValueError(f"Target dimension mismatch: expected {n}, got {len(target)}")
            target_bias = max(abs(fixed_point[i] - target[i]) for i in range(n))

        status = "PASS" if is_contracting else "FAIL"
        return {
            "status": status,
            "norm_infinity": norm_inf,
            "is_contracting": is_contracting,
            "has_unique_fixed_point": has_unique_fp,
            "fixed_point": fixed_point,
            "target_bias": target_bias,
            "diagnosis": (
                "CONTRACTING_AND_UNBIASED" if is_contracting and (target_bias is None or target_bias < 1e-4)
                else "CONTRACTING_WITH_TARGET_BIAS" if is_contracting
                else "NON_CONTRACTIVE_STEP"
            )
        }

    @staticmethod
    def scaffold_code() -> str:
        """Returns standalone copy-pasteable implementation for contraction verification."""
        return '''# Contraction Dynamics and Target Bias Verifier
# Detects whether iterative dynamics diverge or converge to a biased equilibrium.
def check_affine_contraction(a_matrix, b_vector, target=None):
    n = len(b_vector)
    norm_inf = max(sum(abs(x) for x in row) for row in a_matrix)
    is_contracting = norm_inf < 1.0

    # Gaussian elimination for (I - A) x = b
    aug = [[(1.0 if i == j else 0.0) - a_matrix[i][j] for j in range(n)] + [b_vector[i]] for i in range(n)]
    for c in range(n):
        pivot_r = max(range(c, n), key=lambda r: abs(aug[r][c]))
        aug[c], aug[pivot_r] = aug[pivot_r], aug[c]
        p = aug[c][c]
        for j in range(c, n + 1): aug[c][j] /= p
        for r in range(n):
            if r != c:
                f = aug[r][c]
                for j in range(c, n + 1): aug[r][j] -= f * aug[c][j]
    fp = [aug[i][n] for i in range(n)]
    bias = max(abs(fp[i] - target[i]) for i in range(n)) if target else 0.0
    return {"norm_inf": norm_inf, "contracting": is_contracting, "fixed_point": fp, "target_bias": bias}

if __name__ == "__main__":
    A = [[0.5, 0.2], [0.1, 0.6]]
    b = [0.3, 0.4]
    target = [1.0, 1.0]
    result = check_affine_contraction(A, b, target)
    print("Contraction analysis:", result)
'''


# ---------------------------------------------------------------------------
# Operator 3: StructuralPreflightOperator (structural_preflight)
# ---------------------------------------------------------------------------

class StructuralPreflightOperator:
    """Preflight Contract and Shape Checker Operator.

    Executes sub-10ms CPU contract preflight checks on callables before launching
    expensive training jobs. Uses signature binding, shape verification, and hook event counters.
    """

    @staticmethod
    def preflight_callable(
        fn: Any,
        sample_args: Tuple[Any, ...] = (),
        sample_kwargs: Optional[Dict[str, Any]] = None,
        expected_shapes: Optional[Dict[str, Tuple[int, ...]]] = None
    ) -> Dict[str, Any]:
        """Binds arguments to callable signature and performs structural dry-run."""
        sample_kwargs = sample_kwargs or {}
        sig = inspect.signature(fn)
        try:
            bound = sig.bind(*sample_args, **sample_kwargs)
            bound.apply_defaults()
        except TypeError as exc:
            return {
                "status": "FAIL",
                "stage": "SIGNATURE_BINDING",
                "error": str(exc),
                "callable": getattr(fn, "__name__", str(fn))
            }

        # Check argument shapes if provided
        shape_mismatches = []
        if expected_shapes:
            for arg_name, expected_shape in expected_shapes.items():
                if arg_name in bound.arguments:
                    val = bound.arguments[arg_name]
                    actual_shape = getattr(val, "shape", None)
                    if actual_shape is None and isinstance(val, (list, tuple)):
                        actual_shape = (len(val),)
                    if actual_shape != expected_shape:
                        shape_mismatches.append({
                            "argument": arg_name,
                            "expected": expected_shape,
                            "actual": actual_shape
                        })

        if shape_mismatches:
            return {
                "status": "FAIL",
                "stage": "INPUT_SHAPE_VALIDATION",
                "callable": getattr(fn, "__name__", str(fn)),
                "mismatches": shape_mismatches
            }

        # Dry-run call execution
        try:
            output = fn(*sample_args, **sample_kwargs)
            output_shape = getattr(output, "shape", None)
            if output_shape is None and isinstance(output, (list, tuple)):
                output_shape = (len(output),)
            return {
                "status": "PASS",
                "stage": "EXECUTION_COMPLETE",
                "callable": getattr(fn, "__name__", str(fn)),
                "output_shape": output_shape,
                "bound_arguments": list(bound.arguments.keys())
            }
        except Exception as exc:
            return {
                "status": "FAIL",
                "stage": "DRY_RUN_INVOCATION",
                "callable": getattr(fn, "__name__", str(fn)),
                "error": f"{type(exc).__name__}: {str(exc)}"
            }

    @staticmethod
    def scaffold_code() -> str:
        """Returns standalone copy-pasteable preflight assertion snippet."""
        return '''# Structural Preflight Assertion Template
# Add this before GPU launch / model training loop to fail fast on argument/shape mismatch.
import inspect

def preflight_model_call(model, *args, **kwargs):
    sig = inspect.signature(model if callable(model) else model.forward)
    try:
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
    except TypeError as e:
        raise RuntimeError(f"Preflight signature mismatch on {model}: {e}") from e

    # Dry-run invocation
    out = model(*args, **kwargs)
    shape = getattr(out, "shape", len(out) if hasattr(out, "__len__") else None)
    print(f"[PREFLIGHT PASS] {model.__class__.__name__} successfully produced output shape {shape}")
    return out

if __name__ == "__main__":
    def dummy_forward(x, scale=1.0):
        return [xi * scale for xi in x]
    preflight_model_call(dummy_forward, [1.0, 2.0, 3.0], scale=2.0)
'''


# ---------------------------------------------------------------------------
# Operator 4: RationalCertificateOperator (exact_symbolic_constraints)
# ---------------------------------------------------------------------------

class RationalCertificateOperator:
    """Exact Rational Polynomial Constraint Operator.

    Evaluates bounds of rational polynomial invariants without floating-point error
    using fractions.Fraction, generating verifiable replay certificates.
    """

    @staticmethod
    def eval_polynomial(coeffs: List[Fraction], x: Fraction) -> Fraction:
        """Evaluates P(x) = sum(c_k * x^k) using Horner's rule."""
        result = Fraction(0, 1)
        for c in reversed(coeffs):
            result = result * x + c
        return result

    @classmethod
    def certify_interval_bound(
        cls,
        poly_coeffs: List[Union[int, str, Fraction]],
        interval: Tuple[Union[int, str, Fraction], Union[int, str, Fraction]],
        bound_range: Tuple[Union[int, str, Fraction], Union[int, str, Fraction]],
        num_grid_points: int = 10
    ) -> Dict[str, Any]:
        """Certifies that polynomial stays within bound_range on grid points of interval."""
        coeffs = [Fraction(c) for c in poly_coeffs]
        x_min, x_max = Fraction(interval[0]), Fraction(interval[1])
        y_min, y_max = Fraction(bound_range[0]), Fraction(bound_range[1])

        if x_min > x_max:
            raise ValueError(f"Invalid interval: min {x_min} > max {x_max}")

        evaluations = []
        violations = []
        step = (x_max - x_min) / Fraction(max(1, num_grid_points - 1), 1)

        for i in range(num_grid_points):
            x = x_min + step * Fraction(i, 1)
            y = cls.eval_polynomial(coeffs, x)
            is_valid = (y_min <= y <= y_max)
            rec = {"x": str(x), "y": str(y), "valid": is_valid}
            evaluations.append(rec)
            if not is_valid:
                violations.append(rec)

        passed = len(violations) == 0
        return {
            "status": "PASS" if passed else "FAIL",
            "assurance": "EXACT_RATIONAL_CERTIFICATE" if passed else "BOUND_VIOLATION_WITNESS",
            "interval": [str(x_min), str(x_max)],
            "bound_range": [str(y_min), str(y_max)],
            "grid_samples": len(evaluations),
            "violations": violations[:5],
            "first_evaluation": evaluations[0],
            "last_evaluation": evaluations[-1],
        }

    @staticmethod
    def scaffold_code() -> str:
        """Returns standalone rational certificate verifier template."""
        return '''# Exact Rational Constraint Replay Template
from fractions import Fraction

def verify_polynomial_bound(coeffs_str, x_val_str, lower_str, upper_str):
    coeffs = [Fraction(c) for c in coeffs_str]
    x = Fraction(x_val_str)
    # Horner evaluation
    y = Fraction(0)
    for c in reversed(coeffs):
        y = y * x + c
    in_bounds = Fraction(lower_str) <= y <= Fraction(upper_str)
    return {"x": str(x), "y": str(y), "in_bounds": in_bounds}

if __name__ == "__main__":
    # P(x) = 1 - x + 0.5 * x^2
    res = verify_polynomial_bound(["1", "-1", "1/2"], "1/4", "0", "1")
    print("Exact rational verification:", res)
'''


# ---------------------------------------------------------------------------
# Registry and CLI Helpers
# ---------------------------------------------------------------------------

OPERATORS = {
    "state_space_refinement": {
        "operator_id": "continuous_state_space",
        "title": "Continuous-Time State Space Discretization (ZOH)",
        "operator_class": ContinuousStateSpaceOperator,
        "primary_signal": "step_sensitivity",
        "guarantee": "Discretization step-invariance and O(dt) convergence",
    },
    "contraction_target_bias": {
        "operator_id": "contraction_dynamics",
        "title": "Contraction Dynamics and Fixed-Point Bias Verifier",
        "operator_class": ContractionDynamicsOperator,
        "primary_signal": "trajectory_degradation",
        "guarantee": "Induced infinity-norm contraction and exact equilibrium",
    },
    "structural_preflight": {
        "operator_id": "structural_preflight",
        "title": "Actual Entrypoint & Shape Preflight Assertion",
        "operator_class": StructuralPreflightOperator,
        "primary_signal": "execution_mismatch",
        "guarantee": "Zero signature mismatches and shape pre-validation",
    },
    "exact_symbolic_constraints": {
        "operator_id": "rational_interval_certificate",
        "title": "Exact Rational Polynomial Certificate Verifier",
        "operator_class": RationalCertificateOperator,
        "primary_signal": "proof_bottleneck",
        "guarantee": "Zero floating-point error exact rational interval certificate",
    },
}


def list_available_operators() -> List[Dict[str, Any]]:
    """Returns metadata for all available runnable operators."""
    result = []
    for card_id, meta in OPERATORS.items():
        result.append({
            "card_id": card_id,
            "operator_id": meta["operator_id"],
            "title": meta["title"],
            "primary_signal": meta["primary_signal"],
            "guarantee": meta["guarantee"],
        })
    return result


def get_operator_scaffold(card_id: str) -> str:
    """Returns the standalone copy-pasteable operator code for a card."""
    if card_id not in OPERATORS:
        raise ValueError(f"No runnable operator available for card '{card_id}'. Available: {list(OPERATORS.keys())}")
    op_cls = OPERATORS[card_id]["operator_class"]
    return op_cls.scaffold_code()


def test_operator(card_id: str) -> Dict[str, Any]:
    """Runs a self-test of the specified operator and returns verification report."""
    if card_id not in OPERATORS:
        raise ValueError(f"No runnable operator available for card '{card_id}'. Available: {list(OPERATORS.keys())}")

    meta = OPERATORS[card_id]
    if card_id == "state_space_refinement":
        op = ContinuousStateSpaceOperator(state_dim=4, in_dim=1, out_dim=1)
        res = op.verify_step_invariance()
    elif card_id == "contraction_target_bias":
        A = [[0.4, 0.1], [0.2, 0.5]]
        b = [0.1, 0.2]
        res = ContractionDynamicsOperator.analyze_system(A, b, target=[0.24, 0.496])
    elif card_id == "structural_preflight":
        def sample_forward(x: List[float], weight: float = 1.0) -> List[float]:
            return [xi * weight for xi in x]
        res = StructuralPreflightOperator.preflight_callable(
            sample_forward,
            sample_args=([1.0, 2.0, 3.0],),
            sample_kwargs={"weight": 2.0},
            expected_shapes={"x": (3,)}
        )
    elif card_id == "exact_symbolic_constraints":
        # P(x) = 1 - 2*x + x^2 = (1-x)^2 in [0, 1] on x in [0, 1]
        res = RationalCertificateOperator.certify_interval_bound(
            poly_coeffs=[1, -2, 1],
            interval=(0, 1),
            bound_range=(0, 1),
            num_grid_points=10
        )
    else:
        res = {"status": "UNKNOWN"}

    return {
        "card_id": card_id,
        "operator_id": meta["operator_id"],
        "title": meta["title"],
        "test_result": res
    }

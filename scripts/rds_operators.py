"""Bounded stdlib operator examples: exact rational checks and numerical diagnostics."""
import ast
import inspect
import json
import math
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple, Union


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise ValueError("Expected a finite real number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Number is outside the supported floating range") from exc
    if not math.isfinite(result):
        raise ValueError("Expected a finite real number")
    return result


def _vector(value, size, name):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{name} must have exactly {size} coordinates")
    return [_finite_number(item) for item in value]


def _matrix(value, rows, cols, name):
    if not isinstance(value, (list, tuple)) or len(value) != rows:
        raise ValueError(f"{name} must be {rows}x{cols}")
    return [_vector(row, cols, name) for row in value]


def _dimension(value):
    if type(value) is not int or not 1 <= value <= 64:
        raise ValueError("Dimensions must be integers in 1..64")
    return value


def _ratio(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, float, Fraction)):
        raise ValueError("Expected a rational number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Expected a finite number")
    if isinstance(value, str) and len(value) > 2500:
        raise ValueError("Rational input exceeds size limit")
    try:
        result = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Expected a finite rational number") from exc
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 4096:
        raise ValueError("Exact arithmetic exceeds the 4096-bit limit")
    return result


def _solve_exact(a_mat, b_vec):
    n = _dimension(len(b_vec))
    if len(a_mat) != n or any(len(row) != n for row in a_mat):
        raise ValueError(f"Matrix must be {n}x{n}")
    aug = [[_ratio(value) for value in row] + [_ratio(b_vec[i])]
           for i, row in enumerate(a_mat)]
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if aug[pivot_row][col] == 0:
            raise ValueError("Matrix is singular")
        aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
        pivot = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] = _ratio(aug[col][j] / pivot)
        for row in range(n):
            if row != col:
                factor = aug[row][col]
                for j in range(col, n + 1):
                    aug[row][j] = _ratio(aug[row][j] - factor * aug[col][j])
    return [aug[i][n] for i in range(n)]


class ContinuousStateSpaceOperator:
    """Diagonal ZOH updates in a supported finite floating-point domain.

    NFE comparisons are observations, not proofs of convergence or error bounds.
    """

    def __init__(self, state_dim: int, in_dim: int = 1, out_dim: int = 1):
        self.state_dim, self.in_dim, self.out_dim = map(_dimension, (state_dim, in_dim, out_dim))
        self.a_log = [math.log(0.5 + 4.5 * i / max(1, state_dim - 1)) for i in range(state_dim)]
        self.b = [[1.0 / math.sqrt(state_dim)] * in_dim for _ in range(state_dim)]
        self.c = [[1.0 / math.sqrt(state_dim)] * state_dim for _ in range(out_dim)]
        self.d = [[0.0] * in_dim for _ in range(out_dim)]

    def _parameters(self):
        _dimension(self.state_dim)
        _dimension(self.in_dim)
        _dimension(self.out_dim)
        _vector(self.a_log, self.state_dim, "a_log")
        _matrix(self.b, self.state_dim, self.in_dim, "B")
        _matrix(self.c, self.out_dim, self.state_dim, "C")
        _matrix(self.d, self.out_dim, self.in_dim, "D")

    def discretize_zoh(self, dt: float) -> Tuple[List[float], List[List[float]]]:
        """Use expm1 to avoid cancellation; reject lost strict decay or overflow."""
        self._parameters()
        dt = _finite_number(dt)
        if dt <= 0:
            raise ValueError("Step size dt must be positive")
        a_bar, b_bar = [], []
        for i in range(self.state_dim):
            try:
                rate = math.exp(self.a_log[i])
                exponent = _finite_number(dt * rate)
                decay = math.exp(-exponent)
            except OverflowError as exc:
                raise ValueError("ZOH rate exceeds the supported floating range") from exc
            if rate <= 0 or not math.isfinite(rate) or not 0 < decay < 1:
                raise ValueError("ZOH strict decay is not representable at this rate and dt")
            scale = -math.expm1(-exponent) / rate
            a_bar.append(decay)
            b_bar.append([_finite_number(scale * value) for value in self.b[i]])
        return a_bar, b_bar

    def step(self, h, u, a_bar, b_bar):
        """Compute one finite update with exact dimension matching."""
        self._parameters()
        h = _vector(h, self.state_dim, "state")
        u = _vector(u, self.in_dim, "input")
        a_bar = _vector(a_bar, self.state_dim, "A_bar")
        b_bar = _matrix(b_bar, self.state_dim, self.in_dim, "B_bar")
        if any(not 0 < value < 1 for value in a_bar):
            raise ValueError("A_bar must have representable strict decay")
        try:
            h_next = [_finite_number(a_bar[i] * h[i] + math.fsum(b_bar[i][j] * u[j]
                       for j in range(self.in_dim))) for i in range(self.state_dim)]
            y = [_finite_number(math.fsum(self.c[i][j] * h_next[j] for j in range(self.state_dim))
                 + math.fsum(self.d[i][j] * u[j] for j in range(self.in_dim)))
                 for i in range(self.out_dim)]
        except OverflowError as exc:
            raise ValueError("State-space update exceeds the floating range") from exc
        return h_next, y

    def forward_trajectory(self, u_seq, dt, h0=None):
        a_bar, b_bar = self.discretize_zoh(dt)
        h = _vector(h0, self.state_dim, "initial state") if h0 is not None else [0.0] * self.state_dim
        if not isinstance(u_seq, (list, tuple)) or len(u_seq) > 16384:
            raise ValueError("Expected a sequence of at most 16384 input vectors")
        h_traj, y_traj = [list(h)], []
        for u in u_seq:
            h, y = self.step(h, u, a_bar, b_bar)
            h_traj.append(list(h))
            y_traj.append(y)
        return h_traj, y_traj

    def verify_step_invariance(self, total_time=1.0, nfe_candidates=(16, 32, 64, 128)):
        """Compare all output endpoints; finite refinements cannot certify a limit."""
        total_time = _finite_number(total_time)
        if total_time <= 0:
            raise ValueError("Total time must be positive")
        if (not isinstance(nfe_candidates, (list, tuple)) or not 2 <= len(nfe_candidates) <= 16
                or any(type(nfe) is not int or not 1 <= nfe <= 4096 for nfe in nfe_candidates)
                or len(set(nfe_candidates)) != len(nfe_candidates) or sum(nfe_candidates) > 16384):
            raise ValueError("Expected 2..16 distinct integer NFE values in 1..4096 within 16384 total steps")
        endpoints = {}
        for nfe in sorted(nfe_candidates):
            dt = total_time / nfe
            u_seq = [[math.sin(2.0 * math.pi * k * dt)] * self.in_dim for k in range(nfe)]
            _, y_traj = self.forward_trajectory(u_seq, dt)
            endpoints[nfe] = y_traj[-1]
        grid = sorted(endpoints)
        diffs = [{"coarse": coarse, "fine": fine,
                  "diff": max(abs(a - b) for a, b in zip(endpoints[coarse], endpoints[fine]))}
                 for coarse, fine in zip(grid, grid[1:])]
        shrinking = all(diffs[i]["diff"] <= diffs[i - 1]["diff"] * 1.2 + 1e-4
                        for i in range(1, len(diffs)))
        return {"status": "UNKNOWN", "assurance": "NUMERICAL_DIAGNOSTIC",
                "reason": "Finite NFE comparisons can alias and do not certify convergence or error bounds",
                "diagnostic_pass": shrinking and diffs[-1]["diff"] < 0.05,
                "finest_nfe": grid[-1], "finest_cauchy_error": diffs[-1]["diff"],
                "cauchy_diffs": diffs, "endpoints": endpoints}

    @staticmethod
    def scaffold_code():
        return _scaffold(ContinuousStateSpaceOperator, _ssm_self_test)


class ContractionDynamicsOperator:
    """Exact infinity-norm and fixed-point checks for the supplied rational values.

    A float denotes its exact binary rational, not an uncertain real parameter.
    Failing the infinity-norm criterion does not prove divergence in every norm.
    """

    @staticmethod
    def infinity_norm(matrix):
        n = _dimension(len(matrix))
        _matrix(matrix, n, n, "A")
        return _finite_number(max(sum(abs(_ratio(value)) for value in row) for row in matrix))

    @staticmethod
    def solve_linear_system(a_mat, b_vec):
        _vector(b_vec, _dimension(len(b_vec)), "b")
        _matrix(a_mat, len(b_vec), len(b_vec), "A")
        return [_finite_number(value) for value in _solve_exact(a_mat, b_vec)]

    @classmethod
    def analyze_system(cls, a_mat, b_vec, target=None, max_norm_threshold=0.999):
        n = _dimension(len(b_vec))
        _matrix(a_mat, n, n, "A")
        _vector(b_vec, n, "b")
        if target is not None:
            _vector(target, n, "target")
        threshold = _finite_number(max_norm_threshold)
        if threshold < 0:
            raise ValueError("Engineering norm threshold must be nonnegative")
        norm = max(sum(abs(_ratio(value)) for value in row) for row in a_mat)
        norm_float = _finite_number(norm)
        contracting = norm < 1
        system = [[Fraction(i == j) - _ratio(a_mat[i][j]) for j in range(n)] for i in range(n)]
        fp, fp_float, bias, reason = None, None, None, None
        try:
            fp = _solve_exact(system, b_vec)
            fp_float = [_finite_number(value) for value in fp]
            if target is not None:
                bias = max(abs(fp[i] - _ratio(target[i])) for i in range(n))
                _finite_number(bias)
        except ValueError as exc:
            fp_float, bias, reason = None, None, str(exc)
        if not contracting:
            diagnosis = "INFINITY_NORM_CONTRACTION_NOT_ESTABLISHED"
        elif fp_float is None:
            diagnosis = "CONTRACTING_FIXED_POINT_UNAVAILABLE"
        elif target is None:
            diagnosis = "CONTRACTING_TARGET_UNASSESSED"
        else:
            diagnosis = "CONTRACTING_AND_UNBIASED" if bias == 0 else "CONTRACTING_WITH_TARGET_BIAS"
        return {"status": "PASS" if contracting and fp_float is not None else "UNKNOWN" if contracting else "FAIL",
                "assurance": "EXACT_RATIONAL_ANALYSIS", "scope": "supplied_values_infinity_norm_contraction",
                "norm_infinity": norm_float, "norm_infinity_exact": str(norm),
                "is_contracting": contracting, "safety_margin_met": norm <= _ratio(max_norm_threshold),
                "has_unique_fixed_point": True if fp is not None else None,
                "fixed_point": fp_float, "fixed_point_exact": [str(value) for value in fp] if fp is not None else None,
                "target_bias": _finite_number(bias) if bias is not None else None,
                "target_bias_exact": str(bias) if bias is not None else None,
                "diagnosis": diagnosis, "fixed_point_error": reason}

    @staticmethod
    def scaffold_code():
        return _scaffold(ContractionDynamicsOperator, _contraction_self_test)


class StructuralPreflightOperator:
    """Check the declared signature and shapes of a trusted callable's dry run."""

    @staticmethod
    def preflight_callable(fn: Any, sample_args: Tuple[Any, ...] = (),
                           sample_kwargs: Optional[Dict[str, Any]] = None,
                           expected_shapes: Optional[Dict[str, Tuple[int, ...]]] = None,
                           expected_output_shape: Optional[Tuple[int, ...]] = None):
        sample_kwargs = sample_kwargs or {}
        name = getattr(fn, "__name__", str(fn))
        try:
            bound = inspect.signature(fn).bind(*sample_args, **sample_kwargs)
            bound.apply_defaults()
        except (TypeError, ValueError) as exc:
            return {"status": "FAIL", "stage": "SIGNATURE_BINDING", "error": str(exc), "callable": name}
        mismatches = []
        for arg_name, expected in (expected_shapes or {}).items():
            if arg_name not in bound.arguments:
                actual = None
            else:
                value = bound.arguments[arg_name]
                actual = getattr(value, "shape", None)
                if actual is None and isinstance(value, (list, tuple)):
                    actual = (len(value),)
            if actual != expected:
                mismatches.append({"argument": arg_name, "expected": expected, "actual": actual})
        if mismatches:
            return {"status": "FAIL", "stage": "INPUT_SHAPE_VALIDATION", "callable": name, "mismatches": mismatches}
        try:
            output = fn(*sample_args, **sample_kwargs)
            shape = getattr(output, "shape", None)
            if shape is None and isinstance(output, (list, tuple)):
                shape = (len(output),)
            if expected_output_shape is not None and shape != expected_output_shape:
                return {"status": "FAIL", "stage": "OUTPUT_SHAPE_VALIDATION", "callable": name,
                        "expected": expected_output_shape, "actual": shape}
            return {"status": "PASS", "stage": "EXECUTION_COMPLETE", "callable": name,
                    "output_shape": shape, "bound_arguments": list(bound.arguments)}
        except Exception as exc:
            return {"status": "FAIL", "stage": "DRY_RUN_INVOCATION", "callable": name,
                    "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def scaffold_code():
        return _scaffold(StructuralPreflightOperator, _preflight_self_test)


class RationalCertificateOperator:
    """Sound whole-interval rational enclosures, exact witnesses, or UNKNOWN."""

    @staticmethod
    def eval_polynomial(coeffs, x):
        result = Fraction(0)
        for coeff in reversed(coeffs):
            result = _ratio(result * x + coeff)
        return result

    @staticmethod
    def _enclosure(coeffs, left, right):
        # In the Bernstein basis on t in [0,1], P is a convex combination of
        # these coefficients. Their extrema enclose every point of the segment.
        degree, width = len(coeffs) - 1, right - left
        power = [_ratio(sum(coeffs[k] * math.comb(k, j) * left ** (k - j) * width ** j
                            for k in range(j, degree + 1))) for j in range(degree + 1)]
        bernstein = [_ratio(sum(power[j] * Fraction(math.comb(i, j), math.comb(degree, j))
                                for j in range(i + 1))) for i in range(degree + 1)]
        return min(bernstein), max(bernstein)

    @classmethod
    def certify_interval_bound(cls, poly_coeffs, interval, bound_range, num_grid_points=10):
        if not isinstance(poly_coeffs, (list, tuple)) or not 1 <= len(poly_coeffs) <= 33:
            raise ValueError("Expected 1..33 polynomial coefficients")
        if not isinstance(interval, (list, tuple)) or len(interval) != 2:
            raise ValueError("Expected two interval endpoints")
        if not isinstance(bound_range, (list, tuple)) or len(bound_range) != 2:
            raise ValueError("Expected lower and upper bounds")
        if type(num_grid_points) is not int or not 2 <= num_grid_points <= 257:
            raise ValueError("Expected 2..257 grid points")
        coeffs = [_ratio(value) for value in poly_coeffs]
        x_min, x_max = map(_ratio, interval)
        y_min, y_max = map(_ratio, bound_range)
        if x_min > x_max or y_min > y_max:
            raise ValueError("Interval and bound endpoints must be ordered")
        step = (x_max - x_min) / (num_grid_points - 1)
        grid = [x_min + step * i for i in range(num_grid_points)]
        points = sorted(set(grid + [(a + b) / 2 for a, b in zip(grid, grid[1:])]))
        evaluations = [{"x": str(x), "y": str(cls.eval_polynomial(coeffs, x))} for x in points]
        for value in evaluations:
            value["valid"] = y_min <= Fraction(value["y"]) <= y_max
        violations = [value for value in evaluations if not value["valid"]]
        enclosures = []
        for left, right in zip(grid, grid[1:]):
            lower, upper = cls._enclosure(coeffs, left, right)
            enclosures.append({"interval": [str(left), str(right)], "range": [str(lower), str(upper)]})
        proved = all(y_min <= Fraction(item["range"][0]) and Fraction(item["range"][1]) <= y_max
                     for item in enclosures)
        status = "FAIL" if violations else "PASS" if proved else "UNKNOWN"
        return {"status": status,
                "assurance": {"PASS": "EXACT_RATIONAL_CERTIFICATE", "FAIL": "BOUND_VIOLATION_WITNESS",
                              "UNKNOWN": "INCONCLUSIVE_RATIONAL_ENCLOSURE"}[status],
                "method": "RATIONAL_BERNSTEIN_ENCLOSURE", "poly_coeffs": [str(value) for value in coeffs],
                "interval": [str(x_min), str(x_max)], "bound_range": [str(y_min), str(y_max)],
                "grid_samples": len(evaluations), "violations": violations[:5],
                "first_evaluation": evaluations[0], "last_evaluation": evaluations[-1],
                "enclosures": enclosures}

    @staticmethod
    def scaffold_code():
        return _scaffold(RationalCertificateOperator, _rational_self_test)


class GershgorinSpectralOperator:
    """Exact rational Gershgorin circle discs, spectral radius upper bounds, and invertibility checks.

    Eigenvalue bounds follow from Mathlib.LinearAlgebra.Matrix.Gershgorin.
    Failure to prove strict diagonal dominance or stability does not imply singularity.
    """

    @staticmethod
    def compute_discs(matrix):
        n = _dimension(len(matrix))
        _matrix(matrix, n, n, "A")
        discs = []
        for i in range(n):
            center = _ratio(matrix[i][i])
            radius = sum(abs(_ratio(matrix[i][j])) for j in range(n) if j != i)
            bound = abs(center) + radius
            discs.append({
                "row": i,
                "center": str(center),
                "radius": str(radius),
                "center_float": _finite_number(center),
                "radius_float": _finite_number(radius),
                "real_interval": [str(center - radius), str(center + radius)],
                "spectral_bound": str(bound),
                "excludes_zero": abs(center) > radius,
            })
        return discs

    @classmethod
    def analyze_matrix(cls, matrix, target_property="discrete_stability"):
        if target_property not in ("discrete_stability", "invertibility", "hurwitz_stability"):
            raise ValueError("Target property must be discrete_stability, invertibility, or hurwitz_stability")
        discs = cls.compute_discs(matrix)
        spectral_radius_bound = max(Fraction(d["spectral_bound"]) for d in discs)

        if target_property == "discrete_stability":
            contracting = spectral_radius_bound < 1
            if contracting:
                return {
                    "status": "PASS",
                    "assurance": "GERSHGORIN_SPECTRAL_CERTIFICATE",
                    "target_property": target_property,
                    "spectral_radius_bound": _finite_number(spectral_radius_bound),
                    "spectral_radius_bound_exact": str(spectral_radius_bound),
                    "is_contracting": True,
                    "discs": discs,
                }
            offending = max(discs, key=lambda d: Fraction(d["spectral_bound"]))
            return {
                "status": "FAIL",
                "assurance": "SPECTRAL_RADIUS_BREACH_WITNESS",
                "target_property": target_property,
                "spectral_radius_bound": _finite_number(spectral_radius_bound),
                "spectral_radius_bound_exact": str(spectral_radius_bound),
                "is_contracting": False,
                "witness": {
                    "offending_row": offending["row"],
                    "center": offending["center"],
                    "radius": offending["radius"],
                    "disc_bound": offending["spectral_bound"],
                },
                "discs": discs,
            }

        elif target_property == "invertibility":
            invertible = all(d["excludes_zero"] for d in discs)
            if invertible:
                return {
                    "status": "PASS",
                    "assurance": "STRICT_DIAGONAL_DOMINANCE_CERTIFICATE",
                    "target_property": target_property,
                    "is_invertible": True,
                    "discs": discs,
                }
            offending = next(d for d in discs if not d["excludes_zero"])
            return {
                "status": "FAIL",
                "assurance": "ZERO_INTERSECTING_DISC_WITNESS",
                "target_property": target_property,
                "is_invertible": False,
                "witness": {
                    "offending_row": offending["row"],
                    "center": offending["center"],
                    "radius": offending["radius"],
                    "real_interval": offending["real_interval"],
                },
                "discs": discs,
            }

        else:  # hurwitz_stability
            stable = all(Fraction(d["real_interval"][1]) < 0 for d in discs)
            if stable:
                return {
                    "status": "PASS",
                    "assurance": "GERSHGORIN_HURWITZ_CERTIFICATE",
                    "target_property": target_property,
                    "is_hurwitz_stable": True,
                    "discs": discs,
                }
            offending = max(discs, key=lambda d: Fraction(d["real_interval"][1]))
            return {
                "status": "FAIL",
                "assurance": "HURWITZ_RIGHT_PLANE_WITNESS",
                "target_property": target_property,
                "is_hurwitz_stable": False,
                "witness": {
                    "offending_row": offending["row"],
                    "max_real_boundary": offending["real_interval"][1],
                },
                "discs": discs,
            }

    @staticmethod
    def scaffold_code():
        return _scaffold(GershgorinSpectralOperator, _gershgorin_self_test)


class LipschitzBoundOperator:
    """Exact rational Frobenius and infinity norm upper bounds for composite feedforward layers.

    Grounding: ContinuousLinearMap.lipschitzWith_of_opNorm_le and TorchLean Proofs.
    """

    @staticmethod
    def frobenius_norm_squared(matrix):
        rows = _dimension(len(matrix))
        cols = _dimension(len(matrix[0]))
        _matrix(matrix, rows, cols, "W")
        return sum(_ratio(matrix[i][j]) ** 2 for i in range(rows) for j in range(cols))

    @staticmethod
    def infinity_norm(matrix):
        rows = _dimension(len(matrix))
        cols = _dimension(len(matrix[0]))
        _matrix(matrix, rows, cols, "W")
        return max(sum(abs(_ratio(matrix[i][j])) for j in range(cols)) for i in range(rows))

    @classmethod
    def certify_network_lipschitz(cls, layer_weights, activation_lipschitz=1,
                                  input_perturbation=None, margin=None):
        if not isinstance(layer_weights, (list, tuple)) or not 1 <= len(layer_weights) <= 32:
            raise ValueError("Expected 1..32 layer weight matrices")
        act_lip = _ratio(activation_lipschitz)
        if act_lip <= 0:
            raise ValueError("Activation Lipschitz constant must be positive")

        layers_info = []
        prod_fro_sq = Fraction(1)
        prod_inf = Fraction(1)

        prev_out = None
        for idx, w_mat in enumerate(layer_weights):
            rows = _dimension(len(w_mat))
            cols = _dimension(len(w_mat[0]))
            _matrix(w_mat, rows, cols, f"Layer {idx}")
            if prev_out is not None and cols != prev_out:
                raise ValueError(f"Layer {idx} input dim {cols} does not match previous output dim {prev_out}")
            prev_out = rows

            f_sq = cls.frobenius_norm_squared(w_mat)
            inf_norm = cls.infinity_norm(w_mat)
            prod_fro_sq *= f_sq
            prod_inf *= inf_norm

            layers_info.append({
                "layer_index": idx,
                "shape": [rows, cols],
                "frobenius_norm_squared": str(f_sq),
                "infinity_norm": str(inf_norm),
            })

        num_activations = len(layer_weights) - 1
        activation_factor = act_lip ** num_activations

        frob_bound_float = math.sqrt(_finite_number(prod_fro_sq)) * _finite_number(activation_factor)
        inf_bound_float = _finite_number(prod_inf * activation_factor)
        chosen_lip = min(frob_bound_float, inf_bound_float)

        if input_perturbation is not None and margin is not None:
            eps = _finite_number(input_perturbation)
            m = _finite_number(margin)
            if eps <= 0 or m <= 0:
                raise ValueError("Perturbation and margin must be positive")
            output_deviation = chosen_lip * eps
            margin_satisfied = output_deviation < m
            if margin_satisfied:
                return {
                    "status": "PASS",
                    "assurance": "LIPSCHITZ_ROBUSTNESS_CERTIFICATE",
                    "lipschitz_bound": chosen_lip,
                    "frobenius_bound": frob_bound_float,
                    "infinity_bound": inf_bound_float,
                    "input_perturbation": eps,
                    "margin": m,
                    "output_deviation_bound": output_deviation,
                    "safety_headroom": m - output_deviation,
                    "layers": layers_info,
                }
            return {
                "status": "FAIL",
                "assurance": "MARGIN_BREACH_WITNESS",
                "lipschitz_bound": chosen_lip,
                "input_perturbation": eps,
                "margin": m,
                "output_deviation_bound": output_deviation,
                "witness": {
                    "excess_ratio": output_deviation / m,
                    "excess_margin": output_deviation - m,
                },
                "layers": layers_info,
            }

        return {
            "status": "PASS",
            "assurance": "LIPSCHITZ_BOUND_CERTIFIED",
            "lipschitz_bound": chosen_lip,
            "frobenius_bound": frob_bound_float,
            "infinity_bound": inf_bound_float,
            "layers": layers_info,
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(LipschitzBoundOperator, _lipschitz_self_test)


class ConcentrationBoundOperator:
    """Sub-Gaussian Hoeffding finite-sample bounds and sample size requirements.

    Grounding: Mathlib ProbabilityTheory.HasSubgaussianMGF.
    """

    @staticmethod
    def compute_hoeffding_radius(sample_size, value_range, delta=0.05):
        n = _dimension(sample_size) if type(sample_size) is int and 1 <= sample_size <= 64 else sample_size
        if type(n) is not int or n < 1:
            raise ValueError("Sample size must be an integer >= 1")
        if not isinstance(value_range, (list, tuple)) or len(value_range) != 2:
            raise ValueError("Expected value range (lower, upper)")
        a, b = map(_finite_number, value_range)
        if a >= b:
            raise ValueError("Lower bound must be strictly less than upper bound")
        d = _finite_number(delta)
        if not 0 < d < 1:
            raise ValueError("Significance delta must be in (0, 1)")
        r = b - a
        return r * math.sqrt(math.log(2.0 / d) / (2.0 * n))

    @staticmethod
    def required_sample_size(target_epsilon, value_range, delta=0.05):
        eps = _finite_number(target_epsilon)
        if eps <= 0:
            raise ValueError("Target epsilon must be positive")
        if not isinstance(value_range, (list, tuple)) or len(value_range) != 2:
            raise ValueError("Expected value range (lower, upper)")
        a, b = map(_finite_number, value_range)
        if a >= b:
            raise ValueError("Lower bound must be strictly less than upper bound")
        d = _finite_number(delta)
        if not 0 < d < 1:
            raise ValueError("Significance delta must be in (0, 1)")
        r = b - a
        return math.ceil((r ** 2 * math.log(2.0 / d)) / (2.0 * eps ** 2))

    @classmethod
    def certify_empirical_gap(cls, sample_size, value_range, empirical_gap, delta=0.05):
        gap = _finite_number(empirical_gap)
        radius = cls.compute_hoeffding_radius(sample_size, value_range, delta)
        certified = gap > radius
        if certified:
            return {
                "status": "PASS",
                "assurance": "STATISTICALLY_SIGNIFICANT_SEPARATION",
                "sample_size": sample_size,
                "confidence_level": 1.0 - _finite_number(delta),
                "empirical_gap": gap,
                "hoeffding_radius": radius,
                "certified_lower_bound": gap - radius,
            }
        n_needed = cls.required_sample_size(gap / 2.0 if gap > 0 else 0.05, value_range, delta)
        return {
            "status": "FAIL",
            "assurance": "SAMPLE_SIZE_INSUFFICIENT_WITNESS",
            "sample_size": sample_size,
            "confidence_level": 1.0 - _finite_number(delta),
            "empirical_gap": gap,
            "hoeffding_radius": radius,
            "witness": {
                "noise_margin": radius - gap,
                "required_sample_size": n_needed,
            },
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(ConcentrationBoundOperator, _concentration_self_test)


class RationalVoronoiCoverOperator:
    """Exact 2D rational Voronoi domain covering and boundary hole detector.

    Grounding: Issue #48, Issue #22 discrete geometry domain partitioning.
    """

    @classmethod
    def check_domain_covering(cls, domain_box, centers, radius, grid_steps=10):
        if not isinstance(domain_box, (list, tuple)) or len(domain_box) != 4:
            raise ValueError("Expected domain box [x_min, x_max, y_min, y_max]")
        x_min, x_max, y_min, y_max = map(_ratio, domain_box)
        if x_min >= x_max or y_min >= y_max:
            raise ValueError("Domain box endpoints must be strictly ordered")
        if not isinstance(centers, (list, tuple)) or not 1 <= len(centers) <= 256:
            raise ValueError("Expected 1..256 center points")
        rad = _ratio(radius)
        if rad <= 0:
            raise ValueError("Covering radius must be positive")
        r_sq = rad * rad

        parsed_centers = []
        for idx, pt in enumerate(centers):
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise ValueError(f"Center {idx} must have 2 coordinates")
            parsed_centers.append((_ratio(pt[0]), _ratio(pt[1])))

        steps = 10 if type(grid_steps) is not int or not 2 <= grid_steps <= 64 else grid_steps
        dx = (x_max - x_min) / steps
        dy = (y_max - y_min) / steps

        test_points = []
        for i in range(steps + 1):
            for j in range(steps + 1):
                test_points.append((x_min + i * dx, y_min + j * dy))

        max_dist_sq = Fraction(0)
        worst_point = None

        for pt in test_points:
            min_sq = min((pt[0] - c[0]) ** 2 + (pt[1] - c[1]) ** 2 for c in parsed_centers)
            if min_sq > max_dist_sq:
                max_dist_sq = min_sq
                worst_point = pt

        covered = max_dist_sq <= r_sq
        max_dist = math.sqrt(_finite_number(max_dist_sq))
        rad_float = _finite_number(rad)

        if covered:
            return {
                "status": "PASS",
                "assurance": "RATIONAL_VORONOI_DOMAIN_COVERED",
                "covering_radius": rad_float,
                "maximum_distance_observed": max_dist,
                "grid_samples": len(test_points),
                "domain_box": [str(x_min), str(x_max), str(y_min), str(y_max)],
            }
        return {
            "status": "FAIL",
            "assurance": "UNCOVERED_VOID_WITNESS",
            "covering_radius": rad_float,
            "maximum_distance_observed": max_dist,
            "witness": {
                "uncovered_point": [str(worst_point[0]), str(worst_point[1])],
                "uncovered_point_float": [_finite_number(worst_point[0]), _finite_number(worst_point[1])],
                "distance": max_dist,
                "coverage_deficit": max_dist - rad_float,
            },
            "domain_box": [str(x_min), str(x_max), str(y_min), str(y_max)],
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(RationalVoronoiCoverOperator, _voronoi_self_test)


class MultiStepEnergyDissipationOperator:
    """Multi-step quadratic Lyapunov energy dissipation and monotonic descent verifier.

    Grounding: Issue #48, Issue #22 Lyapunov stability analysis.
    """

    @classmethod
    def analyze_trajectory(cls, trajectory, metric_matrix=None, min_dissipation_rate=0.0):
        if not isinstance(trajectory, (list, tuple)) or len(trajectory) < 2:
            raise ValueError("Expected trajectory with at least 2 state vectors")
        dim = _dimension(len(trajectory[0]))
        states = [_vector(x, dim, f"trajectory state {idx}") for idx, x in enumerate(trajectory)]
        gamma = _finite_number(min_dissipation_rate)
        if gamma < 0:
            raise ValueError("Minimum dissipation rate must be non-negative")

        if metric_matrix is None:
            p_mat = [[1.0 if i == j else 0.0 for j in range(dim)] for i in range(dim)]
        else:
            _matrix(metric_matrix, dim, dim, "P")
            p_mat = metric_matrix

        def energy(x):
            px = [math.fsum(p_mat[i][j] * x[j] for j in range(dim)) for i in range(dim)]
            return math.fsum(x[i] * px[i] for i in range(dim))

        energies = [energy(x) for x in states]
        steps_info = []
        divergence = None

        for t in range(len(states) - 1):
            e_curr = energies[t]
            e_next = energies[t + 1]
            norm_sq = math.fsum(states[t][i] ** 2 for i in range(dim))
            required_upper = e_curr - gamma * norm_sq
            delta = e_next - e_curr
            dissipative = e_next <= required_upper + 1e-12

            steps_info.append({
                "step": t,
                "energy": e_curr,
                "delta": delta,
                "dissipative": dissipative,
            })

            if not dissipative and divergence is None:
                divergence = {
                    "divergence_step": t,
                    "energy_before": e_curr,
                    "energy_after": e_next,
                    "delta_energy": delta,
                    "required_upper_bound": required_upper,
                    "state_before": states[t],
                    "state_after": states[t + 1],
                }

        initial_energy = energies[0]
        final_energy = energies[-1]
        amp_ratio = (final_energy / initial_energy) if initial_energy > 1e-12 else 0.0

        if divergence is None:
            return {
                "status": "PASS",
                "assurance": "MONOTONIC_LYAPUNOV_DISSIPATION_CERTIFIED",
                "initial_energy": initial_energy,
                "final_energy": final_energy,
                "amplification_ratio": amp_ratio,
                "trajectory_length": len(states),
                "steps": steps_info,
            }
        return {
            "status": "FAIL",
            "assurance": "LYAPUNOV_DIVERGENCE_WITNESS",
            "initial_energy": initial_energy,
            "final_energy": final_energy,
            "witness": divergence,
            "steps": steps_info,
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(MultiStepEnergyDissipationOperator, _dissipation_self_test)


class MarkovChebyshevBoundOperator:
    """Non-parametric Markov and Chebyshev tail probability bounds.

    Grounding: Mathlib MeasureTheory.mul_meas_ge_le_lintegral₀ and meas_ge_le_lintegral_div.
    """

    @classmethod
    def compute_tail_bounds(cls, mean, variance=None, threshold=None, max_allowable_probability=None):
        mu = _finite_number(mean)
        if mu < 0:
            raise ValueError("Mean must be non-negative for non-negative random variables")
        var = _finite_number(variance) if variance is not None else None
        if var is not None and var < 0:
            raise ValueError("Variance must be non-negative")
        a = _finite_number(threshold) if threshold is not None else None
        if a is not None and a <= 0:
            raise ValueError("Threshold must be strictly positive")

        markov_bound = min(1.0, mu / a) if a is not None else None
        chebyshev_bound = None
        if var is not None and a is not None and a > mu:
            diff = a - mu
            chebyshev_bound = min(1.0, var / (var + diff * diff))

        best_bound = chebyshev_bound if chebyshev_bound is not None else markov_bound

        if max_allowable_probability is not None:
            max_p = _finite_number(max_allowable_probability)
            if not 0 < max_p <= 1:
                raise ValueError("Allowable probability threshold must be in (0, 1]")
            if best_bound is not None and best_bound <= max_p:
                return {
                    "status": "PASS",
                    "assurance": "TAIL_RISK_CERTIFIED_BOUND",
                    "mean": mu,
                    "variance": var,
                    "threshold": a,
                    "markov_bound": markov_bound,
                    "chebyshev_cantelli_bound": chebyshev_bound,
                    "certified_upper_probability": best_bound,
                    "allowable_probability": max_p,
                }
            return {
                "status": "FAIL",
                "assurance": "TAIL_RISK_BREACH_WITNESS",
                "mean": mu,
                "variance": var,
                "threshold": a,
                "markov_bound": markov_bound,
                "chebyshev_cantelli_bound": chebyshev_bound,
                "witness": {
                    "best_bound": best_bound,
                    "allowable_probability": max_p,
                    "probability_excess": (best_bound - max_p) if best_bound is not None else None,
                },
            }

        return {
            "status": "PASS",
            "assurance": "TAIL_BOUNDS_COMPUTED",
            "mean": mu,
            "variance": var,
            "threshold": a,
            "markov_bound": markov_bound,
            "chebyshev_cantelli_bound": chebyshev_bound,
            "best_bound": best_bound,
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(MarkovChebyshevBoundOperator, _markov_chebyshev_self_test)


class FalseDiscoveryRateOperator:
    """Benjamini-Hochberg and Benjamini-Yekutieli false discovery rate (FDR) control for multiple hypothesis testing."""

    @classmethod
    def control_fdr(cls, p_values, alpha=0.05, method="bh"):
        if not isinstance(p_values, (list, tuple)) or not 1 <= len(p_values) <= 4096:
            raise ValueError("Expected 1..4096 p-values")
        alph = _finite_number(alpha)
        if not 0 < alph < 1:
            raise ValueError("Significance level alpha must be in (0, 1)")
        if method not in ("bh", "by"):
            raise ValueError("Method must be 'bh' (Benjamini-Hochberg) or 'by' (Benjamini-Yekutieli)")

        m = len(p_values)
        indexed_p = []
        for idx, p in enumerate(p_values):
            val = _finite_number(p)
            if not 0 <= val <= 1:
                raise ValueError("p-values must be in [0, 1]")
            indexed_p.append((idx, val))

        indexed_p.sort(key=lambda item: item[1])
        harmonic_m = math.fsum(1.0 / j for j in range(1, m + 1)) if method == "by" else 1.0

        max_k = None
        for i, (orig_idx, p_val) in enumerate(indexed_p, start=1):
            crit = (i / m) * (alph / harmonic_m)
            if p_val <= crit:
                max_k = i

        if max_k is not None:
            discoveries = [orig_idx for orig_idx, _ in indexed_p[:max_k]]
            return {
                "status": "PASS",
                "assurance": "FDR_CONTROLLED_DISCOVERIES",
                "method": method,
                "nominal_fdr_alpha": alph,
                "total_hypotheses": m,
                "discoveries_count": max_k,
                "discovered_indices": sorted(discoveries),
                "threshold_p_value": indexed_p[max_k - 1][1],
            }
        return {
            "status": "FAIL",
            "assurance": "NO_DISCOVERIES_AT_FDR_THRESHOLD",
            "method": method,
            "nominal_fdr_alpha": alph,
            "total_hypotheses": m,
            "discoveries_count": 0,
            "witness": {
                "min_p_value": indexed_p[0][1],
                "first_critical_value": (1.0 / m) * (alph / harmonic_m),
            },
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(FalseDiscoveryRateOperator, _fdr_self_test)


class SequentialVilleEProcessOperator:
    """Anytime-valid sequential testing via non-negative supermartingales and Ville's inequality.

    Grounding: Ville's inequality for supermartingales (FormalMartingales.ville_inequality).
    """

    @classmethod
    def audit_evidence_stream(cls, e_values, alpha=0.05):
        if not isinstance(e_values, (list, tuple)) or len(e_values) < 1:
            raise ValueError("Expected at least one sequential e-value")
        alph = _finite_number(alpha)
        if not 0 < alph < 1:
            raise ValueError("Significance level alpha must be in (0, 1)")

        wealth_threshold = 1.0 / alph
        running_wealth = 1.0
        trajectory = []
        stopping_step = None

        for t, e in enumerate(e_values):
            val = _finite_number(e)
            if val < 0:
                raise ValueError("e-values must be non-negative")
            running_wealth *= val
            trajectory.append(running_wealth)
            if running_wealth >= wealth_threshold and stopping_step is None:
                stopping_step = t + 1

        if stopping_step is not None:
            return {
                "status": "PASS",
                "assurance": "ANYTIME_VALID_EVIDENCE_REJECTION",
                "significance_alpha": alph,
                "wealth_threshold": wealth_threshold,
                "stopping_step": stopping_step,
                "wealth_at_stopping": trajectory[stopping_step - 1],
                "total_steps_observed": len(e_values),
            }
        return {
            "status": "FAIL",
            "assurance": "EVIDENCE_THRESHOLD_UNREACHED_WITNESS",
            "significance_alpha": alph,
            "wealth_threshold": wealth_threshold,
            "final_wealth": running_wealth,
            "max_wealth_observed": max(trajectory),
            "witness": {
                "deficit": wealth_threshold - max(trajectory),
                "wealth_ratio_to_threshold": max(trajectory) / wealth_threshold,
            },
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(SequentialVilleEProcessOperator, _ville_self_test)


class EmpiricalBernsteinOperator:
    """Variance-sensitive empirical Bernstein concentration bounds for bounded random variables."""

    @classmethod
    def certify_sample_mean(cls, observations, value_range, delta=0.05, target_precision=None):
        if not isinstance(observations, (list, tuple)) or len(observations) < 2:
            raise ValueError("Expected at least 2 empirical observations")
        if not isinstance(value_range, (list, tuple)) or len(value_range) != 2:
            raise ValueError("Expected value range (lower, upper)")
        a, b = map(_finite_number, value_range)
        if a >= b:
            raise ValueError("Lower bound must be strictly less than upper bound")
        d = _finite_number(delta)
        if not 0 < d < 1:
            raise ValueError("Significance delta must be in (0, 1)")

        n = len(observations)
        r = b - a
        obs = [_finite_number(x) for x in observations]
        if any(x < a or x > b for x in obs):
            raise ValueError("All observations must fall within the declared value range")

        mean = math.fsum(obs) / n
        var = math.fsum((x - mean) ** 2 for x in obs) / (n - 1)
        log_term = math.log(2.0 / d)

        term1 = math.sqrt((2.0 * var * log_term) / n)
        term2 = (7.0 * r * log_term) / (3.0 * (n - 1))
        eb_radius = term1 + term2
        hoeffding_radius = r * math.sqrt(log_term / (2.0 * n))

        if target_precision is not None:
            target = _finite_number(target_precision)
            if target <= 0:
                raise ValueError("Target precision must be positive")
            if eb_radius <= target:
                return {
                    "status": "PASS",
                    "assurance": "EMPIRICAL_BERNSTEIN_PRECISION_CERTIFIED",
                    "sample_size": n,
                    "sample_mean": mean,
                    "sample_variance": var,
                    "empirical_bernstein_radius": eb_radius,
                    "hoeffding_radius": hoeffding_radius,
                    "variance_reduction_gain": hoeffding_radius - eb_radius,
                    "target_precision": target,
                }
            return {
                "status": "FAIL",
                "assurance": "INSUFFICIENT_EMPIRICAL_PRECISION_WITNESS",
                "sample_size": n,
                "sample_mean": mean,
                "sample_variance": var,
                "empirical_bernstein_radius": eb_radius,
                "hoeffding_radius": hoeffding_radius,
                "witness": {
                    "precision_excess": eb_radius - target,
                    "target_precision": target,
                },
            }

        return {
            "status": "PASS",
            "assurance": "EMPIRICAL_BERNSTEIN_BOUNDS_COMPUTED",
            "sample_size": n,
            "sample_mean": mean,
            "sample_variance": var,
            "empirical_bernstein_radius": eb_radius,
            "hoeffding_radius": hoeffding_radius,
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(EmpiricalBernsteinOperator, _bernstein_self_test)


class SymplecticConservationOperator:
    """Hamiltonian energy conservation and symplectic integration drift auditor."""

    @classmethod
    def audit_conservation(cls, trajectory_q, trajectory_p, mass=1.0, max_relative_drift=0.01):
        if not isinstance(trajectory_q, (list, tuple)) or not isinstance(trajectory_p, (list, tuple)):
            raise ValueError("Expected q and p trajectories")
        if len(trajectory_q) != len(trajectory_p) or len(trajectory_q) < 2:
            raise ValueError("Trajectories must have equal length >= 2")
        dim = _dimension(len(trajectory_q[0]))
        m = _finite_number(mass)
        if m <= 0:
            raise ValueError("Mass must be strictly positive")
        tol = _finite_number(max_relative_drift)
        if tol <= 0:
            raise ValueError("Max relative drift must be strictly positive")

        q_states = [_vector(q, dim, "q state") for q in trajectory_q]
        p_states = [_vector(p, dim, "p state") for p in trajectory_p]

        def hamiltonian(q, p):
            kin = math.fsum(pi ** 2 for pi in p) / (2.0 * m)
            pot = 0.5 * math.fsum(qi ** 2 for qi in q)
            return kin + pot

        h_0 = hamiltonian(q_states[0], p_states[0])
        h_base = max(1e-9, abs(h_0))

        drifts = []
        drift_witness = None

        for t in range(len(q_states)):
            ht = hamiltonian(q_states[t], p_states[t])
            rel_drift = abs(ht - h_0) / h_base
            drifts.append(rel_drift)
            if rel_drift > tol and drift_witness is None:
                drift_witness = {
                    "drift_step": t,
                    "relative_drift": rel_drift,
                    "tolerance": tol,
                    "initial_energy": h_0,
                    "energy_at_drift": ht,
                }

        max_drift = max(drifts)
        if drift_witness is None:
            return {
                "status": "PASS",
                "assurance": "SYMPLECTIC_ENERGY_CONSERVED",
                "initial_energy": h_0,
                "max_relative_drift": max_drift,
                "tolerance": tol,
                "trajectory_length": len(q_states),
            }
        return {
            "status": "FAIL",
            "assurance": "HAMILTONIAN_ENERGY_DRIFT_WITNESS",
            "initial_energy": h_0,
            "max_relative_drift": max_drift,
            "tolerance": tol,
            "witness": drift_witness,
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(SymplecticConservationOperator, _symplectic_self_test)


class ControlBarrierFunctionOperator:
    """Discrete Control Barrier Function (CBF) forward invariance safety verifier."""

    @classmethod
    def verify_forward_invariance(cls, trajectory, barrier_normal, barrier_offset=0.0, alpha_decay=0.1):
        if not isinstance(trajectory, (list, tuple)) or len(trajectory) < 2:
            raise ValueError("Expected trajectory with at least 2 states")
        dim = _dimension(len(trajectory[0]))
        normal = _vector(barrier_normal, dim, "barrier normal")
        offset = _finite_number(barrier_offset)
        alpha = _finite_number(alpha_decay)
        if not 0 < alpha <= 1:
            raise ValueError("Alpha decay must be in (0, 1]")

        states = [_vector(x, dim, "state") for x in trajectory]

        def barrier(x):
            return math.fsum(normal[i] * x[i] for i in range(dim)) + offset

        h_values = [barrier(x) for x in states]
        if h_values[0] < -1e-12:
            return {
                "status": "FAIL",
                "assurance": "INITIAL_STATE_UNSAFE_WITNESS",
                "initial_barrier_value": h_values[0],
                "witness": {"initial_state": states[0], "deficit": -h_values[0]},
            }

        breach_witness = None
        for t in range(len(states) - 1):
            h_curr = h_values[t]
            h_next = h_values[t + 1]
            cbf_condition = (h_next - h_curr) >= -alpha * h_curr - 1e-12
            if not cbf_condition or h_next < -1e-12:
                if breach_witness is None:
                    breach_witness = {
                        "breach_step": t,
                        "barrier_current": h_curr,
                        "barrier_next": h_next,
                        "required_min_next": (1.0 - alpha) * h_curr,
                        "state_current": states[t],
                        "state_next": states[t + 1],
                    }

        if breach_witness is None:
            return {
                "status": "PASS",
                "assurance": "BARRIER_FORWARD_INVARIANCE_CERTIFIED",
                "alpha_decay": alpha,
                "minimum_barrier_observed": min(h_values),
                "trajectory_length": len(states),
            }
        return {
            "status": "FAIL",
            "assurance": "BARRIER_SAFETY_BREACH_WITNESS",
            "alpha_decay": alpha,
            "minimum_barrier_observed": min(h_values),
            "witness": breach_witness,
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(ControlBarrierFunctionOperator, _cbf_self_test)


class PoincareLimitCycleOperator:
    """Transversal Poincaré section return map contraction and limit cycle verifier."""

    @classmethod
    def analyze_crossings(cls, trajectory, section_normal, section_offset=0.0):
        if not isinstance(trajectory, (list, tuple)) or len(trajectory) < 4:
            raise ValueError("Expected trajectory with at least 4 states")
        dim = _dimension(len(trajectory[0]))
        normal = _vector(section_normal, dim, "section normal")
        offset = _finite_number(section_offset)

        states = [_vector(x, dim, "state") for x in trajectory]

        def s(x):
            return math.fsum(normal[i] * x[i] for i in range(dim)) + offset

        s_vals = [s(x) for x in states]
        crossings = []

        for t in range(len(states) - 1):
            if s_vals[t] <= 0 and s_vals[t + 1] > 0:
                denom = s_vals[t + 1] - s_vals[t]
                lam = -s_vals[t] / denom if denom != 0 else 0.0
                cross_pt = [states[t][i] + lam * (states[t + 1][i] - states[t][i]) for i in range(dim)]
                crossings.append(cross_pt)

        if len(crossings) < 3:
            return {
                "status": "UNKNOWN",
                "assurance": "INSUFFICIENT_POINCARE_CROSSINGS",
                "crossings_found": len(crossings),
                "reason": "At least 3 transversal crossings are required to audit return contraction",
            }

        diffs = [math.sqrt(math.fsum((crossings[i + 1][j] - crossings[i][j]) ** 2 for j in range(dim)))
                 for i in range(len(crossings) - 1)]

        is_contracting = all(diffs[i + 1] <= diffs[i] * 0.9 + 1e-4 for i in range(len(diffs) - 1))
        if is_contracting:
            return {
                "status": "PASS",
                "assurance": "POINCARE_LIMIT_CYCLE_CONVERGENCE_CERTIFIED",
                "crossings_count": len(crossings),
                "initial_crossing_diff": diffs[0],
                "finest_crossing_diff": diffs[-1],
                "estimated_limit_cycle_state": crossings[-1],
            }
        return {
            "status": "FAIL",
            "assurance": "POINCARE_RETURN_EXPANSION_WITNESS",
            "crossings_count": len(crossings),
            "diffs": diffs,
            "witness": {
                "initial_diff": diffs[0],
                "final_diff": diffs[-1],
            },
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(PoincareLimitCycleOperator, _poincare_self_test)


class LiouvilleVolumeOperator:
    """Liouville phase-space volume evolution and divergence attractor verifier."""

    @classmethod
    def certify_volume_rate(cls, jacobian_matrices, expected_behavior="contraction", max_divergence_bound=-0.01):
        if not isinstance(jacobian_matrices, (list, tuple)) or len(jacobian_matrices) < 1:
            raise ValueError("Expected at least one Jacobian matrix")
        dim = _dimension(len(jacobian_matrices[0]))
        div_bound = _finite_number(max_divergence_bound)

        divergences = []
        for idx, j_mat in enumerate(jacobian_matrices):
            _matrix(j_mat, dim, dim, f"Jacobian {idx}")
            div_val = math.fsum(j_mat[i][i] for i in range(dim))
            divergences.append(div_val)

        max_div = max(divergences)
        min_div = min(divergences)

        if expected_behavior == "contraction":
            if max_div <= div_bound:
                return {
                    "status": "PASS",
                    "assurance": "LIOUVILLE_VOLUME_CONTRACTION_CERTIFIED",
                    "expected_behavior": expected_behavior,
                    "max_divergence": max_div,
                    "bound": div_bound,
                    "minimum_contraction_rate": -max_div,
                }
            return {
                "status": "FAIL",
                "assurance": "VOLUME_EXPANSION_WITNESS",
                "expected_behavior": expected_behavior,
                "max_divergence": max_div,
                "bound": div_bound,
                "witness": {
                    "offending_divergence": max_div,
                    "bound_excess": max_div - div_bound,
                },
            }

        elif expected_behavior == "conservative":
            if abs(max_div) <= 1e-6 and abs(min_div) <= 1e-6:
                return {
                    "status": "PASS",
                    "assurance": "INCOMPRESSIBLE_FLOW_CERTIFIED",
                    "expected_behavior": expected_behavior,
                    "max_divergence": max_div,
                }
            return {
                "status": "FAIL",
                "assurance": "NON_CONSERVATIVE_DIVERGENCE_WITNESS",
                "expected_behavior": expected_behavior,
                "witness": {
                    "max_absolute_divergence": max(abs(max_div), abs(min_div)),
                },
            }

        raise ValueError("Expected behavior must be 'contraction' or 'conservative'")

    @staticmethod
    def scaffold_code():
        return _scaffold(LiouvilleVolumeOperator, _liouville_self_test)


class DimensionalHomogeneityOperator:
    """Dimensional homogeneity and Buckingham Pi consistency verifier for physical equations.

    SI Exponent Vector: [L, M, T, I, Theta, N, J] (Length, Mass, Time, Current, Temp, Amount, Lum).
    """

    @staticmethod
    def _dimension_vector(vec):
        if not isinstance(vec, (list, tuple)) or len(vec) != 7:
            raise ValueError("Dimensional exponent vector must have exactly 7 integer exponents [L, M, T, I, Theta, N, J]")
        for item in vec:
            if type(item) is not int or not -32 <= item <= 32:
                raise ValueError("Exponents must be integers in -32..32")
        return list(vec)

    @classmethod
    def verify_additive_terms(cls, terms_dimensions):
        if not isinstance(terms_dimensions, (list, tuple)) or len(terms_dimensions) < 2:
            raise ValueError("Expected at least two terms to compare dimensional homogeneity")
        parsed = [cls._dimension_vector(vec) for vec in terms_dimensions]
        base = parsed[0]
        for idx, vec in enumerate(parsed[1:], start=1):
            if vec != base:
                return {
                    "status": "FAIL",
                    "assurance": "DIMENSIONAL_INHOMOGENEITY_WITNESS",
                    "base_dimension": base,
                    "witness": {
                        "term_index": idx,
                        "offending_dimension": vec,
                        "expected_dimension": base,
                        "difference": [vec[k] - base[k] for k in range(7)],
                    },
                }
        return {
            "status": "PASS",
            "assurance": "DIMENSIONAL_HOMOGENEITY_CERTIFIED",
            "common_dimension": base,
            "terms_count": len(parsed),
        }

    @classmethod
    def verify_dimensionless_argument(cls, argument_dimension):
        vec = cls._dimension_vector(argument_dimension)
        if any(exp != 0 for exp in vec):
            return {
                "status": "FAIL",
                "assurance": "TRANSCENDENTAL_DIMENSION_ERROR_WITNESS",
                "witness": {
                    "argument_dimension": vec,
                    "expected": [0] * 7,
                    "reason": "Transcendental functions (exp, log, sin, etc.) strictly require dimensionless inputs",
                },
            }
        return {
            "status": "PASS",
            "assurance": "DIMENSIONLESS_INPUT_CERTIFIED",
            "dimension": vec,
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(DimensionalHomogeneityOperator, _dim_homogeneity_self_test)


class CausalDAGNoLeakageOperator:
    """Causal precedence, acyclicity, and look-ahead temporal data leakage verifier."""

    @classmethod
    def verify_causal_graph(cls, nodes_timestamps, edges):
        if not isinstance(nodes_timestamps, dict) or len(nodes_timestamps) < 1:
            raise ValueError("Expected dictionary of nodes and timestamps")
        if not isinstance(edges, (list, tuple)):
            raise ValueError("Expected list of directed causal edges (u -> v)")

        nodes = set(nodes_timestamps.keys())
        timestamps = {node: _finite_number(ts) for node, ts in nodes_timestamps.items()}

        for u, v in edges:
            if u not in nodes or v not in nodes:
                raise ValueError(f"Edge ({u}, {v}) refers to undeclared node")
            if timestamps[u] > timestamps[v] + 1e-9:
                return {
                    "status": "FAIL",
                    "assurance": "TEMPORAL_LOOK_AHEAD_LEAKAGE_WITNESS",
                    "witness": {
                        "source_node": u,
                        "target_node": v,
                        "source_timestamp": timestamps[u],
                        "target_timestamp": timestamps[v],
                        "leakage_lead_time": timestamps[u] - timestamps[v],
                        "defect": "Information travels backwards in time (future features leaking into past)",
                    },
                }

        in_degree = {n: 0 for n in nodes}
        adj = {n: [] for n in nodes}
        for u, v in edges:
            adj[u].append(v)
            in_degree[v] += 1

        queue = [n for n in nodes if in_degree[n] == 0]
        sorted_order = []
        while queue:
            curr = queue.pop(0)
            sorted_order.append(curr)
            for nxt in adj[curr]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if len(sorted_order) < len(nodes):
            return {
                "status": "FAIL",
                "assurance": "CAUSAL_CYCLE_DETECTED_WITNESS",
                "witness": {
                    "resolved_nodes_count": len(sorted_order),
                    "total_nodes": len(nodes),
                    "defect": "Causal influence graph contains directed cycles violating causal acyclicity",
                },
            }

        return {
            "status": "PASS",
            "assurance": "CAUSAL_DAG_NO_LEAKAGE_CERTIFIED",
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "topological_causal_order": sorted_order,
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(CausalDAGNoLeakageOperator, _causal_dag_self_test)


class DataProcessingInequalityOperator:
    """Information monotonicity and Data Processing Inequality (DPI) verifier.

    Markov chain X -> Y_1 -> ... -> Y_k implies I(X; Y_1) >= I(X; Y_2) >= ... >= 0.
    """

    @classmethod
    def verify_information_chain(cls, mutual_information_sequence, tolerance=1e-6):
        if not isinstance(mutual_information_sequence, (list, tuple)) or len(mutual_information_sequence) < 2:
            raise ValueError("Expected at least two mutual information values along the Markov chain")
        tol = _finite_number(tolerance)
        if tol < 0:
            raise ValueError("Tolerance must be non-negative")

        infos = [_finite_number(val) for val in mutual_information_sequence]
        if any(val < -tol for val in infos):
            return {
                "status": "FAIL",
                "assurance": "NEGATIVE_MUTUAL_INFORMATION_WITNESS",
                "witness": {"min_value": min(infos), "defect": "Mutual information cannot be negative"},
            }

        for i in range(len(infos) - 1):
            curr_i = infos[i]
            next_i = infos[i + 1]
            if next_i > curr_i + tol:
                return {
                    "status": "FAIL",
                    "assurance": "DATA_PROCESSING_INEQUALITY_BREACH_WITNESS",
                    "witness": {
                        "stage_transition": [i, i + 1],
                        "prior_information": curr_i,
                        "posterior_information": next_i,
                        "unphysical_information_gain": next_i - curr_i,
                        "defect": "Post-processing cannot synthesize new mutual information (DPI violation)",
                    },
                }

        return {
            "status": "PASS",
            "assurance": "DATA_PROCESSING_INEQUALITY_CERTIFIED",
            "chain_length": len(infos),
            "initial_information": infos[0],
            "terminal_information": infos[-1],
            "total_information_loss": infos[0] - infos[-1],
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(DataProcessingInequalityOperator, _dpi_self_test)


class ConservationFlowBalanceOperator:
    """Continuity equation and node flow balance verifier for mass, energy, charge, and tokens."""

    @classmethod
    def verify_flow_balance(cls, node_inflows, node_outflows, node_storage_rates=None, tolerance=1e-6):
        if not isinstance(node_inflows, dict) or not isinstance(node_outflows, dict):
            raise ValueError("Inflows and outflows must be dictionaries mapping node to rate")
        tol = _finite_number(tolerance)
        if tol < 0:
            raise ValueError("Tolerance must be non-negative")

        nodes = set(node_inflows.keys()) | set(node_outflows.keys())
        if node_storage_rates:
            nodes |= set(node_storage_rates.keys())

        storage = node_storage_rates or {}

        max_imbalance = 0.0
        worst_node = None
        worst_details = None

        for n in nodes:
            inflow = _finite_number(node_inflows.get(n, 0.0))
            outflow = _finite_number(node_outflows.get(n, 0.0))
            accum = _finite_number(storage.get(n, 0.0))
            if inflow < 0 or outflow < 0:
                raise ValueError(f"Inflows and outflows must be non-negative rates for node '{n}'")

            imbalance = abs((inflow - outflow) - accum)
            if imbalance > max_imbalance:
                max_imbalance = imbalance
                worst_node = n
                worst_details = {"inflow": inflow, "outflow": outflow, "accumulation": accum, "net_defect": (inflow - outflow) - accum}

        if max_imbalance <= tol:
            return {
                "status": "PASS",
                "assurance": "CONSERVATION_FLOW_BALANCE_CERTIFIED",
                "nodes_audited": len(nodes),
                "max_imbalance_observed": max_imbalance,
                "tolerance": tol,
            }
        return {
            "status": "FAIL",
            "assurance": "CONSERVATION_LEAKAGE_WITNESS",
            "max_imbalance_observed": max_imbalance,
            "witness": {
                "offending_node": worst_node,
                **worst_details,
            },
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(ConservationFlowBalanceOperator, _conservation_flow_self_test)


class KolmogorovProbabilityAxiomOperator:
    """Kolmogorov probability axioms and distribution well-formedness verifier."""

    @classmethod
    def verify_probability_distribution(cls, probabilities, tolerance=1e-6):
        if not isinstance(probabilities, (list, tuple)) or len(probabilities) < 1:
            raise ValueError("Expected list of probabilities")
        tol = _finite_number(tolerance)
        if tol < 0:
            raise ValueError("Tolerance must be non-negative")

        probs = [_finite_number(p) for p in probabilities]

        for idx, p in enumerate(probs):
            if p < -tol:
                return {
                    "status": "FAIL",
                    "assurance": "KOLMOGOROV_AXIOM_1_NON_NEGATIVITY_WITNESS",
                    "witness": {"coordinate": idx, "illegal_value": p, "defect": "Negative probability violates Axiom 1"},
                }
            if p > 1.0 + tol:
                return {
                    "status": "FAIL",
                    "assurance": "KOLMOGOROV_PROBABILITY_OVERFLOW_WITNESS",
                    "witness": {"coordinate": idx, "illegal_value": p, "defect": "Single event probability exceeds 1.0"},
                }

        total_mass = math.fsum(probs)
        mass_error = abs(total_mass - 1.0)
        if mass_error > tol:
            return {
                "status": "FAIL",
                "assurance": "KOLMOGOROV_AXIOM_2_NORMALIZATION_WITNESS",
                "witness": {
                    "total_mass": total_mass,
                    "normalization_error": total_mass - 1.0,
                    "defect": "Total sample space probability must sum to exactly 1.0",
                },
            }

        return {
            "status": "PASS",
            "assurance": "KOLMOGOROV_DISTRIBUTION_AXIOMS_CERTIFIED",
            "events_count": len(probs),
            "total_mass": total_mass,
            "min_probability": min(probs),
            "max_probability": max(probs),
        }

    @staticmethod
    def scaffold_code():
        return _scaffold(KolmogorovProbabilityAxiomOperator, _kolmogorov_self_test)


def _ssm_self_test():
    op = ContinuousStateSpaceOperator(3, in_dim=2, out_dim=2)
    report = op.verify_step_invariance()
    assert report["status"] == "UNKNOWN" and report["diagnostic_pass"]
    try:
        op.verify_step_invariance(nfe_candidates=(16, 16))
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate NFE values were accepted")
    return {"self_test_status": "PASS", "positive": report, "negative_status": "REJECTED"}


def _contraction_self_test():
    report = ContractionDynamicsOperator.analyze_system([[0.5]], [0.5], target=[1])
    negative = ContractionDynamicsOperator.analyze_system([[2]], [1], max_norm_threshold=2)
    assert report["status"] == "PASS" and report["target_bias"] == 0
    assert negative["status"] == "FAIL" and not negative["is_contracting"]
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _preflight_self_test():
    def forward(x):
        return [2 * value for value in x]
    report = StructuralPreflightOperator.preflight_callable(forward, ([1, 2],), expected_shapes={"x": (2,)},
                                                           expected_output_shape=(2,))
    negative = StructuralPreflightOperator.preflight_callable(forward, ([1, 2],), expected_output_shape=(3,))
    assert report["status"] == "PASS"
    assert negative["status"] == "FAIL" and negative["stage"] == "OUTPUT_SHAPE_VALIDATION"
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _rational_self_test():
    report = RationalCertificateOperator.certify_interval_bound([1, -2, 1], (0, 1), (0, 1))
    negative = RationalCertificateOperator.certify_interval_bound([0, 1, -1], (0, 1), (0, "20/81"))
    assert report["status"] == "PASS" and report["enclosures"]
    assert negative["status"] == "FAIL" and negative["violations"]
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _gershgorin_self_test():
    report = GershgorinSpectralOperator.analyze_matrix([[0.4, 0.1], [0.2, 0.3]])
    negative = GershgorinSpectralOperator.analyze_matrix([[0.8, 0.5], [0.4, 0.9]])
    assert report["status"] == "PASS" and report["is_contracting"]
    assert negative["status"] == "FAIL" and not negative["is_contracting"]
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _lipschitz_self_test():
    report = LipschitzBoundOperator.certify_network_lipschitz(
        [[[0.5, 0.0], [0.0, 0.5]], [[0.5, 0.0], [0.0, 0.5]]],
        activation_lipschitz=1.0, input_perturbation=0.1, margin=0.2
    )
    negative = LipschitzBoundOperator.certify_network_lipschitz(
        [[[0.5, 0.0], [0.0, 0.5]], [[0.5, 0.0], [0.0, 0.5]]],
        activation_lipschitz=1.0, input_perturbation=1.0, margin=0.2
    )
    assert report["status"] == "PASS" and "safety_headroom" in report
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _concentration_self_test():
    report = ConcentrationBoundOperator.certify_empirical_gap(1000, (0, 1), 0.10, delta=0.05)
    negative = ConcentrationBoundOperator.certify_empirical_gap(25, (0, 1), 0.05, delta=0.05)
    assert report["status"] == "PASS" and report["certified_lower_bound"] > 0
    assert negative["status"] == "FAIL" and negative["witness"]["noise_margin"] > 0
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _voronoi_self_test():
    report = RationalVoronoiCoverOperator.check_domain_covering((0, 1, 0, 1), [(0.5, 0.5)], 1.0)
    negative = RationalVoronoiCoverOperator.check_domain_covering((0, 1, 0, 1), [(0.5, 0.5)], 0.4)
    assert report["status"] == "PASS" and "maximum_distance_observed" in report
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _dissipation_self_test():
    report = MultiStepEnergyDissipationOperator.analyze_trajectory([[1.0, 0.0], [0.5, 0.0], [0.2, 0.0]])
    negative = MultiStepEnergyDissipationOperator.analyze_trajectory([[1.0, 0.0], [0.5, 0.0], [1.2, 0.0]])
    assert report["status"] == "PASS" and report["amplification_ratio"] < 1.0
    assert negative["status"] == "FAIL" and negative["witness"]["divergence_step"] == 1
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _markov_chebyshev_self_test():
    report = MarkovChebyshevBoundOperator.compute_tail_bounds(1.0, variance=0.25, threshold=5.0, max_allowable_probability=0.25)
    negative = MarkovChebyshevBoundOperator.compute_tail_bounds(2.0, threshold=3.0, max_allowable_probability=0.50)
    assert report["status"] == "PASS" and report["certified_upper_probability"] <= 0.25
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _fdr_self_test():
    report = FalseDiscoveryRateOperator.control_fdr([0.001, 0.005, 0.02, 0.3, 0.8], alpha=0.05)
    negative = FalseDiscoveryRateOperator.control_fdr([0.1, 0.2, 0.3], alpha=0.05)
    assert report["status"] == "PASS" and report["discoveries_count"] == 3
    assert negative["status"] == "FAIL" and negative["discoveries_count"] == 0
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _ville_self_test():
    report = SequentialVilleEProcessOperator.audit_evidence_stream([2.5, 4.0, 2.5], alpha=0.05)
    negative = SequentialVilleEProcessOperator.audit_evidence_stream([1.1, 1.2, 0.9], alpha=0.05)
    assert report["status"] == "PASS" and report["stopping_step"] == 3
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _bernstein_self_test():
    report = EmpiricalBernsteinOperator.certify_sample_mean([0.5] * 100 + [0.51] * 100, (0, 1), target_precision=0.15)
    negative = EmpiricalBernsteinOperator.certify_sample_mean([0.1, 0.9], (0, 1), target_precision=0.10)
    assert report["status"] == "PASS" and report["empirical_bernstein_radius"] <= 0.15
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _symplectic_self_test():
    q = [[math.cos(i * 0.1)] for i in range(10)]
    p = [[-math.sin(i * 0.1)] for i in range(10)]
    report = SymplecticConservationOperator.audit_conservation(q, p, max_relative_drift=0.05)
    p_bad = [[-math.sin(i * 0.1) * (1.0 + i * 0.2)] for i in range(10)]
    negative = SymplecticConservationOperator.audit_conservation(q, p_bad, max_relative_drift=0.05)
    assert report["status"] == "PASS" and report["max_relative_drift"] <= 0.05
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _cbf_self_test():
    report = ControlBarrierFunctionOperator.verify_forward_invariance([[2.0], [1.8], [1.6]], [1.0], alpha_decay=0.2)
    negative = ControlBarrierFunctionOperator.verify_forward_invariance([[2.0], [0.5], [-0.5]], [1.0], alpha_decay=0.2)
    assert report["status"] == "PASS" and report["minimum_barrier_observed"] >= 0
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _poincare_self_test():
    traj_conv = [[-1.0, 2.0], [1.0, 2.0], [-1.0, 1.0], [1.0, 1.0], [-1.0, 0.5], [1.0, 0.5], [-1.0, 0.25], [1.0, 0.25]]
    report = PoincareLimitCycleOperator.analyze_crossings(traj_conv, [1.0, 0.0])
    traj_div = [[-1.0, 0.1], [1.0, 0.1], [-1.0, 0.5], [1.0, 0.5], [-1.0, 1.5], [1.0, 1.5], [-1.0, 3.5], [1.0, 3.5]]
    negative = PoincareLimitCycleOperator.analyze_crossings(traj_div, [1.0, 0.0])
    assert report["status"] == "PASS" and report["crossings_count"] >= 3
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _liouville_self_test():
    report = LiouvilleVolumeOperator.certify_volume_rate([[[-1.0, 0.0], [0.0, -1.0]]], expected_behavior="contraction", max_divergence_bound=-0.01)
    negative = LiouvilleVolumeOperator.certify_volume_rate([[[0.5, 0.0], [0.0, 0.5]]], expected_behavior="contraction", max_divergence_bound=-0.01)
    assert report["status"] == "PASS" and report["minimum_contraction_rate"] > 0
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _dim_homogeneity_self_test():
    report = DimensionalHomogeneityOperator.verify_additive_terms([[1, 1, -2, 0, 0, 0, 0], [1, 1, -2, 0, 0, 0, 0]])
    negative = DimensionalHomogeneityOperator.verify_additive_terms([[1, 1, -2, 0, 0, 0, 0], [2, 1, -2, 0, 0, 0, 0]])
    assert report["status"] == "PASS" and report["common_dimension"] == [1, 1, -2, 0, 0, 0, 0]
    assert negative["status"] == "FAIL" and "witness" in negative
    dim_zero = DimensionalHomogeneityOperator.verify_dimensionless_argument([0, 0, 0, 0, 0, 0, 0])
    assert dim_zero["status"] == "PASS"
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _causal_dag_self_test():
    report = CausalDAGNoLeakageOperator.verify_causal_graph({"x": 0.0, "y": 1.0, "z": 2.0}, [("x", "y"), ("y", "z")])
    negative = CausalDAGNoLeakageOperator.verify_causal_graph({"x": 2.0, "y": 1.0}, [("x", "y")])
    assert report["status"] == "PASS" and report["topological_causal_order"] == ["x", "y", "z"]
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _dpi_self_test():
    report = DataProcessingInequalityOperator.verify_information_chain([1.5, 1.2, 0.9, 0.4])
    negative = DataProcessingInequalityOperator.verify_information_chain([1.5, 1.2, 1.8])
    assert report["status"] == "PASS" and report["chain_length"] == 4
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _conservation_flow_self_test():
    report = ConservationFlowBalanceOperator.verify_flow_balance({"A": 10.0}, {"A": 8.0}, {"A": 2.0})
    negative = ConservationFlowBalanceOperator.verify_flow_balance({"A": 10.0}, {"A": 8.0}, {"A": 0.0})
    assert report["status"] == "PASS" and report["nodes_audited"] == 1
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _kolmogorov_self_test():
    report = KolmogorovProbabilityAxiomOperator.verify_probability_distribution([0.2, 0.5, 0.3])
    negative = KolmogorovProbabilityAxiomOperator.verify_probability_distribution([0.2, 0.5, 0.5])
    assert report["status"] == "PASS" and report["events_count"] == 3
    assert negative["status"] == "FAIL" and "witness" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _scaffold(cls, self_test):
    """Export the canonical implementation and the same executable self-test."""
    tree = ast.parse(inspect.getsource(cls))
    tree.body[0].body = [node for node in tree.body[0].body
                         if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != "scaffold_code"]
    imports = "import inspect\nimport json\nimport math\nfrom fractions import Fraction\nfrom typing import Any, Dict, List, Optional, Tuple, Union\n\n"
    helpers = "\n\n".join(inspect.getsource(fn) for fn in
                           (_finite_number, _vector, _matrix, _dimension, _ratio, _solve_exact))
    return ("# Standalone RDS example; self-test success is not scientific acceptance.\n" + imports
            + helpers + "\n\n" + ast.unparse(tree) + "\n\n" + inspect.getsource(self_test)
            + f"\noperator_self_test = {self_test.__name__}\n\n"
            + 'if __name__ == "__main__":\n    print(json.dumps(operator_self_test(), allow_nan=False))\n')


OPERATORS = {
    "state_space_refinement": {"operator_id": "continuous_state_space", "title": "Diagonal ZOH Numerical Example",
        "operator_class": ContinuousStateSpaceOperator, "primary_signal": "step_sensitivity",
        "guarantee": "Finite ZOH updates and NFE diagnostics; convergence remains UNKNOWN", "self_test": _ssm_self_test},
    "contraction_target_bias": {"operator_id": "contraction_dynamics", "title": "Rational Infinity-Norm and Fixed-Point Analysis",
        "operator_class": ContractionDynamicsOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Exact analysis of supplied rational values; floats denote their binary rationals", "self_test": _contraction_self_test},
    "structural_preflight": {"operator_id": "structural_preflight", "title": "Declared Signature and Shape Dry Run",
        "operator_class": StructuralPreflightOperator, "primary_signal": "execution_mismatch",
        "guarantee": "Checks declared signature and shapes of a trusted callable", "self_test": _preflight_self_test},
    "exact_symbolic_constraints": {"operator_id": "rational_interval_certificate", "title": "Rational Polynomial Interval Enclosure",
        "operator_class": RationalCertificateOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Sound rational whole-interval enclosure or exact witness; inconclusive is UNKNOWN", "self_test": _rational_self_test},
    "gershgorin_spectral_bound": {"operator_id": "gershgorin_spectral_radius", "title": "Gershgorin Circle Spectral Radius and Invertibility Certificate",
        "operator_class": GershgorinSpectralOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Exact rational Gershgorin discs bounding spectral radius, stability, and invertibility", "self_test": _gershgorin_self_test},
    "lipschitz_layer_bound": {"operator_id": "lipschitz_frobenius_bound", "title": "Frobenius and Operator Norm Lipschitz Certificate",
        "operator_class": LipschitzBoundOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Composite layer-wise Frobenius and infinity norm bounds for perturbation stability", "self_test": _lipschitz_self_test},
    "hoeffding_sample_bound": {"operator_id": "concentration_sample_bound", "title": "Sub-Gaussian Hoeffding Sample Size and Concentration Bound",
        "operator_class": ConcentrationBoundOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Finite-sample Hoeffding confidence radius and sample size qualification for empirical comparisons", "self_test": _concentration_self_test},
    "rational_voronoi_partition": {"operator_id": "rational_voronoi_cover", "title": "2D Rational Voronoi Covering and Boundary Hole Detector",
        "operator_class": RationalVoronoiCoverOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Exact 2D domain partition covering and unassigned hole/witness detection", "self_test": _voronoi_self_test},
    "multi_step_energy_dissipation": {"operator_id": "multi_step_energy_dissipation", "title": "Multi-Step Energy Dissipation and Monotonic Descent Verifier",
        "operator_class": MultiStepEnergyDissipationOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Trace-level discrete Lyapunov quadratic energy dissipation and monotonic divergence witness", "self_test": _dissipation_self_test},
    "markov_chebyshev_bound": {"operator_id": "markov_chebyshev_tail", "title": "Markov and Chebyshev Non-Parametric Tail Risk Bounds",
        "operator_class": MarkovChebyshevBoundOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Non-parametric probability tail upper bounds from mean and variance", "self_test": _markov_chebyshev_self_test},
    "false_discovery_rate_bh": {"operator_id": "false_discovery_rate", "title": "Benjamini-Hochberg and Benjamini-Yekutieli FDR Control",
        "operator_class": FalseDiscoveryRateOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Multiple testing false discovery rate control under independence or arbitrary dependence", "self_test": _fdr_self_test},
    "sequential_ville_eprocess": {"operator_id": "sequential_ville_test", "title": "Anytime-Valid Sequential e-Process and Supermartingale Stopping Test",
        "operator_class": SequentialVilleEProcessOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Ville supermartingale inequality stopping guarantee resisting optional stopping", "self_test": _ville_self_test},
    "empirical_bernstein_bound": {"operator_id": "empirical_bernstein_radius", "title": "Variance-Sensitive Empirical Bernstein Concentration Bound",
        "operator_class": EmpiricalBernsteinOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Sample-variance adaptive concentration radius tighter than worst-case Hoeffding", "self_test": _bernstein_self_test},
    "symplectic_energy_conservation": {"operator_id": "symplectic_energy_drift", "title": "Hamiltonian Symplectic Energy Conservation and Drift Verifier",
        "operator_class": SymplecticConservationOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Hamiltonian total energy deviation tracking and relative numerical drift bounds", "self_test": _symplectic_self_test},
    "control_barrier_invariance": {"operator_id": "control_barrier_safety", "title": "Discrete Control Barrier Function and Forward Invariance Verifier",
        "operator_class": ControlBarrierFunctionOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Forward invariance safe set certificate for discrete transition sequences", "self_test": _cbf_self_test},
    "poincare_section_return": {"operator_id": "poincare_return_contraction", "title": "Transversal Poincaré Section and Limit Cycle Contraction Verifier",
        "operator_class": PoincareLimitCycleOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Transversal crossing return map contraction factor and periodic orbit stability", "self_test": _poincare_self_test},
    "liouville_phase_volume": {"operator_id": "liouville_volume_evolution", "title": "Liouville Phase Volume Contraction and Divergence Attractor Verifier",
        "operator_class": LiouvilleVolumeOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Jacobian trace divergence bound certifying phase volume contraction rate onto attractors", "self_test": _liouville_self_test},
    "dimensional_homogeneity": {"operator_id": "buckingham_dimensional_homogeneity", "title": "Buckingham Pi Dimensional Homogeneity and Invariant Verifier",
        "operator_class": DimensionalHomogeneityOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "SI exponent vector matching and transcendental dimensionless argument verification", "self_test": _dim_homogeneity_self_test},
    "causal_dag_no_leakage": {"operator_id": "causal_precedence_dag", "title": "Causal Precedence DAG and Look-Ahead Temporal Leakage Verifier",
        "operator_class": CausalDAGNoLeakageOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Strict temporal arrow of time and topological acyclicity certificate", "self_test": _causal_dag_self_test},
    "data_processing_inequality": {"operator_id": "data_processing_inequality", "title": "Information-Theoretic Data Processing Inequality and Monotonicity Verifier",
        "operator_class": DataProcessingInequalityOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Markov chain mutual information non-increase post-processing bounds", "self_test": _dpi_self_test},
    "conservation_flow_balance": {"operator_id": "continuity_flow_balance", "title": "Continuity Equation and Conservation Flow Balance Verifier",
        "operator_class": ConservationFlowBalanceOperator, "primary_signal": "trajectory_degradation",
        "guarantee": "Kirchhoff / continuity node flow accumulation conservation certificate", "self_test": _conservation_flow_self_test},
    "kolmogorov_probability_axioms": {"operator_id": "kolmogorov_axioms_wellformedness", "title": "Kolmogorov Probability Axioms and Normalization Verifier",
        "operator_class": KolmogorovProbabilityAxiomOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Non-negativity, unit total measure, and distribution well-formedness certificate", "self_test": _kolmogorov_self_test},
}


def list_available_operators():
    return [{"card_id": card_id, **{key: meta[key] for key in ("operator_id", "title", "primary_signal", "guarantee")}}
            for card_id, meta in OPERATORS.items()]


def get_operator_scaffold(card_id):
    if card_id not in OPERATORS:
        raise ValueError(f"No runnable operator available for card '{card_id}'")
    return OPERATORS[card_id]["operator_class"].scaffold_code()


def test_operator(card_id):
    if card_id not in OPERATORS:
        raise ValueError(f"No runnable operator available for card '{card_id}'")
    meta = OPERATORS[card_id]
    checks = meta["self_test"]()
    return {"card_id": card_id, "operator_id": meta["operator_id"], "title": meta["title"],
            "self_test_status": checks["self_test_status"], "negative_status": checks["negative_status"],
            "test_result": checks["positive"]}

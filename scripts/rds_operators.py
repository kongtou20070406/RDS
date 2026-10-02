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

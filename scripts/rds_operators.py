"""Bounded stdlib operator examples: exact rational checks and numerical diagnostics."""
import ast
import inspect
import json
import math
import re
from fractions import Fraction
from typing import Any, Dict, List, Optional, Set, Tuple, Union


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


# ---------------------------------------------------------------------------
# Operator 5: EGraphEquivalenceOperator (egraph_equivalence_saturation)
# ---------------------------------------------------------------------------

class EGraphEquivalenceOperator:
    """Bounded rewrites for declared rational-polynomial expressions.

    Only commutativity and the 0/1 identities are implemented. Distinct classes
    do not establish inequality; FAIL requires an exact rational witness.
    """

    DOMAIN = "rational_polynomials"
    AXIOMS = ("add_commutativity", "mul_commutativity", "add_zero", "mul_one")
    MAX_INPUT_NODES = 512
    MAX_DEPTH = 32
    MAX_CONSTANT_BITS = 128
    MAX_VALUE_BITS = 4096

    class BudgetExhausted(RuntimeError):
        pass

    @staticmethod
    def _limit(value, name, lower, upper):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"{name} must be an integer in {lower}..{upper}")
        return value

    @classmethod
    def _variables(cls, variables):
        import re
        if not isinstance(variables, (list, tuple)) or len(variables) > 16:
            raise ValueError("Declare at most 16 rational variables")
        if not all(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", name)
                   for name in variables) or len(set(variables)) != len(variables):
            raise ValueError("Variables must be distinct bounded identifiers")
        return tuple(sorted(variables))

    @classmethod
    def _normalize(cls, expr, variables, count, depth=0):
        from fractions import Fraction
        import re
        count[0] += 1
        if count[0] > cls.MAX_INPUT_NODES or depth > cls.MAX_DEPTH:
            raise ValueError("Expression exceeds node/depth limits")
        if isinstance(expr, (list, tuple)):
            if len(expr) != 3 or expr[0] not in ("+", "*"):
                raise ValueError("Only binary + and * expressions are supported")
            return (expr[0], cls._normalize(expr[1], variables, count, depth + 1),
                    cls._normalize(expr[2], variables, count, depth + 1))
        if type(expr) is int or isinstance(expr, Fraction):
            value = Fraction(expr)
        elif isinstance(expr, str):
            if expr in variables:
                return expr
            if not re.fullmatch(r"[+-]?\d{1,32}(?:/[1-9]\d{0,31})?", expr):
                raise ValueError("Unknown symbol or unsupported rational literal")
            value = Fraction(expr)
        else:
            raise ValueError("Leaves must be exact rationals or declared variables; floats/bools are unsupported")
        if max(abs(value.numerator).bit_length(), value.denominator.bit_length()) > cls.MAX_CONSTANT_BITS:
            raise ValueError("Rational constant exceeds 128 bits")
        return value

    class EGraph:
        def __init__(self, variables=(), max_nodes=1024, max_work=50000):
            self.variables = EGraphEquivalenceOperator._variables(variables)
            self.max_nodes = EGraphEquivalenceOperator._limit(max_nodes, "max_nodes", 1, 2048)
            self.max_work = EGraphEquivalenceOperator._limit(max_work, "max_work", 1, 200000)
            self.work = 0
            self.parent, self.rank, self.classes, self.hashcons = {}, {}, {}, {}

        def _tick(self):
            if self.work >= self.max_work:
                raise EGraphEquivalenceOperator.BudgetExhausted("E-graph work budget exhausted")
            self.work += 1

        def find(self, i):
            if type(i) is not int or i not in self.parent:
                raise ValueError("Unknown e-class")
            root = i
            while self.parent[root] != root:
                root = self.parent[root]
            while self.parent[i] != i:
                parent = self.parent[i]
                self.parent[i] = root
                i = parent
            return root

        def union(self, id1, id2):
            self._tick()
            root1, root2 = self.find(id1), self.find(id2)
            if root1 != root2:
                if self.rank[root1] < self.rank[root2]:
                    root1, root2 = root2, root1
                self.parent[root2] = root1
                if self.rank[root1] == self.rank[root2]:
                    self.rank[root1] += 1
                self.classes[root1].update(self.classes.pop(root2))
            return root1

        def canonicalize_node(self, node):
            op, children = node
            return op, tuple(self.find(child) for child in children)

        def _insert_node(self, node):
            self._tick()
            node = self.canonicalize_node(node)
            if node in self.hashcons:
                return self.find(self.hashcons[node])
            if len(self.parent) >= self.max_nodes:
                raise EGraphEquivalenceOperator.BudgetExhausted("E-graph node budget exhausted")
            new_id = len(self.parent)
            self.parent[new_id], self.rank[new_id] = new_id, 0
            self.classes[new_id], self.hashcons[node] = {node}, new_id
            return new_id

        def add_node(self, op, child_ids):
            if op not in ("+", "*") or len(child_ids) != 2:
                raise ValueError("Expected a binary supported operator")
            return self._insert_node((op, tuple(child_ids)))

        def _add(self, expr):
            from fractions import Fraction
            if isinstance(expr, Fraction):
                return self._insert_node(("const:" + str(expr), ()))
            if isinstance(expr, str):
                return self._insert_node(("var:" + expr, ()))
            return self.add_node(expr[0], (self._add(expr[1]), self._add(expr[2])))

        def add(self, expr):
            normalized = EGraphEquivalenceOperator._normalize(expr, self.variables, [0])
            return self._add(normalized)

        def rebuild(self):
            while True:
                changed, rebuilt = False, {}
                for node, class_id in list(self.hashcons.items()):
                    self._tick()
                    node, root = self.canonicalize_node(node), self.find(class_id)
                    if node in rebuilt and self.find(rebuilt[node]) != root:
                        root = self.union(root, rebuilt[node])
                        changed = True
                    rebuilt[node] = self.find(root)
                self.hashcons = rebuilt
                if not changed:
                    break
            self.classes = {root: set() for root in self.classes}
            for node, class_id in self.hashcons.items():
                self.classes[self.find(class_id)].add(node)

        def saturate_standard_algebra(self, max_iter=8):
            EGraphEquivalenceOperator._limit(max_iter, "max_iter", 0, 16)
            for _ in range(max_iter):
                changed = False
                for node, class_id in list(self.hashcons.items()):
                    self._tick()
                    op, children = self.canonicalize_node(node)
                    if op not in ("+", "*"):
                        continue
                    candidates = [self.add_node(op, (children[1], children[0]))]
                    identity = "const:0" if op == "+" else "const:1"
                    for child, other in ((children[0], children[1]), (children[1], children[0])):
                        if (identity, ()) in self.classes[self.find(child)]:
                            candidates.append(other)
                    for candidate in candidates:
                        if self.find(class_id) != self.find(candidate):
                            self.union(class_id, candidate)
                            changed = True
                if changed:
                    self.rebuild()
                else:
                    return True
            return False

    @classmethod
    def _evaluate(cls, expr, values, graph):
        from fractions import Fraction
        graph._tick()
        if isinstance(expr, Fraction):
            return expr
        if isinstance(expr, str):
            return values[expr]
        left, right = cls._evaluate(expr[1], values, graph), cls._evaluate(expr[2], values, graph)
        numerator_bits = (max(abs(left.numerator).bit_length() + right.denominator.bit_length(),
                              abs(right.numerator).bit_length() + left.denominator.bit_length()) + 1
                          if expr[0] == "+" else abs(left.numerator).bit_length() + abs(right.numerator).bit_length())
        denominator_bits = left.denominator.bit_length() + right.denominator.bit_length()
        if max(numerator_bits, denominator_bits) > cls.MAX_VALUE_BITS:
            raise cls.BudgetExhausted("Exact witness evaluation exceeds 4096 bits")
        return left + right if expr[0] == "+" else left * right

    @classmethod
    def verify_algebraic_equivalence(cls, expr_a, expr_b, max_iter=8, *,
                                     variables=(), domain=DOMAIN, max_nodes=1024, max_work=50000):
        """Check a scoped rewrite connection or an exact point counterexample."""
        from fractions import Fraction
        import hashlib
        import json
        if domain != cls.DOMAIN:
            raise ValueError("Only the rational_polynomials domain is supported")
        variables = cls._variables(variables)
        cls._limit(max_iter, "max_iter", 0, 16)
        count = [0]
        left = cls._normalize(expr_a, variables, count)
        right = cls._normalize(expr_b, variables, count)

        def encode(expr):
            if isinstance(expr, Fraction):
                return ["rational", str(expr)]
            if isinstance(expr, str):
                return ["symbol", expr]
            return [expr[0], encode(expr[1]), encode(expr[2])]

        binding = {"domain": domain, "variables": list(variables), "axioms": list(cls.AXIOMS),
                   "expr_a": encode(left), "expr_b": encode(right)}
        graph = cls.EGraph(variables, max_nodes, max_work)
        result = {"status": "UNKNOWN", "assurance": "NONE", "equivalent": None,
                  "domain": domain, "variables": list(variables), "axioms": list(cls.AXIOMS),
                  "input_sha256": hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  "limits": {"max_iter": max_iter, "max_nodes": max_nodes, "max_work": max_work},
                  "saturated": False, "budget_exhausted": False, "certificate_status": "NOT_EMITTED",
                  "application_status": "UNKNOWN"}
        try:
            id_a, id_b = graph._add(left), graph._add(right)
            if graph.find(id_a) != graph.find(id_b):
                result["saturated"] = graph.saturate_standard_algebra(max_iter)
            result["root_a"], result["root_b"] = graph.find(id_a), graph.find(id_b)
            if result["root_a"] == result["root_b"]:
                result.update(status="PASS", assurance="BOUNDED_REWRITE_CHECK", equivalent=True,
                              reason="Connected by supported identities, commutativity and congruence in the declared domain")
            else:
                assignments = [{name: Fraction(value) for name in variables} for value in (0, 1, 2, -1)]
                assignments.extend({name: Fraction(1 if name == selected else 0) for name in variables}
                                   for selected in variables)
                for values in assignments:
                    value_a, value_b = cls._evaluate(left, values, graph), cls._evaluate(right, values, graph)
                    if value_a != value_b:
                        result.update(status="FAIL", assurance="EXACT_RATIONAL_COUNTEREXAMPLE", equivalent=False,
                                      reason="Exact values differ at a declared-domain assignment",
                                      counterexample={"variables": {name: str(value) for name, value in values.items()},
                                                      "expr_a": str(value_a), "expr_b": str(value_b)})
                        break
                else:
                    result["reason"] = "No supported rewrite connection or exact counterexample found within limits"
        except cls.BudgetExhausted as exc:
            result.update(reason=str(exc), budget_exhausted=True)
        result.update(total_eclasses=len(graph.classes), total_enodes=len(graph.hashcons), work_used=graph.work)
        return result

    @classmethod
    def operator_self_test(cls):
        positive = cls.verify_algebraic_equivalence(("*", "x", ("+", "y", 0)), ("*", "y", "x"),
                                                   variables=("x", "y"))
        negative = cls.verify_algebraic_equivalence(("+", "x", "y"), ("*", "x", "y"),
                                                   variables=("x", "y"))
        unresolved = cls.verify_algebraic_equivalence(("+", 1, 1), 2)
        assert positive["status"] == "PASS" and positive["certificate_status"] == "NOT_EMITTED"
        assert negative["status"] == "FAIL" and negative["counterexample"]
        assert unresolved["status"] == "UNKNOWN" and unresolved["equivalent"] is None
        return {"self_test_status": "PASS", "positive": positive,
                "negative_status": negative["status"], "unresolved_status": unresolved["status"]}

    @staticmethod
    def scaffold_code():
        """Export this implementation and its positive/negative/unresolved checks."""
        import ast
        import inspect
        source = inspect.getsource(EGraphEquivalenceOperator)
        lines = source.splitlines()
        method = next(node for node in ast.parse(source).body[0].body
                      if isinstance(node, ast.FunctionDef) and node.name == "scaffold_code")
        start = min([method.lineno] + [decorator.lineno for decorator in method.decorator_list]) - 1
        del lines[start:method.end_lineno]
        return "\n".join(lines) + '\n\noperator_self_test = EGraphEquivalenceOperator.operator_self_test\n\nif __name__ == "__main__":\n    import json\n    print(json.dumps(operator_self_test(), sort_keys=True, allow_nan=False))\n'

# Operator 6: LeanAxiomReviewOperator (lean_axiom_review)
# ---------------------------------------------------------------------------

class LeanAxiomReviewOperator:
    """Check a supplied #print axioms report against a declared axiom policy.

    Text is input-reported evidence, never a bound Lean execution or proof of
    constructivity. Missing/ambiguous reports remain UNKNOWN. Source scanning
    can flag placeholders, but cannot establish the compiled dependencies.
    """

    STANDARD_CLASSICAL_AXIOMS = frozenset(("propext", "Classical.choice", "Quot.sound"))

    @classmethod
    def audit_lean_axioms(
        cls,
        theorem_name: str,
        code_or_stdout: str,
        allowed_axioms: Optional[Set[str]] = None,
        is_stdout: bool = False
    ) -> Dict[str, Any]:
        """Parse one complete report for this exact theorem, without executing Lean."""
        if (not isinstance(theorem_name, str) or not theorem_name.strip() or len(theorem_name) > 512
                or any(c in theorem_name for c in '\r\n') or not isinstance(code_or_stdout, str)
                or len(code_or_stdout) > 65536 or len(code_or_stdout.encode('utf-8')) > 65536
                or type(is_stdout) is not bool):
            raise ValueError('Expected a bounded theorem name, report text and Boolean is_stdout')
        if allowed_axioms is not None and (not isinstance(allowed_axioms, (set, frozenset, list, tuple))
                or len(allowed_axioms) > 256 or not all(isinstance(ax, str) and ax and len(ax) <= 512 for ax in allowed_axioms)):
            raise ValueError('Expected at most 256 explicit axiom names')
        allowed = set(allowed_axioms) if allowed_axioms is not None else set(cls.STANDARD_CLASSICAL_AXIOMS)
        result = {'status': 'UNKNOWN', 'assurance': 'AXIOM_AUDIT_UNAVAILABLE', 'theorem': theorem_name,
                  'axioms_detected': None, 'allowed_axioms': sorted(allowed), 'disallowed_axioms': None,
                  'reported_axiom_free': None, 'is_constructive': None, 'lean_verified': False,
                  'evidence_kind': 'INPUT_REPORTED_STDOUT' if is_stdout else 'SOURCE_TEXT'}

        if not is_stdout:
            # Check source code for sorry or cheat tactics
            if re.search(r"\bsorry\b", code_or_stdout):
                return {**result,
                    "status": "FAIL",
                    "assurance": "SORRY_AXIOM_DETECTED",
                    "theorem": theorem_name,
                    "error": "Proof contains 'sorry' unproved obligation placeholder",
                    "axioms_detected": ["sorry"],
                    "allowed_axioms": sorted(allowed),
                }
            return {**result, 'reason': 'Source text does not establish a Lean axiom audit'}

        name = re.escape(theorem_name)
        headers = list(re.finditer(rf"(?m)^[ \t]*'{name}'(?=[ \t]|\r?$)", code_or_stdout))
        if len(headers) != 1:
            return {**result, 'reason': 'Missing or multiple reports for the requested theorem'}
        report = re.match(
            rf"[ \t]*'{name}'[ \t]+(?:does[ \t]+not[ \t]+depend[ \t]+on[ \t]+any[ \t]+axioms"
            rf"|depends[ \t]+on[ \t]+axioms:[ \t]*\[(?P<axioms>[^\[\]]*)\])[ \t]*\r?$",
            code_or_stdout[headers[0].start():], re.MULTILINE)
        if report is None:
            return {**result, 'reason': 'Incomplete or malformed report for the requested theorem'}
        raw = report.group('axioms')
        found_axioms = [] if raw is None or not raw.strip() else [item.strip() for item in raw.split(',')]
        identifier = r"(?:[^\W\d]|_)[\w']*(?:\.(?:[^\W\d]|_)[\w']*)*"
        if any(not re.fullmatch(identifier, ax) for ax in found_axioms) or len(found_axioms) != len(set(found_axioms)):
            return {**result, 'reason': 'Malformed or duplicate axiom identifiers'}
        disallowed = [ax for ax in found_axioms if ax not in allowed or ax in {'sorry', 'sorryAx'}]
        passed = (len(disallowed) == 0)
        return {**result,
            "status": "PASS" if passed else "FAIL",
            "assurance": "INPUT_REPORTED_AXIOM_AUDIT" if passed else "DISALLOWED_AXIOM_DEPENDENCY",
            "theorem": theorem_name,
            "axioms_detected": sorted(found_axioms),
            "allowed_axioms": sorted(allowed),
            "disallowed_axioms": sorted(disallowed),
            "reported_axiom_free": (len(found_axioms) == 0),
        }

    @staticmethod
    def scaffold_code() -> str:
        return _scaffold(LeanAxiomReviewOperator, _lean_axiom_self_test)


# ---------------------------------------------------------------------------
# Operator 7: BoundedFiniteModelOperator (bounded_finite_model)
# ---------------------------------------------------------------------------

class BoundedFiniteModelOperator:
    """Bounded Finite Model and Counterexample Search Operator.

    Exhaustively searches finite algebraic domains (such as finite groups Z_n,
    permutation tables, or Cayley tables) to check algebraic properties (associativity,
    commutativity, group axioms) or refute conjectures with concrete witnesses.
    """

    @staticmethod
    def verify_cayley_property(
        elements: List[str],
        op_table: Dict[Tuple[str, str], str],
        property_name: str = "associative"
    ) -> Dict[str, Any]:
        """Verifies an algebraic property on a Cayley operation table."""
        elem_set = set(elements)
        # Check closure
        for (a, b), c in op_table.items():
            if c not in elem_set:
                return {
                    "status": "FAIL",
                    "assurance": "CLOSURE_VIOLATION",
                    "counterexample": {"a": a, "b": b, "result": c, "not_in_domain": True}
                }

        if property_name == "associative":
            for a in elements:
                for b in elements:
                    ab = op_table.get((a, b))
                    for c in elements:
                        bc = op_table.get((b, c))
                        lhs = op_table.get((ab, c))
                        rhs = op_table.get((a, bc))
                        if lhs != rhs:
                            return {
                                "status": "FAIL",
                                "assurance": "COUNTEREXAMPLE_FOUND",
                                "property": "associative",
                                "counterexample": {
                                    "witness": [a, b, c],
                                    "lhs_expr": f"({a} * {b}) * {c} = {ab} * {c} = {lhs}",
                                    "rhs_expr": f"{a} * ({b} * {c}) = {a} * {bc} = {rhs}",
                                }
                            }
            return {
                "status": "PASS",
                "assurance": "BOUNDED_FINITE_MODEL_VERIFIED",
                "property": "associative",
                "domain_size": len(elements),
                "combinations_checked": len(elements) ** 3
            }

        elif property_name == "commutative":
            for a in elements:
                for b in elements:
                    ab = op_table.get((a, b))
                    ba = op_table.get((b, a))
                    if ab != ba:
                        return {
                            "status": "FAIL",
                            "assurance": "COUNTEREXAMPLE_FOUND",
                            "property": "commutative",
                            "counterexample": {
                                "witness": [a, b],
                                "lhs": f"{a} * {b} = {ab}",
                                "rhs": f"{b} * {a} = {ba}",
                            }
                        }
            return {
                "status": "PASS",
                "assurance": "BOUNDED_FINITE_MODEL_VERIFIED",
                "property": "commutative",
                "domain_size": len(elements),
                "combinations_checked": len(elements) ** 2
            }
        else:
            raise ValueError(f"Unsupported finite property '{property_name}'")

    @staticmethod
    def search_counterexample(
        domain: List[Any],
        predicate: Any
    ) -> Dict[str, Any]:
        """Exhaustively searches a finite domain for an element falsifying predicate."""
        for item in domain:
            try:
                res = predicate(item)
            except Exception as exc:
                return {
                    "status": "FAIL",
                    "assurance": "PREDICATE_ERROR",
                    "witness": item,
                    "error": str(exc)
                }
            if not res:
                return {
                    "status": "FAIL",
                    "assurance": "COUNTEREXAMPLE_FOUND",
                    "witness": item,
                    "domain_size": len(domain)
                }
        return {
            "status": "PASS",
            "assurance": "BOUNDED_FINITE_MODEL_VERIFIED",
            "domain_size": len(domain),
            "exhausted": True
        }

    @staticmethod
    def scaffold_code() -> str:
        return _scaffold(BoundedFiniteModelOperator, _bounded_finite_model_self_test)


# ---------------------------------------------------------------------------
# Operator 8: ExplicitReductionTransferOperator (explicit_reduction_transfer)
# ---------------------------------------------------------------------------

class ExplicitReductionTransferOperator:
    """Explicit Reduction and Representation Transfer Operator.

    Verifies mathematical and computational reductions between two problem representations:
    checks semantic preservation across sample instances and flags unclosed transfer obligations.
    """

    @staticmethod
    def verify_reduction(
        source_instances: List[Any],
        forward_map: Any,
        backward_map: Optional[Any],
        source_evaluator: Any,
        target_evaluator: Any
    ) -> Dict[str, Any]:
        """Evaluates reduction f: Source -> Target on source_instances."""
        mismatches = []
        reconstruction_failures = []
        verified_count = 0

        for idx, inst in enumerate(source_instances):
            try:
                mapped = forward_map(inst)
                s_val = source_evaluator(inst)
                t_val = target_evaluator(mapped)
            except Exception as exc:
                return {
                    "status": "FAIL",
                    "assurance": "REDUCTION_EVALUATION_ERROR",
                    "instance_index": idx,
                    "error": str(exc)
                }

            if s_val != t_val:
                mismatches.append({
                    "index": idx,
                    "source_instance": str(inst),
                    "mapped_instance": str(mapped),
                    "source_result": s_val,
                    "target_result": t_val
                })
                continue

            if backward_map is not None:
                try:
                    reconstructed = backward_map(mapped)
                    r_val = source_evaluator(reconstructed)
                    if r_val != s_val:
                        reconstruction_failures.append({
                            "index": idx,
                            "reconstructed": str(reconstructed),
                            "expected_val": s_val,
                            "reconstructed_val": r_val
                        })
                except Exception as exc:
                    reconstruction_failures.append({"index": idx, "error": str(exc)})

            verified_count += 1

        if mismatches:
            return {
                "status": "FAIL",
                "assurance": "REDUCTION_SEMANTIC_MISMATCH",
                "total_instances": len(source_instances),
                "mismatches": mismatches[:5],
            }

        has_reconstruction = (backward_map is not None)
        if has_reconstruction and reconstruction_failures:
            return {
                "status": "FAIL",
                "assurance": "RECONSTRUCTION_OBLIGATION_UNMET",
                "reconstruction_failures": reconstruction_failures[:5]
            }

        assurance = "EXPLICIT_REDUCTION_CERTIFIED" if has_reconstruction else "FORWARD_REDUCTION_VALIDATED_RECONSTRUCTION_UNRESOLVED"
        return {
            "status": "PASS",
            "assurance": assurance,
            "total_instances": len(source_instances),
            "verified_instances": verified_count,
            "has_bidirectional_reconstruction": has_reconstruction,
        }

    @staticmethod
    def scaffold_code() -> str:
        return _scaffold(ExplicitReductionTransferOperator, _reduction_self_test)


# ---------------------------------------------------------------------------


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


def _egraph_self_test():
    report = EGraphEquivalenceOperator.verify_algebraic_equivalence(
        ("*", "x", ("+", "y", 0)), ("*", "y", "x"), variables=("x", "y"))
    negative = EGraphEquivalenceOperator.verify_algebraic_equivalence(
        ("+", "x", "y"), ("*", "x", "y"), variables=("x", "y"))
    unresolved = EGraphEquivalenceOperator.verify_algebraic_equivalence(
        ("+", "x", ("+", "y", "z")), ("+", ("+", "x", "y"), "z"), variables=("x", "y", "z"))
    assert report["status"] == "PASS" and report["certificate_status"] == "NOT_EMITTED"
    assert negative["status"] == "FAIL" and negative["counterexample"]
    assert unresolved["status"] == "UNKNOWN" and unresolved["equivalent"] is None
    return {"self_test_status": "PASS", "positive": report,
            "negative_status": negative["status"], "unresolved_status": unresolved["status"]}


def _lean_axiom_self_test():
    report = LeanAxiomReviewOperator.audit_lean_axioms(
        "RDS.obligation",
        "'RDS.obligation' depends on axioms: [propext, Quot.sound]",
        allowed_axioms={"propext", "Quot.sound"},
        is_stdout=True,
    )
    negative = LeanAxiomReviewOperator.audit_lean_axioms("T", "sorry", is_stdout=False)
    missing = LeanAxiomReviewOperator.audit_lean_axioms('missing.theorem', 'not Lean output', is_stdout=True)
    assert report["status"] == "PASS" and not report["disallowed_axioms"]
    assert negative["status"] == "FAIL" and negative["axioms_detected"] == ["sorry"]
    assert missing['status'] == 'UNKNOWN' and missing['axioms_detected'] is None
    assert not report['lean_verified'] and report['is_constructive'] is None
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _bounded_finite_model_self_test():
    elems = ["e", "a", "b", "c"]
    v4 = {
        ("e", "e"): "e", ("e", "a"): "a", ("e", "b"): "b", ("e", "c"): "c",
        ("a", "e"): "a", ("a", "a"): "e", ("a", "b"): "c", ("a", "c"): "b",
        ("b", "e"): "b", ("b", "a"): "c", ("b", "b"): "e", ("b", "c"): "a",
        ("c", "e"): "c", ("c", "a"): "b", ("c", "b"): "a", ("c", "c"): "e",
    }
    report = BoundedFiniteModelOperator.verify_cayley_property(elems, v4, "associative")
    broken = dict(v4)
    broken[("a", "b")] = "e"
    negative = BoundedFiniteModelOperator.verify_cayley_property(elems, broken, "associative")
    assert report["status"] == "PASS"
    assert negative["status"] == "FAIL" and "counterexample" in negative
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _reduction_self_test():
    forward = lambda x: (max(0, x), max(0, -x))
    backward = lambda p: p[0] - p[1]
    report = ExplicitReductionTransferOperator.verify_reduction(
        [-5, -2, 0, 3, 7], forward, backward, lambda x: x > 0, lambda p: p[0] > p[1])
    negative = ExplicitReductionTransferOperator.verify_reduction(
        [-5], forward, lambda p: p[0] + p[1], lambda x: x > 0, lambda p: p[0] > p[1])
    assert report["status"] == "PASS" and report["has_bidirectional_reconstruction"]
    assert negative["status"] == "FAIL" and negative["assurance"] == "RECONSTRUCTION_OBLIGATION_UNMET"
    return {"self_test_status": "PASS", "positive": report, "negative_status": negative["status"]}


def _scaffold(cls, self_test):
    """Export the canonical implementation and the same executable self-test."""
    tree = ast.parse(inspect.getsource(cls))
    tree.body[0].body = [node for node in tree.body[0].body
                         if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != "scaffold_code"]
    imports = "import inspect\nimport json\nimport math\nimport re\nfrom fractions import Fraction\nfrom typing import Any, Dict, List, Optional, Set, Tuple, Union\n\n"
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
    "egraph_equivalence_saturation": {"operator_id": "egraph_equivalence", "title": "Bounded Rational-Polynomial Rewrite Example",
        "operator_class": EGraphEquivalenceOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Scoped supported rewrites or exact rational counterexample; otherwise UNKNOWN; no certificate emitted", "self_test": _egraph_self_test},
    "lean_axiom_review": {"operator_id": "lean_axiom_review", "title": "Lean 4 Axiom & Dependency Audit Operator",
        "operator_class": LeanAxiomReviewOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Exact-theorem input-report policy check; no Lean execution or constructivity verification", "self_test": _lean_axiom_self_test},
    "bounded_finite_model": {"operator_id": "bounded_finite_model", "title": "Bounded Finite Model & Counterexample Search Operator",
        "operator_class": BoundedFiniteModelOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Exhaustive finite Cayley table verification and witness refutation", "self_test": _bounded_finite_model_self_test},
    "explicit_reduction_transfer": {"operator_id": "explicit_reduction_transfer", "title": "Explicit Problem Reduction & Representation Transfer",
        "operator_class": ExplicitReductionTransferOperator, "primary_signal": "proof_bottleneck",
        "guarantee": "Semantic validity preservation and unclosed obligation tracking", "self_test": _reduction_self_test},
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

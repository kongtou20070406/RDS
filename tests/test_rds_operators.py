"""Unit tests for runnable theory operators and executable scaffolding."""
from fractions import Fraction
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_operators as ops


class OperatorUnitTests(unittest.TestCase):
    def test_continuous_state_space_discretization_and_stability(self):
        op = ops.ContinuousStateSpaceOperator(state_dim=4, in_dim=1, out_dim=1)
        # Verify Hurwitz stability: eigenvalues A_cont = -exp(a_log) < 0
        for al in op.a_log:
            self.assertGreater(math.exp(al), 0.0)

        # Discretization
        a_bar, b_bar = op.discretize_zoh(dt=0.05)
        self.assertEqual(len(a_bar), 4)
        for val in a_bar:
            # Must be in (0, 1) for stability
            self.assertGreater(val, 0.0)
            self.assertLess(val, 1.0)
        self.assertEqual(len(b_bar), 4)
        self.assertEqual(len(b_bar[0]), 1)

        # Invalid dt
        with self.assertRaises(ValueError):
            op.discretize_zoh(dt=0.0)
        with self.assertRaises(ValueError):
            op.discretize_zoh(dt=-0.1)

    def test_continuous_state_space_step_invariance(self):
        op = ops.ContinuousStateSpaceOperator(state_dim=3, in_dim=1, out_dim=1)
        report = op.verify_step_invariance(total_time=1.0, nfe_candidates=(16, 32, 64, 128))
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["assurance"], "NUMERICAL_DIAGNOSTIC")
        self.assertTrue(report["diagnostic_pass"])
        self.assertLess(report["finest_cauchy_error"], 0.01)
        # Cauchy differences must shrink monotonically
        diffs = [d["diff"] for d in report["cauchy_diffs"]]
        self.assertGreater(diffs[0], diffs[1])
        self.assertGreater(diffs[1], diffs[2])

    def test_contraction_dynamics_operator(self):
        # Strictly contracting system: ||A||_inf = 0.5 < 1
        A_contracting = [[0.3, 0.2], [0.1, 0.4]]
        b = [0.2, 0.3]
        target = [0.55, 0.59]  # close to analytical fixed point
        res = ops.ContractionDynamicsOperator.analyze_system(A_contracting, b, target=target)
        self.assertEqual(res["status"], "PASS")
        self.assertTrue(res["is_contracting"])
        self.assertTrue(res["has_unique_fixed_point"])
        self.assertLess(res["norm_infinity"], 1.0)
        self.assertIsNotNone(res["fixed_point"])

        # Non-contracting system: ||A||_inf = 1.3 > 1
        A_divergent = [[0.8, 0.5], [0.4, 0.7]]
        res_div = ops.ContractionDynamicsOperator.analyze_system(A_divergent, b)
        self.assertEqual(res_div["status"], "FAIL")
        self.assertFalse(res_div["is_contracting"])
        self.assertEqual(res_div["diagnosis"], "INFINITY_NORM_CONTRACTION_NOT_ESTABLISHED")

        # Invalid matrix shapes
        with self.assertRaises(ValueError):
            ops.ContractionDynamicsOperator.analyze_system([[1.0]], [1.0, 2.0])

    def test_structural_preflight_operator(self):
        def valid_callable(x, scale=1.0):
            return [val * scale for val in x]

        # Valid invocation
        res = ops.StructuralPreflightOperator.preflight_callable(
            valid_callable,
            sample_args=([1.0, 2.0],),
            sample_kwargs={"scale": 3.0},
            expected_shapes={"x": (2,)}
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["stage"], "EXECUTION_COMPLETE")
        self.assertEqual(res["output_shape"], (2,))

        # Signature mismatch (extra unexpected kwarg)
        bad_sig = ops.StructuralPreflightOperator.preflight_callable(
            valid_callable,
            sample_args=([1.0],),
            sample_kwargs={"unknown_param": True}
        )
        self.assertEqual(bad_sig["status"], "FAIL")
        self.assertEqual(bad_sig["stage"], "SIGNATURE_BINDING")

        # Shape mismatch
        bad_shape = ops.StructuralPreflightOperator.preflight_callable(
            valid_callable,
            sample_args=([1.0, 2.0],),
            expected_shapes={"x": (4,)}
        )
        self.assertEqual(bad_shape["status"], "FAIL")
        self.assertEqual(bad_shape["stage"], "INPUT_SHAPE_VALIDATION")

        # Exception during invocation
        def crashing_callable(x):
            raise ZeroDivisionError("division by zero in model layer")
        bad_run = ops.StructuralPreflightOperator.preflight_callable(
            crashing_callable,
            sample_args=(1.0,)
        )
        self.assertEqual(bad_run["status"], "FAIL")
        self.assertEqual(bad_run["stage"], "DRY_RUN_INVOCATION")
        self.assertIn("ZeroDivisionError", bad_run["error"])

    def test_rational_certificate_operator(self):
        # P(x) = 1 - x on [0, 1], values strictly in [0, 1]
        res = ops.RationalCertificateOperator.certify_interval_bound(
            poly_coeffs=[1, -1],
            interval=(0, 1),
            bound_range=(0, 1),
            num_grid_points=5
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["assurance"], "EXACT_RATIONAL_CERTIFICATE")
        self.assertEqual(len(res["violations"]), 0)

        # Violation case: P(x) = 2*x on [0, 1], bounds [0, 1] (violates for x > 0.5)
        res_violation = ops.RationalCertificateOperator.certify_interval_bound(
            poly_coeffs=[0, 2],
            interval=(0, 1),
            bound_range=(0, 1),
            num_grid_points=5
        )
        self.assertEqual(res_violation["status"], "FAIL")
        self.assertEqual(res_violation["assurance"], "BOUND_VIOLATION_WITNESS")
        self.assertGreater(len(res_violation["violations"]), 0)

        # Invalid interval (min > max)
        with self.assertRaises(ValueError):
            ops.RationalCertificateOperator.certify_interval_bound([1], (2, 1), (0, 1))

    def test_egraph_equivalence_operator(self):
        # Algebraic equivalence under commutativity and identity
        res = ops.EGraphEquivalenceOperator.verify_algebraic_equivalence(
            ("*", "x", ("+", "y", "0")),
            ("*", "y", "x")
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["assurance"], "EGRAPH_EQUIVALENCE_CERTIFIED")
        self.assertTrue(res["equivalent"])
        self.assertEqual(res["root_a"], res["root_b"])

        # Non-equivalent terms remain distinct
        res_distinct = ops.EGraphEquivalenceOperator.verify_algebraic_equivalence(
            ("+", "x", "y"),
            ("*", "x", "y")
        )
        self.assertEqual(res_distinct["status"], "FAIL")
        self.assertEqual(res_distinct["assurance"], "EGRAPH_DISTINCT_CLASSES")
        self.assertFalse(res_distinct["equivalent"])

    def test_lean_axiom_review_operator(self):
        # 1. Clean constructive theorem
        res_constructive = ops.LeanAxiomReviewOperator.audit_lean_axioms(
            "RDS.constructive",
            "'RDS.constructive' does not depend on any axioms",
            allowed_axioms=set(),
            is_stdout=True
        )
        self.assertEqual(res_constructive["status"], "PASS")
        self.assertEqual(res_constructive["assurance"], "AXIOM_DEPENDENCY_VERIFIED")
        self.assertTrue(res_constructive["is_constructive"])
        self.assertEqual(res_constructive["axioms_detected"], [])

        # 2. Classical axioms allowed
        res_classical = ops.LeanAxiomReviewOperator.audit_lean_axioms(
            "RDS.classical",
            "'RDS.classical' depends on axioms: [propext, Quot.sound]",
            allowed_axioms={"propext", "Quot.sound"},
            is_stdout=True
        )
        self.assertEqual(res_classical["status"], "PASS")
        self.assertEqual(res_classical["axioms_detected"], ["Quot.sound", "propext"])

        # 3. Disallowed axiom
        res_disallowed = ops.LeanAxiomReviewOperator.audit_lean_axioms(
            "RDS.unauthorized",
            "'RDS.unauthorized' depends on axioms: [Classical.choice, UnsoundAxiom]",
            allowed_axioms={"Classical.choice"},
            is_stdout=True
        )
        self.assertEqual(res_disallowed["status"], "FAIL")
        self.assertEqual(res_disallowed["assurance"], "DISALLOWED_AXIOM_DEPENDENCY")
        self.assertIn("UnsoundAxiom", res_disallowed["disallowed_axioms"])

        # 4. 'sorry' gap in source code
        res_sorry = ops.LeanAxiomReviewOperator.audit_lean_axioms(
            "RDS.incomplete",
            "theorem obligation : 1 = 1 := by sorry",
            is_stdout=False
        )
        self.assertEqual(res_sorry["status"], "FAIL")
        self.assertEqual(res_sorry["assurance"], "SORRY_AXIOM_DETECTED")

    def test_bounded_finite_model_operator(self):
        elems = ["e", "a", "b", "c"]
        v4 = {
            ("e", "e"): "e", ("e", "a"): "a", ("e", "b"): "b", ("e", "c"): "c",
            ("a", "e"): "a", ("a", "a"): "e", ("a", "b"): "c", ("a", "c"): "b",
            ("b", "e"): "b", ("b", "a"): "c", ("b", "b"): "e", ("b", "c"): "a",
            ("c", "e"): "c", ("c", "a"): "b", ("c", "b"): "a", ("c", "c"): "e",
        }
        res_v4 = ops.BoundedFiniteModelOperator.verify_cayley_property(elems, v4, "associative")
        self.assertEqual(res_v4["status"], "PASS")
        self.assertEqual(res_v4["assurance"], "BOUNDED_FINITE_MODEL_VERIFIED")
        self.assertEqual(res_v4["combinations_checked"], 64)

        # Non-associative magma: (a * a) * b != a * (a * b)
        bad_table = dict(v4)
        bad_table[("a", "a")] = "b"  # mutate multiplication
        res_bad = ops.BoundedFiniteModelOperator.verify_cayley_property(elems, bad_table, "associative")
        self.assertEqual(res_bad["status"], "FAIL")
        self.assertEqual(res_bad["assurance"], "COUNTEREXAMPLE_FOUND")
        self.assertIn("witness", res_bad["counterexample"])

        # Counterexample search over finite domain
        domain = [2, 4, 6, 7, 8]
        is_even = lambda n: n % 2 == 0
        search_res = ops.BoundedFiniteModelOperator.search_counterexample(domain, is_even)
        self.assertEqual(search_res["status"], "FAIL")
        self.assertEqual(search_res["assurance"], "COUNTEREXAMPLE_FOUND")
        self.assertEqual(search_res["witness"], 7)

    def test_explicit_reduction_transfer_operator(self):
        # 1. Full bidirectional reduction
        res_full = ops.ExplicitReductionTransferOperator.verify_reduction(
            source_instances=[-10, -1, 0, 5, 12],
            forward_map=lambda x: (max(0, x), max(0, -x)),
            backward_map=lambda p: p[0] - p[1],
            source_evaluator=lambda x: x > 0,
            target_evaluator=lambda p: p[0] > p[1]
        )
        self.assertEqual(res_full["status"], "PASS")
        self.assertEqual(res_full["assurance"], "EXPLICIT_REDUCTION_CERTIFIED")
        self.assertEqual(res_full["verified_instances"], 5)

        # 2. Forward only (backward unresolved)
        res_fwd = ops.ExplicitReductionTransferOperator.verify_reduction(
            source_instances=[1, 2, 3],
            forward_map=lambda x: x * 2,
            backward_map=None,
            source_evaluator=lambda x: x > 0,
            target_evaluator=lambda y: y > 0
        )
        self.assertEqual(res_fwd["status"], "PASS")
        self.assertEqual(res_fwd["assurance"], "FORWARD_REDUCTION_VALIDATED_RECONSTRUCTION_UNRESOLVED")

        # 3. Semantic mismatch
        res_mismatch = ops.ExplicitReductionTransferOperator.verify_reduction(
            source_instances=[-2, 3],
            forward_map=lambda x: x * -1,  # inverts sign, breaks positivity
            backward_map=None,
            source_evaluator=lambda x: x > 0,
            target_evaluator=lambda y: y > 0
        )
        self.assertEqual(res_mismatch["status"], "FAIL")
        self.assertEqual(res_mismatch["assurance"], "REDUCTION_SEMANTIC_MISMATCH")

    def test_registry_and_scaffolding(self):
        available = ops.list_available_operators()
        self.assertEqual(len(available), 8)
        card_ids = [item["card_id"] for item in available]
        self.assertIn("state_space_refinement", card_ids)
        self.assertIn("contraction_target_bias", card_ids)
        self.assertIn("structural_preflight", card_ids)
        self.assertIn("exact_symbolic_constraints", card_ids)
        self.assertIn("egraph_equivalence_saturation", card_ids)
        self.assertIn("lean_axiom_review", card_ids)
        self.assertIn("bounded_finite_model", card_ids)
        self.assertIn("explicit_reduction_transfer", card_ids)

        for card_id in card_ids:
            scaffold = ops.get_operator_scaffold(card_id)
            self.assertIn("if __name__ == '__main__':", scaffold.replace('"', "'"))
            test_report = ops.test_operator(card_id)
            self.assertEqual(test_report["self_test_status"], "PASS")
            expected = "UNKNOWN" if card_id == "state_space_refinement" else "PASS"
            self.assertEqual(test_report["test_result"]["status"], expected)

        with self.assertRaises(ValueError):
            ops.get_operator_scaffold("unknown_card_id")
        with self.assertRaises(ValueError):
            ops.test_operator("unknown_card_id")

    def test_interval_missed_peak_and_inconclusive_enclosure(self):
        # All original ten points satisfy the bound, but the midpoint does not.
        result = ops.RationalCertificateOperator.certify_interval_bound([0, 1, -1], (0, 1), (0, "20/81"))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn({"x": "1/2", "y": "1/4", "valid": False}, result["violations"])
        # A sound enclosing interval can be too wide; absence of a witness is UNKNOWN.
        result = ops.RationalCertificateOperator.certify_interval_bound([0, 1, -1], (0, 1), (0, "1/4"), 2)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["enclosures"][0]["range"], ["0", "1/2"])

    def test_interval_whole_domain_positive_cases(self):
        for coeffs, domain, bounds in [([1, -2, 1], (0, 1), (0, 1)),
                                       ([0, 0, 1], (-1, 1), (0, 1)),
                                       ([3], (2, 2), (3, 3))]:
            with self.subTest(coeffs=coeffs):
                result = ops.RationalCertificateOperator.certify_interval_bound(coeffs, domain, bounds, 11)
                self.assertEqual(result["status"], "PASS")
                self.assertTrue(result["enclosures"])
                for segment in result["enclosures"]:
                    left, right = map(Fraction, segment["interval"])
                    lower, upper = map(Fraction, segment["range"])
                    for i in range(17):
                        value = ops.RationalCertificateOperator.eval_polynomial(list(map(Fraction, coeffs)),
                                                                                left + (right - left) * i / 16)
                        self.assertLessEqual(lower, value)
                        self.assertLessEqual(value, upper)

    def test_interval_invalid_and_bounded_inputs(self):
        cases = [([], (0, 1), (0, 1), 10), ([1], (0, 1), (1, 0), 10),
                 ([1], (0, 1), (0, 1), 0), ([1], (0, 1), (0, 1), 1),
                 ([1], (0, 1), (0, 1), True), ([1], (0, 1), (0, 1), 258),
                 ([1] * 34, (0, 1), (0, 1), 10), ([float("nan")], (0, 1), (0, 1), 10)]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                ops.RationalCertificateOperator.certify_interval_bound(*args)

    def test_nfe_aliasing_stays_unknown_and_distinct_grids_required(self):
        op = ops.ContinuousStateSpaceOperator(1)
        report = op.verify_step_invariance(total_time=128)
        self.assertTrue(report["diagnostic_pass"])
        self.assertEqual(report["status"], "UNKNOWN")
        # The exact solution for the default scalar system is far from this aliased observation.
        rate, omega, time = 0.5, 2 * math.pi, 128
        endpoint = (rate * math.sin(omega * time) - omega * math.cos(omega * time)
                    + omega * math.exp(-rate * time)) / (rate * rate + omega * omega)
        self.assertGreater(abs(report["endpoints"][128][0] - endpoint), 0.15)
        for grid in [(16, 16), (16,), (), (0, 16), (-1, 16), (True, 16), (1.5, 16), (16, 4097)]:
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                op.verify_step_invariance(nfe_candidates=grid)
        for time in [0, -1, float("nan"), float("inf")]:
            with self.subTest(time=time), self.assertRaises(ValueError):
                op.verify_step_invariance(total_time=time)
        self.assertEqual(ops.ContinuousStateSpaceOperator(2, 2, 2).verify_step_invariance()["status"], "UNKNOWN")

    def test_zoh_cancellation_and_unsupported_floating_ranges(self):
        op = ops.ContinuousStateSpaceOperator(1)
        _, b_bar = op.discretize_zoh(1e-8)
        expected = -math.expm1(-0.5e-8) / 0.5
        self.assertAlmostEqual(b_bar[0][0], expected, delta=expected * 1e-15)
        for dt in [float("nan"), float("inf"), 1e-300, 1e308]:
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                op.discretize_zoh(dt)
        for rate_log in [-1000, 1000, float("nan"), float("inf")]:
            with self.subTest(rate_log=rate_log), self.assertRaises(ValueError):
                op.a_log = [rate_log]
                op.discretize_zoh(0.1)

    def test_ssm_dimensions_and_nonfinite_updates(self):
        for dims in [(0, 1, 1), (-1, 1, 1), (True, 1, 1), (1, 0, 1), (1, 1, 65)]:
            with self.subTest(dims=dims), self.assertRaises(ValueError):
                ops.ContinuousStateSpaceOperator(*dims)
        op = ops.ContinuousStateSpaceOperator(1)
        for sequence, state in [([[1, 99]], [0]), ([[1]], [0, 42]), ([[]], [0]),
                                ([[float("inf")]], [0]), ([[1]], [float("nan")])]:
            with self.subTest(sequence=sequence, state=state), self.assertRaises(ValueError):
                op.forward_trajectory(sequence, 0.1, state)
        for name, value in [("b", [[float("nan")]]), ("c", [[float("inf")]]), ("d", [[0, 0]])]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                op = ops.ContinuousStateSpaceOperator(1)
                setattr(op, name, value)
                op.discretize_zoh(0.1)

    def test_contraction_threshold_does_not_change_mathematics(self):
        divergent = ops.ContractionDynamicsOperator.analyze_system([[2]], [1], max_norm_threshold=2)
        self.assertEqual(divergent["status"], "FAIL")
        self.assertFalse(divergent["is_contracting"])
        slow = ops.ContractionDynamicsOperator.analyze_system([[0.9995]], [0], target=[0])
        self.assertEqual(slow["status"], "PASS")
        self.assertTrue(slow["is_contracting"])
        self.assertFalse(slow["safety_margin_met"])
        boundary = ops.ContractionDynamicsOperator.analyze_system([[1]], [1])
        self.assertFalse(boundary["is_contracting"])
        self.assertIsNone(boundary["fixed_point"])
        self.assertIsNone(boundary["target_bias"])
        # The display float rounds to one; the exact binary-rational sum remains below one.
        rounded = ops.ContractionDynamicsOperator.analyze_system([[0.5, math.nextafter(0.5, 0)], [0, 0]], [0, 0])
        self.assertEqual(rounded["norm_infinity"], 1.0)
        self.assertLess(Fraction(rounded["norm_infinity_exact"]), 1)
        self.assertEqual(rounded["status"], "PASS")

    def test_contraction_exact_near_singular_and_unknown_target(self):
        a = 1 - 5e-13
        report = ops.ContractionDynamicsOperator.analyze_system([[a]], [1], target=[0], max_norm_threshold=math.nextafter(1, 0))
        expected = Fraction(1) / (1 - Fraction(a))
        self.assertEqual(Fraction(report["fixed_point_exact"][0]), expected)
        self.assertEqual(report["diagnosis"], "CONTRACTING_WITH_TARGET_BIAS")
        self.assertGreater(report["target_bias"], 1e12)
        unknown = ops.ContractionDynamicsOperator.analyze_system([[0.5]], [1])
        self.assertIsNone(unknown["target_bias"])
        self.assertEqual(unknown["diagnosis"], "CONTRACTING_TARGET_UNASSESSED")
        unavailable = ops.ContractionDynamicsOperator.analyze_system([[math.nextafter(1, 0)]], [1e308], target=[0])
        self.assertEqual(unavailable["status"], "UNKNOWN")
        self.assertIsNone(unavailable["target_bias"])
        self.assertEqual(unavailable["diagnosis"], "CONTRACTING_FIXED_POINT_UNAVAILABLE")

    def test_contraction_nonfinite_and_dimension_inputs(self):
        cases = [([[0, 0], [0, float("nan")]], [0, 0], None), ([[0.5]], [float("inf")], None),
                 ([[0.5]], [0], [float("nan")]), ([[0.5]], [0], []), ([[0.5]], [0], [0, 0]),
                 ([], [], None), ([[0.5, 1]], [0], None)]
        for matrix, offset, target in cases:
            with self.subTest(matrix=matrix, offset=offset, target=target), self.assertRaises(ValueError):
                ops.ContractionDynamicsOperator.analyze_system(matrix, offset, target)
        for threshold in [float("nan"), float("inf"), -1]:
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                ops.ContractionDynamicsOperator.analyze_system([[0.5]], [1], max_norm_threshold=threshold)

    def test_preflight_output_contract_and_absent_argument(self):
        wrong = ops.StructuralPreflightOperator.preflight_callable(lambda x: [x], (1,), expected_output_shape=(2,))
        self.assertEqual(wrong["status"], "FAIL")
        self.assertEqual(wrong["stage"], "OUTPUT_SHAPE_VALIDATION")
        absent = ops.StructuralPreflightOperator.preflight_callable(lambda x: [x], (1,), expected_shapes={"missing": (1,)})
        self.assertEqual(absent["status"], "FAIL")

    def test_exports_use_canonical_implementations_with_failing_self_checks(self):
        for card_id, meta in ops.OPERATORS.items():
            with self.subTest(card_id=card_id):
                namespace = {"__name__": "exported_operator"}
                exec(compile(ops.get_operator_scaffold(card_id), "<exported-operator>", "exec"), namespace)
                self.assertIn(meta["operator_class"].__name__, namespace)
                result = namespace["operator_self_test"]()
                self.assertEqual(result["self_test_status"], "PASS")
                # Break the exported class: its self-test must fail, not merely print a demonstration.
                exported_class = namespace[meta["operator_class"].__name__]
                if card_id == "state_space_refinement":
                    exported_class.verify_step_invariance = lambda *args, **kwargs: {"status": "PASS"}
                elif card_id == "contraction_target_bias":
                    exported_class.analyze_system = lambda *args, **kwargs: {"status": "FAIL"}
                elif card_id == "structural_preflight":
                    exported_class.preflight_callable = lambda *args, **kwargs: {"status": "PASS"}
                else:
                    exported_class.certify_interval_bound = lambda *args, **kwargs: {"status": "FAIL"}
                with self.assertRaises(AssertionError):
                    namespace["operator_self_test"]()


if __name__ == "__main__":
    unittest.main()

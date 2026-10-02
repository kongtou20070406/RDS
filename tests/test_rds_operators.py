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
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["assurance"], "STEP_INVARIANCE_CERTIFIED")
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
        self.assertEqual(res_div["diagnosis"], "NON_CONTRACTIVE_STEP")

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
            self.assertEqual(test_report["test_result"]["status"], "PASS")

        with self.assertRaises(ValueError):
            ops.get_operator_scaffold("unknown_card_id")
        with self.assertRaises(ValueError):
            ops.test_operator("unknown_card_id")


if __name__ == "__main__":
    unittest.main()

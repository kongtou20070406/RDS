"""Proxy-vs-application progress policy through the real Advisor entry (#43, #22).

Synthetic fixture: local qualification passes on repeated runs while the
application/transfer measurement never happens. The selector must keep the
application obligation open, offer the discriminating observation instead of
another local qualification, leave adapter errors as UNKNOWN (never a theory),
and let changed evidence legitimately reopen review without blocking
replication or healthy routes. All names and values are invented; this is a
behavioral contract, not a universal three-failure veto or causal diagnosis.
"""
import copy
import unittest

from test_rds_advisor_search import fact, node


class ProgressPolicyTests(unittest.TestCase):
    """One harness per case family; no research execution is involved."""

    def setUp(self):
        from test_rds_project import ProjectTests
        from rds_advisor import RDSAdvisor
        self.helper = ProjectTests()
        self.helper.setUp()
        self.addCleanup(self.helper.tearDown)
        self.root, self.store = self.helper.root, self.helper.store
        self.advisor = RDSAdvisor(self.root)

    OBSERVATIONS = [{"run": "synthetic_a", "local_qualification": True, "application_gain": None},
                    {"run": "synthetic_b", "local_qualification": True, "application_gain": None},
                    {"run": "synthetic_c", "local_qualification": True, "application_gain": None}]

    @staticmethod
    def graph():
        return {"nodes": [node("app-probe", pre=[{"fact": "local_qualification", "value": True}],
                                satisfied=[{"fact": "application_gain", "value": True}],
                                action_id="app-transfer-check")], "edges": []}

    @staticmethod
    def context(observations=(), adapter_error=False):
        from test_rds_advisor_search import node as _node
        facts = {"application_gain": fact(None, source="no application measurement exists")}
        if adapter_error:
            facts["local_qualification"] = {"value": None, "source": "adapter:synthetic_a",
                                            "adapter_status": "ADAPTER_FAILED"}
        else:
            runs = list(observations or ProgressPolicyTests.OBSERVATIONS)
            facts["local_qualification"] = fact(True, binding={"run_id": runs[-1]["run"]})
        return {"decision": {"id": "choose", "goal_revision": "g1", "scope": {"dataset": "dev"},
                             "goal_conditions": [{"fact": "local_qualification", "value": True},
                                                 {"fact": "application_gain", "value": True}]},
                "facts": facts}

    def discriminated_graph(self):
        graph = self.graph()
        action = graph["nodes"][0]["executable"]["action"]
        action.update(target="application_gain",
                      description="distinguish rival explanations of the local-pass/application-gap",
                      competing_explanations=["transfer_overfitting", "protocol_mismatch"],
                      required_observables=["aligned held-out application outcome"],
                      outcomes=[{"observation": "held-out matches local",
                                 "next_decision": "check measurement protocol"},
                                {"observation": "held-out diverges",
                                 "next_decision": "treat as transfer gap"}])
        action["discrimination"] = {"scope_id": "application-transfer", "source": "synthetic fixture",
                                    "predictions": {"transfer_overfitting": ["held-out diverges"],
                                                    "protocol_mismatch": ["held-out matches local"]}}
        return graph

    def search(self, context, graph):
        state = self.store.snapshot()
        state["advisor_context"] = copy.deepcopy(context)
        before = copy.deepcopy(state)
        report = next(r for r in self.advisor.recommend_next_directions(state, graph)
                      if r["type"] == "EXECUTABLE_DIRECTION_SEARCH")
        self.assertEqual(state, before, "Advisor must not mutate reported state")
        return report["search"]

    def test_repeated_local_pass_never_counts_as_application_progress(self):
        search = self.search(self.context(), self.discriminated_graph())
        review = search["selection_review"]
        self.assertEqual([(c["fact"], c["truth"]) for c in review["goal"]["conditions"]],
                         [("local_qualification", "TRUE"), ("application_gain", "UNKNOWN")])
        self.assertEqual([(c["id"], c["status"]) for c in search["candidates"]],
                         [("app-probe:app-transfer-check", "READY")])
        # The ready route is a supported discriminating test whose rival predictions
        # differ; the next move names it, not another local qualification.
        move = review["next_move"]
        self.assertEqual(move["kind"], "DESIGN_DISCRIMINATOR")
        self.assertIn("application/transfer obligation", move["reason"])
        self.assertNotIn("three", move["reason"].lower())
        self.assertEqual(review["assurance"], "INPUT_REPORTED_NOT_SCIENTIFIC_VERIFICATION")

    def test_discriminating_predictions_are_conditional_and_rival(self):
        search = self.search(self.context(), self.discriminated_graph())
        candidate = search["candidates"][0]
        report = search["selection_review"]["candidates"][0]
        self.assertEqual(report["basis"], "CONDITIONAL_RIVAL_TEST")
        self.assertEqual(report["distinguishing_pairs"], 1)
        self.assertEqual(candidate["action"]["discrimination"]["predictions"],
                         {"transfer_overfitting": ["held-out diverges"],
                          "protocol_mismatch": ["held-out matches local"]})

    def test_adapter_error_leaves_science_unknown_and_requests_evidence(self):
        search = self.search(self.context(adapter_error=True), self.discriminated_graph())
        review = search["selection_review"]
        self.assertEqual([(c["fact"], c["truth"]) for c in review["goal"]["conditions"]],
                         [("local_qualification", "UNKNOWN"), ("application_gain", "UNKNOWN")])
        # The failed adapter becomes a read-only evidence request, never FALSE and
        # never an automatic capability deficit or theory refutation.
        self.assertEqual([(q["fact"], q["kind"]) for q in search["queries"]],
                         [("local_qualification", "READ_ONLY_EVIDENCE_REQUEST")])
        self.assertEqual([(c["id"], c["status"]) for c in search["candidates"]],
                         [("app-probe:app-transfer-check", "NEEDS_EVIDENCE")])
        self.assertEqual(review["next_move"]["kind"], "RESOLVE_PREMISE")

    def test_without_a_discriminating_spec_the_premise_step_stays_generic(self):
        graph = self.graph()
        action = graph["nodes"][0]["executable"]["action"]
        action.update(target="application_gain",
                      description="check the application measurement")
        search = self.search(self.context(), graph)
        move = search["selection_review"]["next_move"]
        self.assertEqual(move["kind"], "RESOLVE_PREMISE")
        self.assertIn("unresolved evidence", move["reason"])

    def record_rejection(self, checkpoint_id, context, candidate):
        from rds_checkpoints import save_checkpoint
        decision = context["decision"]
        return save_checkpoint(self.root, checkpoint_id, self.store.snapshot(), kind="project", decision={
            "question_id": decision["id"], "goal_revision": decision["goal_revision"],
            "scope": decision["scope"], "candidate": candidate, "outcome": "rejected",
            "evidence": context["facts"]})

    def test_replication_is_blocked_but_changed_evidence_reopens_review(self):
        context = self.context()
        candidate = self.search(context, self.graph())["candidates"][0]
        self.record_rejection("reject-1", context, candidate)
        # Same evidence again: recorded rejection blocks the unchanged repeat.
        repeated = self.search(context, self.graph())
        self.assertEqual([(c["id"], c["status"]) for c in repeated["blocked_candidates"]],
                         [("app-probe:app-transfer-check", "BLOCKED_REJECTED_ROUTE")])
        self.assertEqual([f["kind"] for f in repeated["loop_review"]["flags"]],
                         ["REPEAT_REJECTED_ROUTE"])
        # A genuinely new local run (new binding) is changed evidence: the route
        # legitimately reopens for review; no refund or duplicate launch is implied.
        reopened = self.search(self.context(observations=[{"run": "synthetic_new",
                                                           "local_qualification": True,
                                                           "application_gain": None}]), self.graph())
        self.assertEqual([(c["id"], c["status"], c["loop_review"]["kind"]) for c in reopened["candidates"]],
                         [("app-probe:app-transfer-check", "READY", "REOPEN_REVIEW")])
        self.assertEqual(reopened["blocked_candidates"], [])

    def test_unrelated_goal_keeps_healthy_route_available(self):
        context = self.context()
        candidate = self.search(context, self.graph())["candidates"][0]
        self.record_rejection("reject-2", context, candidate)
        other = copy.deepcopy(context)
        other["decision"]["goal_revision"] = "g2"
        fresh = self.search(other, self.graph())
        self.assertEqual([(c["id"], c["status"]) for c in fresh["candidates"]],
                         [("app-probe:app-transfer-check", "READY")])
        self.assertEqual(fresh["blocked_candidates"], [])


if __name__ == "__main__":
    unittest.main()

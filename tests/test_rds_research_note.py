"""Explicit decision bookkeeping must not invent recall, evidence or authority."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_research_note import load_research_note, review_research_note


def goal(revision="goal-1", **fields):
    return {"revision": revision, "metric": {"name": "heldout_error", "unit": "MSE"},
            "budget": {"wall_seconds": {"cap": 60, "unit": "seconds"}}, "direction": "test a paired intervention",
            "source": {"locator": "fixture:declared-goal"}, **fields}


def event(eid, kind="proposal", **fields):
    base = {"id": eid, "kind": kind, "question_id": "question-1", "goal_revision": "goal-1", "scope": {"horizon": 64},
            "idea_id": "idea-1", "source": {"locator": f"fixture:{eid}"}}
    if kind == "proposal":
        base.update(intervention={"type": "set_iterations", "parameters": {"iterations": 64}},
                    next_if_positive="decision-run", next_if_negative="decision-stop")
    elif kind == "decision":
        base.update(decision_id="decision-stop", outcome="rejected", reason="No reported held-out improvement")
    return {**base, **fields}


def fixture():
    return {"schema_version": 1, "goal": goal(), "config": {"discussion_limit": 3},
            "events": [event("p1"), event("reject", "decision")]}


def kinds(report):
    return [row["kind"] for row in report["flags"]]


class ResearchNoteTests(unittest.TestCase):
    def test_rejected_reproposal_has_source_bound_reason(self):
        spec = fixture()
        spec["events"].append(event("repeat"))
        report = review_research_note(spec)
        self.assertEqual(report["statistics"]["repeat_proposal_count"], 1)
        self.assertEqual(report["flags"][0]["rejection_ref"], "reject")
        self.assertEqual(report["rejections"][0]["reason"], "No reported held-out improvement")
        self.assertEqual(report["rejections"][0]["source"]["locator"], "fixture:reject")

    def test_renaming_idea_cannot_hide_identical_typed_intervention(self):
        spec = fixture()
        spec["events"].append(event("rename", idea_id="fresh-name"))
        self.assertIn("REPEAT_REJECTED_IDEA", kinds(review_research_note(spec)))

    def test_free_text_similarity_is_not_semantic_recall(self):
        spec = fixture()
        spec["events"].append(event("different", idea_id="idea-2", description="same original prose",
                                    intervention={"type": "paired_control", "parameters": {"iterations": 64}}))
        self.assertNotIn("REPEAT_REJECTED_IDEA", kinds(review_research_note(spec)))

    def test_explicit_new_evidence_scope_or_intervention_all_require_review(self):
        variants = [{"new_evidence_refs": ["fixture:new-result"]}, {"scope": {"horizon": 128}},
                    {"intervention": {"type": "set_iterations", "parameters": {"iterations": 128}}}]
        for fields in variants:
            with self.subTest(fields=fields):
                spec = fixture()
                spec["events"].append(event("reopen", **fields))
                report = review_research_note(spec)
                self.assertIn("REOPEN_REVIEW", kinds(report))
                self.assertEqual(report["statistics"]["repeat_proposal_count"], 0)
                self.assertEqual(len(report["rejections"]), 1)
                self.assertEqual(report["current_decisions"][0]["outcome"], "rejected")
                self.assertEqual(report["authorization"], "NOT_GRANTED_BY_NOTE")

    def test_unsubstantiated_changed_scope_label_does_not_hide_repeat(self):
        spec = fixture()
        spec["events"].append(event("repeat", changed_scope=True, changed_intervention=True))
        self.assertEqual(review_research_note(spec)["statistics"]["repeat_proposal_count"], 1)

    def test_atomic_types_do_not_alias_numeric_and_boolean_interventions(self):
        spec = fixture()
        spec["events"][0]["intervention"]["parameters"] = {"enabled": 1}
        spec["events"].append(event("changed", intervention={"type": "set_iterations", "parameters": {"enabled": True}}))
        self.assertIn("REOPEN_REVIEW", kinds(review_research_note(spec)))

    def test_other_question_or_goal_scope_is_not_a_rejected_repeat(self):
        spec = fixture()
        spec["events"].append(event("independent", question_id="question-2"))
        self.assertEqual(review_research_note(spec)["statistics"]["repeat_proposal_count"], 0)

    def test_same_outcome_decision_id_makes_experiment_ineffective(self):
        spec = fixture()
        spec["events"].append(event("no-effect", next_if_positive="decision-stop"))
        report = review_research_note(spec)
        self.assertEqual(report["statistics"]["ineffective_experiment_count"], 1)
        self.assertIn("INEFFECTIVE_EXPERIMENT", kinds(report))

    def test_aba_decisions_flag_oscillation_with_stable_ids(self):
        spec = fixture()
        spec["events"] = [event("a1", "decision", decision_id="A", outcome="accepted"),
                          event("b", "decision", decision_id="B", idea_id="idea-2", outcome="accepted"),
                          event("a2", "decision", decision_id="A", outcome="accepted")]
        report = review_research_note(spec)
        self.assertEqual(report["flags"][0]["decision_ids"], ["A", "B", "A"])
        self.assertEqual(report["current_decisions"][0]["id"], "a2")

    def test_aba_across_scope_is_not_oscillation(self):
        spec = fixture()
        spec["events"] = [event("a1", "decision", decision_id="A", outcome="accepted"),
                          event("b", "decision", decision_id="B", scope={"horizon": 128}, outcome="accepted"),
                          event("a2", "decision", decision_id="A", outcome="accepted")]
        self.assertNotIn("DECISION_OSCILLATION", kinds(review_research_note(spec)))

    def test_consecutive_same_decision_updates_source_without_oscillation(self):
        spec = fixture()
        spec["events"].append(event("reaffirm", "decision", reason="New explicit reason"))
        report = review_research_note(spec)
        self.assertNotIn("DECISION_OSCILLATION", kinds(report))
        self.assertEqual(report["current_decisions"][0]["source"]["locator"], "fixture:reaffirm")
        self.assertEqual(report["current_decisions"][0]["reason"], "New explicit reason")

    def test_stable_decision_id_cannot_silently_change_meaning(self):
        spec = fixture()
        spec["events"].append(event("rewrite", "decision", outcome="accepted"))
        with self.assertRaisesRegex(ValueError, "stable decision_id"):
            review_research_note(spec)

    def test_discussion_threshold_suggests_convergence_without_choosing(self):
        spec = fixture()
        spec["events"].extend(event(f"talk-{i}", "discussion") for i in range(3))
        report = review_research_note(spec)
        self.assertEqual(report["statistics"]["discussion_without_plan"], 3)
        self.assertIn("CONVERGENCE_SUGGESTION", kinds(report))
        self.assertEqual(report["current_decisions"][0]["outcome"], "rejected")
        self.assertEqual(report["authorization"], "NOT_GRANTED_BY_NOTE")

    def test_explicit_typed_plan_resolves_discussion_count_but_not_authorization(self):
        spec = fixture()
        spec["events"].extend(event(f"talk-{i}", "discussion") for i in range(3))
        spec["events"].append(event("plan", "decision", decision_id="decision-plan", outcome="plan_locked"))
        report = review_research_note(spec)
        self.assertEqual(report["statistics"]["discussion_without_plan"], 0)
        self.assertNotIn("CONVERGENCE_SUGGESTION", kinds(report))
        self.assertEqual(report["current_decisions"][0]["intervention"]["type"], "set_iterations")
        self.assertEqual(report["authorization"], "NOT_GRANTED_BY_NOTE")

    def test_plan_label_without_concrete_intervention_cannot_suppress_flag(self):
        spec = fixture()
        spec["events"] = [event("plan", "decision", outcome="plan_locked")]
        with self.assertRaisesRegex(ValueError, "typed intervention"):
            review_research_note(spec)

    def test_accepted_and_verified_labels_are_not_authenticated_results(self):
        spec = fixture()
        spec["events"].append(event("result", "result", accepted=True, verified=True, success=True))
        report = review_research_note(spec)
        self.assertEqual(report["result_assurance"], "INPUT_REPORTED")
        self.assertEqual(report["assurance"], "INPUT_REPORTED")
        self.assertNotIn("verified", report)
        self.assertEqual(len(report["rejections"]), 1)
        self.assertEqual(report["current_decisions"][0]["outcome"], "rejected")

    def test_goal_change_shows_old_new_and_preserves_old_rejection(self):
        spec = fixture()
        old, new = goal(), goal("goal-2", direction="test retention before extending")
        new["metric"] = {"name": "retention_error", "unit": "MSE"}
        spec["goal"] = new
        spec["events"].append(event("drift", "goal_change", old_goal=old, new_goal=new))
        spec["events"].append(event("new-goal-proposal", goal_revision="goal-2"))
        report = review_research_note(spec)
        drift = report["flags"][0]
        self.assertEqual(drift["kind"], "GOAL_DRIFT")
        self.assertEqual(drift["old_goal"]["metric"]["name"], "heldout_error")
        self.assertEqual(drift["new_goal"]["metric"]["name"], "retention_error")
        self.assertEqual(report["rejections"][0]["goal_revision"], "goal-1")
        self.assertEqual(report["statistics"]["repeat_proposal_count"], 0)

    def test_goal_revision_order_and_old_snapshot_cannot_be_rewritten(self):
        spec = fixture()
        g1, g2, g3 = goal(), goal("goal-2"), goal("goal-3")
        spec["goal"] = g3
        spec["events"].extend([event("change-1", "goal_change", old_goal=g1, new_goal=g2),
                               event("change-2", "goal_change", old_goal=goal("goal-2", direction="rewritten"), new_goal=g3)])
        with self.assertRaisesRegex(ValueError, "Old goal"):
            review_research_note(spec)
        spec["events"][-1]["old_goal"] = g2
        spec["events"].append(event("wrong-revision", goal_revision="goal-1"))
        with self.assertRaisesRegex(ValueError, "goal revision"):
            review_research_note(spec)

    def test_source_locator_and_rejection_reason_are_required(self):
        for changes in ({"source": {"verified": True}}, {"reason": ""}):
            spec = fixture()
            spec["events"][1].update(changes)
            with self.assertRaises(ValueError):
                review_research_note(spec)

    def test_empty_summary_is_valid_bookkeeping_not_success_score(self):
        spec = fixture()
        spec["events"] = []
        report = review_research_note(spec)
        self.assertEqual(report["current_decisions"], [])
        self.assertEqual(report["statistics"]["repeat_proposal_count"], 0)
        self.assertNotIn("success_rate", report)

    def test_inputs_output_and_raw_refs_are_independent(self):
        spec = fixture()
        spec["events"].append(event("reopen", new_evidence_refs=["fixture:new-result"]))
        original = deepcopy(spec)
        report = review_research_note(spec)
        self.assertEqual(report["raw_refs"][-1]["new_evidence_refs"], ["fixture:new-result"])
        self.assertEqual(spec, original)
        report["goal"]["budget"]["wall_seconds"]["cap"] = 0
        report["rejections"][0]["intervention"]["parameters"]["iterations"] = 0
        report["graph"]["edges"][0]["source"]["locator"] = "modified-output"
        self.assertEqual(spec, original)

    def test_weak_graph_keeps_rejection_and_marks_reopening_pending(self):
        spec = fixture()
        spec["events"].extend([event("repeat"), event("reopen", new_evidence_refs=["fixture:new-result"])])
        report = review_research_note(spec)
        graph = report["graph"]
        self.assertEqual(graph["purpose"], "ANTI_LOOP_BOOKKEEPING")
        self.assertEqual(report["precise_recovery"], "REQUIRES_ORIGINAL_EVIDENCE")
        self.assertIn("rejected", [edge["relation"] for edge in graph["edges"]])
        self.assertIn("repeats_rejected", [edge["relation"] for edge in graph["edges"]])
        reopened = next(edge for edge in graph["edges"] if edge["relation"] == "reopens")
        self.assertEqual(reopened["status"], "REVIEW_REQUIRED")
        self.assertEqual(reopened["rejection_ref"], "reject")
        self.assertEqual(reopened["source"]["locator"], "fixture:reopen")
        ids = {node["id"] for node in graph["nodes"]}
        self.assertTrue(all(edge["from"] in ids and edge["to"] in ids for edge in graph["edges"]))
        self.assertTrue(all(edge["assurance"] == "INPUT_REPORTED" for edge in graph["edges"]))

    def test_weak_graph_namespaces_ids_and_projects_goal_supersession(self):
        spec = fixture()
        spec["events"][0]["idea_id"] = spec["events"][1]["idea_id"] = "goal-1"
        old, new = goal(), goal("goal-2")
        spec["goal"] = new
        spec["events"].append(event("drift", "goal_change", old_goal=old, new_goal=new))
        graph = review_research_note(spec)["graph"]
        ids = {node["id"] for node in graph["nodes"]}
        self.assertIn("goal:goal-1", ids)
        self.assertIn("idea:goal-1", ids)
        edge = next(edge for edge in graph["edges"] if edge["relation"] == "supersedes")
        self.assertEqual((edge["from"], edge["to"]), ("goal:goal-2", "goal:goal-1"))

    def test_schema_caps_finite_values_and_atomic_scopes(self):
        for update in (lambda s: s.update(schema_version=True), lambda s: s.update(events=[event(str(i)) for i in range(201)]),
                       lambda s: s.update(config={"discussion_limit": True}),
                       lambda s: s["goal"]["budget"]["wall_seconds"].update(cap=True),
                       lambda s: s["events"][0].update(scope={"nested": {"x": 1}}),
                       lambda s: s["events"][0].update(new_evidence_refs=[False]),
                       lambda s: s["events"][0].update(source={"locator": "fixture", "padding": "x" * 1024}),
                       lambda s: s.update(extra=float("inf"))):
            with self.subTest(update=update):
                spec = fixture()
                update(spec)
                with self.assertRaises(ValueError):
                    review_research_note(spec)

    def test_duplicate_event_ids_and_unhashable_idea_ids_are_invalid(self):
        for update in (lambda s: s["events"].append(deepcopy(s["events"][0])),
                       lambda s: s["events"][0].update(idea_id=[])):
            spec = fixture()
            update(spec)
            with self.assertRaises(ValueError):
                review_research_note(spec)

    def test_loader_reads_one_markdown_json_block_and_never_writes(self):
        raw = "# Agent-provided summary\n\n```rds-research\n" + json.dumps(fixture()) + "\n```\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "RESEARCH.md"
            path.write_text(raw, encoding="utf-8")
            before = path.read_bytes()
            loaded = load_research_note(path)
            self.assertEqual(loaded, fixture())
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_loader_rejects_duplicate_keys_nonfinite_or_deep_json(self):
        cases = ['{"schema_version":1,"schema_version":1}', '{"x":NaN}', '{"x":1e400}',
                 '{"x":' + '[' * 34 + '0' + ']' * 34 + '}']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "RESEARCH.md"
            for raw in cases:
                with self.subTest(raw=raw):
                    path.write_text("```rds-research\n" + raw + "\n```\n", encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_research_note(path)

    def test_loader_rejects_missing_multiple_unclosed_and_oversized_fences(self):
        block = "```rds-research\n" + json.dumps(fixture()) + "\n```\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "RESEARCH.md"
            for raw in ("# No structured summary", block + block, block + "```rds-research\n{}", block + "x" * (256 * 1024)):
                with self.subTest(length=len(raw)):
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_research_note(path)
            path.write_bytes(b"\xff")
            with self.assertRaises(ValueError):
                load_research_note(path)

    def test_bundled_example_is_illustrative_read_only_summary(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "lightweight" / "RESEARCH.md"
        report = review_research_note(load_research_note(path))
        self.assertEqual(report["statistics"]["repeat_proposal_count"], 1)
        self.assertIn("REOPEN_REVIEW", kinds(report))
        self.assertEqual(report["authorization"], "NOT_GRANTED_BY_NOTE")


if __name__ == "__main__":
    unittest.main()

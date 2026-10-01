"""Read-only batch proposals honor evidence, capacity, elapsed time and budgets."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_resources import plan_resource_batch
from rds_advisor import RDSAdvisor


def fixture(count=4):
    ids = [f"r{i}" for i in range(count)]
    search = {"candidates": [{"id": cid, "status": "READY"} for cid in ids]}
    context = {"capacity": {"gpu": 4}, "occupied": {"gpu": 0}, "window_seconds": 7200,
               "budget": {"available": 100, "reserve": 20, "unit": "credits"},
               "completed": [], "source": "synthetic inventory, no device queried", "estimates": {}}
    for cid in ids:
        context["estimates"][cid] = {"experiment_id": cid, "resources": {"gpu": 1},
            "wall_seconds": 3600, "incremental_cost": 10, "priority": 1, "parallel_safe": True,
            "depends_on": [], "mutex_groups": [], "decision_use": "distinguish a declared rival explanation",
            "source": "synthetic estimate including control and evaluation"}
    return search, context


def status(plan, cid):
    return next(row["status"] for row in plan["pending"] if row["candidate_id"] == cid)


class ResourcePlanTests(unittest.TestCase):
    def test_four_independent_jobs_fill_four_owned_gpus_without_execution(self):
        search, context = fixture()
        before = copy.deepcopy((search, context))
        result = plan_resource_batch(search, context)
        self.assertEqual([row["candidate_id"] for row in result["batch"]], ["r0", "r1", "r2", "r3"])
        self.assertEqual(result["completion_seconds"], 3600)
        self.assertEqual(result["total_attempt_wall_seconds"], 14400)
        gpu = result["resources"]["gpu"]
        self.assertEqual(gpu["batch_slot_seconds"], 14400)
        self.assertEqual(gpu["start_utilization_fraction"], 1)
        self.assertEqual(gpu["batch_available_utilization_fraction"], 1)
        self.assertEqual(gpu["idle_reasons"], [])
        self.assertEqual(result["assurance"], "INPUT_ESTIMATE")
        self.assertFalse(result["execution_started"] or result["budget_reserved"])
        self.assertEqual(result["authorization"], "UNCHANGED")
        self.assertEqual((search, context), before)
        json.dumps(result, allow_nan=False)

    def test_occupied_capacity_is_not_idle_or_reallocated(self):
        search, context = fixture()
        context["occupied"]["gpu"] = 2
        result = plan_resource_batch(search, context)
        self.assertEqual(len(result["batch"]), 2)
        self.assertEqual(result["resources"]["gpu"]["occupied"], 2)
        self.assertEqual(result["resources"]["gpu"]["unassigned_available_slots"], 0)
        self.assertEqual(result["resources"]["gpu"]["idle_reasons"], [])
        self.assertEqual(status(result, "r2"), "CAPACITY_UNAVAILABLE")

    def test_priority_is_research_input_not_cheapest_or_shortest_first(self):
        search, context = fixture(2)
        context["capacity"]["gpu"] = 1
        context["estimates"]["r0"].update(priority=0, incremental_cost=60, wall_seconds=5000)
        context["estimates"]["r1"].update(priority=1, incremental_cost=1, wall_seconds=100)
        result = plan_resource_batch(search, context)
        self.assertEqual([row["candidate_id"] for row in result["batch"]], ["r0"])

    def test_same_experiment_faster_configuration_can_cost_more(self):
        search, context = fixture(2)
        search["candidates"][0]["dominated_by"] = ["r1"]
        search["ranking"] = {"pareto_front": ["r1"]}
        context["estimates"]["r0"].update(experiment_id="experiment", resources={"gpu": 4},
            wall_seconds=1000, incremental_cost=50, comparison_group="same-goal")
        context["estimates"]["r1"].update(experiment_id="experiment", wall_seconds=3600,
            incremental_cost=10, comparison_group="same-goal")
        result = plan_resource_batch(search, context)
        self.assertEqual([row["candidate_id"] for row in result["batch"]], ["r0"])
        self.assertEqual(status(result, "r1"), "ALTERNATIVE_SELECTED")
        self.assertEqual(result["tradeoffs"][0]["seconds_saved"], 2600)
        self.assertEqual(result["tradeoffs"][0]["extra_incremental_cost"], 40)
        self.assertEqual(result["tradeoffs"][0]["extra_resource_seconds"]["gpu"], 400)

    def test_shared_comparison_label_does_not_prove_parallel_safety(self):
        search, context = fixture(2)
        for estimate in context["estimates"].values():
            estimate.update(comparison_group="same-goal", parallel_safe=False)
        result = plan_resource_batch(search, context)
        self.assertEqual(len(result["batch"]), 1)
        self.assertEqual(status(result, "r1"), "PARALLELISM_UNSUPPORTED")

    def test_dependency_must_be_completed_before_batch_not_selected_in_it(self):
        search, context = fixture(2)
        context["estimates"]["r1"]["depends_on"] = ["r0"]
        result = plan_resource_batch(search, context)
        self.assertEqual(status(result, "r1"), "DEPENDENCY_PENDING")
        context["completed"] = ["r0"]
        self.assertEqual(len(plan_resource_batch(search, context)["batch"]), 2)

    def test_independent_control_and_treatment_can_run_but_mutex_cannot(self):
        search, context = fixture(2)
        context["estimates"]["r0"]["decision_use"] = "independent matched control"
        context["estimates"]["r1"]["decision_use"] = "independent paired treatment"
        self.assertEqual(len(plan_resource_batch(search, context)["batch"]), 2)
        for estimate in context["estimates"].values():
            estimate["mutex_groups"] = ["exclusive-data-writer"]
        result = plan_resource_batch(search, context)
        self.assertEqual(status(result, "r1"), "MUTEX_CONFLICT")

    def test_protected_budget_and_resource_quota_are_additive(self):
        search, context = fixture()
        context["budget"] = {"available": 50, "reserve": 25, "unit": "credits"}
        result = plan_resource_batch(search, context)
        self.assertEqual(len(result["batch"]), 2)
        self.assertEqual(result["budget"]["remaining_after_batch"], 30)
        self.assertEqual(status(result, "r2"), "BUDGET_PENDING")
        self.assertIn("BUDGET_PENDING", result["resources"]["gpu"]["idle_reasons"])
        context["resource_seconds_caps"] = {"gpu": 3600}
        result = plan_resource_batch(search, context)
        self.assertEqual(len(result["batch"]), 1)
        self.assertEqual(status(result, "r1"), "RESOURCE_QUOTA_PENDING")

    def test_wall_budget_uses_total_full_duration_and_rejects_underpriced_time(self):
        search, context = fixture()
        context["budget"] = {"available": 10, "reserve": 0, "unit": "wall_seconds"}
        context["window_seconds"] = 10
        for estimate in context["estimates"].values():
            estimate.update(wall_seconds=5, incremental_cost=1)
        with self.assertRaisesRegex(ValueError, "must equal full wall_seconds"):
            plan_resource_batch(search, context)
        for estimate in context["estimates"].values():
            estimate["incremental_cost"] = 5
        result = plan_resource_batch(search, context)
        self.assertEqual(len(result["batch"]), 2)
        self.assertEqual(result["completion_seconds"], 5)
        self.assertEqual(result["total_attempt_wall_seconds"], 10)
        self.assertEqual(result["budget"]["batch_incremental_cost"], 10)
        self.assertEqual(result["budget"]["remaining_after_batch"], 0)

    def test_decimal_money_and_zero_incremental_cost_for_owned_capacity(self):
        search, context = fixture(2)
        context["budget"] = {"available": 0.3, "reserve": 0, "unit": "credits"}
        context["estimates"]["r0"]["incremental_cost"] = 0.1
        context["estimates"]["r1"]["incremental_cost"] = 0.2
        self.assertEqual(len(plan_resource_batch(search, context)["batch"]), 2)
        context["budget"]["available"] = 0
        for estimate in context["estimates"].values():
            estimate["incremental_cost"] = 0
        self.assertEqual(len(plan_resource_batch(search, context)["batch"]), 2)

    def test_unknown_context_never_defaults_to_free_or_idle(self):
        search, original = fixture(1)
        for key in ("occupied", "window_seconds", "completed", "source", "estimates"):
            context = copy.deepcopy(original)
            del context[key]
            with self.subTest(key=key):
                self.assertEqual(status(plan_resource_batch(search, context), "r0"), "NEEDS_EVIDENCE")
        for key in ("available", "reserve", "unit"):
            context = copy.deepcopy(original)
            del context["budget"][key]
            with self.subTest(key=key):
                self.assertEqual(status(plan_resource_batch(search, context), "r0"), "NEEDS_EVIDENCE")
        context = copy.deepcopy(original)
        context["resource_seconds_caps"] = {"gpu": None}
        self.assertEqual(status(plan_resource_batch(search, context), "r0"), "NEEDS_EVIDENCE")

    def test_full_estimate_fields_and_all_resource_dimensions_are_explicit(self):
        search, original = fixture(1)
        for key in original["estimates"]["r0"]:
            context = copy.deepcopy(original)
            del context["estimates"]["r0"][key]
            with self.subTest(key=key):
                self.assertEqual(status(plan_resource_batch(search, context), "r0"), "NEEDS_EVIDENCE")
        context = copy.deepcopy(original)
        context["capacity"]["cpu"] = 4
        context["occupied"]["cpu"] = 0
        self.assertEqual(status(plan_resource_batch(search, context), "r0"), "NEEDS_EVIDENCE")
        context["estimates"]["r0"]["resources"]["cpu"] = 0
        self.assertEqual(len(plan_resource_batch(search, context)["batch"]), 1)

    def test_malformed_values_rejected_and_window_is_full_duration(self):
        search, original = fixture(1)
        for key, value in (("wall_seconds", True), ("wall_seconds", float("nan")),
                ("wall_seconds", float("inf")), ("wall_seconds", -1), ("wall_seconds", 0),
                ("incremental_cost", -1), ("priority", True), ("parallel_safe", "true"),
                ("resources", {"gpu": True}), ("depends_on", ""), ("mutex_groups", None)):
            context = copy.deepcopy(original)
            context["estimates"]["r0"][key] = value
            with self.subTest(key=key, value=value):
                if value is None:
                    self.assertEqual(status(plan_resource_batch(search, context), "r0"), "NEEDS_EVIDENCE")
                else:
                    with self.assertRaises(ValueError):
                        plan_resource_batch(search, context)
        context = copy.deepcopy(original)
        context["window_seconds"] = 3599
        self.assertEqual(status(plan_resource_batch(search, context), "r0"), "WINDOW_EXCEEDED")

    def test_scoped_history_warning_preserves_unrelated_ready_work(self):
        search, context = fixture()
        search["loop_review"] = {"status": "REVIEW_REQUIRED", "flags": [
            {"kind": "REPEAT_REJECTED_ROUTE", "candidate_id": "old"}]}
        search["blocked_candidates"] = [{"id": "old", "status": "BLOCKED_REJECTED_ROUTE"}]
        context["estimates"]["old"] = copy.deepcopy(context["estimates"]["r0"])
        result = plan_resource_batch(search, context)
        self.assertEqual(len(result["batch"]), 4)
        self.assertEqual(status(result, "old"), "UPSTREAM_BLOCKED")
        search["candidates"][0]["loop_review"] = {"kind": "REOPEN_REVIEW"}
        result = plan_resource_batch(search, context)
        self.assertEqual(len(result["batch"]), 3)
        self.assertEqual(status(result, "r0"), "HISTORY_REVIEW_REQUIRED")
        search["loop_review"]["flags"].append({"kind": "LOOP_HISTORY_REVIEW_ERROR"})
        self.assertEqual(plan_resource_batch(search, context)["batch"], [])

    def test_upstream_pending_or_discarded_candidates_are_not_promoted(self):
        search, context = fixture(2)
        search["candidates"][0]["status"] = "NEEDS_QUERY"
        search["discarded_candidates"] = [search["candidates"].pop()]
        result = plan_resource_batch(search, context)
        self.assertEqual(result["batch"], [])
        self.assertEqual(status(result, "r0"), "NOT_READY")
        self.assertEqual(status(result, "r1"), "UPSTREAM_BLOCKED")


class ResourceIntegrationTests(unittest.TestCase):
    def test_actual_checkpoint_rejection_is_filtered_before_resource_planning(self):
        from test_rds_advisor import LedgerLoopTests
        from test_rds_advisor_search import node, fact
        helper = LedgerLoopTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        extra = node("other")
        extra["executable"]["action"].update(target={"name": "different_intervention", "type": "boolean"},
                                               intervention={"value": True})
        helper.graph["nodes"].append(extra)
        helper.context["facts"]["other-done"] = fact(False)
        candidates = helper.search()["search"]["candidates"]
        self.assertEqual(len(candidates), 2)
        rejected = next(row for row in candidates if row["id"].startswith("root:"))
        helper.record("rejected", rejected)
        _, resources = fixture(1)
        estimate = resources["estimates"].pop("r0")
        resources["estimates"] = {row["id"]: dict(estimate, experiment_id=row["id"]) for row in candidates}
        state = helper.store.snapshot()
        state["advisor_context"] = dict(helper.context, resources=resources)
        before = copy.deepcopy((state, helper.store.snapshot()))
        reports = helper.advisor.recommend_next_directions(state, helper.graph)
        result = next(row["resource_plan"] for row in reports if row["type"] == "RESOURCE_BATCH_PLAN")
        self.assertEqual(len(result["batch"]), 1)
        self.assertNotEqual(result["batch"][0]["candidate_id"], rejected["id"])
        self.assertEqual(status(result, rejected["id"]), "UPSTREAM_BLOCKED")
        self.assertEqual((state, helper.store.snapshot()), before)

    def test_actual_cli_preserves_resources_with_and_without_artifact_manifest(self):
        from test_rds_advisor_search import node, fact
        graph = {"nodes": [node("root")], "edges": []}
        _, resources = fixture(1)
        resources["estimates"] = {"root:root-test": resources["estimates"]["r0"]}
        context = {"decision": "choose", "facts": {"root-done": fact(False)}, "resources": resources}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (("graph.json", graph), ("context.json", context),
                    ("artifacts.json", {"schema": "rds-artifact-manifest-v1", "sources": []})):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            for artifacts in ([], ["--artifacts", str(root / "artifacts.json")]):
                with self.subTest(artifacts=bool(artifacts)):
                    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/rds_cli.py"),
                        "--root", str(root), "advise", "--research-context", str(root / "context.json"),
                        "--graph", str(root / "graph.json"), *artifacts],
                        capture_output=True, encoding="utf-8", timeout=15, cwd=ROOT)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = json.loads(result.stdout)
                    plan = next(row["resource_plan"] for row in output["recommendations"]
                                if row["type"] == "RESOURCE_BATCH_PLAN")
                    self.assertEqual(len(plan["batch"]), 1)
                    self.assertFalse((root / ".rds").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

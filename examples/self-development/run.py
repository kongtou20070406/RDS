"""Use RDS to execute and inspect a development iteration; CPU, no API calls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
PATTERNS = ["test_rds_artifacts.py", "test_rds_costs.py", "test_rds_experiments.py",
            "test_rds_rsi.py", "test_rds_project.py", "test_rds_checkpoints.py", "test_rds_development_cli.py",
            "test_rds_two_fidelity.py", "test_rds_two_fidelity_cli.py", "test_rds_advisor_search.py"]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="New empty development workspace; original source is read-only")
    parser.add_argument("--all-tests", action="store_true", help="Run every public test module, including benchmark-backed checks")
    args = parser.parse_args()
    patterns = sorted(p.name for p in (REPO / "tests").glob("test_*.py")) if args.all_tests else PATTERNS
    root = Path(args.workspace).resolve()
    if root == REPO or root.is_relative_to(REPO):
        parser.error("Choose a workspace outside this checkout to avoid recursive source copying")
    if root.exists() and any(root.iterdir()):
        parser.error("Use a new empty workspace; existing research state is never overwritten")
    root.mkdir(parents=True, exist_ok=True)
    for folder in ("scripts", "tests", "references", "examples", "benchmark"):
        shutil.copytree(REPO / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(Path(__file__).with_name("test_driver.py"), root / "test_driver.py")
    config = {"test_patterns": patterns, "goal": "Validate actual RDS development behavior", "scientific_claim": None}
    write(root / "development-config.json", config)
    bindings = [{"path": p.relative_to(root).as_posix(), "sha256": file_sha(p), "role": "code"}
                for p in sorted((root / "scripts").glob("*.py"))]
    data = [{"path": "tests/" + pattern, "sha256": file_sha(root / "tests" / pattern), "role": "data"}
            for pattern in patterns]
    fixture_paths = ["examples/experiment-templates/templates.json", "examples/rsi/base-graph.json",
                     "examples/rsi/candidate-rule.json", "examples/rsi/cases.json"]
    data.extend({"path": path, "sha256": file_sha(root / path), "role": "data"} for path in fixture_paths)
    if args.all_tests:
        bindings.extend({"path": p.relative_to(root).as_posix(), "sha256": file_sha(p), "role": "code"}
                        for p in sorted((root / "benchmark").rglob("*.py")))
        data.extend({"path": p.relative_to(root).as_posix(), "sha256": file_sha(p), "role": "data"}
                    for p in sorted((root / "examples/formal").glob("*.json")))
        data.extend({"path": path, "sha256": file_sha(root / path), "role": "data"}
                    for path in ("references/judgment-graph.yaml", "references/scientific_tuning_principles.json",
                                 "examples/advisor-search/boundary-context.json"))
    bindings.extend(data)
    bindings.extend({"path": path, "sha256": file_sha(root / path), "role": role}
                    for path, role in (("development-config.json", "config"), ("test_driver.py", "evaluator")))
    # Use the runner's documented role-hash convention, from the exact source copy.
    sys.path.insert(0, str(root / "scripts"))
    from rds_project import ProjectStore
    protocol = {role + "_sha256": ProjectStore._role_sha({"bindings": bindings}, role) for role in ("code", "config", "data")}
    protocol.update(data_split="development-regression", init="fresh-process", seed="not-applicable",
                    checkpoint="none", schedule="one-regression-pass", sample_work=patterns,
                    numeric_protocol="python-unittest; counts", metric={"definition": "unittest failure and error count", "reduction": "count"})
    write(root / "development-protocol.json", protocol)
    bindings.append({"path": "development-protocol.json", "sha256": file_sha(root / "development-protocol.json"), "role": "protocol"})
    argv = [sys.executable, "-B", "test_driver.py"]
    contract = {"schema": 1, "description": "Use RDS to validate RDS development; no scientific quality score",
                "bindings": bindings, "allowed_commands": [argv], "output_roots": ["out"], "budget": {"wall_seconds": 120}}
    write(root / "contract.json", contract)
    manifest = {"schema": 1, "id": "development-check", "arm": "tool", "argv": argv,
                "protocol": {"path": "development-protocol.json", "sha256": file_sha(root / "development-protocol.json")},
                "outpaths": ["out/test-results.json"], "timeout_seconds": 90, "resource_estimates": {"wall_seconds": 90}}
    write(root / "run.json", manifest)
    decisions = {"question": "Can this iteration be integrated or must a concrete regression be repaired?",
                 "goal": config["goal"], "candidate": "integrate only after recorded regression acceptance",
                 "pending_evidence": ["raw test output", "rule replay acceptance"], "source_kind": "DEVELOPMENT_INPUT"}
    write(root / "decision.json", decisions)
    cli = root / "scripts" / "rds_cli.py"
    def run(label, *arguments, allow_failure=False):
        completed = subprocess.run([sys.executable, "-B", str(cli), "--root", str(root), *arguments],
                                   cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=120)
        write(root / "out" / (label + ".json"), {"argv": list(arguments), "exit_code": completed.returncode,
                                                 "stdout": completed.stdout, "stderr": completed.stderr})
        if completed.returncode and not allow_failure:
            raise RuntimeError(completed.stderr or completed.stdout)
        return json.loads(completed.stdout)
    run("01-init", "project", "init", "--contract", "contract.json")
    run("02-register", "project", "create", "--manifest", "run.json")
    run("03-checkpoint", "checkpoint", "save", "--id", "before-check", "--decision", "decision.json")
    receipt = run("04-execution", "project", "execute", "--id", "development-check", allow_failure=True)
    write(root / "out/receipt.json", receipt)
    run("05-costs", "project", "costs")
    run("06-restoration", "checkpoint", "restore", "--id", "before-check")
    binding = {"run_id": receipt["run_id"], **protocol}
    imports = {"schema": "rds-artifact-manifest-v1", "decision": "next-development-step", "sources": [
        {"id": "actual-test-counts", "kind": "metric", "path": "out/test-results.json",
         "expected_sha256": file_sha(root / "out/test-results.json"), "binding": binding,
         "facts": [{"id": "failure_count", "pointer": "/failure_count"}, {"id": "case_count", "pointer": "/case_count"}]},
        {"id": "actual-execution-receipt", "kind": "receipt", "path": "out/receipt.json",
         "expected_sha256": file_sha(root / "out/receipt.json"), "binding": binding, "facts": []}],
        "cost_bindings": [{"action_id": "review-next-change", "run_id": receipt["run_id"],
                           "resource": "wall_seconds", "comparison_group": "same-development-protocol"}]}
    write(root / "imports.json", imports)
    action = {"id": "review-next-change", "kind": "READ_ONLY_REVIEW", "description": "Read the next scoped change and its acceptance evidence",
              "competing_explanations": ["recorded software checks pass", "an untested behavior still requires evidence"],
              "required_observables": ["original regression output", "independent rule replay"],
              "outcomes": [{"observation": "bound independent cases accept the change", "next_decision": "integrate the scoped change"},
                           {"observation": "a missing or failing case is found", "next_decision": "repair the concrete gap"}]}
    failed_action = {**action, "id": "inspect-test-failures", "description": "Read the exact failing case and traceback before changing code"}
    graph = {"schema": 1, "nodes": [{"id": "development-regression", "sources": ["out/test-results.json; development-only"],
             "executable": {"decisions": ["next-development-step"],
                 "preconditions": [{"fact": "failure_count", "op": "eq", "value": 0, "on_false": failed_action}], "action": action}}], "edges": []}
    write(root / "development-graph.json", graph)
    imported = run("07-import", "artifacts", "import", "--manifest", "imports.json")
    advice = run("08-advice", "advise", "--artifacts", "imports.json", "--graph", "development-graph.json")
    # The rule proposal is a finite software regression example, never a sealed
    # scientific benchmark. Keep it on a separate graph with an explicit rollback.
    rsi_dir = root / "examples/rsi"
    isolated = root / "isolated-rules.json"
    shutil.copyfile(rsi_dir / "base-graph.json", isolated)
    evaluation = run("09-rule-replay", "meta", "evaluate-rule", "--rule", str(rsi_dir / "candidate-rule.json"),
                     "--graph", str(isolated), "--cases", str(rsi_dir / "cases.json"), "--output", "out/evaluation.json", allow_failure=True)
    adoption = None
    if receipt["run_status"] == "SUCCEEDED" and evaluation["adoption_eligible"]:
        adoption = run("10-isolated-adoption", "meta", "apply-rule", "--rule", str(rsi_dir / "candidate-rule.json"),
                       "--graph", str(isolated), "--cases", str(rsi_dir / "cases.json"), "--evaluation", "out/evaluation.json", "--force")
        record = adoption.get("record_path", adoption.get("record"))
        if not isinstance(record, str):
            raise RuntimeError("Adoption did not provide an explicit rollback record path")
        run("11-rollback", "meta", "rollback-rule", "--record", record, "--graph", str(isolated))
    observations = json.loads((root / "out/test-results.json").read_text(encoding="utf-8"))
    test_summary = {key: observations[key] for key in ("case_count", "failure_count", "skipped_count")}
    test_summary["failing_cases"] = [failure["case_id"] for failure in observations["failures"]]
    print(json.dumps({"workspace": str(root), "run_status": receipt["run_status"],
                      "assessment": receipt["assessment"], "test_observations": test_summary,
                      "artifact_status": imported["status"], "rule_replay_status": evaluation["status"],
                      "rule_cases_evaluated": evaluation["cases_evaluated"], "rule_case_counts": evaluation.get("counts"),
                      "isolated_adoption": {key: adoption[key] for key in ("status", "record_path", "backup_path")} if adoption else None,
                      "advice_record": "out/08-advice.json", "research_policy_gain_measured": False},
                     ensure_ascii=False, indent=2))
    return 0 if receipt["run_status"] == "SUCCEEDED" else 1


if __name__ == "__main__":
    sys.exit(main())

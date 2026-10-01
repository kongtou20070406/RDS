"""Finite scorer/Advisor integration fixture. No AI calls or scientific gain score."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def fixture():
    """Scripted arithmetic and synthetic work costs, explicitly not blinded research."""
    protocol = {"schema_version": 1, "id": "arithmetic-scorer-fixture", "version": 1,
        "frozen_at": "2026-01-01T00:00:00Z", "model_id": "scripted-fixture-v1",
        "starting_evidence_sha256": hashlib.sha256(b"public arithmetic fixture").hexdigest(),
        "budget": {"fixture_work": {"cap": 8, "unit": "fixture_work_units"}}, "tasks": []}
    trajectories, observations = [], []
    for task_id, kind in (("extension", "extension_challenge"), ("retention", "retention_control")):
        intervention = hashlib.sha256((task_id + ":x=2").encode()).hexdigest()
        protocol["tasks"].append({"id": task_id, "kind": kind,
            "confirmations": [{"id": task_id + "-c1", "intervention_sha256": intervention,
                              "metric": "response", "unit": "units", "tolerance": 0}]})
        for arm in ("baseline", "advisor"):
            common = {"task_id": task_id, "arm": arm, "protocol_id": protocol["id"], "protocol_version": 1}
            predicted = 6 if task_id == "extension" and arm == "advisor" else 4
            cost = {"fixture_work": {"value": 1, "unit": "fixture_work_units"}}
            trajectories.append({**common, "model_id": protocol["model_id"],
                "starting_evidence_sha256": protocol["starting_evidence_sha256"],
                "selected_at": "2026-01-02T00:00:00Z", "selection_used_ids": [],
                "predictions": [{"confirmation_id": task_id + "-c1", "value": predicted,
                    "metric": "response", "unit": "units", "predicted_at": "2026-01-03T00:00:00Z"}],
                "attempts": [{"id": task_id + "-attempt", "status": "SUCCEEDED", "costs": cost}],
                "generation": {"operator_ids": ["scripted-arithmetic"]},
                "selection": {"policy_id": "scripted-" + arm}, "source": {"locator": "public fixture"}})
            observations.append({**common, "confirmation_id": task_id + "-c1",
                "intervention_sha256": intervention, "observed": 6 if task_id == "extension" else 4,
                "metric": "response", "unit": "units", "observed_at": "2026-01-04T00:00:00Z",
                "used_for_selection": False, "costs": cost, "source": {"locator": "public fixture oracle"}})
    return protocol, trajectories, observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="New empty fixture workspace outside this checkout")
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    if root == REPO or root.is_relative_to(REPO):
        parser.error("Use a workspace outside this checkout")
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        parser.error("Use a new empty workspace; existing results are never replaced")
    root.mkdir(parents=True, exist_ok=True)
    protocol, trajectories, observations = fixture()
    write(root / "protocol.json", protocol)
    write(root / "trajectories.json", trajectories)

    def cli(label, *arguments):
        result = subprocess.run([sys.executable, "-B", str(REPO / "scripts/rds_cli.py"),
                                 "--root", str(root), *arguments], cwd=root, capture_output=True,
                                encoding="utf-8", timeout=15)
        write(root / (label + ".json"), {"argv": list(arguments), "exit_code": result.returncode,
                                        "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return json.loads(result.stdout)

    score_args = ["advancement", "score", "--protocol", str(root / "protocol.json"),
                  "--trajectories", str(root / "trajectories.json")]
    unknown = cli("01-before-confirmation", *score_args)
    write(root / "confirmations.json", observations)
    score = cli("02-after-confirmation", *score_args, "--confirmations", str(root / "confirmations.json"))
    failed = score["paired_tasks"][0]["baseline"]["confirmation_checks"][0]
    source = {"locator": "02-after-confirmation.json#/stdout; public development fixture"}
    frontier = {"schema_version": 1, "nodes": [
        {"id": "observation", "kind": "observable", "source": source},
        {"id": "incumbent", "kind": "model", "source": source},
        {"id": "explanation", "kind": "requirement", "source": source}],
        "edges": [], "goals": [{"id": "next", "target": "explanation", "anchors": ["observation"],
            "decision": "Ask for an explanation and a new discriminating test", "source": source}],
        "observations": [{"id": "failed-prediction", "model": "incumbent", "node": "observation",
            "observed": failed["observed"], "predicted": failed["predicted"], "tolerance": failed["tolerance"],
            "protocol": {"observed_unit": "units", "predicted_unit": "units"}, "source": source}]}
    write(root / "frontier.json", frontier)
    advice = cli("03-evidence-to-next-question", "advise", "--frontier", str(root / "frontier.json"))
    gaps = next(row["frontier"]["gaps"] for row in advice["recommendations"] if row["type"] == "RESEARCH_FRONTIER")
    checkpoint = {"schema_version": 1, "evaluation_kind": "FINITE_SCORER_FIXTURE_NOT_AI_BENCHMARK",
        "before_confirmation": unknown["status"], "fixture_score_status": score["status"],
        "fixture_metric": score["primary_metric"], "next_question_kinds": sorted({gap["kind"] for gap in gaps}),
        "ai_calls": 0, "scientific_gain": "UNMEASURED", "false_replacement": score["false_replacement"],
        "case_role": "DEVELOPMENT_ONLY", "next_decision": "Freeze a real-model intervention pilot before making any efficacy claim"}
    write(root / "checkpoint.json", checkpoint)
    print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

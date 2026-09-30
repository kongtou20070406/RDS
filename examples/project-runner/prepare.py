"""Prepare a new isolated CPU example and emit real file-bound contract JSON."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from rds_project import file_sha


def prepare(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("Use a new empty demonstration directory")
    for filename in ("experiment.py", "evaluate.py", "data.csv"):
        shutil.copyfile(Path(__file__).with_name(filename), root / filename)
    (root / "config.json").write_text(json.dumps({"data": "data.csv"}), encoding="utf-8")
    protocol = {"code_sha256": file_sha(root / "experiment.py"),
                "config_sha256": file_sha(root / "config.json"), "data_sha256": file_sha(root / "data.csv"),
                "data_split": "demonstration-only", "init": "none", "seed": "none",
                "checkpoint": "none", "schedule": "one closed-form fit", "sample_work": {"rows": 6},
                "numeric_protocol": "Python float; finite recorded dataset"}
    (root / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    role_files = {"code": "experiment.py", "config": "config.json", "data": "data.csv",
                  "evaluator": "evaluate.py", "protocol": "protocol.json"}
    commands = [[sys.executable, "-B", "experiment.py", "--arm", arm, "--output", f"outputs/{arm}.json"]
                for arm in ("control", "treatment")]
    contract = {"schema": 1, "description": "CPU demonstration, not scientific confirmation",
                "bindings": [{"role": role, "path": path, "sha256": file_sha(root / path)}
                             for role, path in role_files.items()], "allowed_commands": commands,
                "output_roots": ["outputs"], "budget": {"wall_seconds": 12, "cpu_seconds": 12}}
    specs = []
    for arm, argv in zip(("control", "treatment"), commands):
        specs.append({"schema": 1, "id": arm, "arm": arm, "control_id": "control" if arm == "treatment" else None,
                      "protocol": {"path": "protocol.json", "sha256": file_sha(root / "protocol.json")},
                      "argv": argv, "outpaths": [f"outputs/{arm}.json"],
                      "resource_estimates": {"wall_seconds": 5, "cpu_seconds": 5}, "timeout_seconds": 4})
    for name, value in [("contract.json", contract), ("control.json", specs[0]), ("treatment.json", specs[1])]:
        (root / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    return {"root": str(root), "contract": str(root / "contract.json"), "manifests": [str(root / "control.json"), str(root / "treatment.json")]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    print(json.dumps(prepare(parser.parse_args().root), indent=2))

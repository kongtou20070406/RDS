"""Actually run RDS import + Advisor on local fixtures, with no experiments."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[1] / "scripts"))
from rds_artifacts import ingest_manifest
from rds_advisor_search import search_directions


def main():
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    graph = {"nodes": [{"id": "inspect-record", "executable": {
        "decisions": ["inspect-local-record"],
        "preconditions": [{"fact": "loss", "op": "lte", "value": 0.4,
                           "query": "Read metrics.csv row 1 loss, check its hash and run identity."}],
        "action": {"id": "interpret-record", "kind": "INTERPRETATION_UPDATE",
                   "description": "Interpret the recorded toy metric within its declared scope.",
                   "competing_explanations": ["the intended run produced this value", "the file belongs to another run"],
                   "required_observables": ["hash-bound row and matching run identity"],
                   "outcomes": [{"observation": "identity and value available", "next_decision": "review the recorded result"},
                                {"observation": "identity or value unknown", "next_decision": "request the original artifact"}]}}}]}
    output = {"scope": "Actual RDS program checks on tiny local fixtures; not scientific-effect scores.", "checks": {}}
    before = {name: (BASE / name).read_bytes() for name in ("config.json", "metrics.csv", "raw.log", "manifest.json")}
    with tempfile.TemporaryDirectory(prefix="dev-check-", dir=BASE) as directory:
        for label in ("present", "missing", "conflicting"):
            candidate = deepcopy(manifest)
            if label == "missing":
                candidate["sources"][1]["path"] = "does-not-exist.csv"
            if label == "conflicting":
                candidate["sources"][1]["binding"]["run_id"] = "another-run"
            path = Path(directory) / (label + ".json")
            path.write_text(json.dumps(candidate, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            imported = ingest_manifest(path, root=BASE)
            advice = search_directions(graph, imported["context"])
            output["checks"][label] = {"import": imported, "advisor": advice}
    output["inputs_unchanged"] = all((BASE / name).read_bytes() == raw for name, raw in before.items())
    # This public fixture report omits the machine-specific root only. Scientific
    # values, statuses and source hashes are unchanged; this is not a private log.
    def public_paths(value):
        if isinstance(value, str):
            return value.replace(str(BASE).replace("\\", "\\\\"), "<artifact-root>").replace(str(BASE), "<artifact-root>")
        if isinstance(value, dict):
            return {key: public_paths(child) for key, child in value.items()}
        if isinstance(value, list):
            return [public_paths(child) for child in value]
        return value
    output = public_paths(output)
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "development-check.json"
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "inputs_unchanged": output["inputs_unchanged"],
                      "checks": {name: {"import": check["import"]["status"],
                                "advisor": check["advisor"]["candidates"][0]["status"]}
                                 for name, check in output["checks"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()

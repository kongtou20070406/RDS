"""Explicit lossless extraction of declared file-hash maps; never verify files."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from rds_artifacts import MAX_FILE_BYTES, strict_json
from rds_verify_types import canonical, require

MAX_FACT_BYTES = 262144


def _bytes(value):
    try:
        raw = canonical(value).encode("utf-8")
        require(len(raw) <= MAX_FILE_BYTES, "Context exceeds 2 MiB")
        strict_json(raw)
        return raw
    except (TypeError, RecursionError, UnicodeError, OverflowError) as exc:
        raise ValueError("Context must be finite, bounded JSON") from exc


def compact_context(spec):
    """Return the context, unique complete manifests and reversible JSON pointers."""
    require(isinstance(spec, dict) and isinstance(spec.get("facts"), dict), "Context requires a facts object")
    require("compaction" not in spec, "Context already contains compaction provenance")
    _bytes(spec)
    context, manifests, changed = deepcopy(spec), {}, []
    for fact_id, fact in context["facts"].items():
        require(isinstance(fact_id, str) and isinstance(fact, dict), "Facts require string ids and object records")
        for field in ("binding", "bindings"):
            binding = fact.get(field)
            if not isinstance(binding, dict) or "code_sha256" not in binding:
                continue
            mapping = binding["code_sha256"]
            if isinstance(mapping, str):
                continue
            require(isinstance(mapping, dict) and 1 <= len(mapping) <= 512,
                    "code_sha256 map must contain 1..512 declared file hashes")
            for name, sha in mapping.items():
                require(isinstance(name, str) and 1 <= len(name) <= 256
                        and not name.startswith("/") and not re.match(r"[A-Za-z]:", name)
                        and "\\" not in name and "\x00" not in name
                        and all(part not in ("", ".", "..") for part in name.split("/")),
                        "File-hash map keys must be plain relative filenames")
                require(isinstance(sha, str) and re.fullmatch(r"[a-fA-F0-9]{64}", sha),
                        "Declared file hashes must be 64 hexadecimal characters")
            identity = hashlib.sha256(_bytes(mapping)).hexdigest()
            manifests.setdefault(identity, mapping)
            binding["code_sha256"] = identity
            pointer = fact_id.replace("~", "~0").replace("/", "~1")
            changed.append("/facts/" + pointer + "/" + field + "/code_sha256")
    require(len(_bytes(context["facts"])) <= MAX_FACT_BYTES, "Compacted facts still exceed 262144 bytes")
    return {"context": context, "manifests": manifests, "changed_paths": changed}


def write_compacted(input_path, output_dir):
    source, target = Path(input_path).resolve(), Path(output_dir).resolve()
    require(source.is_file(), "Input must be an existing regular file")
    with source.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    require(len(raw) <= MAX_FILE_BYTES, "Input exceeds 2 MiB")
    original = strict_json(raw.decode("utf-8-sig"))
    result = compact_context(original)
    source_sha = hashlib.sha256(raw).hexdigest()
    records = {sha: {"path": "manifests/" + sha + ".json", "sha256": sha}
               for sha in sorted(result["manifests"])}
    context = result["context"]
    context["compaction"] = {"schema": "rds-context-compaction-v1",
        "assurance": "DECLARED_MANIFEST_IDENTITY_ONLY", "actual_files_verified": False,
        "original_source": {"path": str(source), "sha256": source_sha, "retained_copy": "source.json"},
        "manifest_identity": "SHA256 of canonical declared file-hash map; not actual code verification",
        "changed_paths": result["changed_paths"], "manifests": records}
    encoded = _bytes(context)
    summary = {"schema": "rds-context-compaction-summary-v1", "original_sha256": source_sha,
        "original_facts_bytes": len(_bytes(original["facts"])),
        "compacted_facts_bytes": len(_bytes(context["facts"])),
        "replacements": len(result["changed_paths"]), "unique_manifests": len(records),
        "context_path": "context.json", "context_sha256": hashlib.sha256(encoded).hexdigest(),
        "paths_relative_to": "--output-dir", "changed_paths": result["changed_paths"], "manifests": records}
    summary_bytes = _bytes(summary)
    target.mkdir(exist_ok=False)
    (target / "manifests").mkdir()
    with (target / "source.json").open("xb") as stream:
        stream.write(raw)
    for sha, mapping in result["manifests"].items():
        with (target / records[sha]["path"]).open("xb") as stream:
            stream.write(_bytes(mapping))
    for name, content in (("context.json", encoded), ("summary.json", summary_bytes)):
        with (target / name).open("xb") as stream:
            stream.write(content)
    return {key: value for key, value in summary.items() if key not in ("schema", "changed_paths", "manifests")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(write_compacted(args.input, args.output_dir), separators=(",", ":")))
        return 0
    except (ValueError, TypeError, OSError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "reason": str(exc)[:32]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

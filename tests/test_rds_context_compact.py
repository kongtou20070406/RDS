"""Manifest extraction preserves evidence and bounds without claiming verification."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rds_context_compact as compact


def fixture():
    mapping = {"experiment.py": "a" * 64, "logs/4h.00a4_stdout.log": "B" * 64}
    fact = {"id": "target", "value": False, "kind": "OBSERVED", "reliable": True,
            "source": "record.json#/check", "binding": {"run_id": "R034", "code_sha256": mapping,
            "config_sha256": "c" * 64, "metric": "held-out loss"}, "scope": {"horizon": 1}}
    other = deepcopy(fact)
    other["id"], other["value"] = "other", {"code_sha256": mapping}
    return {"decision": "choose_next", "facts": {"target/~": fact, "other": other},
            "costs": {"gpu_seconds": 0, "human_hours": 0.25}, "resources": {"models": []},
            "scientific_qualification": "UNKNOWN", "frontier": {"old": [1, None, True]}}


def expand(result):
    context = deepcopy(result["context"])
    context.pop("compaction", None)
    for pointer in result["changed_paths"]:
        parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
        parent = context
        for part in parts[:-1]:
            parent = parent[part]
        parent[parts[-1]] = deepcopy(result["manifests"][parent[parts[-1]]])
    return context


class ContextCompactionTests(unittest.TestCase):
    def test_lossless_roundtrip_dedup_values_scopes_and_costs(self):
        spec, before = fixture(), fixture()
        result = compact.compact_context(spec)
        self.assertEqual(spec, before)
        self.assertEqual(expand(result), before)
        self.assertEqual(len(result["manifests"]), 1)
        self.assertEqual(result["changed_paths"], ["/facts/target~1~0/binding/code_sha256", "/facts/other/binding/code_sha256"])
        identity, mapping = next(iter(result["manifests"].items()))
        self.assertEqual(identity, hashlib.sha256(compact._bytes(mapping)).hexdigest())
        self.assertEqual(result["context"]["facts"]["other"]["value"], spec["facts"]["other"]["value"])
        changed = fixture()
        changed["facts"]["other"]["binding"]["code_sha256"]["experiment.py"] = "d" * 64
        self.assertEqual(len(compact.compact_context(changed)["manifests"]), 2)

    def test_strings_untouched_and_plural_bindings_supported(self):
        spec = fixture()
        for fact in spec["facts"].values():
            fact["binding"]["code_sha256"] = "UNKNOWN"
        result = compact.compact_context(spec)
        self.assertEqual(result["context"], spec)
        self.assertEqual(result["manifests"], {})
        self.assertEqual(result["changed_paths"], [])
        spec = fixture()
        fact = spec["facts"]["other"]
        fact["bindings"] = fact.pop("binding")
        result = compact.compact_context(spec)
        self.assertEqual(expand(result), spec)
        self.assertIn("/facts/other/bindings/code_sha256", result["changed_paths"])

    def test_malformed_manifests_rejected_without_coercion(self):
        invalid = [None, [], 12, {}, {"a.py": "a" * 63}, {"a.py": "g" * 64}, {"a.py": 12},
                   {True: "a" * 64}, {"../a.py": "a" * 64}, {"/a.py": "a" * 64},
                   {"C:/a.py": "a" * 64}, {"a\\b.py": "a" * 64}, {"a//b.py": "a" * 64},
                   {"a/./b.py": "a" * 64}, {"a\x00.py": "a" * 64}, {"x" * 257: "a" * 64},
                   {str(i): "a" * 64 for i in range(513)}]
        for mapping in invalid:
            spec = fixture()
            spec["facts"]["other"]["binding"]["code_sha256"] = mapping
            with self.subTest(mapping=str(mapping)[:60]), self.assertRaises(ValueError):
                compact.compact_context(spec)
        spec = fixture()
        spec["facts"]["other"]["binding"]["code_sha256"] = {str(i): "a" * 64 for i in range(512)}
        self.assertEqual(expand(compact.compact_context(spec)), spec)

    def test_unicode_and_space_filenames_remain_exact_declared_metadata(self):
        spec = fixture()
        mapping = {"测量/输入 样本.json": "A" * 64, "logs/阶段 1.log": "b" * 64}
        spec["facts"]["other"]["binding"]["code_sha256"] = mapping
        result = compact.compact_context(spec)
        self.assertEqual(expand(result), spec)
        self.assertIn(mapping, result["manifests"].values())

    def test_budgets_and_strict_finite_depth_boundaries(self):
        for change in (lambda s: s.update(extra="x" * compact.MAX_FILE_BYTES),
                       lambda s: s["facts"]["other"].update(value="x" * compact.MAX_FACT_BYTES),
                       lambda s: s.update(extra=float("nan")), lambda s: s.update(extra=float("inf")),
                       lambda s: s.update(compaction={}), lambda s: s.update(facts=[])):
            spec = fixture()
            change(spec)
            with self.assertRaises(ValueError):
                compact.compact_context(spec)
        deep = 0
        for _ in range(34):
            deep = [deep]
        with self.assertRaises(ValueError):
            compact.compact_context({**fixture(), "extra": deep})
        spec = {"facts": {"x": {"value": "x" * 262126}}}
        self.assertEqual(len(compact._bytes(spec["facts"])), compact.MAX_FACT_BYTES)
        self.assertEqual(compact.compact_context(spec)["context"], spec)
        spec["facts"]["x"]["value"] += "x"
        with self.assertRaisesRegex(ValueError, "262144"):
            compact.compact_context(spec)

    def test_saved_receipts_raw_source_hash_and_reconstruction(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source.json", Path(folder) / "new"
            spec = fixture()
            raw = b"\xef\xbb\xbf" + json.dumps(spec, indent=2).encode("utf-8") + b"\r\n"
            source.write_bytes(raw)
            summary = compact.write_compacted(source, target)
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual((target / "source.json").read_bytes(), raw)
            self.assertEqual(summary["original_sha256"], hashlib.sha256(raw).hexdigest())
            encoded = (target / "context.json").read_bytes()
            context = json.loads(encoded)
            self.assertEqual(summary["context_sha256"], hashlib.sha256(encoded).hexdigest())
            self.assertEqual(context["compaction"]["assurance"], "DECLARED_MANIFEST_IDENTITY_ONLY")
            self.assertFalse(context["compaction"]["actual_files_verified"])
            manifests = {}
            for identity, record in context["compaction"]["manifests"].items():
                content = (target / record["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), identity)
                manifests[identity] = json.loads(content)
            self.assertEqual(expand({"context": context, "manifests": manifests,
                                     "changed_paths": context["compaction"]["changed_paths"]}), spec)
            self.assertEqual(json.loads((target / "summary.json").read_bytes())["replacements"], 2)
            for existing in (source, target):
                with self.assertRaises(OSError):
                    compact.write_compacted(source, existing)
            self.assertEqual(source.read_bytes(), raw)
            empty = Path(folder) / "empty"
            empty.mkdir()
            with self.assertRaises(OSError):
                compact.write_compacted(source, empty)
            self.assertEqual(list(empty.iterdir()), [])

    def test_cli_strict_json_no_output_on_rejection_and_small_stdout(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source.json", Path(folder) / "new"
            command = [sys.executable, "-B", str(ROOT / "scripts/rds_context_compact.py"),
                       "--input", str(source), "--output-dir", str(target)]
            for raw in (b'{"facts":{},"facts":{}}', b'{"facts":{},"extra":NaN}',
                        b'{"facts":{},"extra":1e999}', b" " * (compact.MAX_FILE_BYTES + 1),
                        b"[" * 2000 + b"0" + b"]" * 2000):
                source.write_bytes(raw)
                result = subprocess.run(command, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "INVALID_INPUT")
                self.assertLessEqual(len(result.stdout), 500)
                self.assertFalse(target.exists())
                self.assertEqual(source.read_bytes(), raw)
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            result = subprocess.run(command, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLessEqual(len(result.stdout), 500)
            self.assertEqual(json.loads(result.stdout)["replacements"], 2)
            result = subprocess.run(command, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()

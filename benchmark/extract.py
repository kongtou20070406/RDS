"""Reproduce the five frozen history packets from the adjacent evaluation corpus.

No Obelisk export or live memory is stored here. Inputs are curated case cards.
Later outcomes and source notes are deliberately separated from proposer inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path

CASES = [
    ("july08-baseline", "EARLY-BENCH.md", "2026-07-08", "development"),
    ("aug02-compiler-ablation", "EXTRA-LOCAL-ABLATION.md", "2026-08-02T03:27:24Z", "supplementary development"),
    ("aug30-gopro-command", "LATE-GOPRO.md", "2026-08-30T11:46:00Z", "historical holdout, now retrospective"),
    ("sep13-c7-boundary", "EXTRA-LEARNABLE-GAIN.md", "2026-09-13T10:13:49Z", "supplementary"),
    ("sep14-48h-budget", "EXTRA-HAZE-BUDGET-COMPLETE.md", "2026-09-14T00:05:00Z", "supplementary prompt-sensitivity replay"),
]


def extract(source, destination):
    manifest = {"version": 1, "evidence_level": "Original-session reports curated in source cards; no training rerun",
                "independence": "Five related NSI/EqOp decisions, not five independent research projects",
                "cases": []}
    for case_id, filename, cutoff, partition in CASES:
        path = source / "cases" / filename
        raw = path.read_bytes()
        card = raw.decode("utf-8-sig")
        prompt, sealed = card.split("## as_of", 1)[1].split("\n## ", 1)
        files = {"prompt": f"prompts/{case_id}.md", "sealed": f"sealed/{case_id}.md"}
        if case_id == "sep13-c7-boundary":
            # Explicit pre-cutoff equation: the earlier blind packet omitted it.
            prompt += ("\n\nSource-aware augmentation (known before the cutoff): "
                       "the executed normalization is a = rho_max * a_hat / (1 + sum(abs(a_hat))). "
                       "With S = sum(abs(a_hat)), actual row mass is m = rho_max*S/(1+S). "
                       "Use this equation when deciding whether an intervention crosses the strict subunit boundary.\n")
            sealed += "\n\n" + (source / "judging" / "C7-boundary-audit.md").read_text(encoding="utf-8")
        if case_id == "sep14-48h-budget":
            sealed += "\n\n" + (source / "cases" / "EXTRA-HAZE-BUDGET.md").read_text(encoding="utf-8").split("## sealed_later_outcome", 1)[1]
        for key, content in (("prompt", prompt.strip()), ("sealed", "## " + sealed.strip())):
            target = destination / files[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content + "\n", encoding="utf-8", newline="\n")
        manifest["cases"].append({"id": case_id, "cutoff": cutoff, "original_partition": partition,
                                  "source_card": "cases/" + filename, "source_sha256": hashlib.sha256(raw).hexdigest(),
                                  **files, "prompt_sha256": hashlib.sha256((destination / files["prompt"]).read_bytes()).hexdigest(),
                                  "sealed_sha256": hashlib.sha256((destination / files["sealed"]).read_bytes()).hexdigest()})
    extra_sources = [source / "judging/C7-boundary-audit.md", source / "cases/EXTRA-HAZE-BUDGET.md"]
    manifest["supplementary_sources"] = [{"path": str(p.relative_to(source)).replace("\\", "/"),
                                           "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in extra_sources]
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    extract(args.source, args.output)

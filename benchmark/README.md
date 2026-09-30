# Five historical RDS decisions

These are retrospective decision replays extracted from the existing
`research-direction-selector-eval` corpus. They do not measure autonomous
research quality or reproduce historical GPU experiments. The historical PSNR
numbers are session reports; the original training artifacts are unavailable here.

| Case | Decision to assess |
|---|---|
| July 8 baseline | A feasible reduced-width benchmark anchor, followed by a fair mixer comparison; no unsupported matched-baseline victory. |
| Aug 2 compiler ablation | Isolate dictionary versus routing while retaining q9/F9/K12 and the budget; a five-image development gain is exploratory. |
| Aug 30 GoPro command | Follow the explicit GoPro pivot, audit the official recipe and old result, then cost a matched comparison. |
| Sep 13 C7 | Distinguish tightening a safety margin from crossing actual row mass 1; use the pre-cutoff executed equation. |
| Sep 14 48h budget | Cancel/defer allocations before spending more, include evaluation overhead, and keep adaptive test reuse exploratory. |

## Prospective response evaluation

Give the proposer only one file from `prompts/`, the skill under evaluation,
and the relevant source-code snapshot. Keep `sealed/` and `rubric.json` away
from the proposer. A judge should first assess the response against the rubric
without seeing later outcomes; reveal outcomes only for retrospective analysis.
The files are separated by convention, not an access-control boundary.

Score each rubric item as 0 (violated/absent), 1 (partial), or 2 (satisfied),
and quote the response evidence. Record model/version, prompt hash, skill commit,
budget and judge. Compare paired cases at the same budget. Do not score matching
the eventual historical choice as inherently correct. These related cases have
been used during skill development and are not a new independent holdout.

The C7 prompt explicitly restores a then-known equation omitted from the earlier
blind packet. This is a source-aware replay, not a claim to reproduce its scores.
The September 14 packet restores the then-known 48h cap and 34.4h queue estimate.
No later 100k result appears in that prompt.

## Automated checks

Run `python -B benchmark/run.py`. This verifies packet integrity and replays
five associated executable guard behaviors in temporary project roots. Numeric
CSV examples are **synthetic scalar surrogates**; they are not historical PSNR,
PyTorch models, or reconstructed training jobs. The budget replay uses 1000 ms
per historical hour to exercise the same allocation arithmetic within the
reference runner's 60-second limit. Passing these tests does not establish that
an LLM will recommend a good scientific direction.

Regenerate packets from the private sibling corpus:

```powershell
python -B benchmark/extract.py --source ../research-direction-selector-eval
```

The manifest binds the source-card bytes and exported packets with SHA-256.
Sealed files retain original Obelisk message UUIDs for local evidence tracing.
They contain curated case text, never full session exports or credential messages.

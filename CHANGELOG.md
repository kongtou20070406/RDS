# Changelog

## Unreleased

- Rename the GitHub repository to `kongtou20070406/research-direction-selector` with the owner's authorization, and update the public documentation links and clone instructions. RDS remains the project abbreviation.
- Adopt the published scientific-autonomy taxonomy from Kramer et al. (Machine Learning, 2026, §5/Table 5), retaining its L0–L5 numbering and definitions. Distinguish it from the older `L3`/`L4` engineering labels and from RSI improvement claims.
- Describe current scoped L2 functionality, the near-term goal of L2 automation across all six research stages, and long-term L4/L5 research targets without claiming completed autonomous discovery.
- Replace the general roadmap with ten concrete work items, each specifying the implementation gap, method, deliverables and acceptance conditions. Prioritize real-project usability, evidence import, continuity and human review. Retain sourced benchmark-selection notes while deferring cross-skill comparisons; no comparison runs are scheduled and end-to-end research scores remain unmeasured.

## 5.5.0-rc.2 — 2026-09-30

Publish Research Direction Selector from `main` after merging the mathematical kernel and Advisor integration. The GitHub repository address remains `kongtou20070406/RDS`.

- Put the full project name, measured component checks and linked raw evidence on the three README homepages. Explain the observed evidence, contract, prerequisite and budget behavior without presenting adapted checks as original scientific benchmark scores.
- Update implementation guides to reflect the merged main branch and preserve the limits of Lean checks, Python certificates and research evidence.
- Restore the three judgment-rule descriptions that require observed, decision-relevant seed instability before proposing additional seeds.
- Keep v5.5.0-rc.1 ledgers readable after the version change; old engine bindings still require a new execution contract. Extend the existing compatibility regression to check both reading and rejection of stale execution bindings.

Validation: 208 regression checks (204 passed, 4 optional skips), including compatibility and graph-reader coverage. The earlier six historical checks, four synthetic scenarios and eight public-task-adapted cases/28 criteria retain their stated scope; no end-to-end scientific score or GPU savings are claimed. The original rc.1 tag is retained.

## 5.5.0-rc.1 — 2026-09-30

RDS assists human research: turn a question into a useful test, preserve evidence, and decide the next step. This pre-release combines the mathematical compatibility work from PR #2 with the human-facing documentation from PR #1 and the Advisor/dashboard update.

- Anchor five components: Skill, execution and acceptance kernel, research state and memory, Advisor, and RSI. Add direct researcher instructions, a prompt to hand to an AI, and an evidence-based roadmap in three READMEs.
- Add bounded Advisor search over explicit sourced facts and reasoning prerequisites. Keep missing evidence and costs unknown; show competing explanations, outcome-dependent decisions and derivations. Five graph rules have executable bindings; proof-obligation metadata alone is not an enforced gate.
- Replace unsupported loss diagnoses and fixed numerical prescriptions with scoped diagnostic candidates. Add comparable curve input and nine source-grounded literature records. Preserve independent WAL imports, limits, deduplication and explicit legacy migration; excerpts stay unreviewed.
- Add a read-only offline HTML dashboard for goals, evidence, budgets, plans and receipts. Correct the stdlib graph reader/writer so dependencies and structured bindings survive without PyYAML.
- Retain the declared mathematical side-condition framework, Python certificates and limited native Lean4 closed-rational checks. Arbitrary mathlib neural-model translation and a general GPU training runner remain future work.

Validation: 208 regression checks (204 passed, 4 optional checks skipped), six historical checks, four synthetic attack scenarios, and eight public-task-adapted component cases with 28 checks. The adapted cases are development fixtures, not original benchmark scores or measured research-quality gains. No GPU training, paid API calls or multi-seed campaigns were run.

Old ledgers remain readable. Existing execution contracts bind the previous engine; create a new contract for execution with the changed version rather than reusing an old binding. The release is published from an integration branch; it does not merge the open source PRs into main.

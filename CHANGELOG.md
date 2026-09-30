# Changelog

## 5.5.0-rc.1 — 2026-09-30

RDS assists human research: turn a question into a useful test, preserve evidence, and decide the next step. This pre-release combines the mathematical compatibility work from PR #2 with the human-facing documentation from PR #1 and the Advisor/dashboard update.

- Anchor five components: Skill, execution and acceptance kernel, research state and memory, Advisor, and RSI. Add direct researcher instructions, a prompt to hand to an AI, and an evidence-based roadmap in three READMEs.
- Add bounded Advisor search over explicit sourced facts and reasoning prerequisites. Keep missing evidence and costs unknown; show competing explanations, outcome-dependent decisions and derivations. Five graph rules have executable bindings; proof-obligation metadata alone is not an enforced gate.
- Replace unsupported loss diagnoses and fixed numerical prescriptions with scoped diagnostic candidates. Add comparable curve input and nine source-grounded literature records. Preserve independent WAL imports, limits, deduplication and explicit legacy migration; excerpts stay unreviewed.
- Add a read-only offline HTML dashboard for goals, evidence, budgets, plans and receipts. Correct the stdlib graph reader/writer so dependencies and structured bindings survive without PyYAML.
- Retain the declared mathematical side-condition framework, Python certificates and limited native Lean4 closed-rational checks. Arbitrary mathlib neural-model translation and a general GPU training runner remain future work.

Validation: 208 regression checks (204 passed, 4 optional checks skipped), six historical checks, four synthetic attack scenarios, and eight public-task-adapted component cases with 28 checks. The adapted cases are development fixtures, not original benchmark scores or measured research-quality gains. No GPU training, paid API calls or multi-seed campaigns were run.

Old ledgers remain readable. Existing execution contracts bind the previous engine; create a new contract for execution with the changed version rather than reusing an old binding. The release is published from an integration branch; it does not merge the open source PRs into main.

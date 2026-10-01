# Low-friction and RSI design review — 2026-10-01

Decision: extend the existing argv runner, checkpoint ledger and independent checker with explicit completion and promotion checks. Use short factual agent progress reports. Scientific gains still require prospective independent evaluation with equal total budgets; neither passing tests nor a hash proves end-to-end improvement.

This is a bounded review of official interface documentation and primary RSI papers, not an exhaustive survey or a reproduction of their experiments.

| Source / checked version | Source-supported finding | RDS decision or limitation |
|---|---|---|
| [Click advanced patterns](https://click.palletsprojects.com/en/stable/advanced/), stable docs checked 2026-10-01 | Token normalization and forwarding are distinct; mixed wrapper/child options have parsing constraints. | Complete only known command aliases and bookkeeping. Protect child argv after an explicit or inferred boundary. |
| [clap Command](https://docs.rs/clap/latest/clap/builder/struct.Command.html), 4.6.6 docs | Declared aliases and opt-in unique subcommand inference are separate facilities. | Exact names win; ambiguous prefixes stop. Existing `run` and `plan` retain semantics. |
| [MLflow validation implementation](https://www.mlflow.org/docs/latest/api_reference/_modules/mlflow/models/evaluation/validation.html), latest checked 2026-10-01 | Metric validation supports direction and absolute/relative comparisons against a baseline. | Explicit same-scope observation comparisons can gate promotion. This prior art does not imply monotonic exploratory observations or correct scientific measurements. |
| [DVC experiment diff](https://dvc.org/doc/command-reference/exp/diff), current docs | Revisions' parameters and metrics can be compared. | Keep weaker originals and frozen input identities; comparisons alone do not establish mechanisms. |
| [Recursive self-improvement of AI research agents](https://arxiv.org/abs/2609.26457v1), Srikanth et al., 2026-09-22 | AIDE² optimizes its own agent code, selects on hidden evaluations and reports transfer to held-out task families. | Research-agent harness evolution can keep the backbone fixed. Replaying exposed development cases is weaker evidence than held-out transfer. RDS has not reproduced AIDE². |
| [CoEvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification](https://arxiv.org/abs/2604.01687v3), Zhang et al., revised 2026-08-10; [author repository](https://github.com/Zhang-Henry/CoEvoSkills) | Skill generation uses surrogate-verifier feedback and separately isolated downstream testing. The current release evolves multi-file packages. | Co-evolution is useful candidate-generation prior art; a self-generated verifier cannot certify universal correctness. Keep independent checker identity and confirmation exposure. Pure-function extraction is not what the released framework requires. |
| [Reinforcement Learning for Self-Improving Agent with Skill Library](https://aclanthology.org/2026.acl-long.69/), Wang et al., ACL July 2026 | SAGE uses Sequential Rollout and skill-integrated rewards in GRPO training. | It is training-method prior art, not an immediate CLI-only drop-in for a frozen Codex Luna login channel. No weight training is introduced here. |

## Corrections to the supplied proposals

The official benchmark title is [ExplorationBench: Measuring AI Systems' Exploration in Verifiable Alien Worlds](https://arxiv.org/abs/2609.30199). Original sandbox access and a prospective RDS A/B run remain separate outstanding work. The supplied claims of 0% decline, a fixed token count, “universal self-written verifier” correctness and large efficiency gains are hypotheses, not observed RDS results.

A bounded command runner limits declared execution and costs; Lean checks a mathematical statement. Proof checking does not provide operating-system isolation for arbitrary Python. Historical success cases help regression review but do not become independent policy confirmation by calling them milestones. These are the strongest limitations relevant to the proposed auto-adoption loop.

## Resulting development scope

Implemented scope: frozen-request names, local Python shorthand, output-parent completion, expanded aliases, common CLI hypergraph access, explicit exact metric comparisons, frozen milestone replay and declared scoped interval rejections. Progress visibility lives in the Skill as one factual sentence at meaningful advances or blockers. Results use existing CAS/events/checkpoints; no new service or parallel research memory is created.

Future hypothesis: extracting reusable capabilities from failed attempts may improve research conversion. Before adoption, a candidate needs frozen parents and source identities, applicable positive/negative/boundary checks, an independently appropriate verifier, confirmation exposure review and rollback. Policy claims additionally need untouched prospective trajectories at matched total budget. The current engineering checks do not establish that hypothesis or L3 autonomy.

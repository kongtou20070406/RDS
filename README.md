# RDS-L3

Research Direction Selector **5.1.0** is a research skill with an executable local
reference kernel, an Obelisk history bridge, and five historical decision packets.

- Reuse the installed Obelisk CLI/CodeAct sandbox for history; no separate memory store or vector database.
- Ordinary experiments use lightweight AST checks. Explicit algebraic thresholds or contraction boundaries invoke an optional scalar symbolic probe; unsupported dynamics fail closed as `UNKNOWN`.
- Transactional budgets, data-exposure tracking and hash-bound execution receipts keep task gain, mechanism evidence and run status separate.
- Replay July 8 baseline, Aug 2 compiler ablation, Aug 30 GoPro instruction, Sep 13 C7 boundary and Sep 14 48h allocation decisions.

The kernel executes restricted scalar rational programs with paired MSE. It is
not a PyTorch trainer, a PSNR evaluator, an OS sandbox or a proof of autonomous
research performance. Historical training scores are reported evidence; automated
replays use explicitly synthetic scalar inputs.

## Install and verify

Use Python 3.11 or newer. Ordinary operation needs no third-party Python package.
Obelisk must already be installed for live history retrieval. To enable the
formal adapter and run all tests:

```powershell
python -m pip install -r requirements-formal.txt
python -B -m unittest discover -s tests -v
python -B benchmark/run.py
```

For skill discovery, place this repository's contents in a skill directory named
`research-direction-selector` under your host's skills root. Start with
[SKILL.md](SKILL.md); the agent should retrieve history only when it affects a decision.

## Run the example

```powershell
python -B scripts/rds_cli.py --root examples/reference-run init --contract examples/reference-run/contract.json
python -B scripts/rds_cli.py --root examples/reference-run hypothesis add --spec examples/reference-run/hypothesis.json
python -B scripts/rds_cli.py --root examples/reference-run plan create --spec examples/reference-run/plan.json
python -B scripts/rds_cli.py --root examples/reference-run run execute --id P1
```

Pass the returned `run_id` to `decide --run`, using the same `--root`. The example
is development-only and produces exploratory task evidence. `init` never erases
existing state. Use a fresh copy/root for a new contract.

See [CLI semantics and formal declarations](references/l3-state-machine.md),
[Obelisk retrieval](references/obelisk.md), and [benchmark protocol](benchmark/README.md).
Operational `.rds` databases and local query files are excluded from Git.

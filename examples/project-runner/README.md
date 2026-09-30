# Real CPU project-runner demonstration

`prepare.py --root <new-empty-directory>` copies a recorded six-row dataset,
an experiment script and its evaluator, then writes actual SHA256-bound
contract and run manifests. The control fits a constant; the treatment fits a
line. Results are measured by this code on demonstration data. They do not
claim scientific confirmation or generalization.

Use `ProjectStore(root).initialize(contract)`, `register(manifest)` and
`execute(run_id)` for each arm, or the `project` CLI commands. The project root
is the fixed working directory. Commands are exact argv lists; no shell is
used. Expected outputs must be new files within authorized output roots.

Run status records process and artifact completion. `task_gain` and `mechanism`
remain `UNKNOWN`; the raw JSON metrics are retained as artifacts rather than
accepted as handwritten scientific verification. Real wall time is measured;
CPU time is unknown and retains its reservation estimate as a separate charge.

## Reusing the actual control

`project control-check` needs the successful **control** receipt and the
current intended control operation. Matching code/data/configuration and seed
does not distinguish this example's `--arm control` from `--arm treatment`.
The current record must contain the full protocol identity plus `arm: control`
and the exact expected `argv`. The JSON returned by `project create` already
contains these under `protocol` and `manifest`; it can be passed as `--current`.
The candidate receipt records its actual argv and working directory. Both must
match the current project's operation and root. Bare `protocol.json` lacks the
operation and remains non-reusable with an `UNKNOWN` operation identity.

For example, from the RDS checkout, with the prepared `$RdsDemo` workspace:

```powershell
python -B scripts/rds_cli.py --root $RdsDemo project create --manifest "$RdsDemo/control.json" | Set-Content -Encoding utf8 "$RdsDemo/current-control.json"
python -B scripts/rds_cli.py --root $RdsDemo project execute --id control | Set-Content -Encoding utf8 "$RdsDemo/control-receipt.json"
python -B scripts/rds_cli.py --root $RdsDemo project control-check --candidate "$RdsDemo/control-receipt.json" --current "$RdsDemo/current-control.json"
```

Register and execute an ID once. Save the returned record during the initial
registration; do not repeat registration just to produce the file. A treatment
receipt cannot become a reusable control, even when its protocol matches.
Successful reuse checks still have `scientific_assessment: UNKNOWN`.

`execute(run_id, background=True)` on Windows registers a unique RDS-owned Task
Scheduler task running the one-attempt `pythonw.exe` worker. Scheduler output is
recorded beside attempt artifacts. Recovery reconciles records and never starts
another attempt. Other platforms support foreground execution only. Approved
project code is trusted; this runner is not an OS sandbox.

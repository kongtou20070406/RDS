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

`execute(run_id, background=True)` on Windows registers a unique RDS-owned Task
Scheduler task running the one-attempt `pythonw.exe` worker. Scheduler output is
recorded beside attempt artifacts. Recovery reconciles records and never starts
another attempt. Other platforms support foreground execution only. Approved
project code is trusted; this runner is not an OS sandbox.

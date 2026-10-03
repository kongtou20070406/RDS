# Local CLI usage log

Every `rds_cli.py` invocation attempts to record its start and exit in a local SQLite log,
automatically. All updated checkouts share one log for the current user. Calls
include help, version, invalid arguments, failed commands and statistics queries.

SQLite waits up to ten seconds per logging transaction for temporary contention;
persistent failures leave the command's original result unchanged. Existing journal
modes are retained, and fresh logs use SQLite's default mode without a first-use
existence/PRAGMA race. The invocation reports a logging failure to stderr as
[RDS-USAGE-DEGRADED], naming the start/finish phase, exception type and available
SQLite error code without printing paths or argument payloads. Its original result
or exception remains unchanged even if the diagnostic stream is unavailable.
An unconfirmed start can be absent from counts; an unconfirmed finish can leave
an unfinished entry. The current process's logging=ENABLED is not proof that
earlier invocations were completely recorded. Missing history is not reconstructed.
Counts describe recorded CLI invocations; API imports and loading Skill instructions
have their own evidence. No prompt, full argv, input path or credential is stored.

Show recent daily counts (14 days by default):

```text
python -B scripts/rds_cli.py usage --days 7
python -B scripts/rds_cli.py usage --since 2026-09-01 --until 2026-10-01
python -B scripts/rds_cli.py usage --days 30 --json
```

Dates are inclusive and use the local calendar date recorded at invocation.
The output shows total recorded calls, daily counts, command/mode counts and
the tracking start. Dates before logging started show `-` in the table and
`calls=null, tracked=false` in JSON; they are not silently reported as zero.
Existing historical calls are not reconstructed from guesses. A query counts
itself, and its start is visible before its exit is written. JSON also reports
successful, failed and unfinished entries; an unfinished entry alone does not
establish that a process is still running.

On Windows the log is `%LOCALAPPDATA%/ResearchDirectionSelector/cli-usage.sqlite3`.
Other platforms use `~/.local/state/ResearchDirectionSelector/cli-usage.sqlite3`.
`RDS_USAGE_DB` can select a different file, including an isolated test log. The
log is independent of project budget/evidence ledgers and is never uploaded.
SQLite transactions support concurrent CLI processes. Storage failures preserve
the original command's return/exception; usage queries expose unavailable or
degraded logging. Usage reports can run without creating project state.

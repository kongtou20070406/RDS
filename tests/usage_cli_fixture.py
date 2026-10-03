"""Real CLI fixture waits; no changes to logging or runtime policy."""
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time

# One invocation can wait ten seconds at both start and exit logging, in
# addition to interpreter startup. This bounds the fixture, not product time.
CLI_WATCHDOG_SECONDS = 60


def ledger_snapshot(path):
    try:
        with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=.1)) as db:
            return {"status": "READ", "calls": [
                dict(zip(("id", "started", "day", "command", "mode", "version", "exit_code", "elapsed_ms"), row))
                for row in db.execute("SELECT id,started,day,command,mode,version,exit_code,elapsed_ms FROM calls ORDER BY id")]}
    except (OSError, sqlite3.Error, ValueError) as exc:
        return {"status": "UNKNOWN", "error": str(exc)}


def run_cli(command, folder, ledger, *, watchdog=CLI_WATCHDOG_SECONDS, ready=None):
    began = time.monotonic()
    started_at = time.time()
    child = subprocess.Popen(command, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8")
    try:
        if ready is not None:
            ready(child)
        try:
            stdout, stderr = child.communicate(timeout=watchdog)
        except subprocess.TimeoutExpired as exc:
            child.kill()
            stdout, stderr = child.communicate(timeout=5)
            exc.output, exc.stderr = stdout, stderr
            exc.add_note(json.dumps({
                "fixture_watchdog": True, "pid": child.pid, "returncode": child.returncode,
                "elapsed": time.monotonic() - began, "phase": "UNKNOWN",
                "stdout": stdout, "stderr": stderr, "ledger": ledger_snapshot(ledger),
            }, ensure_ascii=False))
            raise
        result = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        result.fixture_timing = {"pid": child.pid, "started_at": started_at, "finished_at": time.time(),
                                 "elapsed_seconds": time.monotonic() - began}
        return result
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
        # communicate closes these normally; readiness failures need closure too.
        for stream in (child.stdout, child.stderr):
            stream.close()


def count_diagnostics(ledger, results, report=None):
    """Original synthetic child outputs and row dates expose loss/unfinished/filter failures."""
    return json.dumps({"report": report, "ledger": ledger_snapshot(ledger), "children": [
        {**getattr(result, "fixture_timing", {}), "returncode": result.returncode,
         "stdout": result.stdout, "stderr": result.stderr} for result in results]},
        ensure_ascii=True, sort_keys=True)


def wait_marker(path, *, child=None, stop=None):
    deadline = time.monotonic() + CLI_WATCHDOG_SECONDS
    while not path.exists():
        if stop is not None and stop.is_set():
            raise RuntimeError("Synthetic writer stopped")
        if child is not None and child.poll() is not None:
            raise RuntimeError("Child exited before its readiness marker")
        if time.monotonic() >= deadline:
            raise RuntimeError("Synthetic marker missing: " + path.name)
        time.sleep(.01)


@contextmanager
def paused_schema(folder, ledger):
    """Pause one real CLI after schema preparation, with bounded parent cleanup."""
    work = Path(folder) / "usage-schema-pause"
    work.mkdir()
    (work / "sitecustomize.py").write_text(r'''
import json, os, pathlib, sqlite3, time
_connect = sqlite3.connect
_work = pathlib.Path(os.environ["RDS_USAGE_SCHEMA_PAUSE"])
class Connection(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        result = super().execute(sql, *args, **kwargs)
        if sql.startswith("CREATE INDEX") and not (_work / "ready").exists():
            (_work / "ready").write_text(json.dumps({"in_transaction": self.in_transaction}))
            deadline = time.monotonic() + 60
            while not (_work / "release").exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Synthetic schema-pause gate expired")
                time.sleep(.01)
        return result
def connect(path, *args, **kwargs):
    if pathlib.Path(path).resolve() == pathlib.Path(os.environ["RDS_USAGE_DB"]).resolve():
        kwargs["factory"] = Connection
    return _connect(path, *args, **kwargs)
sqlite3.connect = connect
''', encoding="utf-8")
    try:
        yield {"work": work, "environment": {
            "RDS_USAGE_SCHEMA_PAUSE": str(work),
            "PYTHONPATH": str(work) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        }}
    finally:
        (work / "release").touch()


# Only the declared synthetic database is instrumented. Real connect/BEGIN/
# commit/close calls run unchanged; gates let the parent hold two real writers.
HOOK = r'''
import os, pathlib, sqlite3, time
_connect = sqlite3.connect
_number = 0
_work = pathlib.Path(os.environ["RDS_USAGE_FIXTURE_SCOPE"])
class Connection(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        if sql == "BEGIN IMMEDIATE":
            (_work / (str(self.number) + "-waiting")).touch()
        return super().execute(sql, *args, **kwargs)
    def close(self):
        result = super().close()
        if self.number == 1:
            (_work / "start-closed").touch()
            deadline = time.monotonic() + 60
            while not (_work / "exit-writer-ready").exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Synthetic exit-writer gate expired")
                time.sleep(.01)
        return result
def connect(path, *args, **kwargs):
    global _number
    if pathlib.Path(path).resolve() != pathlib.Path(os.environ["RDS_USAGE_DB"]).resolve():
        return _connect(path, *args, **kwargs)
    _number += 1
    kwargs["factory"] = Connection
    connection = _connect(path, *args, **kwargs)
    connection.number = _number
    return connection
sqlite3.connect = connect
'''


@contextmanager
def dual_sqlite_wait(folder, ledger):
    work = Path(folder) / "usage-lock-fixture"
    work.mkdir()
    (work / "sitecustomize.py").write_text(HOOK, encoding="utf-8")
    locked, stop = threading.Event(), threading.Event()
    intervals, errors = [], []

    def hold():
        began = time.monotonic()
        while (remaining := 8.2 - (time.monotonic() - began)) > 0:
            if stop.wait(remaining):
                raise RuntimeError("Synthetic writer stopped")
        intervals.append(time.monotonic() - began)

    def writer():
        try:
            with closing(sqlite3.connect(ledger, timeout=10)) as db:
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    locked.set()
                    wait_marker(work / "1-waiting", stop=stop)
                    hold()
                wait_marker(work / "start-closed", stop=stop)
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    (work / "exit-writer-ready").touch()
                    wait_marker(work / "2-waiting", stop=stop)
                    hold()
        except BaseException as exc:
            if not stop.is_set():
                errors.append(exc)
            locked.set()
            (work / "exit-writer-ready").touch()

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        if not locked.wait(CLI_WATCHDOG_SECONDS):
            raise RuntimeError("Synthetic first writer did not acquire its lock")
        if errors:
            raise errors[0]
        yield {"environment": {
            "RDS_USAGE_FIXTURE_SCOPE": str(work),
            "PYTHONPATH": str(work) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        }, "intervals": intervals}
    finally:
        stop.set()
        thread.join(timeout=12)
        if thread.is_alive():
            raise RuntimeError("Synthetic writer did not stop")
        if errors:
            raise errors[0]

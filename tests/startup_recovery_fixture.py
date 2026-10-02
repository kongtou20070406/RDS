"""Isolated synthetic startup test; no production policy or runtime changes."""
import contextlib
import faulthandler
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_project import ProjectStore, _Job

# Fixture deadlock guard, not a controller SLA or a changed child timeout.
# Room for existing ten-second SQLite waits and CI scheduling is deliberate.
WATCHDOG_SECONDS = 60


def run_fixture(root, spec, *, scenario="ordinary", watchdog=WATCHDOG_SECONDS):
    work = Path(root) / ".startup-fixture"
    work.mkdir()
    spec_path = work / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    report_path = work / "report.json"
    with (work / "stdout.txt").open("wb") as stdout, (work / "stderr.txt").open("wb") as stderr:
        process = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()), str(root), str(spec_path), scenario],
            stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        job = None
        expired = False
        try:
            job = _Job(process)
            # Establish ownership before this controller can launch its real child.
            process.stdin.write(b"start\n")
            process.stdin.close()
            if scenario == "stalled_claim":
                # The negative's short watchdog starts only after the real claim
                # has reached its controlled stall, not during interpreter startup.
                ready_deadline = time.monotonic() + WATCHDOG_SECONDS
                while process.poll() is None and not (work / "stalled").exists():
                    if time.monotonic() >= ready_deadline:
                        raise subprocess.TimeoutExpired(process.args, WATCHDOG_SECONDS)
                    time.sleep(0.02)
            process.wait(timeout=watchdog)
        except subprocess.TimeoutExpired:
            expired = True
            # Request diagnostics before termination on both platforms. If its
            # Python threads cannot respond, the owned Job remains the fallback.
            (work / "watchdog-request").write_text("expired", encoding="utf-8")
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                job.stop()
                process.wait(timeout=5)
        finally:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                if job is not None:
                    job.stop()
                else:
                    process.kill()
                process.wait(timeout=5)
            if job is not None:
                job.close()
    return {
        "watchdog_expired": expired, "returncode": process.returncode,
        "report": json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None,
        "stdout": (work / "stdout.txt").read_text(encoding="utf-8", errors="replace"),
        "stderr": (work / "stderr.txt").read_text(encoding="utf-8", errors="replace"),
    }


def controller(root, spec_path, scenario):
    # Import the same assertion scenario used by unittest, without initializing
    # a second ledger or altering the parent's admitted contract.
    from test_rds_project import ProjectTests
    case = ProjectTests()
    case.root = Path(root)
    case.store = ProjectStore(root)
    work = case.root / ".startup-fixture"
    report = {"phase": "controller_started", "controller_pid": os.getpid()}
    report_lock = threading.Lock()
    owned_jobs = []
    original_job = _Job

    def tracked_job(process):
        job = original_job(process)
        owned_jobs.append(job)
        return job

    def interrupted(signum, frame):
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        for job in owned_jobs:
            job.stop()
        os._exit(124)

    signal.signal(signal.SIGTERM, interrupted)

    def watch_parent_request():
        while True:
            if (work / "watchdog-request").exists():
                interrupted(None, None)
            time.sleep(0.02)

    threading.Thread(target=watch_parent_request, daemon=True).start()

    def save():
        temporary = work / "report.tmp"
        temporary.write_text(json.dumps(report), encoding="utf-8")
        temporary.replace(work / "report.json")

    def record(phase):
        with report_lock:
            report["phase"] = phase
            save()
            report["snapshot"] = case.store.snapshot()
            report["snapshot_phase"] = phase
            save()

    def stalled_claim(*args):
        record("stalled_claim")
        (work / "stalled").write_text("claimed", encoding="utf-8")
        threading.Event().wait()

    original_finish = case.store._finish

    def finish_under_write_lock(*args, **kwargs):
        held = threading.Event()
        errors = []

        def writer():
            db = None
            try:
                db = sqlite3.connect(case.store.path, timeout=10)
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    began = time.monotonic()
                    held.set()
                    time.sleep(5.2)
                report["writer_lock_seconds"] = time.monotonic() - began
            except BaseException as exc:
                errors.append(exc)
                held.set()
            finally:
                if db is not None:
                    db.close()

        holder = threading.Thread(target=writer)
        holder.start()
        try:
            held.wait()
            if errors:
                raise errors[0]
            record("waiting_for_sqlite_settlement")
            result = original_finish(*args, **kwargs)
        finally:
            holder.join()
        if errors:
            raise errors[0]
        return result

    try:
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("rds_project._Job", side_effect=tracked_job))
            if scenario == "sqlite_wait":
                stack.enter_context(patch.object(case.store, "_finish", side_effect=finish_under_write_lock))
            elif scenario == "stalled_claim":
                stack.enter_context(patch.object(case.store, "_execute_claim", side_effect=stalled_claim))
            elif scenario != "ordinary":
                raise ValueError("Unknown fixture scenario")
            spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
            case._assert_foreground_startup_recovery(spec, record)
        record("assertions_passed")
        return 0
    except BaseException as exc:
        report["exception"] = {"type": type(exc).__name__, "message": str(exc)}
        report["traceback"] = traceback.format_exc()
        record(report["phase"])
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    faulthandler.enable()
    if sys.stdin.buffer.readline() != b"start\n":
        raise SystemExit("Fixture ownership handshake missing")
    raise SystemExit(controller(*sys.argv[1:]))

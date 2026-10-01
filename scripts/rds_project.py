"""Bounded execution of explicitly authorized project commands (stdlib only).

This is an operational ledger, not conversational memory or an OS sandbox.
An allowed project command is trusted code; output paths constrain this runner's
own writes and declared artifacts, not every write performed by that code.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import uuid


TERMINAL = {"COMPLETED", "FAILED", "INTERRUPTED"}
ROLES = {"code", "config", "data", "evaluator", "protocol"}
IDENTITY = ("code_sha256", "config_sha256", "data_sha256", "data_split",
            "init", "seed", "checkpoint", "schedule", "sample_work", "numeric_protocol")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name, positive=False):
    require(not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and (value > 0 if positive else value >= 0),
            f"Invalid {name}")
    return float(value)


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def _alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) can terminate processes on Windows. Never use it here.
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x100000, False, pid)
        if not handle:
            return False if ctypes.get_last_error() == 87 else None
        try:
            return api.WaitForSingleObject(handle, 0) == 258
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None


class _Job:
    """Own the launched process tree, without enumerating unrelated processes."""
    def __init__(self, process):
        self.process = process
        self.handle = None
        if os.name != "nt":
            return
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t),
                        ("max_working", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_ulonglong * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = self.api.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not handle or not self.api.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            if handle:
                self.api.CloseHandle(handle)
            raise OSError("Cannot establish project process job")
        if not self.api.AssignProcessToJobObject(handle, int(process._handle)):
            self.api.CloseHandle(handle)
            raise OSError("Cannot bind owned process to project job")
        self.handle = handle

    def stop(self):
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)
        elif self.process.poll() is None:
            if os.name == "nt":
                self.process.kill()
            else:
                os.killpg(self.process.pid, signal.SIGKILL)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        require(self.root.is_dir(), "Project root must exist")
        self.state_dir = self.root / ".rds"
        require(self.state_dir.resolve().is_relative_to(self.root), "State directory escapes project root")
        self.path = self.state_dir / "project.sqlite3"
        self.artifact_dir = self.state_dir / "project-artifacts"

    def _path(self, relative, output=False, contract=None):
        require(isinstance(relative, str) and relative and not Path(relative).is_absolute()
                and not Path(relative).drive and ":" not in relative, "Expected project-relative path")
        if output and os.name == "nt":
            require(all(part in (".", "..") or not part.endswith((".", " ")) for part in Path(relative).parts),
                    "Windows output path components cannot end in a dot or space")
        path = (self.root / relative).resolve()
        require(path.is_relative_to(self.root) and path != self.root, "Path escapes project root")
        require(not path.is_relative_to(self.state_dir.resolve()), "Project files cannot address operational state")
        if output:
            roots = [(self.root / item).resolve() for item in contract["output_roots"]]
            require(any(path.is_relative_to(item) and path != item for item in roots), "Output is outside authorized roots")
            require(path not in {(self.root / b["path"]).resolve() for b in contract["bindings"]}, "Output overwrites bound input")
        return path

    def _output_key(self, path):
        if os.name == "nt":
            # Win32 aliases apply before the output exists, also in old ledgers.
            path = Path(*(part if part in (".", "..") else part.rstrip(". ") for part in Path(path).parts))
        return os.path.normcase(str((self.root / path).resolve()))

    def _output_claims(self, db):
        # Keep legacy absolute/relative, case and Win32 suffix aliases exclusive.
        claims = {}
        for row in db.execute("SELECT path,run_id FROM output_claims"):
            claims.setdefault(self._output_key(row["path"]), set()).add(row["run_id"])
        return claims

    def _check_start(self, db, run):
        # This run is already reserved. Do not charge its estimate a second time,
        # but do not let that reservation override costs settled since admission.
        for resource, amount in run["resource_estimates"].items():
            row = db.execute("SELECT * FROM budget WHERE resource=?", (resource,)).fetchone()
            require(row is not None and row["reserved"] + 1e-9 >= amount,
                    f"Missing {resource} reservation")
            require(row["spent"] + row["charged"] + row["reserved"] <= row["cap"] + 1e-9,
                    f"Insufficient {resource} budget before start")
        contract = self._contract(db)
        claims = self._output_claims(db)
        for path in run["manifest"]["outpaths"]:
            key = self._output_key(self._path(path, True, contract))
            require(claims.get(key) == {run["id"]}, "Output is not exclusively claimed by this run")

    @contextmanager
    def _db(self, readonly=False):
        if readonly:
            if not self.path.is_file():
                raise FileNotFoundError("Project contract has not been initialized")
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10)
            db.execute("PRAGMA query_only=ON")
        else:
            require(self.path.resolve().is_relative_to(self.root), "Project database escapes root")
            db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _contract(db):
        row = db.execute("SELECT body,sha256 FROM contract WHERE id=1").fetchone()
        require(row is not None, "Project contract is missing")
        value = json.loads(row["body"])
        require(digest(value) == row["sha256"], "Contract integrity failure")
        return value

    def _bindings(self, contract):
        found = []
        errors = []
        checked = {}
        for b in contract["bindings"]:
            try:
                path = self._path(b["path"])
                if path not in checked:
                    checked[path] = file_sha(path)
                actual = checked[path]
            except (OSError, ValueError) as exc:
                actual = None
                errors.append(f"Binding unavailable: {b['path']}: {exc}")
            found.append({"path": b["path"], "role": b["role"], "sha256": actual})
            if actual != b["sha256"]:
                errors.append(f"Binding changed: {b['path']}")
        return found, errors

    @staticmethod
    def _role_sha(contract, role):
        values = [{"path": b["path"], "sha256": b["sha256"]}
                  for b in contract["bindings"] if b["role"] == role]
        return values[0]["sha256"] if len(values) == 1 else digest(sorted(values, key=lambda b: b["path"]))

    def initialize(self, contract):
        require(isinstance(contract, dict) and type(contract.get("schema")) is int
                and contract["schema"] == 1, "Project contract schema must be 1")
        require(set(contract) <= {"schema", "bindings", "allowed_commands", "output_roots", "budget", "description"}, "Unknown contract fields")
        require(isinstance(contract.get("bindings"), list) and contract["bindings"], "Bindings required")
        paths = {}
        binding_roles = set()
        roles = set()
        for b in contract["bindings"]:
            require(isinstance(b, dict) and set(b) == {"path", "sha256", "role"}, "Invalid binding")
            require(b["role"] in ROLES, "Unknown binding role")
            path = self._path(b["path"])
            require((path, b["role"]) not in binding_roles and path.is_file(), "Missing or duplicate binding role")
            if path not in paths:
                paths[path] = file_sha(path)
            require(paths[path] == b["sha256"], "Initial binding mismatch")
            binding_roles.add((path, b["role"]))
            roles.add(b["role"])
        require(ROLES <= roles, "code/config/data/evaluator/protocol bindings required")
        commands = contract.get("allowed_commands")
        require(isinstance(commands, list) and commands, "Allowed argv commands required")
        for argv in commands:
            self._command(argv)
        roots = contract.get("output_roots")
        require(isinstance(roots, list) and roots, "Output roots required")
        for item in roots:
            self._path(item)
        budget = contract.get("budget")
        require(isinstance(budget, dict) and "wall_seconds" in budget, "Budget vector requires wall_seconds")
        for unit, cap in budget.items():
            require(isinstance(unit, str) and unit and len(unit) <= 64, "Invalid resource name")
            number(cap, f"budget.{unit}")
        canonical(contract)
        self.state_dir.mkdir(exist_ok=True)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS contract(id INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS budget(resource TEXT PRIMARY KEY,cap REAL NOT NULL,spent REAL NOT NULL DEFAULT 0,charged REAL NOT NULL DEFAULT 0,reserved REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,status TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS output_claims(path TEXT PRIMARY KEY,run_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts(run_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS exposures(id INTEGER PRIMARY KEY,run_id TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,body TEXT NOT NULL);
            """)
            for table in ("contract", "receipts", "exposures", "events"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END")
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT sha256 FROM contract WHERE id=1").fetchone()
            if old:
                require(old["sha256"] == digest(contract), "Contract is frozen; use a new project root")
            else:
                db.execute("INSERT INTO contract VALUES (1,?,?)", (digest(contract), canonical(contract)))
                db.executemany("INSERT INTO budget(resource,cap) VALUES (?,?)", list(budget.items()))
        return self.snapshot()

    @staticmethod
    def _command(argv):
        require(isinstance(argv, list) and argv and all(isinstance(a, str) and a and "\x00" not in a for a in argv), "Command must be a nonempty argv list")
        found = shutil.which(argv[0])
        require(found is not None and Path(found).is_file(), "Command executable unavailable")
        require(Path(found).stem.lower() not in {"cmd", "powershell", "pwsh", "sh", "bash", "zsh", "fish"}
                and Path(found).suffix.lower() not in {".bat", ".cmd", ".ps1"}, "Project commands cannot invoke a shell")
        return str(Path(found).resolve())

    def register(self, spec):
        require(isinstance(spec, dict) and type(spec.get("schema")) is int
                and spec["schema"] == 1, "Run manifest schema must be 1")
        require(set(spec) <= {"schema", "id", "arm", "control_id", "protocol", "argv", "outpaths", "resource_estimates", "timeout_seconds", "description"}, "Unknown manifest fields; handwritten verification is not accepted")
        run_id = spec.get("id", "")
        require(isinstance(run_id, str) and 1 <= len(run_id) <= 80 and all(c.isalnum() or c in "-_" for c in run_id), "Invalid run ID")
        require(spec.get("arm") in {"control", "treatment", "tool"}, "Invalid arm")
        require(spec.get("control_id") is None or isinstance(spec["control_id"], str), "Invalid control ID")
        require(spec["arm"] != "treatment" or spec.get("control_id"), "Treatment requires a control ID")
        timeout = number(spec.get("timeout_seconds"), "timeout_seconds", True)
        executor = self._command(spec.get("argv"))
        with self._db() as db:
            contract = self._contract(db)
            require(spec["argv"] in contract["allowed_commands"], "Command is not authorized")
            bindings, errors = self._bindings(contract)
            require(not errors, "; ".join(errors))
            estimates = spec.get("resource_estimates")
            require(isinstance(estimates, dict) and set(estimates) == set(contract["budget"]), "Resource estimates must match budget dimensions")
            estimates = {key: number(value, f"estimate.{key}") for key, value in estimates.items()}
            require(estimates["wall_seconds"] >= timeout, "Wall reservation must cover timeout")
            protocol_ref = spec.get("protocol")
            require(isinstance(protocol_ref, dict) and set(protocol_ref) == {"path", "sha256"}, "Protocol must bind a file and SHA256")
            require(any(b["role"] == "protocol" and b["path"] == protocol_ref["path"] and b["sha256"] == protocol_ref["sha256"] for b in contract["bindings"]), "Protocol is not bound by contract")
            protocol = load_json(self._path(protocol_ref["path"]))
            require(isinstance(protocol, dict) and all(k in protocol for k in IDENTITY), "Protocol identity fields required")
            require(not {"path", "sha256"} & set(protocol), "Protocol identity uses reserved fields")
            for role in ("code", "config", "data"):
                require(protocol[role + "_sha256"] == self._role_sha(contract, role), "Protocol identity conflicts with bindings")
            outpaths = spec.get("outpaths")
            require(isinstance(outpaths, list) and (outpaths or spec["arm"] == "tool"), "Expected output paths required")
            outputs = [self._path(p, True, contract) for p in outpaths]
            require(len(set(outputs)) == len(outputs) and all(not p.exists() for p in outputs), "Outputs must be unique and absent before registration")
            run = {"id": run_id, "run_id": run_id, "status": "RESERVED", "run_status": "RESERVED",
                   "manifest": spec, "manifest_sha256": digest(spec), "resource_estimates": estimates,
                   "protocol": {**protocol, **protocol_ref}, "executor": executor,
                   "executor_sha256": file_sha(executor), "attempt_id": None, "worker_pid": None,
                   "pid": None, "started_at": None, "finished_at": None, "observed_wall_seconds": 0.0,
                   "scheduler": None}
            db.execute("BEGIN IMMEDIATE")
            require(db.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone() is None, "Run ID already exists")
            if spec.get("control_id"):
                require(db.execute("SELECT 1 FROM runs WHERE id=?", (spec["control_id"],)).fetchone() is not None, "Unknown control ID")
            for resource, amount in estimates.items():
                row = db.execute("SELECT * FROM budget WHERE resource=?", (resource,)).fetchone()
                require(row["spent"] + row["charged"] + row["reserved"] + amount <= row["cap"] + 1e-9, f"Insufficient {resource} budget")
            claims = self._output_claims(db)
            for path in outputs:
                key = self._output_key(path)
                require(key not in claims, "Output is already claimed by another run")
                db.execute("INSERT INTO output_claims VALUES (?,?)", (key, run_id))
            for resource, amount in estimates.items():
                db.execute("UPDATE budget SET reserved=reserved+? WHERE resource=?", (amount, resource))
            db.execute("INSERT INTO runs VALUES (?,?,?)", (run_id, "RESERVED", canonical(run)))
        return run

    @staticmethod
    def _run(db, run_id):
        row = db.execute("SELECT body FROM runs WHERE id=?", (run_id,)).fetchone()
        require(row is not None, "Unknown run ID")
        run = json.loads(row["body"])
        require(digest(run["manifest"]) == run["manifest_sha256"], "Manifest integrity failure")
        return run

    @staticmethod
    def _save(db, run):
        run["run_status"] = "SUCCEEDED" if run["status"] == "COMPLETED" else run["status"]
        db.execute("UPDATE runs SET status=?,body=? WHERE id=?", (run["status"], canonical(run), run["id"]))

    def execute(self, run_id, background=False):
        require(isinstance(background, bool), "background must be Boolean")
        if background and os.name != "nt":
            raise NotImplementedError("Background execution requires Windows Task Scheduler")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            run = self._run(db, run_id)
            require(run["status"] == "RESERVED" and run["attempt_id"] is None, "Run already dispatched or started; recover never reruns it")
            self._check_start(db, run)
            run["attempt_id"] = uuid.uuid4().hex
            if background:
                run["scheduler"] = {"task_id": "RDS-Project-" + run["attempt_id"], "status": "REGISTERING"}
            else:
                # Keep the foreground controller identifiable before it claims
                # the worker, so recovery cannot close this startup window.
                run["worker_pid"] = os.getpid()
            self._save(db, run)
        if background:
            try:
                self._schedule(run)
            except Exception as exc:
                # A controller error is not proof that the scheduled worker did
                # not start. Never close an active worker's reservation here.
                return self._finish(run_id, run["attempt_id"], "FAILED", None, None, None,
                                    [f"Scheduler dispatch failed: {exc}; launch/costs may be unknown"], only_unstarted=True)
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self._run(db, run_id)
                if current["status"] == "RESERVED":
                    current["scheduler"]["status"] = "REGISTERED"
                self._save(db, current)
            return current
        return self._execute_claim(run_id, run["attempt_id"])

    def _execute_claim(self, run_id, attempt_id):
        attempt_start = time.monotonic()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            run = self._run(db, run_id)
            require(run["status"] == "RESERVED" and run["attempt_id"] == attempt_id, "Run cannot be started twice")
            self._check_start(db, run)
            run.update(status="RUNNING", worker_pid=os.getpid(), started_at=time.time())
            if run["scheduler"]:
                run["scheduler"]["status"] = "RUNNING"
            self._save(db, run)
            contract = self._contract(db)
        before, errors = self._bindings(contract)
        with self._db() as db:
            current = self._run(db, run_id)
            current["bindings_before"] = before
            self._save(db, current)
        try:
            if file_sha(run["executor"]) != run["executor_sha256"]:
                errors.append("Command executable changed")
            if any(self._path(p, True, contract).exists() for p in run["manifest"]["outpaths"]):
                errors.append("Output already exists before start")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
        work = self.artifact_dir / run_id
        require(work.resolve().is_relative_to(self.root), "Artifact directory escapes root")
        work.mkdir(parents=True, exist_ok=True)
        manifest_path = work / "manifest.json"
        manifest_path.write_text(canonical(run["manifest"]), encoding="utf-8")
        if errors:
            return self._finish(run_id, attempt_id, "FAILED", None, time.monotonic() - attempt_start, False, errors, before)
        for p in run["manifest"]["outpaths"]:
            self._path(p, True, contract).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("INSERT INTO exposures(run_id,body) VALUES (?,?)", (run_id, canonical({"run_id": run_id, "attempt_id": attempt_id, "at": time.time(), "kind": "declared_input_access", "data": [b for b in before if b["role"] == "data"], "eligibility_change": "none"})))
        start = time.monotonic()
        process = job = None
        started = False
        timeout = False
        exit_code = None
        status = "FAILED"
        try:
            with (work / "stdout.bin").open("xb") as out, (work / "stderr.bin").open("xb") as err:
                flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                argv = [run["executor"], *run["manifest"]["argv"][1:]]
                with self._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = self._run(db, run_id)
                    require(current["status"] == "RUNNING" and current["attempt_id"] == attempt_id
                            and current["pid"] is None, "Run cannot be started twice")
                    self._check_start(db, current)
                    process = subprocess.Popen(argv, cwd=self.root, shell=False, stdin=subprocess.DEVNULL,
                                               stdout=out, stderr=err, creationflags=flags, start_new_session=os.name != "nt")
                    started = True
                    job = _Job(process)
                    current["pid"] = process.pid
                    self._save(db, current)
                while process.poll() is None:
                    elapsed = time.monotonic() - start
                    with self._db() as db:
                        current = self._run(db, run_id)
                        current["observed_wall_seconds"] = elapsed
                        self._save(db, current)
                    if elapsed >= run["manifest"]["timeout_seconds"]:
                        timeout = True
                        job.stop()
                        break
                    time.sleep(min(0.05, max(0.001, run["manifest"]["timeout_seconds"] - elapsed)))
                exit_code = process.wait()
                status = "COMPLETED" if exit_code == 0 and not timeout else "FAILED"
                if timeout:
                    errors.append("Process timeout")
                elif exit_code != 0:
                    errors.append(f"Nonzero process exit: {exit_code}")
        except BaseException as exc:
            if process is not None:
                if job:
                    job.stop()
                elif process.poll() is None:
                    process.kill()
                exit_code = process.wait()
            status = "INTERRUPTED" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "FAILED"
            errors.append(f"Execution interrupted: {type(exc).__name__}: {exc}")
        finally:
            if job:
                job.close()
        return self._finish(run_id, attempt_id, status, exit_code, time.monotonic() - attempt_start,
                            started, errors, before, timeout)

    def _finish(self, run_id, attempt_id, status, exit_code, wall, started, errors, before=None, timeout=False, only_unstarted=False, recovering=False):
        with self._db() as db:
            run = self._run(db, run_id)
            contract = self._contract(db)
        require(run["attempt_id"] == attempt_id, "Attempt mismatch")
        after, binding_errors = self._bindings(contract)
        before = before if before is not None else run.get("bindings_before")
        errors = list(errors) + binding_errors
        try:
            require(file_sha(run["executor"]) == run["executor_sha256"], "Command executable changed")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
        artifacts = []
        work = self.artifact_dir / run_id
        for name in ("manifest.json", "stdout.bin", "stderr.bin", "scheduler.stdout.bin", "scheduler.stderr.bin", "worker.log"):
            path = work / name
            if path.is_file():
                artifacts.append({"path": path.relative_to(self.root).as_posix(), "sha256": file_sha(path), "size": path.stat().st_size, "kind": name})
        if (work / "manifest.json").is_file() and file_sha(work / "manifest.json") != run["manifest_sha256"]:
            errors.append("Recorded manifest artifact changed")
        if started is not False:
            for relative in run["manifest"]["outpaths"]:
                try:
                    path = self._path(relative, True, contract)
                    require(path.is_file(), f"Missing output: {relative}")
                    artifacts.append({"path": relative, "sha256": file_sha(path), "size": path.stat().st_size, "kind": "project_output"})
                except (OSError, ValueError) as exc:
                    errors.append(str(exc))
        if errors and status == "COMPLETED":
            status = "FAILED"
        resources = {}
        for key, estimate in run["resource_estimates"].items():
            measured = wall if key == "wall_seconds" else None
            resources[key] = {"unit": "seconds" if key.endswith("_seconds") else key,
                              "measured": measured, "unknown": measured is None,
                              "charged_estimate": estimate if measured is None else 0.0}
            if key == "wall_seconds" and wall is None:
                resources[key]["observed_lower_bound"] = run["observed_wall_seconds"]
        receipt = {"schema": 1, "run_id": run_id, "attempt_id": attempt_id,
                   "run_status": "SUCCEEDED" if status == "COMPLETED" else status, "process_status": status,
                   "arm": run["manifest"]["arm"], "control_id": run["manifest"].get("control_id"),
                   "protocol": run["protocol"], "manifest_sha256": run["manifest_sha256"],
                   "bindings_before": before, "bindings_after": after,
                   "argv": run["manifest"]["argv"], "cwd": str(self.root),
                   "executor_sha256": run["executor_sha256"], "worker_pid": run["worker_pid"],
                   "pid": run["pid"], "started_at": run["started_at"], "ended_at": time.time(),
                   "exit_code": exit_code, "timeout": timeout, "process_started": started,
                   "resources": resources, "artifacts": artifacts,
                   "assessment": {"task_gain": "UNKNOWN", "mechanism": "UNKNOWN"},
                   # RDS attempt lifecycle, not a query of the OS task's current state.
                   "errors": errors, "scheduler": ({**run["scheduler"], "status": status}
                                                     if run["scheduler"] else None)}
        receipt["sha256"] = digest(receipt)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT body FROM receipts WHERE run_id=?", (run_id,)).fetchone()
            if old:
                return json.loads(old["body"])
            current = self._run(db, run_id)
            require(current["attempt_id"] == attempt_id and current["status"] not in TERMINAL, "Run already terminal")
            # Evidence collection can race with startup or progress. Recheck
            # the latest identity while holding the settlement write lock.
            if recovering and (current != run or _alive(current["worker_pid"]) is not False
                               or _alive(current["pid"]) is not False):
                return {**current, "recovery": "Run changed or process may still be active; no rerun or termination"}
            if only_unstarted and current["status"] == "RUNNING":
                return {**current, "dispatch_error": errors[0]}
            for key, resource in resources.items():
                db.execute("UPDATE budget SET reserved=reserved-?,spent=spent+?,charged=charged+? WHERE resource=?",
                           (run["resource_estimates"][key], resource["measured"] or 0.0, resource["charged_estimate"], key))
            current.update(status=status, finished_at=receipt["ended_at"], scheduler=receipt["scheduler"])
            self._save(db, current)
            db.execute("INSERT INTO receipts VALUES (?,?,?)", (run_id, receipt["sha256"], canonical(receipt)))
            db.execute("INSERT INTO events(body) VALUES (?)", (canonical({"kind": "ATTEMPT_FINISHED", "run_id": run_id, "sha256": receipt["sha256"]}),))
        return receipt

    def recover(self, run_id):
        with self._db(True) as db:
            run = self._run(db, run_id)
            old = db.execute("SELECT body FROM receipts WHERE run_id=?", (run_id,)).fetchone()
            if old:
                return json.loads(old["body"])
        if run["attempt_id"] is None:
            return {**run, "recovery": "Unstarted reservation; no process to restart"}
        if run["status"] == "RESERVED" and run["scheduler"]:
            return {**run, "recovery": "Dispatched scheduler task; do not start another process"}
        if _alive(run["worker_pid"]) is not False or _alive(run["pid"]) is not False:
            return {**run, "recovery": "Process may still be active; no rerun or termination"}
        return self._finish(run_id, run["attempt_id"], "INTERRUPTED", None, None, None,
                            ["Worker and process unavailable; final costs and exit status unknown; no automatic rerun"], recovering=True)

    def snapshot(self, check_bindings=False):
        require(isinstance(check_bindings, bool), "check_bindings must be Boolean")
        with self._db(True) as db:
            db.execute("BEGIN")
            contract = self._contract(db)
            budget = {}
            for row in db.execute("SELECT * FROM budget ORDER BY resource"):
                budget[row["resource"]] = {"cap": row["cap"], "spent_measured": row["spent"],
                                           "charged_estimate": row["charged"], "reserved": row["reserved"],
                                           "remaining": row["cap"] - row["spent"] - row["charged"] - row["reserved"],
                                           "unit": "seconds" if row["resource"].endswith("_seconds") else row["resource"]}
            snapshot = {"schema": 1, "contract": contract, "contract_sha256": digest(contract), "budget": budget,
                    "runs": [json.loads(r["body"]) for r in db.execute("SELECT body FROM runs ORDER BY id")],
                    "exposures": [json.loads(r["body"]) for r in db.execute("SELECT body FROM exposures ORDER BY id")],
                    "receipts": [json.loads(r["body"]) for r in db.execute("SELECT body FROM receipts ORDER BY run_id")]}
        if check_bindings:
            found, errors = self._bindings(contract)
            snapshot["binding_check"] = {"files": found, "errors": errors}
        return snapshot

    def _schedule(self, run):
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        require(pythonw.is_file(), "Hidden scheduler execution requires pythonw.exe")
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        require(powershell is not None, "PowerShell unavailable for Task Scheduler")
        worker = Path(__file__).with_name("rds_project_worker.py").resolve()
        argv = [str(worker), "--root", str(self.root), "--run-id", run["id"], "--attempt-id", run["attempt_id"]]
        quote = lambda s: "'" + str(s).replace("'", "''") + "'"
        task_id = run["scheduler"]["task_id"]
        script = ("$ErrorActionPreference='Stop'; "
                  f"$action=New-ScheduledTaskAction -Execute {quote(pythonw)} -Argument {quote(subprocess.list2cmdline(argv))} -WorkingDirectory {quote(self.root)}; "
                  "$settings=New-ScheduledTaskSettingsSet -Hidden -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 30); "
                  f"Register-ScheduledTask -TaskName {quote(task_id)} -Action $action -Settings $settings -Description 'RDS owned bounded project attempt' | Out-Null; "
                  f"Start-ScheduledTask -TaskName {quote(task_id)}")
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                cwd=self.root, shell=False, capture_output=True, timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        log = self.artifact_dir / run["id"]
        require(log.resolve().is_relative_to(self.root), "Scheduler log escapes root")
        log.mkdir(parents=True, exist_ok=True)
        (log / "scheduler.stdout.bin").write_bytes(result.stdout)
        (log / "scheduler.stderr.bin").write_bytes(result.stderr)
        require(result.returncode == 0, f"Task Scheduler exit {result.returncode}; see recorded scheduler logs")

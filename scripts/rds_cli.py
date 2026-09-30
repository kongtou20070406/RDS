#!/usr/bin/env python3
"""RDS L3 local reference kernel; this is NOT an OS security boundary.

SQLite transactions arbitrate admission, resource allocations, and receipts.
The fixed runner executes rational ASTs with a paired MSE evaluator. External
JSON cannot certify manipulation, metric gain, final authorization or success.
"""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import uuid

from rds_probe import parse_source, rational, read_rows, formal_requirement

VERSION = "5.2.0"
RESOURCES = {"runtime_ms", "runs"}
SELF_SIGNED = {"manipulation_verified", "falsifier_triggered", "primary_metric_gain",
               "final_run_authorized", "matched_recipe", "matched_compute"}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def digest(value):
    raw = value if isinstance(value, bytes) else canonical(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError("Non-finite JSON value: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def load_spec(path):
    return strict_json(Path(path).read_text(encoding="utf-8-sig"))


def read_bounded(path, cap):
    with open(path, "rb") as handle:
        raw = handle.read(cap + 1)
    require(len(raw) <= cap, "Artifact exceeds the reference runner limit")
    return raw


def reject_self_signatures(obj):
    if isinstance(obj, dict):
        require(not SELF_SIGNED.intersection(obj), "Self-signed verification fields are forbidden")
        for value in obj.values():
            reject_self_signatures(value)
    elif isinstance(obj, list):
        for value in obj:
            reject_self_signatures(value)


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value),
            "Invalid identity (up to 80 ASCII letters, numbers, _, . or -)")
    return value


def resource_vector(value, positive=False):
    require(isinstance(value, dict) and set(value) == RESOURCES,
            "Budget must explicitly contain runtime_ms and runs")
    require(all(type(v) is int and 0 <= v <= 10**12 for v in value.values()),
            "Resource amounts must be nonnegative bounded integers, never bool/float")
    if positive:
        require(value["runtime_ms"] > 0 and value["runs"] == 1,
                "A plan reserves positive runtime_ms and exactly one run")
    return value


def engine_id():
    # Ordinary AST admission/execution must work without importing a solver.
    try:
        sympy_version = importlib.metadata.version("sympy")
    except importlib.metadata.PackageNotFoundError:
        sympy_version = None
    here = Path(__file__).resolve().parent
    return digest({"cli": digest((here / "rds_cli.py").read_bytes()),
                   "probe": digest((here / "rds_probe.py").read_bytes()),
                   "python": sys.version, "sympy": sympy_version})


def formal_gate(hypothesis, source):
    if formal_requirement(hypothesis) is None:
        return {"status": "PASS", "assurance": "AST_ONLY", "backend": "ast"}
    payload = {"operation": "admission", "hypothesis": hypothesis, "source": source}
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("rds_probe.py"))],
            input=canonical(payload).encode("utf-8"), capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        raise ValueError("Formal gate UNKNOWN: verifier exceeded 15 seconds") from None
    require(completed.returncode == 0, "Formal gate failed: " + completed.stdout.decode("utf-8", errors="replace"))
    probe = strict_json(completed.stdout.decode("utf-8"))
    require(probe.get("status") == "PASS", "Formal gate " + probe.get("status", "UNKNOWN") + ": " + probe.get("reason", "no boundary crossing"))
    return probe


class RDSState:
    def __init__(self, root_dir):
        self.root = Path(root_dir).resolve()
        self.directory = self.root / ".rds"
        self.db_path = self.directory / "state.sqlite3"

    def connect(self, create=False):
        if create:
            require(not (self.directory / "contract.json").exists(),
                    "Legacy v5 JSON state found; preserve it and initialize a new root")
            self.directory.mkdir(parents=True, exist_ok=True)
        require(create or self.db_path.exists(), "RDS is not initialized")
        db = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        if create:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts (sha TEXT PRIMARY KEY, raw BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts (run_id TEXT PRIMARY KEY, sha TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS receipt_no_update BEFORE UPDATE ON receipts
                BEGIN SELECT RAISE(ABORT, 'receipts are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS receipt_no_delete BEFORE DELETE ON receipts
                BEGIN SELECT RAISE(ABORT, 'receipts are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS event_no_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS event_no_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS artifact_no_update BEFORE UPDATE ON artifacts
                BEGIN SELECT RAISE(ABORT, 'artifacts are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS artifact_no_delete BEFORE DELETE ON artifacts
                BEGIN SELECT RAISE(ABORT, 'artifacts are append-only'); END;
            """)
        return db

    @contextmanager
    def transaction(self, create=False):
        db = self.connect(create)
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
            state = strict_json(row[0]) if row else {}
            if state:
                require(state["version"] in {VERSION, "5.1.0"}, "Incompatible state version")
                require(digest(state["contract"]) == state["contract_sha256"], "Contract integrity failure")
                if "branches" not in state:
                    state["branches"] = {
                        "main": {
                            "id": "main", "parent_id": None, "orthogonal_dimension": "baseline",
                            "rationale": "Initial primary exploration branch", "status": "ACTIVE",
                            "stagnation_count": 0, "created_ns": 0,
                            "hypotheses": list(state.get("hypotheses", {}).keys())
                        }
                    }
                if "active_branch" not in state:
                    state["active_branch"] = "main"
                if "baseline_cache" not in state:
                    state["baseline_cache"] = {}
            yield db, state
            if state:
                self.invariants(state)
                db.execute("INSERT INTO state VALUES (1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                           (canonical(state),))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def invariants(state):
        budget = state["budget"]
        for key in RESOURCES:
            require(budget["spent"][key] >= 0 and budget["reserved"][key] >= 0, "Negative ledger balance")
            require(budget["spent"][key] + budget["reserved"][key] <= budget["limits"][key],
                    "Budget invariant violated")
            live = sum(p["spec"]["resources"][key] for p in state["plans"].values()
                       if p["run_status"] == "RESERVED")
            require(live == budget["reserved"][key], "Reservation ledger does not match plans")

    @staticmethod
    def event(db, kind, **fields):
        body = {"kind": kind, "time_ns": time.time_ns(), **fields}
        cur = db.execute("INSERT INTO events(body) VALUES (?)", (canonical(body),))
        return cur.lastrowid

    @staticmethod
    def artifact(db, raw):
        sha = digest(raw)
        db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?)", (sha, raw))
        return sha


def cmd_init(args, rds):
    contract = load_spec(args.contract)
    reject_self_signatures(contract)
    for key in ("project_id", "claim", "primary_metric", "budget", "splits"):
        require(key in contract, "Missing contract field: " + key)
    identity(contract["project_id"])
    metric = contract["primary_metric"]
    require(metric["name"] == "mse" and metric["direction"] == "min",
            "The reference runner supports only paired MSE minimization")
    require(rational(metric["min_useful_delta"]) > 0, "Precommit a positive minimum useful gain")
    require(contract.get("evaluation_scope") in {"finite_locked_dataset", "population"},
            "Declare evaluation_scope: finite_locked_dataset or population")
    limits = resource_vector(contract["budget"]["limits"])
    floor = resource_vector(contract["budget"]["confirmation_floor"])
    require(all(floor[k] <= limits[k] for k in RESOURCES), "Confirmation reserve exceeds cap")
    require(contract["splits"], "Register at least one data partition")
    registry = {}
    for sid, split in contract["splits"].items():
        identity(sid)
        require(split["role"] in {"train", "development", "confirmation"}, "Unknown split role")
        identity(split["cohort"])
        path = Path(split["path"])
        path = (rds.root / path).resolve() if not path.is_absolute() else path.resolve()
        raw = read_bounded(path, 2_000_000)
        rows = read_rows(raw.decode("utf-8-sig"))
        require(split.get("prior_exposure") in ("none_declared", "unknown", "exposed"),
                "Custodian must declare prior_exposure; unknown is ineligible for confirmation")
        registry[sid] = {**split, "path": str(path), "sha256": digest(raw),
                         "sample_ids": [digest(r[0]) for r in rows]}
    contract["splits"] = registry
    baseline = Path(contract["baseline_source"])
    baseline = (rds.root / baseline).resolve() if not baseline.is_absolute() else baseline.resolve()
    baseline_raw = read_bounded(baseline, 8192)
    baseline_ast = parse_source(baseline_raw.decode("utf-8-sig"))["control"]
    contract["baseline_control_ast"] = ast.dump(baseline_ast)
    contract["baseline_source_sha256"] = digest(baseline_raw)
    with rds.transaction(create=True) as (db, state):
        require(not state, "Already initialized; init never erases history")
        state.update(version=VERSION, contract=contract, contract_sha256=digest(contract),
                     engine_sha256=engine_id(), hypotheses={}, plans={}, exposures=[], final_plan=None,
                     active_branch="main",
                     branches={
                         "main": {
                             "id": "main", "parent_id": None, "orthogonal_dimension": "baseline",
                             "rationale": "Initial primary exploration branch", "status": "ACTIVE",
                             "stagnation_count": 0, "created_ns": time.time_ns(),
                             "hypotheses": []
                         }
                     },
                     baseline_cache={},
                     budget={"limits": limits, "confirmation_floor": floor,
                             "spent": {k: 0 for k in RESOURCES}, "reserved": {k: 0 for k in RESOURCES}})
        rds.event(db, "CONTRACT_LOCKED", contract_sha256=state["contract_sha256"])
    return {"version": VERSION, "contract_sha256": digest(contract)}


def cmd_hypothesis(args, rds):
    spec = load_spec(args.spec)
    reject_self_signatures(spec)
    hid = identity(spec["id"])
    require(spec.get("proposition") and spec.get("falsifier"), "Precommit proposition and falsifier")
    require(spec.get("type") in {"task_gain", "mechanism", "search_policy"}, "Unknown hypothesis type")
    formal_requirement(spec)
    with rds.transaction() as (db, state):
        require(hid not in state["hypotheses"], "Hypothesis already locked; create a revision ID")
        state["hypotheses"][hid] = {"spec": spec, "sha256": digest(spec), "task_gain": "UNTESTED",
                                   "mechanism": "UNTESTED", "search_policy": "UNTESTED", "assessments": []}
        active_b = state.get("active_branch", "main")
        if active_b in state.get("branches", {}):
            if hid not in state["branches"][active_b]["hypotheses"]:
                state["branches"][active_b]["hypotheses"].append(hid)
        rds.event(db, "HYPOTHESIS_LOCKED", hypothesis_id=hid, sha256=digest(spec), branch_id=active_b)
    return {"hypothesis_id": hid, "branch_id": active_b}


def related_splits(contract, split_id):
    """Transitive alias/overlap closure. Cohorts mean shared information lineage."""
    registry, related = contract["splits"], {split_id}
    while True:
        additions = {sid for sid, candidate in registry.items() for old in related
                     if candidate["cohort"] == registry[old]["cohort"]
                     or candidate["sha256"] == registry[old]["sha256"]
                     or set(candidate["sample_ids"]).intersection(registry[old]["sample_ids"])}
        if additions <= related:
            return related
        related |= additions


def clean_confirmation(state, split_id, own_run=None):
    related = related_splits(state["contract"], split_id)
    if any(state["contract"]["splits"][sid]["role"] != "confirmation"
           or state["contract"]["splits"][sid]["prior_exposure"] != "none_declared" for sid in related):
        return False
    return not any(e["split_id"] in related and not
                   (e["purpose"] == "final_evaluate" and e.get("run_id") == own_run)
                   for e in state["exposures"])


def validate_plan(plan, state, rds):
    reject_self_signatures(plan)
    require(set(plan) == {"id", "hypothesis_id", "split_id", "purpose", "source", "resources"},
            "Plan fields: id, hypothesis_id, split_id, purpose, source, resources; no imported permits")
    identity(plan["id"])
    require(plan["hypothesis_id"] in state["hypotheses"], "Unknown hypothesis")
    require(plan["split_id"] in state["contract"]["splits"], "Unknown split")
    require(plan["purpose"] in {"explore", "confirm"}, "Unknown purpose")
    resources = resource_vector(plan["resources"], positive=True)
    require(resources["runtime_ms"] <= 60000, "Reference runner has a 60-second maximum allocation")
    require(state["final_plan"] is None, "Selection is frozen by a final plan")
    split = state["contract"]["splits"][plan["split_id"]]
    if plan["purpose"] == "confirm":
        require(split["role"] == "confirmation", "Confirmation requires a confirmation partition")
        require(clean_confirmation(state, plan["split_id"]), "Confirmation lineage already exposed")
        require(not any(p["run_status"] in {"RESERVED", "RUNNING"} for p in state["plans"].values()),
                "Finish or cancel active exploration before freezing final selection")
    else:
        require(split["role"] == "development", "Exploration requires development data")
    budget = state["budget"]
    for key in RESOURCES:
        protected = budget["confirmation_floor"][key] if plan["purpose"] == "explore" else 0
        require(budget["spent"][key] + budget["reserved"][key] + resources[key] + protected
                <= budget["limits"][key], "Budget unavailable or protected for confirmation: " + key)
    path = Path(plan["source"])
    path = (rds.root / path).resolve() if not path.is_absolute() else path.resolve()
    source = read_bounded(path, 8192)
    functions = parse_source(source.decode("utf-8-sig"))
    require(ast.dump(functions["control"]) == state["contract"]["baseline_control_ast"],
            "Baseline computation changed from the locked contract")
    require(engine_id() == state["engine_sha256"], "Verifier version changed; a new contract is required")
    probe = formal_gate(state["hypotheses"][plan["hypothesis_id"]]["spec"], source.decode("utf-8-sig"))
    return {"source_path": str(path), "source_sha256": digest(source), "source": source.decode("utf-8-sig"),
            "admission_probe": probe,
            "engine_sha256": state["engine_sha256"], "contract_sha256": state["contract_sha256"],
            "hypothesis_sha256": state["hypotheses"][plan["hypothesis_id"]]["sha256"],
            "dataset_sha256": split["sha256"], "plan_sha256": digest(plan)}


def cmd_plan(args, rds, advisory=False):
    plan = load_spec(args.plan if advisory else args.spec)
    with rds.transaction() as (db, state):
        existing = state["plans"].get(plan.get("id"))
        if existing:
            require(digest(plan) == existing["binding"]["plan_sha256"], "Plan ID reused with changed contents")
            return {"plan_id": plan["id"], "run_status": existing["run_status"], "idempotent": True}
        binding = validate_plan(plan, state, rds)
        if advisory:
            return {"status": "ADMISSIBLE_NOW", "reserved": False,
                    "probe": binding["admission_probe"],
                    "note": "Admission is rechecked atomically by plan create"}
        state["plans"][plan["id"]] = {"spec": plan, "binding": binding, "run_status": "RESERVED",
                                       "run_id": "RUN-" + uuid.uuid4().hex, "assessment": None}
        for key, value in plan["resources"].items():
            state["budget"]["reserved"][key] += value
        if plan["purpose"] == "confirm":
            state["final_plan"] = plan["id"]
        rds.artifact(db, binding["source"].encode("utf-8"))
        rds.event(db, "PLAN_RESERVED", plan_id=plan["id"], binding=binding, resources=plan["resources"])
    return {"plan_id": plan["id"], "run_status": "RESERVED", "binding": binding}


def cmd_cancel(args, rds):
    with rds.transaction() as (db, state):
        plan = state["plans"][args.id]
        if plan["run_status"] == "CANCELLED":
            return {"run_status": "CANCELLED", "idempotent": True}
        require(plan["run_status"] == "RESERVED", "Only an unstarted reservation can be released")
        for key, value in plan["spec"]["resources"].items():
            state["budget"]["reserved"][key] -= value
        plan["run_status"] = "CANCELLED"
        if state["final_plan"] == args.id:
            state["final_plan"] = None
        rds.event(db, "PLAN_CANCELLED", plan_id=args.id)
    return {"run_status": "CANCELLED"}


def cmd_expose(args, rds):
    with rds.transaction() as (db, state):
        require(args.split in state["contract"]["splits"], "Unknown split")
        exposure = {"split_id": args.split, "purpose": args.purpose, "actor": args.actor,
                    "reason": args.reason, "time_ns": time.time_ns()}
        exposure["seq"] = rds.event(db, "DATA_EXPOSURE", **exposure)
        state["exposures"].append(exposure)
        affected = related_splits(state["contract"], args.split)
        for plan in state["plans"].values():
            if plan["spec"]["purpose"] == "confirm" and plan["spec"]["split_id"] in affected:
                if plan["assessment"] and plan["assessment"]["task_gain"] in {"CONFIRMED", "REFUTED"}:
                    state["hypotheses"][plan["spec"]["hypothesis_id"]]["task_gain"] = "NEEDS_REVIEW"
                    rds.event(db, "ASSESSMENT_INVALIDATED", run_id=plan["run_id"], cause=exposure["seq"])
    return {"exposure": exposure}


def cmd_run(args, rds):
    with rds.transaction() as (db, state):
        plan = state["plans"][args.id]
        if plan["run_status"] != "RESERVED":
            return {"run_id": plan["run_id"], "run_status": plan["run_status"], "idempotent": True}
        binding, spec = plan["binding"], plan["spec"]
        require(engine_id() == binding["engine_sha256"], "Verifier changed after admission")
        require(digest(read_bounded(binding["source_path"], 8192)) == binding["source_sha256"],
                "Source changed after plan lock")
        require(digest(spec) == binding["plan_sha256"], "Plan integrity failure")
        require(state["hypotheses"][spec["hypothesis_id"]]["sha256"] == binding["hypothesis_sha256"],
                "Hypothesis binding failure")
        if spec["purpose"] == "confirm":
            require(clean_confirmation(state, spec["split_id"]), "Confirmation contaminated after admission")
        # Charge once before execution. No refund after start or a lost runner.
        for key, value in spec["resources"].items():
            state["budget"]["reserved"][key] -= value
            state["budget"]["spent"][key] += value
        plan["run_status"] = "RUNNING"
        plan["started_ns"] = time.time_ns()
        plan["lease_expires_ns"] = plan["started_ns"] + (spec["resources"]["runtime_ms"] + 5000) * 1_000_000
        exposure = {"split_id": spec["split_id"], "purpose": "final_evaluate" if spec["purpose"] == "confirm"
                    else "development_evaluate", "run_id": plan["run_id"], "actor": "reference_runner",
                    "time_ns": time.time_ns()}
        exposure["seq"] = rds.event(db, "DATA_ACCESS_COMMITTED", **exposure)
        state["exposures"].append(exposure)
        dataset_path = state["contract"]["splits"][spec["split_id"]]["path"]
        hypothesis = state["hypotheses"][spec["hypothesis_id"]]["spec"]
        run_id = plan["run_id"]
        baseline_key = digest({
            "control_ast": state["contract"]["baseline_control_ast"],
            "dataset_sha256": binding["dataset_sha256"]
        })
        cached_control = state.get("baseline_cache", {}).get(baseline_key, {}).get("observations")
    started = time.monotonic_ns()
    data_raw, stdout, stderr, result = b"", b"", b"", None
    returncode, status = None, "FAILED"
    try:
        data_raw = read_bounded(dataset_path, 2_000_000)
        require(digest(data_raw) == binding["dataset_sha256"], "Dataset changed after contract lock")
        payload = {"source": binding["source"], "data": data_raw.decode("utf-8-sig"), "hypothesis": hypothesis}
        if cached_control:
            payload["cached_control"] = cached_control
        worker = Path(__file__).resolve().with_name("rds_probe.py")
        completed = subprocess.run([sys.executable, "-I", str(worker)],
                                   input=canonical(payload).encode("utf-8"), capture_output=True,
                                   timeout=spec["resources"]["runtime_ms"] / 1000, shell=False)
        stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
        if returncode == 0:
            result = strict_json(stdout.decode("utf-8"))
            status = "SUCCEEDED"
    except subprocess.TimeoutExpired as exc:
        status, stdout, stderr = "TIMED_OUT", exc.stdout or b"", exc.stderr or b""
    except (OSError, ValueError, UnicodeError) as exc:
        stderr = str(exc).encode("utf-8")
    receipt = {"run_id": run_id, "plan_id": spec["id"], "binding": binding, "run_status": status,
               "returncode": returncode, "elapsed_ms": (time.monotonic_ns() - started) // 1_000_000,
               "charged_allocation": spec["resources"], "result": result,
               "baseline_key": baseline_key, "control_reused": bool(cached_control)}
    with rds.transaction() as (db, state):
        live = state["plans"][args.id]
        if live["run_status"] != "RUNNING":
            return {"run_status": live["run_status"], "late_result_discarded": True}
        receipt["artifacts"] = {"data": rds.artifact(db, data_raw), "stdout": rds.artifact(db, stdout),
                                "stderr": rds.artifact(db, stderr)}
        if status == "SUCCEEDED" and result and not cached_control:
            if "baseline_cache" not in state:
                state["baseline_cache"] = {}
            control_map = {r["sample_id"]: {"control": r["control"], "control_loss": r["control_loss"]}
                           for r in result.get("observations", [])}
            state["baseline_cache"][baseline_key] = {
                "control_mean": result.get("control_mean"),
                "observations": control_map,
                "first_run_id": run_id
            }
            rds.event(db, "BASELINE_CACHED", baseline_key=baseline_key, run_id=run_id)
        receipt["sha256"] = digest(receipt)
        db.execute("INSERT INTO receipts VALUES (?,?,?)", (run_id, receipt["sha256"], canonical(receipt)))
        live["run_status"] = status
        rds.event(db, "RUN_FINISHED", run_id=run_id, run_status=status, receipt_sha256=receipt["sha256"])
    return {"run_id": run_id, "run_status": status, "receipt_sha256": receipt["sha256"],
            "control_reused": bool(cached_control)}


def cmd_recover(args, rds):
    with rds.transaction() as (db, state):
        plan = state["plans"][args.id]
        require(plan["run_status"] == "RUNNING", "Only RUNNING plans require reconciliation")
        require(time.time_ns() > plan["lease_expires_ns"], "Execution lease has not expired")
        plan["run_status"] = "RECOVERY_REQUIRED"
        rds.event(db, "RECOVERY_REQUIRED", run_id=plan["run_id"],
                  reason="No terminal receipt; allocation remains charged, no automatic rerun")
    return {"run_status": "RECOVERY_REQUIRED", "budget_refunded": False}


def merge_axis(old, new):
    if old in {"NEEDS_REVIEW", "DISPUTED"}:
        return old
    if {old, new} in ({"CONFIRMED", "REFUTED"}, {"SUPPORTED", "REFUTED"}):
        return "DISPUTED"
    rank = {"UNTESTED": 0, "NOT_TESTED": 1, "INCONCLUSIVE": 2, "EXPLORATORY": 3,
            "SUPPORTED": 4, "CONFIRMED": 4, "REFUTED": 4}
    return new if rank[new] >= rank[old] else old


def assess(result, contract, purpose, clean, formal):
    gain = rational(result["gain"])
    useful = gain > rational(contract["primary_metric"]["min_useful_delta"])
    final = purpose == "confirm" and clean and contract["evaluation_scope"] == "finite_locked_dataset"
    task = ("CONFIRMED" if useful else "REFUTED") if final else ("EXPLORATORY" if useful else "INCONCLUSIVE")
    probe, mechanism = result["probe"], "UNTESTED"
    if formal:
        mechanism = "NOT_TESTED" if probe["status"] == "FAIL" else "INCONCLUSIVE"
        # Passing manipulation never supports causality. This adapter can refute
        # ONLY its typed necessity claim with an executed exact counterexample.
        if probe["status"] == "PASS" and probe["necessity_counterexamples"]:
            mechanism = "REFUTED"
    return {"task_gain": task, "mechanism": mechanism, "search_policy": "UNTESTED",
            "scope": contract["evaluation_scope"], "gain": result["gain"], "manipulation": probe["status"],
            "note": "Finite benchmark comparison only; no population inference or causal support"}


def cmd_decide(args, rds):
    with rds.transaction() as (db, state):
        require(engine_id() == state["engine_sha256"], "Verifier changed; old receipts require versioned review")
        matches = [p for p in state["plans"].values() if p["run_id"] == args.run]
        require(len(matches) == 1, "Unknown run receipt")
        plan = matches[0]
        row = db.execute("SELECT body FROM receipts WHERE run_id=?", (args.run,)).fetchone()
        require(row is not None, "A runner-generated receipt is required")
        receipt = strict_json(row[0])
        sha = receipt.pop("sha256")
        require(digest(receipt) == sha, "Receipt integrity failure")
        require(receipt["binding"] == plan["binding"], "Receipt/plan binding mismatch")
        require(receipt["run_id"] == args.run and receipt["plan_id"] == plan["spec"]["id"],
                "Receipt identity mismatch")
        for artifact_sha in receipt["artifacts"].values():
            artifact = db.execute("SELECT raw FROM artifacts WHERE sha=?", (artifact_sha,)).fetchone()
            require(artifact is not None and digest(artifact[0]) == artifact_sha, "Raw artifact integrity failure")
        require(receipt["run_status"] == "SUCCEEDED" and plan["run_status"] == "SUCCEEDED",
                "Execution failure is not scientific refutation")
        if plan["assessment"] is not None:
            active_b = state.get("active_branch", "main")
            branch_info = state.get("branches", {}).get(active_b, {})
            stagnation_report = {
                "branch_id": active_b,
                "stagnation_count": branch_info.get("stagnation_count", 0),
                "stagnated": branch_info.get("stagnation_count", 0) >= 3,
                "threshold": 3,
                "recommendation": "IDEMPOTENT_DECISION"
            }
            return {"assessment": plan["assessment"], "idempotent": True,
                    "stagnation": stagnation_report,
                    "current_task_gain": state["hypotheses"][plan["spec"]["hypothesis_id"]]["task_gain"]}
        spec = plan["spec"]
        node = state["hypotheses"][spec["hypothesis_id"]]
        clean = clean_confirmation(state, spec["split_id"], args.run)
        outcome = assess(receipt["result"], state["contract"], spec["purpose"], clean, node["spec"].get("formal"))
        plan["assessment"] = {**outcome, "receipt_sha256": sha, "run_id": args.run,
                              "hypothesis_sha256": node["sha256"], "clean_confirmation": clean}
        node["assessments"].append(plan["assessment"])
        for axis in ("task_gain", "mechanism"):
            node[axis] = merge_axis(node[axis], outcome[axis])
        rds.event(db, "ASSESSMENT_RECORDED", **plan["assessment"])

        # Policy RSI: Stagnation tracking (FML-Bench v2)
        active_b = state.get("active_branch", "main")
        branch_info = state.get("branches", {}).get(active_b)
        stagnation_report = None
        if branch_info is not None:
            gain_val = rational(receipt["result"]["gain"])
            min_delta = rational(state["contract"]["primary_metric"]["min_useful_delta"])
            useful = gain_val > min_delta
            if useful and outcome["task_gain"] in {"CONFIRMED", "EXPLORATORY"}:
                branch_info["stagnation_count"] = 0
                branch_info["status"] = "ACTIVE"
            else:
                branch_info["stagnation_count"] += 1
                if branch_info["stagnation_count"] >= 3:
                    branch_info["status"] = "STAGNATING"
                    rds.event(db, "STAGNATION_DETECTED", branch_id=active_b,
                              stagnation_count=branch_info["stagnation_count"])
            stagnated = branch_info["stagnation_count"] >= 3
            stagnation_report = {
                "branch_id": active_b,
                "stagnation_count": branch_info["stagnation_count"],
                "stagnated": stagnated,
                "threshold": 3,
                "recommendation": (
                    "STAGNATION_DETECTED: Consecutive 3 runs without useful gain. "
                    "Switch from greedy parameter search to orthogonal branching (FML-Bench v2) via 'branch fork'."
                    if stagnated else "CONTINUE_GREEDY"
                )
            }
    return {"assessment": plan["assessment"], "stagnation": stagnation_report}


def cmd_status(args, rds):
    with rds.transaction() as (db, state):
        result = dict(state)
        result["receipts"] = [strict_json(r[0]) for r in db.execute("SELECT body FROM receipts ORDER BY run_id")]
        result["event_count"] = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return result


def cmd_branch(args, rds):
    with rds.transaction() as (db, state):
        branches = state.get("branches", {})
        active = state.get("active_branch", "main")
        if args.action == "status":
            info = branches.get(active, {})
            stagnated = info.get("stagnation_count", 0) >= 3
            return {
                "active_branch": active,
                "status": info.get("status", "ACTIVE"),
                "stagnation_count": info.get("stagnation_count", 0),
                "stagnated": stagnated,
                "recommendation": (
                    "STAGNATION_DETECTED: Consecutive 3 runs without useful gain. "
                    "Consider 'branch fork' to open an orthogonal research direction (FML-Bench v2)."
                    if stagnated else "ACTIVE: Continue current branch exploration."
                ),
                "branch_details": info
            }
        elif args.action == "list":
            return {"active_branch": active, "branches": branches}
        elif args.action == "switch":
            bid = identity(args.id)
            require(bid in branches, f"Unknown branch ID '{bid}'")
            state["active_branch"] = bid
            rds.event(db, "BRANCH_SWITCHED", branch_id=bid)
            return {"active_branch": bid, "status": branches[bid].get("status", "ACTIVE")}
        elif args.action == "fork":
            spec = load_spec(args.spec)
            reject_self_signatures(spec)
            bid = identity(spec["id"])
            parent = identity(spec.get("parent_id", active))
            require(bid not in branches, f"Branch ID '{bid}' already exists")
            require(parent in branches, f"Parent branch '{parent}' does not exist")
            require(spec.get("orthogonal_dimension"), "Must declare orthogonal_dimension (e.g. representation, mechanism, loss)")
            require(spec.get("rationale"), "Must declare rationale for branching")

            if "budget_split" in spec:
                split = resource_vector(spec["budget_split"])
                budget = state["budget"]
                for k in RESOURCES:
                    available = budget["limits"][k] - (budget["spent"][k] + budget["reserved"][k])
                    require(split[k] <= available,
                            f"Branch budget split exceeds available unspent {k}: {split[k]} > {available}")

            branches[bid] = {
                "id": bid,
                "parent_id": parent,
                "orthogonal_dimension": spec["orthogonal_dimension"],
                "rationale": spec["rationale"],
                "status": "ACTIVE",
                "stagnation_count": 0,
                "created_ns": time.time_ns(),
                "budget_split": spec.get("budget_split"),
                "hypotheses": []
            }
            state["active_branch"] = bid
            rds.event(db, "BRANCH_FORKED", branch_id=bid, parent_id=parent,
                      orthogonal_dimension=spec["orthogonal_dimension"])
            return {"forked_branch": bid, "parent_id": parent, "active_branch": bid}
        else:
            raise ValueError(f"Unknown branch action: {args.action}")


def cmd_meta(args, rds):
    from rds_meta import (
        validate_rule, load_judgment_graph, apply_rule, reflect_from_state
    )
    if args.action == "list-rules":
        _, graph = load_judgment_graph(getattr(args, "graph", None))
        return {"schema": graph.get("schema", 1), "total_nodes": len(graph.get("nodes", [])),
                "nodes": graph.get("nodes", [])}
    elif args.action == "validate-rule":
        spec = load_spec(args.rule)
        reject_self_signatures(spec)
        validate_rule(spec)
        return {"status": "VALID", "rule_id": spec["id"], "sha256": digest(spec)}
    elif args.action == "apply-rule":
        spec = load_spec(args.rule)
        reject_self_signatures(spec)
        res = apply_rule(spec, graph_path=getattr(args, "graph", None),
                         force=getattr(args, "force", False),
                         dry_run=getattr(args, "dry_run", False))
        try:
            with rds.transaction() as (db, state):
                rds.event(db, "RULE_APPLIED", **res)
        except Exception:
            pass
        return res
    elif args.action == "reflect":
        with rds.transaction() as (db, state):
            receipts = [strict_json(r[0]) for r in db.execute("SELECT body FROM receipts ORDER BY run_id")]
            evidence = None
            if getattr(args, "terms", None):
                evidence = {"terms": args.terms, "scope": state["contract"].get("project_id", "project")}
            proposals = reflect_from_state(state, receipts, evidence)
            if getattr(args, "output", None):
                Path(args.output).write_text(json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"proposed_rules_count": len(proposals), "proposals": proposals}
    elif args.action == "fuzz":
        from rds_adversary import AdversarialMutator
        plan = load_spec(args.plan)
        m_type = getattr(args, "type", "all")
        mutants = AdversarialMutator.mutate_plan(plan, mutation_type=m_type)
        return {"original_plan_id": plan.get("id"), "mutants_count": len(mutants), "mutants": mutants}
    elif args.action == "evaluate-alignment":
        from rds_adversary import AlignmentEvaluator
        rule = load_spec(args.rule)
        evaluator = AlignmentEvaluator(Path(args.root))
        return evaluator.evaluate_rule(rule)
    elif args.action == "auto-repair":
        from rds_adversary import AutoRepairEngine
        graph_path = Path(getattr(args, "graph", None) or (Path(__file__).resolve().parents[1] / "references/judgment-graph.yaml"))
        engine = AutoRepairEngine(Path(args.root), graph_path)
        dry = getattr(args, "dry_run", False)
        return engine.run_self_repair(dry_run=dry)
    else:
        raise ValueError(f"Unknown meta action: {args.action}")


def cmd_advise(args, rds):
    from rds_advisor import RDSAdvisor
    from rds_meta import load_judgment_graph
    advisor = RDSAdvisor(Path(args.root))
    
    with rds.transaction() as (db, state):
        _, graph = load_judgment_graph(getattr(args, "graph", None))
        
        # Scenario A: Telemetry diagnosis
        if getattr(args, "telemetry", None):
            telemetry = load_spec(args.telemetry)
            return advisor.advise_on_loss_dynamics(telemetry)

        # Scenario B: Fit status diagnosis (Underfitting vs Overfitting)
        if getattr(args, "train_loss", None) is not None and getattr(args, "val_loss", None) is not None:
            b_loss = float(args.baseline_loss) if getattr(args, "baseline_loss", None) is not None else None
            return advisor.diagnose_fit_status(float(args.train_loss), float(args.val_loss), b_loss)

        # Scenario C: Document Ingestion & Learning
        if getattr(args, "doc", None):
            return advisor.ingest_document(Path(args.doc), topic=getattr(args, "topic", None))

        # Scenario D: Plan advice (pre-check simulation)
        if getattr(args, "plan", None):
            plan = load_spec(args.plan)
            # Check gate advisory
            try:
                # Run lightweight gate check in memory
                cmd_plan(argparse.Namespace(plan=args.plan, action="check"), rds, advisory=True)
                gate_err = None
            except Exception as e:
                gate_err = str(e)

            if gate_err:
                return advisor.advise_on_rejection(gate_err, plan)
            return {
                "advisor_type": "PLAN_COMPLIANCE_PASS",
                "status": "APPROVED",
                "actionable_suggestion": "方案通过门禁安全检查。空白对照将自动复用已验证缓存，可安全提交执行。"
            }

        # Scenario E: Global strategic directions
        recommendations = advisor.recommend_next_directions(state, graph)
        return {
            "advisor_type": "STRATEGIC_RESEARCH_ADVICE",
            "active_branch": state.get("active_branch", "main"),
            "recommendations_count": len(recommendations),
            "recommendations": recommendations
        }


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    p.add_argument("--version", action="version", version=VERSION)
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("--contract", required=True)
    hypo = commands.add_parser("hypothesis").add_subparsers(dest="action", required=True).add_parser("add")
    hypo.add_argument("--spec", required=True)
    gate = commands.add_parser("gate").add_subparsers(dest="action", required=True).add_parser("check")
    gate.add_argument("--plan", required=True)
    plans = commands.add_parser("plan").add_subparsers(dest="action", required=True)
    plans.add_parser("create").add_argument("--spec", required=True)
    plans.add_parser("cancel").add_argument("--id", required=True)
    runs = commands.add_parser("run").add_subparsers(dest="action", required=True)
    for action in ("execute", "recover"):
        runs.add_parser(action).add_argument("--id", required=True)
    expose = commands.add_parser("data").add_subparsers(dest="action", required=True).add_parser("expose")
    expose.add_argument("--split", required=True)
    expose.add_argument("--purpose", choices=["view", "train", "select", "memory_retrieval", "prior_exposure"], required=True)
    expose.add_argument("--actor", required=True)
    expose.add_argument("--reason", required=True)
    commands.add_parser("decide").add_argument("--run", required=True)
    commands.add_parser("status")

    # Policy RSI: Branch & Stagnation Engine
    branch = commands.add_parser("branch", help="RSI Policy Stagnation & Branching engine")
    b_actions = branch.add_subparsers(dest="action", required=True)
    b_actions.add_parser("status")
    b_actions.add_parser("list")
    b_sw = b_actions.add_parser("switch")
    b_sw.add_argument("--id", required=True)
    b_fork = b_actions.add_parser("fork")
    b_fork.add_argument("--spec", required=True)

    # Graph RSI: Meta-Reflection & Rule Evolution Engine
    meta = commands.add_parser("meta", help="RSI Meta-Reflection & Rule Evolution engine")
    m_actions = meta.add_subparsers(dest="action", required=True)
    m_list = m_actions.add_parser("list-rules")
    m_list.add_argument("--graph", default=None)
    m_val = m_actions.add_parser("validate-rule")
    m_val.add_argument("--rule", required=True)
    m_app = m_actions.add_parser("apply-rule")
    m_app.add_argument("--rule", required=True)
    m_app.add_argument("--graph", default=None)
    m_app.add_argument("--force", action="store_true")
    m_ref = m_actions.add_parser("reflect")
    m_ref.add_argument("--terms", default=None)
    m_ref.add_argument("--output", default=None)
    m_fuzz = m_actions.add_parser("fuzz")
    m_fuzz.add_argument("--plan", required=True)
    m_fuzz.add_argument("--type", choices=["all", "self_sign", "split_escalate", "budget_stretch", "control_perturb"], default="all")
    m_eval = m_actions.add_parser("evaluate-alignment")
    m_eval.add_argument("--rule", required=True)
    m_rep = m_actions.add_parser("auto-repair")
    m_rep.add_argument("--graph", default=None)
    m_rep.add_argument("--dry-run", action="store_true")

    history = commands.add_parser("history", help="Read history through the installed Obelisk CLI")
    actions = history.add_subparsers(dest="subcommand", required=True)
    prepare = actions.add_parser("prepare")
    prepare.add_argument("--project-path")
    prepare.add_argument("--terms")
    prepare.add_argument("--offset", type=int, default=0)
    prepare.add_argument("--uuid")
    prepare.add_argument("--raw-offset", type=int, default=0)
    prepare.add_argument("--output", required=True)
    actions.add_parser("query").add_argument("--query", required=True)

    adv = commands.add_parser("advise", help="Get programmatic mathematical and strategic advice for models")
    adv.add_argument("--plan", default=None)
    adv.add_argument("--telemetry", default=None)
    adv.add_argument("--doc", default=None)
    adv.add_argument("--topic", default=None)
    adv.add_argument("--train-loss", default=None)
    adv.add_argument("--val-loss", default=None)
    adv.add_argument("--baseline-loss", default=None)
    adv.add_argument("--graph", default=None)
    return p


def main():
    args = parser().parse_args()
    rds = RDSState(args.root)
    try:
        if args.command == "history":
            from rds_obelisk import history_command
            history_command(args)
            return 0
        if args.command == "advise":
            result = cmd_advise(args, rds)
        elif args.command == "branch":
            result = cmd_branch(args, rds)
        elif args.command == "meta":
            result = cmd_meta(args, rds)
        elif args.command == "init":
            result = cmd_init(args, rds)
        elif args.command == "hypothesis":
            result = cmd_hypothesis(args, rds)
        elif args.command == "gate":
            result = cmd_plan(args, rds, advisory=True)
        elif args.command == "plan":
            result = cmd_plan(args, rds) if args.action == "create" else cmd_cancel(args, rds)
        elif args.command == "run":
            result = cmd_run(args, rds) if args.action == "execute" else cmd_recover(args, rds)
        elif args.command == "data":
            result = cmd_expose(args, rds)
        elif args.command == "decide":
            result = cmd_decide(args, rds)
        else:
            result = cmd_status(args, rds)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, SyntaxError, ImportError, subprocess.SubprocessError) as exc:
        print("[RDS-REJECT] " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())

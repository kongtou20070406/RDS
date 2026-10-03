"""Check or prepare a paired stable Lean/mathlib upgrade; never accept it.

Each reviewed commit retains exact locks. Apply only resolves dependencies;
native build, axiom audit and certificate replay remain mandatory afterwards.
"""
import argparse
from contextlib import suppress
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/leanprover-community/mathlib4"
MATHLIB_URL = "https://github.com/leanprover-community/mathlib4.git"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
FILES = ("formal/lean-toolchain", "formal/lakefile.lean",
         "formal/lake-manifest.json", "scripts/rds_statistical_verify.py")
STABLE = re.compile(r"v4\.[0-9]+\.[0-9]+")
REVISION = re.compile(r"[0-9a-f]{40}")
LAKE_PIN = re.compile(
    r'(require\s+mathlib\s+from\s+git\s*"'
    + re.escape(MATHLIB_URL) + r'"\s*@\s*")(v4\.[0-9]+\.[0-9]+)(")')
LAKE_TEMPLATE = re.compile(
    r"\s*import\s+Lake\s+open\s+Lake\s+DSL\s+package\s+Formal\s+where\s+"
    + LAKE_PIN.pattern + r"\s+@\[\s*default_target\s*\]\s+lean_lib\s+Formal\s*")
CHECKER_PIN = re.compile(r'(?m)^(MATHLIB_REV = ")([0-9a-f]{40})(")\r?$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stable_tag(tag):
    require(isinstance(tag, str) and STABLE.fullmatch(tag),
            "Version must be an exact stable v4.X.X tag; prereleases and moving refs are unsupported")
    return tag


def fetch(url):
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "RDS-Lean-upgrade"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
    require(len(data) <= MAX_RESPONSE_BYTES, "GitHub response exceeds the 2-MiB limit")
    return data


def mathlib_package(manifest):
    require(isinstance(manifest, dict) and isinstance(manifest.get("packages"), list),
            "Invalid Lake manifest")
    packages = [item for item in manifest["packages"]
                if isinstance(item, dict) and item.get("name") == "mathlib"]
    require(len(packages) == 1, "Manifest must contain exactly one mathlib dependency")
    package = packages[0]
    require(package.get("url") == MATHLIB_URL and package.get("type") == "git",
            "Mathlib must use its official Git repository")
    require(isinstance(package.get("rev"), str) and REVISION.fullmatch(package["rev"]),
            "Mathlib revision must be a complete lowercase 40-hex commit")
    return package


def local_lock(root):
    original = {name: (root / name).read_bytes() for name in FILES}
    text = {name: data.decode("utf-8") for name, data in original.items()}
    toolchain = text[FILES[0]].strip()
    require(toolchain.startswith("leanprover/lean4:"), "Unsupported Lean toolchain template")
    tag = stable_tag(toolchain.removeprefix("leanprover/lean4:"))
    pin = LAKE_TEMPLATE.fullmatch(text[FILES[1]])
    require(pin is not None, "Unsupported Lakefile template; expected the bundled Formal project "
            "without comments or additional declarations")
    require(pin[2] == tag, "Lean and Lakefile mathlib versions differ")
    package = mathlib_package(json.loads(text[FILES[2]]))
    require(package.get("inputRev") == tag, "Manifest mathlib inputRev differs from the paired version")
    checker = list(CHECKER_PIN.finditer(text[FILES[3]]))
    require(len(checker) == 1 and len(re.findall(r"(?m)^\s*MATHLIB_REV\s*=", text[FILES[3]])) == 1,
            "Checker must contain one supported MATHLIB_REV assignment")
    require(checker[0][2] == package["rev"], "Checker MATHLIB_REV differs from the manifest")
    return original, {"lean": tag, "mathlib": tag, "mathlib_revision": package["rev"]}


def target_lock(version=None):
    if version is None:
        release = json.loads(fetch(API + "/releases/latest"))
        require(isinstance(release, dict) and release.get("draft") is False
                and release.get("prerelease") is False, "Latest mathlib release is not stable")
        version = stable_tag(release.get("tag_name"))
    else:
        version = stable_tag(version)
    commit = json.loads(fetch(API + "/commits/" + version))
    revision = commit.get("sha") if isinstance(commit, dict) else None
    require(isinstance(revision, str) and REVISION.fullmatch(revision), "Invalid upstream mathlib commit")
    toolchain = fetch("https://raw.githubusercontent.com/leanprover-community/mathlib4/"
                      + revision + "/lean-toolchain").decode("utf-8").strip()
    require(toolchain == "leanprover/lean4:" + version,
            "Upstream mathlib does not declare the matching exact stable Lean toolchain")
    return {"lean": version, "mathlib": version, "mathlib_revision": revision}


def _stop_tree(process, job):
    """Stop owned children before configuration rollback, including on interruption."""
    if os.name == "nt":
        if job is not None and job.handle:
            job.stop()
        else:
            taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
            with suppress(OSError, subprocess.SubprocessError):
                subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                               shell=False, timeout=30, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            if process.poll() is None:
                process.kill()
    else:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=30)


def _run_owned(command, cwd, *, timeout=600, env=None):
    if os.name == "nt":
        from rds_project import _Job
    with tempfile.TemporaryFile() as output:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(command, cwd=cwd, env=env, shell=False, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT, creationflags=flags,
                                   start_new_session=os.name != "nt")
        job = None
        try:
            if os.name == "nt":
                job = _Job(process)
            process.wait(timeout=timeout)
        except BaseException:
            _stop_tree(process, job)
            raise
        finally:
            if os.name != "nt":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            if job is not None:
                job.close()
        if process.returncode:
            output.seek(0, 2)
            output.seek(max(0, output.tell() - 8192))
            raise ValueError("lake update mathlib failed (exit " + str(process.returncode)
                             + "): " + output.read().decode("utf-8", errors="replace"))


def resolve_lake(root):
    env = os.environ.copy()
    env["MATHLIB_NO_CACHE_ON_UPDATE"] = "1"
    _run_owned(["lake", "update", "mathlib"], root / "formal", timeout=600, env=env)


def update(root=ROOT, *, apply=False, version=None, check_lock=False):
    root = Path(root).resolve()
    if version is not None:
        stable_tag(version)
    original, current = local_lock(root)
    if check_lock:
        require(version is None and not apply, "--check-lock cannot select an upgrade version")
        return {"mode": "check-lock", "valid": True, "current": current}
    target = target_lock(version)
    report = {"mode": "apply" if apply else "check", "current": current,
              "target": target, "update_available": current != target, "changed_files": []}
    if apply and current != target:
        require(all((root / name).read_bytes() == data for name, data in original.items()),
                "Configuration changed during upstream lookup; retry after reviewing it")
        try:
            (root / FILES[0]).write_text("leanprover/lean4:" + target["lean"] + "\n", encoding="utf-8")
            lakefile = original[FILES[1]].decode("utf-8")
            (root / FILES[1]).write_text(LAKE_PIN.sub(lambda m: m[1] + target["mathlib"] + m[3], lakefile),
                                       encoding="utf-8")
            resolve_lake(root)
            package = mathlib_package(json.loads((root / FILES[2]).read_text(encoding="utf-8")))
            require(package.get("inputRev") == target["mathlib"]
                    and package["rev"] == target["mathlib_revision"],
                    "Resolved manifest does not match the official mathlib tag commit")
            checker = original[FILES[3]].decode("utf-8")
            (root / FILES[3]).write_text(CHECKER_PIN.sub(
                lambda m: m[1] + package["rev"] + m[3], checker), encoding="utf-8")
            _, updated = local_lock(root)
            require(updated == target, "Updated Lean/mathlib/checker bindings are inconsistent")
        except BaseException:
            for name, data in original.items():
                (root / name).write_bytes(data)
            raise
        report["changed_files"] = [name for name, data in original.items()
                                   if (root / name).read_bytes() != data]
    if apply:
        report["validation_required"] = ["lake build", "Formal axiom audit",
                                          "native Lean and statistical certificate replay"]
        report["accepted"] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only stable upgrade check (default)")
    mode.add_argument("--check-lock", action="store_true", help="Validate local paired locks without network or Lake")
    mode.add_argument("--apply", action="store_true", help="Prepare a paired upgrade; build/audit/replay are still required")
    parser.add_argument("--version", help="Exact stable mathlib/Lean tag, e.g. v4.34.1")
    parser.add_argument("--root", type=Path, default=ROOT, help="RDS checkout root")
    args = parser.parse_args(argv)
    try:
        result = update(args.root, apply=args.apply, version=args.version, check_lock=args.check_lock)
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

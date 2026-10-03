"""Paired upgrades preserve locks on failure and require separate acceptance."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_lean_toolchain as upgrade

OLD, NEW = "v4.33.1", "v4.34.1"
OLD_REV, NEW_REV = "a" * 40, "b" * 40


class ToolchainUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        # update() resolves its root, including native Windows 8.3 aliases.
        # Compare the same directory spelling in the acceptance fixture.
        self.root = Path(self.folder.name).resolve()
        for folder in ("formal", "scripts"):
            (self.root / folder).mkdir()
        (self.root / upgrade.FILES[0]).write_text("leanprover/lean4:" + OLD + "\n", encoding="utf-8")
        (self.root / upgrade.FILES[1]).write_text(
            'import Lake\nopen Lake DSL\npackage Formal where\nrequire mathlib from git\n  "'
            + upgrade.MATHLIB_URL + '" @ "' + OLD + '"\n@[default_target]\nlean_lib Formal\n',
            encoding="utf-8")
        self.write_manifest(OLD, OLD_REV)
        (self.root / upgrade.FILES[3]).write_text('MATHLIB_REV = "' + OLD_REV + '"\n', encoding="utf-8")
        self.original = self.snapshot()

    def write_manifest(self, version, revision):
        (self.root / upgrade.FILES[2]).write_text(json.dumps({"packages": [{
            "name": "mathlib", "type": "git", "url": upgrade.MATHLIB_URL,
            "inputRev": version, "rev": revision}]}), encoding="utf-8")

    def snapshot(self):
        return {name: (self.root / name).read_bytes() for name in upgrade.FILES}

    def upstream(self, url):
        if url.endswith("/releases/latest"):
            return json.dumps({"tag_name": NEW, "draft": False, "prerelease": False}).encode()
        if url.endswith("/commits/" + NEW):
            return json.dumps({"sha": NEW_REV}).encode()
        self.assertEqual(url, "https://raw.githubusercontent.com/leanprover-community/mathlib4/"
                         + NEW_REV + "/lean-toolchain")
        return ("leanprover/lean4:" + NEW + "\n").encode()

    def run_cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = upgrade.main(["--root", str(self.root), *args])
        return code, json.loads(output.getvalue())

    def test_check_cli_is_read_only_and_reports_latest_pair(self):
        with mock.patch.object(upgrade, "fetch", side_effect=self.upstream), \
                mock.patch.object(upgrade.subprocess, "run") as run:
            code, report = self.run_cli("--check")
        self.assertEqual(code, 0)
        self.assertTrue(report["update_available"])
        self.assertEqual(report["target"]["mathlib_revision"], NEW_REV)
        self.assertEqual(self.snapshot(), self.original)
        run.assert_not_called()

    def test_apply_updates_all_four_bindings_without_build_commit_or_push(self):
        def lake(root):
            self.assertEqual(root, self.root)
            self.write_manifest(NEW, NEW_REV)
        with mock.patch.object(upgrade, "fetch", side_effect=self.upstream), \
                mock.patch.object(upgrade, "resolve_lake", side_effect=lake) as run:
            code, report = self.run_cli("--apply", "--version", NEW)
        self.assertEqual(code, 0, report)
        self.assertEqual(set(report["changed_files"]), set(upgrade.FILES))
        self.assertEqual(upgrade.local_lock(self.root)[1], report["target"])
        self.assertFalse(report["accepted"])
        self.assertIn("lake build", report["validation_required"])
        run.assert_called_once()

    def test_moving_refs_and_prereleases_are_rejected_before_network(self):
        with mock.patch.object(upgrade, "fetch") as fetch:
            for version in ("v4.35.0-rc3", "nightly", "master", "stable", "4.34.1", "v3.51.1"):
                code, _ = self.run_cli("--apply", "--version", version)
                self.assertEqual(code, 1, version)
                self.assertEqual(self.snapshot(), self.original)
        fetch.assert_not_called()

    def test_network_or_toolchain_download_failures_leave_all_configs_untouched(self):
        for failure_index in range(3):
            count = 0
            def failing(url):
                nonlocal count
                index, count = count, count + 1
                if index == failure_index:
                    raise OSError("network unavailable")
                return self.upstream(url)
            with mock.patch.object(upgrade, "fetch", side_effect=failing), \
                    mock.patch.object(upgrade.subprocess, "run") as run:
                code, _ = self.run_cli("--apply")
            self.assertEqual(code, 1)
            self.assertEqual(self.snapshot(), self.original)
            run.assert_not_called()

    def test_lake_errors_timeouts_and_wrong_resolution_restore_all_four_files(self):
        for failure in ("exit", "timeout", "missing", "wrong-commit"):
            def lake(root):
                self.write_manifest(NEW, "c" * 40)
                if failure != "wrong-commit":
                    (self.root / upgrade.FILES[0]).write_text("changed by lake hook", encoding="utf-8")
                    (self.root / upgrade.FILES[3]).write_text("changed by lake hook", encoding="utf-8")
                if failure == "timeout":
                    raise subprocess.TimeoutExpired(["lake", "update", "mathlib"], 600)
                if failure == "missing":
                    raise FileNotFoundError("lake unavailable")
                if failure == "exit":
                    raise ValueError("lake update mathlib failed")
            with mock.patch.object(upgrade, "fetch", side_effect=self.upstream), \
                    mock.patch.object(upgrade, "resolve_lake", side_effect=lake):
                code, _ = self.run_cli("--apply")
            self.assertEqual(code, 1, failure)
            self.assertEqual(self.snapshot(), self.original, failure)

    def test_same_paired_commit_is_a_noop_even_in_apply_mode(self):
        def current_upstream(url):
            if url.endswith("/commits/" + OLD):
                return json.dumps({"sha": OLD_REV}).encode()
            self.assertTrue(url.endswith(OLD_REV + "/lean-toolchain"))
            return ("leanprover/lean4:" + OLD + "\n").encode()
        with mock.patch.object(upgrade, "fetch", side_effect=current_upstream), \
                mock.patch.object(upgrade.subprocess, "run") as run:
            code, report = self.run_cli("--apply", "--version", OLD)
        self.assertEqual(code, 0)
        self.assertFalse(report["update_available"])
        self.assertEqual(report["changed_files"], [])
        self.assertEqual(self.snapshot(), self.original)
        run.assert_not_called()

    def test_lock_check_rejects_each_inconsistent_binding_without_network_or_lake(self):
        with mock.patch.object(upgrade, "fetch") as fetch, \
                mock.patch.object(upgrade.subprocess, "run") as run:
            self.assertEqual(self.run_cli("--check-lock")[0], 0)
            for name in upgrade.FILES:
                for filename, data in self.original.items():
                    (self.root / filename).write_bytes(data)
                path = self.root / name
                if name == upgrade.FILES[2]:
                    self.write_manifest(NEW, OLD_REV)
                else:
                    text = path.read_text(encoding="utf-8")
                    path.write_text(text.replace(OLD_REV, NEW_REV) if name == upgrade.FILES[3]
                                    else text.replace(OLD, NEW), encoding="utf-8")
                before = self.snapshot()
                self.assertEqual(self.run_cli("--check-lock")[0], 1, name)
                self.assertEqual(self.snapshot(), before)
        fetch.assert_not_called()
        run.assert_not_called()

    def test_checker_mismatch_and_duplicate_assignment_fail_before_upgrade_lookup(self):
        path = self.root / upgrade.FILES[3]
        for source in ('MATHLIB_REV = "' + NEW_REV + '"\n',
                       ('MATHLIB_REV = "' + OLD_REV + '"\n') * 2):
            path.write_text(source, encoding="utf-8")
            before = self.snapshot()
            with mock.patch.object(upgrade, "fetch") as fetch:
                self.assertEqual(self.run_cli("--apply")[0], 1)
            self.assertEqual(self.snapshot(), before)
            fetch.assert_not_called()

    def test_prerelease_metadata_or_unpaired_upstream_toolchain_is_rejected(self):
        for failure in ("prerelease", "toolchain"):
            def invalid(url):
                if failure == "prerelease" and url.endswith("/releases/latest"):
                    return json.dumps({"tag_name": NEW, "draft": False, "prerelease": True}).encode()
                if failure == "toolchain" and url.endswith("/lean-toolchain"):
                    return b"leanprover/lean4:v4.35.0-rc3\n"
                return self.upstream(url)
            with mock.patch.object(upgrade, "fetch", side_effect=invalid):
                self.assertEqual(self.run_cli("--apply")[0], 1)
            self.assertEqual(self.snapshot(), self.original)

    def test_http_reads_are_bounded_and_have_a_timeout(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"x" * (upgrade.MAX_RESPONSE_BYTES + 1)
        with mock.patch.object(upgrade.urllib.request, "urlopen", return_value=response) as open_url:
            with self.assertRaisesRegex(ValueError, "limit"):
                upgrade.fetch(upgrade.API + "/releases/latest")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 30)
        response.__enter__.return_value.read.assert_called_once_with(upgrade.MAX_RESPONSE_BYTES + 1)

    def test_commented_stable_pin_cannot_hide_a_real_moving_dependency(self):
        path = self.root / upgrade.FILES[1]
        valid = self.original[upgrade.FILES[1]].decode("utf-8")
        stanza = 'require mathlib from git "' + upgrade.MATHLIB_URL + '" @ "' + OLD + '"'
        cases = ["-- " + stanza + "\n" + valid.replace(OLD, "main"),
                 "/- " + stanza + " -/\n" + valid.replace(OLD, "main"),
                 "/- outer /- " + stanza + " -/ outer -/\n" + valid.replace(OLD, "main"),
                 valid + "\n/- harmless comment -/\n"]
        with mock.patch.object(upgrade, "fetch") as fetch, \
                mock.patch.object(upgrade, "resolve_lake") as lake:
            for source in cases:
                path.write_text(source, encoding="utf-8")
                before = self.snapshot()
                code, report = self.run_cli("--apply")
                self.assertEqual(code, 1)
                self.assertIn("Unsupported Lakefile template", report["reason"])
                self.assertEqual(self.snapshot(), before)
        fetch.assert_not_called()
        lake.assert_not_called()

    def test_dependency_resolution_disables_the_mathlib_cache_build_hook(self):
        with mock.patch.object(upgrade, "_run_owned") as run:
            upgrade.resolve_lake(self.root)
        self.assertEqual(run.call_args.args, (["lake", "update", "mathlib"], self.root / "formal"))
        self.assertEqual(run.call_args.kwargs["timeout"], 600)
        self.assertEqual(run.call_args.kwargs["env"]["MATHLIB_NO_CACHE_ON_UPDATE"], "1")

    def test_real_timeout_and_interrupt_stop_children_before_rollback(self):
        native_popen = subprocess.Popen
        native_stop = upgrade._stop_tree
        for interruption in ("timeout", "keyboard"):
            marker = self.root / (interruption + "-late-write")
            ready = self.root / (interruption + "-ready")
            gate = self.root / (interruption + "-start-work")
            child = ("import json,pathlib,sys,time; "
                     "pathlib.Path(sys.argv[2]).write_text(json.dumps({'ready_at':time.monotonic()})); "
                     "gate=pathlib.Path(sys.argv[3]); "
                     "exec('while not gate.exists():\\n time.sleep(0.01)'); "
                     "time.sleep(2); pathlib.Path(sys.argv[1]).write_text(json.dumps({'wrote_at':time.monotonic()}))")
            parent = ("import pathlib,subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
                      + repr(child) + ",*sys.argv[1:]]); time.sleep(10)")
            command = [sys.executable, "-c", parent, str(marker), str(ready), str(gate)]
            timing = {}

            def launch(*args, **kwargs):
                process = native_popen(*args, **kwargs)
                if args[0] == command:
                    real_wait = process.wait
                    def ready_wait(timeout=None):
                        process.wait = real_wait
                        deadline = time.monotonic() + 5
                        while not ready.exists() and time.monotonic() < deadline:
                            time.sleep(0.01)
                        self.assertTrue(ready.exists(), "Synthetic child never started")
                        timing["ready_at"] = json.loads(ready.read_text())["ready_at"]
                        timing["began_at"] = time.monotonic()
                        gate.write_text("start")
                        if interruption == "keyboard":
                            raise KeyboardInterrupt
                        return real_wait(timeout=timeout)
                    process.wait = ready_wait
                return process

            def stop(process, job):
                timing["cancelled_at"] = time.monotonic()
                return native_stop(process, job)

            def lake(root):
                upgrade._run_owned(command, root / "formal", timeout=1)

            with mock.patch.object(upgrade, "fetch", side_effect=self.upstream), \
                    mock.patch.object(upgrade, "resolve_lake", side_effect=lake), \
                    mock.patch.object(upgrade.subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(upgrade, "_stop_tree", side_effect=stop), \
                    mock.patch.object(upgrade.subprocess, "run", wraps=subprocess.run) as fallback:
                if interruption == "keyboard":
                    with self.assertRaises(KeyboardInterrupt):
                        upgrade.update(self.root, apply=True)
                else:
                    self.assertEqual(self.run_cli("--apply")[0], 1)
                fallback.assert_not_called()
            self.assertLessEqual(timing["ready_at"], timing["began_at"])
            self.assertLessEqual(timing["began_at"], timing["cancelled_at"])
            self.assertEqual(self.snapshot(), self.original)
            time.sleep(2.2)
            written = json.loads(marker.read_text()) if marker.exists() else None
            self.assertIsNone(written, "Child write timestamp " + str(written)
                              + " versus cancellation " + str(timing["cancelled_at"]))


class RepositoryToolchainTests(unittest.TestCase):
    def test_actual_checkout_has_consistent_source_locks_without_network(self):
        with mock.patch.object(upgrade, "fetch", side_effect=AssertionError("Lock check must be offline")), \
                mock.patch.object(upgrade, "resolve_lake", side_effect=AssertionError("Lock check must not run Lake")):
            report = upgrade.update(check_lock=True)
        self.assertTrue(report["valid"])
        self.assertEqual(report["mode"], "check-lock")


if __name__ == "__main__":
    unittest.main()

"""Exercise exported host packages away from the source checkout."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_plugins


class PluginPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="rds plugin ")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.workspace = Path(cls.temp.name)
        cls.output = cls.workspace / "export"
        build_plugins.build(cls.output)
        # Move the whole export: host paths must not retain checkout locations.
        cls.moved = cls.workspace / "relocated 包"
        cls.output.rename(cls.moved)

    def test_each_package_runs_the_real_cli_and_packaged_advisor_resources(self):
        for host in ("claude", "codex", "omp"):
            with self.subTest(host=host):
                skill = self.moved / host / build_plugins.NAME / "skills" / build_plugins.NAME
                project = self.workspace / (host + " project")
                project.mkdir()
                env = {**os.environ, "RDS_USAGE_DB": str(project / "usage.sqlite3")}
                cli = [sys.executable, "-B", str(skill / "scripts/rds_cli.py"), "--root", str(project)]
                version = subprocess.run(cli + ["--version"], cwd=project, env=env,
                                         capture_output=True, text=True, encoding="utf-8", timeout=15)
                self.assertEqual(version.returncode, 0, version.stderr)
                result = subprocess.run(cli + ["advise", "--context", str(skill / "examples/advisor-search/boundary-context.json"),
                           "--graph", str(skill / "references/judgment-graph.yaml")], cwd=project, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                answer = json.loads(result.stdout)
                self.assertTrue(any(row.get("type") == "EXECUTABLE_DIRECTION_SEARCH" for row in answer["recommendations"]))
                self.assertFalse((skill / ".rds").exists())
                self.assertFalse((project / ".rds").exists())
                self.assertTrue((skill / "formal/lakefile.lean").is_file())
                self.assertTrue((skill / "references/theory-tools.json").is_file())

    def test_manifest_hook_command_runs_from_unrelated_cwd_after_relocation(self):
        for host, variable in (("claude", "CLAUDE_PLUGIN_ROOT"), ("codex", "PLUGIN_ROOT")):
            with self.subTest(host=host):
                plugin = self.moved / host / build_plugins.NAME
                config = json.loads((plugin / "integrations/hooks.json").read_text(encoding="utf-8"))
                command = config["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
                argv = shlex.split(command)
                argv[0] = sys.executable
                entry = plugin / "skills" / build_plugins.NAME / "scripts/rds_cli.py"
                payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(self.workspace),
                           "tool_input": {"command": f'python -B "{entry}" --version'},
                           "tool_response": {"exit_code": 0}}
                result = subprocess.run(argv, input=json.dumps(payload), env={**os.environ, variable: str(plugin)},
                                        cwd=self.workspace, capture_output=True, encoding="utf-8", timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
                self.assertIn("RDS | ", context)
                self.assertEqual("RDS | CLI: returned", context.splitlines()[0])
                self.assertNotIn(str(ROOT), command)
                self.assertFalse((self.workspace / ".rds").exists())

    def test_hosts_do_not_load_each_others_hooks_and_paths_resolve(self):
        omp = self.moved / "omp" / build_plugins.NAME
        self.assertFalse((omp / ".claude-plugin").exists())
        self.assertFalse((omp / "hooks/hooks.json").exists())
        package = json.loads((omp / "package.json").read_text(encoding="utf-8"))
        for path in package["omp"]["extensions"]:
            self.assertTrue((omp / path).is_file())
        for host, manifest in (("claude", ".claude-plugin/plugin.json"), ("codex", ".codex-plugin/plugin.json")):
            root = self.moved / host / build_plugins.NAME
            config = json.loads((root / manifest).read_text(encoding="utf-8"))
            self.assertTrue((root / config["hooks"]).is_file())
            self.assertFalse((root / "hooks/hooks.json").exists(), "avoid duplicate default and manifest hooks")

    def test_existing_output_is_preserved(self):
        marker = self.moved / "keep.txt"
        marker.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "never overwritten"):
            build_plugins.build(self.moved)
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_untracked_private_content_does_not_enter_export(self):
        source = self.workspace / "minimal source"
        source.mkdir()
        subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
        for relative in ("SKILL.md", "LICENSE", "scripts/rds_cli.py", "scripts/rds_conversation_hook.py",
                         "integrations/omp/rds-status.mjs", "docs/public.md"):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('VERSION = "5.8.0"\n' if relative.endswith("rds_cli.py") else "public", encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
        (source / "docs/private.md").write_text("private research", encoding="utf-8")
        (source / ".rds").mkdir()
        (source / ".rds/private.json").write_text("private state", encoding="utf-8")
        target = self.workspace / "minimal export"
        build_plugins.build(target, source)
        for host in ("claude", "codex", "omp"):
            skill = target / host / build_plugins.NAME / "skills" / build_plugins.NAME
            self.assertTrue((skill / "docs/public.md").is_file())
            self.assertFalse((skill / "docs/private.md").exists())
            self.assertFalse((skill / ".rds").exists())


if __name__ == "__main__":
    unittest.main()

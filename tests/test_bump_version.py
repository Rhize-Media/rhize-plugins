"""Regression tests for dual-host plugin version updates."""

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts" / "bump_version.py")
bump_version = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bump_version)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_repo(root: Path, plugin: str, *, dual: bool) -> Path:
    plugin_dir = root / plugin
    claude = plugin_dir / ".claude-plugin" / "plugin.json"
    claude.parent.mkdir(parents=True)
    claude.write_text(json.dumps({"name": plugin, "version": "0.0.0"}) + "\n", encoding="utf-8")
    if dual:
        codex = plugin_dir / ".codex-plugin" / "plugin.json"
        codex.parent.mkdir(parents=True)
        codex.write_text(json.dumps({"name": plugin, "version": "0.0.0"}) + "\n", encoding="utf-8")
        (plugin_dir / "package.json").write_text(json.dumps({"name": plugin, "version": "0.0.0"}) + "\n", encoding="utf-8")
        context = plugin_dir / "service" / "src" / "api" / "context.mjs"
        context.parent.mkdir(parents=True)
        context.write_text("const VERSION = '0.0.0';\n", encoding="utf-8")
        plist = plugin_dir / "native" / "reminders-helper" / "Resources" / "Info.plist"
        plist.parent.mkdir(parents=True)
        plist.write_text("<plist><dict><key>CFBundleShortVersionString</key><string>0.0.0</string></dict></plist>\n", encoding="utf-8")

    marketplace = root / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(
        json.dumps({"version": "2.27.0", "plugins": [{"name": plugin, "version": "0.0.0"}]}) + "\n",
        encoding="utf-8",
    )
    return root


class UpdatePluginManifestsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_repo = bump_version.REPO
        self.temp_dir = TemporaryDirectory()

    def tearDown(self) -> None:
        bump_version.REPO = self.original_repo
        self.temp_dir.cleanup()

    def test_updates_claude_and_codex_manifests(self) -> None:
        repo = seed_repo(Path(self.temp_dir.name), "rhize-tasks", dual=True)
        bump_version.REPO = repo

        bump_version.apply_bumps({"rhize-tasks": "0.1.0"}, "2.28.0")

        self.assertEqual(load(repo / "rhize-tasks/.claude-plugin/plugin.json")["version"], "0.1.0")
        self.assertEqual(load(repo / "rhize-tasks/.codex-plugin/plugin.json")["version"], "0.1.0")
        self.assertEqual(load(repo / "rhize-tasks/package.json")["version"], "0.1.0")
        self.assertIn("const VERSION = '0.1.0';", (repo / "rhize-tasks/service/src/api/context.mjs").read_text(encoding="utf-8"))
        self.assertIn("<string>0.1.0</string>", (repo / "rhize-tasks/native/reminders-helper/Resources/Info.plist").read_text(encoding="utf-8"))
        self.assertEqual(load(repo / ".claude-plugin/marketplace.json")["version"], "2.28.0")

    def test_accepts_runtime_version_derived_from_package_json(self) -> None:
        repo = seed_repo(Path(self.temp_dir.name), "rhize-tasks", dual=True)
        bump_version.REPO = repo
        context = repo / "rhize-tasks/service/src/api/context.mjs"
        derived = "const VERSION = JSON.parse(readFileSync(new URL('../../../package.json', import.meta.url), 'utf8')).version;\n"
        context.write_text(derived, encoding="utf-8")

        bump_version.apply_bumps({"rhize-tasks": "0.2.0"}, "2.28.0")

        self.assertEqual(load(repo / "rhize-tasks/package.json")["version"], "0.2.0")
        self.assertEqual(context.read_text(encoding="utf-8"), derived)

    def test_keeps_single_manifest_plugins_supported(self) -> None:
        repo = seed_repo(Path(self.temp_dir.name), "legacy-plugin", dual=False)
        bump_version.REPO = repo

        bump_version.apply_bumps({"legacy-plugin": "0.1.0"}, "2.28.0")

        self.assertEqual(load(repo / "legacy-plugin/.claude-plugin/plugin.json")["version"], "0.1.0")
        self.assertFalse((repo / "legacy-plugin/.codex-plugin/plugin.json").exists())


class LastReleaseRefTests(unittest.TestCase):
    """Regression coverage for the release-base bug: a commit that touches
    marketplace.json without changing any version line (e.g. editing plugin
    descriptions) must not be mistaken for the last release."""

    def setUp(self) -> None:
        self.original_repo = bump_version.REPO
        self.temp_dir = TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        bump_version.REPO = self.repo

    def tearDown(self) -> None:
        bump_version.REPO = self.original_repo
        self.temp_dir.cleanup()

    def _commit(self, message: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=self.repo, check=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, capture_output=True, text=True, check=True
        ).stdout.strip()

    def _write_marketplace(self, payload: dict) -> None:
        mf = self.repo / ".claude-plugin" / "marketplace.json"
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def test_ignores_a_commit_that_only_touches_descriptions(self) -> None:
        self._write_marketplace(
            {"version": "1.0.0", "plugins": [{"name": "rhize-devflow", "version": "1.0.0", "description": "old"}]}
        )
        release_sha = self._commit("release(devflow): 1.0.0")

        self._write_marketplace(
            {"version": "1.0.0", "plugins": [{"name": "rhize-devflow", "version": "1.0.0", "description": "new"}]}
        )
        self._commit("docs(devflow): reword marketplace description")

        self.assertEqual(bump_version.last_release_ref(None), release_sha)

    def test_finds_a_later_commit_that_changed_a_version(self) -> None:
        self._write_marketplace(
            {"version": "1.0.0", "plugins": [{"name": "rhize-devflow", "version": "1.0.0", "description": "old"}]}
        )
        self._commit("release(devflow): 1.0.0")

        self._write_marketplace(
            {"version": "1.0.0", "plugins": [{"name": "rhize-devflow", "version": "1.0.0", "description": "new"}]}
        )
        self._commit("docs(devflow): reword marketplace description")

        self._write_marketplace(
            {"version": "1.1.0", "plugins": [{"name": "rhize-devflow", "version": "1.1.0", "description": "new"}]}
        )
        release_sha = self._commit("release(devflow): 1.1.0")

        self.assertEqual(bump_version.last_release_ref(None), release_sha)


class PluginContractCheckTests(unittest.TestCase):
    def test_runs_impact_map_contract_devflow_suite_and_generated_map_freshness(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="PASS\n", stderr="")
        with patch.object(bump_version.subprocess, "run", return_value=completed) as run:
            errors = bump_version.run_repository_contract_checks()

        self.assertEqual(errors, [])
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                [
                    bump_version.sys.executable,
                    str(ROOT / "tests/rhize-devflow/test_impact_map_contract.py"),
                ],
                [
                    bump_version.sys.executable,
                    "-m",
                    "pytest",
                    str(ROOT / "tests/rhize-devflow"),
                    "-q",
                ],
                [
                    bump_version.sys.executable,
                    str(ROOT / "scripts/validate_skill_map.py"),
                    "--check-stale",
                ],
                [
                    bump_version.sys.executable,
                    str(ROOT / "scripts/validate_plugin_configs.py"),
                ],
            ],
        )

    def test_reports_each_failed_repository_contract(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="FAIL\n", stderr="details\n"
        )
        with patch.object(bump_version.subprocess, "run", return_value=completed):
            errors = bump_version.run_repository_contract_checks()

        self.assertEqual(
            errors,
            [
                "CodeGraph + impact-map contract failed",
                "Dev Flow test suite failed",
                "skill-map freshness failed",
                "Plugin config lint failed",
            ],
        )

    def test_directory_contract_entries_invoke_pytest_as_a_module(self) -> None:
        """Regression coverage for the file-vs-directory detection in
        run_repository_contract_checks() itself, independent of whatever the
        real REPOSITORY_CONTRACTS tuple happens to contain — a directory
        entry must be run via `-m pytest`, never as a plain script."""
        original = bump_version.REPOSITORY_CONTRACTS
        bump_version.REPOSITORY_CONTRACTS = (("Directory contract", "tests/rhize-devflow", "-q"),)
        try:
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            with patch.object(bump_version.subprocess, "run", return_value=completed) as run:
                errors = bump_version.run_repository_contract_checks()
            self.assertEqual(errors, [])
            self.assertEqual(
                run.call_args_list[0].args[0],
                [
                    bump_version.sys.executable,
                    "-m",
                    "pytest",
                    str(ROOT / "tests/rhize-devflow"),
                    "-q",
                ],
            )
        finally:
            bump_version.REPOSITORY_CONTRACTS = original

    def test_file_contract_entries_still_invoke_the_script_directly(self) -> None:
        original = bump_version.REPOSITORY_CONTRACTS
        bump_version.REPOSITORY_CONTRACTS = (
            ("File contract", "scripts/validate_skill_map.py", "--check-stale"),
        )
        try:
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            with patch.object(bump_version.subprocess, "run", return_value=completed) as run:
                errors = bump_version.run_repository_contract_checks()
            self.assertEqual(errors, [])
            self.assertEqual(
                run.call_args_list[0].args[0],
                [
                    bump_version.sys.executable,
                    str(ROOT / "scripts/validate_skill_map.py"),
                    "--check-stale",
                ],
            )
        finally:
            bump_version.REPOSITORY_CONTRACTS = original

    def test_contract_failure_blocks_check_when_release_commit_is_the_base(self) -> None:
        args = SimpleNamespace(since=None)
        with (
            patch.object(bump_version, "last_release_ref", return_value="release"),
            patch.object(bump_version, "changed_dirs", return_value=set()),
            patch.object(
                bump_version,
                "run_repository_contract_checks",
                return_value=["CodeGraph + impact-map contract failed"],
            ),
        ):
            result = bump_version.cmd_check(args, {})

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()

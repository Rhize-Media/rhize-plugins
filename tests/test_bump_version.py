"""Regression tests for dual-host plugin version updates."""

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


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
        self.assertEqual(load(repo / ".claude-plugin/marketplace.json")["version"], "2.28.0")

    def test_keeps_single_manifest_plugins_supported(self) -> None:
        repo = seed_repo(Path(self.temp_dir.name), "legacy-plugin", dual=False)
        bump_version.REPO = repo

        bump_version.apply_bumps({"legacy-plugin": "0.1.0"}, "2.28.0")

        self.assertEqual(load(repo / "legacy-plugin/.claude-plugin/plugin.json")["version"], "0.1.0")
        self.assertFalse((repo / "legacy-plugin/.codex-plugin/plugin.json").exists())


if __name__ == "__main__":
    unittest.main()

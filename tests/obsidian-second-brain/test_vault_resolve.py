"""Tests for the obsidian-second-brain vault-hint path resolution.

Covers vault_resolve.is_vault_path() directly (unit level) and the
vault-write-hint.py / vault-read-hint.py hook scripts as subprocesses
(integration level), proving all three resolution branches --
OBSIDIAN_VAULT_PATH env var, Obsidian's registered vaults
(obsidian.json), and the legacy iCloud default -- actually fire the hint,
and that a path in none of them produces no output.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "obsidian-second-brain"
SCRIPTS_DIR = PLUGIN / "hooks" / "scripts"
WRITE_HOOK = SCRIPTS_DIR / "vault-write-hint.py"
READ_HOOK = SCRIPTS_DIR / "vault-read-hint.py"

SPEC = importlib.util.spec_from_file_location(
    "vault_resolve", SCRIPTS_DIR / "vault_resolve.py"
)
assert SPEC and SPEC.loader
vault_resolve = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = vault_resolve
SPEC.loader.exec_module(vault_resolve)


def run_hook(script: Path, file_path: str, env: dict) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    full_env = dict(os.environ)
    full_env.pop("OBSIDIAN_VAULT_PATH", None)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(script)],
        input=payload,
        capture_output=True,
        text=True,
        env=full_env,
        cwd=tempfile.gettempdir(),  # prove cwd-independence
    )


class IsVaultPathTests(unittest.TestCase):
    """Unit-level coverage of vault_resolve.is_vault_path()."""

    def setUp(self) -> None:
        # Point the module at a config path that does not exist by default,
        # so tests don't depend on (or clobber) this machine's real
        # ~/Library/Application Support/obsidian/obsidian.json.
        self._config_patch = mock.patch.object(
            vault_resolve, "OBSIDIAN_CONFIG_PATH", Path("/nonexistent/obsidian.json")
        )
        self._config_patch.start()
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("OBSIDIAN_VAULT_PATH", None)

    def tearDown(self) -> None:
        self._config_patch.stop()
        self._env_patch.stop()

    def test_a_env_var_vault_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OBSIDIAN_VAULT_PATH"] = tmp
            self.assertTrue(vault_resolve.is_vault_path(f"{tmp}/note.md"))
            # sibling directory sharing a prefix must NOT match
            self.assertFalse(vault_resolve.is_vault_path(f"{tmp}-other/note.md"))

    def test_b_registered_obsidian_vault_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_dir = os.path.join(tmp, "MyVault")
            os.makedirs(vault_dir)
            config_path = Path(tmp) / "obsidian.json"
            config_path.write_text(
                json.dumps(
                    {
                        "vaults": {
                            "abc123": {"path": vault_dir, "ts": 1234567890},
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(vault_resolve, "OBSIDIAN_CONFIG_PATH", config_path):
                self.assertTrue(
                    vault_resolve.is_vault_path(f"{vault_dir}/Notes/note.md")
                )

    def test_c_icloud_default_still_matches_with_nothing_configured(self) -> None:
        icloud_path = (
            "/Users/someone/Library/Mobile Documents/"
            "iCloud~md~obsidian/Documents/Obsidian Vault/Notes/note.md"
        )
        self.assertTrue(vault_resolve.is_vault_path(icloud_path))

    def test_d_path_in_no_vault_does_not_match(self) -> None:
        self.assertFalse(vault_resolve.is_vault_path("/tmp/unrelated/note.md"))

    def test_env_var_takes_precedence_over_registered_vaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_vault = os.path.join(tmp, "EnvVault")
            other_vault = os.path.join(tmp, "OtherVault")
            os.makedirs(env_vault)
            os.makedirs(other_vault)
            config_path = Path(tmp) / "obsidian.json"
            config_path.write_text(
                json.dumps({"vaults": {"x": {"path": other_vault}}}),
                encoding="utf-8",
            )
            os.environ["OBSIDIAN_VAULT_PATH"] = env_vault
            with mock.patch.object(vault_resolve, "OBSIDIAN_CONFIG_PATH", config_path):
                self.assertTrue(vault_resolve.is_vault_path(f"{env_vault}/n.md"))
                # still resolvable via the registered-vaults branch too
                self.assertTrue(vault_resolve.is_vault_path(f"{other_vault}/n.md"))

    def test_multiple_env_var_paths_colon_separated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_a = os.path.join(tmp, "A")
            vault_b = os.path.join(tmp, "B")
            os.makedirs(vault_a)
            os.makedirs(vault_b)
            os.environ["OBSIDIAN_VAULT_PATH"] = f"{vault_a}:{vault_b}"
            self.assertTrue(vault_resolve.is_vault_path(f"{vault_a}/n.md"))
            self.assertTrue(vault_resolve.is_vault_path(f"{vault_b}/n.md"))

    def test_malformed_obsidian_json_fails_silently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "obsidian.json"
            config_path.write_text("{not valid json", encoding="utf-8")
            with mock.patch.object(vault_resolve, "OBSIDIAN_CONFIG_PATH", config_path):
                # must not raise, must just fall through to no-match
                self.assertFalse(vault_resolve.is_vault_path("/tmp/whatever/n.md"))


class ResolveVaultPathsTests(unittest.TestCase):
    """Unit-level coverage of vault_resolve.resolve_vault_paths().

    Shares IsVaultPathTests' isolation setup: a nonexistent config path and a
    cleared OBSIDIAN_VAULT_PATH env var, so results depend only on what each
    test configures -- never on this machine's real Obsidian setup.
    """

    def setUp(self) -> None:
        self._config_patch = mock.patch.object(
            vault_resolve, "OBSIDIAN_CONFIG_PATH", Path("/nonexistent/obsidian.json")
        )
        self._config_patch.start()
        # Isolate from this machine's real iCloud vault too, so the "zero
        # vaults" case is genuinely zero regardless of what's mounted.
        self._icloud_patch = mock.patch.object(
            vault_resolve, "ICLOUD_VAULT_PATH", Path("/nonexistent/icloud-vault")
        )
        self._icloud_patch.start()
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("OBSIDIAN_VAULT_PATH", None)

    def tearDown(self) -> None:
        self._config_patch.stop()
        self._icloud_patch.stop()
        self._env_patch.stop()

    def test_zero_vaults_returns_empty_list(self) -> None:
        self.assertEqual(vault_resolve.resolve_vault_paths(), [])

    def test_one_vault_from_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OBSIDIAN_VAULT_PATH"] = tmp
            self.assertEqual(vault_resolve.resolve_vault_paths(), [tmp])

    def test_multiple_vaults_env_then_registered_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_vault = os.path.join(tmp, "EnvVault")
            other_vault = os.path.join(tmp, "OtherVault")
            os.makedirs(env_vault)
            os.makedirs(other_vault)
            config_path = Path(tmp) / "obsidian.json"
            config_path.write_text(
                json.dumps({"vaults": {"x": {"path": other_vault}}}),
                encoding="utf-8",
            )
            os.environ["OBSIDIAN_VAULT_PATH"] = env_vault
            with mock.patch.object(vault_resolve, "OBSIDIAN_CONFIG_PATH", config_path):
                self.assertEqual(
                    vault_resolve.resolve_vault_paths(), [env_vault, other_vault]
                )

    def test_duplicate_env_and_registered_vault_deduped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_dir = os.path.join(tmp, "SameVault")
            os.makedirs(vault_dir)
            config_path = Path(tmp) / "obsidian.json"
            config_path.write_text(
                json.dumps({"vaults": {"x": {"path": vault_dir}}}),
                encoding="utf-8",
            )
            os.environ["OBSIDIAN_VAULT_PATH"] = vault_dir
            with mock.patch.object(vault_resolve, "OBSIDIAN_CONFIG_PATH", config_path):
                self.assertEqual(vault_resolve.resolve_vault_paths(), [vault_dir])

    def test_duplicate_multiple_env_paths_deduped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OBSIDIAN_VAULT_PATH"] = f"{tmp}:{tmp}"
            self.assertEqual(vault_resolve.resolve_vault_paths(), [tmp])

    def test_icloud_fallback_only_when_path_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icloud_vault = Path(tmp) / "Obsidian Vault"
            icloud_vault.mkdir()
            with mock.patch.object(vault_resolve, "ICLOUD_VAULT_PATH", icloud_vault):
                self.assertEqual(
                    vault_resolve.resolve_vault_paths(), [str(icloud_vault)]
                )

    def test_icloud_fallback_absent_when_path_missing(self) -> None:
        # ICLOUD_VAULT_PATH is patched to a nonexistent path in setUp().
        self.assertEqual(vault_resolve.resolve_vault_paths(), [])

    def test_never_raises_on_malformed_obsidian_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "obsidian.json"
            config_path.write_text("{not valid json", encoding="utf-8")
            with mock.patch.object(vault_resolve, "OBSIDIAN_CONFIG_PATH", config_path):
                self.assertEqual(vault_resolve.resolve_vault_paths(), [])


class HookScriptIntegrationTests(unittest.TestCase):
    """Subprocess-level coverage: the real hook scripts, real stdin/stdout,
    invoked from a different cwd than the script's own directory (mirrors
    how Claude Code invokes them via ${CLAUDE_PLUGIN_ROOT})."""

    def _assert_hint_fires(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.strip(), "expected a hint on stdout")
        payload = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", payload)
        self.assertIn(
            "additionalContext", payload["hookSpecificOutput"]
        )

    def _assert_no_hint(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_write_hook_env_var_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_hook(
                WRITE_HOOK, f"{tmp}/note.md", {"OBSIDIAN_VAULT_PATH": tmp}
            )
            self._assert_hint_fires(result)
            self.assertIn("wikilinks", result.stdout)

    def test_read_hook_env_var_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_hook(
                READ_HOOK, f"{tmp}/note.md", {"OBSIDIAN_VAULT_PATH": tmp}
            )
            self._assert_hint_fires(result)
            self.assertIn("vault-align", result.stdout)

    def test_write_hook_registered_vault_branch(self) -> None:
        with tempfile.TemporaryDirectory() as fake_home:
            vault_dir = os.path.join(fake_home, "MyVault")
            os.makedirs(vault_dir)
            obsidian_dir = os.path.join(
                fake_home, "Library", "Application Support", "obsidian"
            )
            os.makedirs(obsidian_dir)
            with open(os.path.join(obsidian_dir, "obsidian.json"), "w") as f:
                json.dump({"vaults": {"x": {"path": vault_dir}}}, f)

            result = run_hook(
                WRITE_HOOK, f"{vault_dir}/note.md", {"HOME": fake_home}
            )
            self._assert_hint_fires(result)

    def test_write_hook_icloud_default_branch(self) -> None:
        icloud_path = (
            "/Users/someone/Library/Mobile Documents/"
            "iCloud~md~obsidian/Documents/Obsidian Vault/Notes/note.md"
        )
        result = run_hook(WRITE_HOOK, icloud_path, {})
        self._assert_hint_fires(result)

    def test_write_hook_no_match_produces_no_output(self) -> None:
        result = run_hook(WRITE_HOOK, "/tmp/unrelated/note.md", {})
        self._assert_no_hint(result)

    def test_write_hook_non_md_file_produces_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_hook(
                WRITE_HOOK, f"{tmp}/note.txt", {"OBSIDIAN_VAULT_PATH": tmp}
            )
            self._assert_no_hint(result)


if __name__ == "__main__":
    unittest.main()

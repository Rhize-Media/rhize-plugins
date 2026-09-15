"""Tests for hooks/session-start-env.sh — exports PROCEDURAL_MEMORY_PLUGIN_ROOT via CLAUDE_ENV_FILE.

Background (measured 2026-09-15): Claude Code substitutes ${CLAUDE_PLUGIN_ROOT} into plugin
config text at load time but never exports it to the Bash tool's environment, so shell
commands that name the launcher through the variable expand to `/scripts/...`. Hook
processes do receive CLAUDE_PLUGIN_ROOT, and SessionStart hooks receive CLAUDE_ENV_FILE,
whose contents are loaded into later Bash tool calls. This hook bridges the two.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "procedural-memory"
HOOK = PLUGIN / "hooks/session-start-env.sh"

# Same discipline as the other hook tests: run under every POSIX shell present and require
# identical behaviour, so dash (Debian/Ubuntu /bin/sh, macOS 15+) is exercised wherever it exists.
SHELLS = ["/bin/sh"] + [s for s in ("/bin/dash", "/usr/bin/dash") if Path(s).exists()]


def run_hook(shell: str, env_extra: dict[str, str], unset: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_ENV_FILE", "CLAUDE_PLUGIN_ROOT", *unset)}
    env.update(env_extra)
    return subprocess.run([shell, str(HOOK)], env=env, capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("shell", SHELLS)
def test_exports_runner_supplied_root(shell: str, tmp_path: Path) -> None:
    env_file = tmp_path / "sessionstart-hook-0.sh"
    root = tmp_path / "plugin root with space"
    root.mkdir()
    result = run_hook(shell, {"CLAUDE_ENV_FILE": str(env_file), "CLAUDE_PLUGIN_ROOT": str(root)})
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert env_file.read_text() == f"export PROCEDURAL_MEMORY_PLUGIN_ROOT='{root}'\n"
    # The line must round-trip through a real shell to the same value.
    echoed = subprocess.run(
        [shell, "-c", f". '{env_file}'; printf '%s' \"$PROCEDURAL_MEMORY_PLUGIN_ROOT\""],
        capture_output=True, text=True, timeout=10,
    )
    assert echoed.stdout == str(root)


@pytest.mark.parametrize("shell", SHELLS)
def test_falls_back_to_script_relative_root_when_variable_withheld(shell: str, tmp_path: Path) -> None:
    env_file = tmp_path / "sessionstart-hook-0.sh"
    result = run_hook(shell, {"CLAUDE_ENV_FILE": str(env_file)})
    assert result.returncode == 0, result.stderr
    exported = env_file.read_text()
    assert exported == f"export PROCEDURAL_MEMORY_PLUGIN_ROOT='{PLUGIN.resolve()}'\n"


@pytest.mark.parametrize("shell", SHELLS)
def test_no_env_file_means_no_output_and_exit_zero(shell: str, tmp_path: Path) -> None:
    result = run_hook(shell, {"CLAUDE_PLUGIN_ROOT": str(tmp_path)})
    assert result.returncode == 0
    assert result.stdout == "" and result.stderr == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("shell", SHELLS)
def test_single_quote_in_root_is_escaped_and_round_trips(shell: str, tmp_path: Path) -> None:
    env_file = tmp_path / "sessionstart-hook-0.sh"
    root = tmp_path / "it's a root"
    root.mkdir()
    result = run_hook(shell, {"CLAUDE_ENV_FILE": str(env_file), "CLAUDE_PLUGIN_ROOT": str(root)})
    assert result.returncode == 0, result.stderr
    echoed = subprocess.run(
        [shell, "-c", f". '{env_file}'; printf '%s' \"$PROCEDURAL_MEMORY_PLUGIN_ROOT\""],
        capture_output=True, text=True, timeout=10,
    )
    assert echoed.returncode == 0, echoed.stderr
    assert echoed.stdout == str(root)


def test_hook_is_wired_as_session_start_with_quoted_root() -> None:
    doc = json.loads((PLUGIN / "hooks/hooks.json").read_text())
    entries = doc["hooks"]["SessionStart"]
    commands = [h["command"] for group in entries for h in group["hooks"]]
    assert any('"${CLAUDE_PLUGIN_ROOT}/hooks/session-start-env.sh"' in c for c in commands), commands
    assert os.access(HOOK, os.X_OK)

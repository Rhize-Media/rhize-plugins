"""Pytest wrapper for test_refactor_gate_config_scope.sh.

The shell test is the suite of record for the config-only exemption in
refactor_gate.py (see that script's own header for what it exercises). This
wrapper just makes it collectible by `pytest`, running it via subprocess and
asserting a clean exit; the shell script's own assertions carry the real
signal, and its stdout/stderr is surfaced on failure for debugging.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve().parent / "test_refactor_gate_config_scope.sh"


def test_refactor_gate_config_scope_shell_suite() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available on this host")

    result = subprocess.run(
        [bash, str(SCRIPT)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"test_refactor_gate_config_scope.sh failed (exit {result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )

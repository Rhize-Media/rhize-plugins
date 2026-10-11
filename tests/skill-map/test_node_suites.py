"""Run every repo Node test suite (tests/**/test_*.js) under pytest so CI executes them.

Each suite is a standalone script that exits non-zero on failure. Skips (does not fail) when no
`node` binary is on PATH, matching the other node-dependent tests in this directory.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SUITES = sorted(p for p in (REPO / 'tests').rglob('test_*.js') if 'node_modules' not in p.parts)
NODE = shutil.which('node')


@pytest.mark.skipif(NODE is None, reason='node not on PATH')
@pytest.mark.parametrize('suite', SUITES, ids=lambda p: str(p.relative_to(REPO)))
def test_node_suite(suite):
    result = subprocess.run([NODE, str(suite)], cwd=REPO, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f'{suite.name} failed:\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}'

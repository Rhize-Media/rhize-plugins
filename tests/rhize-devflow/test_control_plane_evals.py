#!/usr/bin/env python3
"""Pytest wrapper for evals/rhize-devflow/run_evals.py (Task 9 of the Dev Flow
3.0 control-plane plan -- see
.claude/plans/rhize-devflow-v3-engineering-control-plane.md,
"Task 9 -- Add evals, usage measures, and release enforcement").

Runs the deterministic control-plane eval suite -- trigger-precision heuristic
+ quality-assertion fixtures against check.md/review.md, plus a keyword-drift
check -- as part of the normal `python3 -m pytest tests/ -q` run, so a
regression here fails the suite the same way any other test would. No live
model calls are made (see evals/rhize-devflow/README.md for why: the plan
forbids live paid-service calls in automated tests).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_EVALS = REPO_ROOT / "evals" / "rhize-devflow" / "run_evals.py"

assert RUN_EVALS.is_file(), f"missing {RUN_EVALS}"


def test_devflow_control_plane_evals_pass() -> None:
    result = subprocess.run(
        [sys.executable, str(RUN_EVALS), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "evals/rhize-devflow/run_evals.py failed (see evals/results/ for the "
        f"latest report):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


if __name__ == "__main__":
    sys.exit(0 if subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"]).returncode == 0 else 1)

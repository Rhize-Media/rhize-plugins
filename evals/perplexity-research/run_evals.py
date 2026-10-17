#!/usr/bin/env python3
"""Run only the free, offline Perplexity regression suite."""
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    raise SystemExit(subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/perplexity-research"],
        cwd=Path(__file__).resolve().parents[2], timeout=110,
    ).returncode)

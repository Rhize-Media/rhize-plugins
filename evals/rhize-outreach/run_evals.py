#!/usr/bin/env python3
"""Run deterministic tests for the Rhize Outreach plugin installer and wizard."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "tests" / "rhize-outreach" / "setup.test.mjs"
result = subprocess.run(
    ["node", "--test", str(TEST)],
    cwd=ROOT,
    capture_output=True,
    text=True,
    check=False,
)
report = {
    "outcome": "PASS" if result.returncode == 0 else "FAIL",
    "checks": 5,
    "summary": (result.stdout + result.stderr).strip(),
}
print(json.dumps(report, indent=2))
raise SystemExit(result.returncode)

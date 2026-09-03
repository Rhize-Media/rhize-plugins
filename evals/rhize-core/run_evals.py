#!/usr/bin/env python3
"""evals/rhize-core/run_evals.py -- free offline coverage gate for the rhize-core plugin
(the marketplace control plane: the fleet setup wizard and its four platform scripts).

rhize-core ships no skills, so there is no routing/collision contract to grade the way
evals/parallel-agent-skills/scripts/evaluate_ops_skills.py grades rhize-ops' skills. What
this suite CAN grade offline and for free is the platform's own test suite (schema
validation, the setup orchestrator, the artifacts renderer, git-preflight, and the
rhize-ops fallback drift/self-containment contract) -- so it runs `pytest tests/rhize-core
-q` via subprocess and reports the result in the same JSON shape evaluate_ops_skills.py
emits (schema_version, evaluation, status, failures, limitations), so the central
evaluation-catalog.json runner contract stays uniform across components.

Usage:
    python3 evals/rhize-core/run_evals.py            # human-readable summary
    python3 evals/rhize-core/run_evals.py --json      # machine-readable report
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_TARGET = "tests/rhize-core"


def run_pytest() -> tuple[int, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_TARGET, "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, (completed.stdout + completed.stderr)


def evaluate() -> dict:
    exit_code, output = run_pytest()
    passed = exit_code == 0
    tail_lines = output.strip().splitlines()[-40:]
    return {
        "schema_version": 1,
        "evaluation": "rhize-core-platform-test-suite",
        "status": "pass" if passed else "fail",
        "exit_code": exit_code,
        "output_tail": tail_lines,
        "failures": [] if passed else [f"{TEST_TARGET}: pytest exited {exit_code}"],
        "limitations": [
            "Grades that the platform's own offline test suite passes -- schema validation, "
            "the setup orchestrator, the artifacts renderer, git-preflight, and the "
            "rhize-ops fallback drift/self-containment contract. It does not exercise the "
            "wizard's interactive AskUserQuestion phases or any live/paid/networked effect.",
        ],
    }


def print_report(result: dict) -> None:
    print("=" * 60)
    print("rhize-core platform test suite")
    print("=" * 60)
    print(f"\n-- pytest {TEST_TARGET} --")
    for line in result["output_tail"]:
        print(f"  {line}")
    print("\n" + "=" * 60)
    print("RESULT:", "PASS" if result["status"] == "pass" else "FAIL")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable JSON report instead of text")
    args = parser.parse_args()

    result = evaluate()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

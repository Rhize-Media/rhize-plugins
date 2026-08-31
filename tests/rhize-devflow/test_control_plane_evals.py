#!/usr/bin/env python3
"""Pytest wrapper for evals/rhize-devflow/run_evals.py (Task 9 of the Dev Flow
3.0 control-plane plan -- see
.claude/plans/rhize-devflow-v3-engineering-control-plane.md,
"Task 9 -- Add evals, usage measures, and release enforcement").

Runs the deterministic control-plane eval suite -- trigger-precision heuristic
+ quality-assertion fixtures against check.md/review.md and the canonical simplify/promotion
skills, plus a keyword-drift
check -- as part of the normal `python3 -m pytest tests/ -q` run, so a
regression here fails the suite the same way any other test would. No live
model calls are made (see evals/rhize-devflow/README.md for why: the plan
forbids live paid-service calls in automated tests).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_EVALS = REPO_ROOT / "evals" / "rhize-devflow" / "run_evals.py"

assert RUN_EVALS.is_file(), f"missing {RUN_EVALS}"


def load_eval_module():
    spec = importlib.util.spec_from_file_location("rhize_devflow_evals", RUN_EVALS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_devflow_control_plane_evals_pass() -> None:
    result = subprocess.run(
        [sys.executable, str(RUN_EVALS), "--json", "--no-write"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "evals/rhize-devflow/run_evals.py failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    report = json.loads(result.stdout)
    assert report["coverage"]["ok"] is True
    assert len(report["coverage"]["discoveredSkills"]) == 9
    assert len(report["coverage"]["qualitySkills"]) == 9
    assert report["benchmark"]["ok"] is True
    assert report["benchmark"]["skillCount"] == 9


def test_benchmark_contract_rejects_ambiguous_or_swapped_arms() -> None:
    module = load_eval_module()
    document = module.load_json(REPO_ROOT / "evals/rhize-devflow/benchmark_contracts.json")
    malformed = copy.deepcopy(document)
    malformed["skills"][0]["armA"]["implementation"] = "Use an unspecified baseline."
    malformed["skills"][0]["armA"]["variant"] = malformed["skills"][0]["armB"]["variant"]
    result = module.validate_benchmark_contracts(malformed)
    assert result["ok"] is False
    assert any("exact non-plugin path" in problem for problem in result["problems"])
    assert any("variants must be distinct" in problem for problem in result["problems"])


def test_benchmark_contract_rejects_missing_metrics_and_fabricated_evidence() -> None:
    module = load_eval_module()
    document = module.load_json(REPO_ROOT / "evals/rhize-devflow/benchmark_contracts.json")
    malformed = copy.deepcopy(document)
    malformed["commonMetrics"] = [
        metric for metric in malformed["commonMetrics"] if metric["name"] != "failures_refusals"
    ]
    malformed["evidenceRules"]["fabricatedEvidence"] = "allowed"
    result = module.validate_benchmark_contracts(malformed)
    assert result["ok"] is False
    assert any("failures_refusals" in problem for problem in result["problems"])
    assert any("fabricated benchmark evidence" in problem for problem in result["problems"])


if __name__ == "__main__":
    sys.exit(0 if subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"]).returncode == 0 else 1)

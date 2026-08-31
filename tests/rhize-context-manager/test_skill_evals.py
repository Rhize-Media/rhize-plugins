from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "evals" / "rhize-context-manager" / "run_evals.py"


def load_eval_module():
    spec = importlib.util.spec_from_file_location("rhize_context_manager_evals", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_context_manager_skills_have_runnable_eval_contracts() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"context-manager skill evals failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert len(report["coverage"]["discoveredSkills"]) == 16
    assert len(report["coverage"]["routingSkills"]) == 16
    assert len(report["coverage"]["qualitySkills"]) == 16
    assert report["routing"]["totalCases"] == 48
    assert report["benchmark"]["skillCount"] == 16
    assert report["benchmark"]["naturalCaptureRules"] == {
        "receiptSource": "real_redacted_only",
        "fabricatedReceipts": "forbidden",
        "dateOnlyOrdering": "indeterminate",
        "incompleteCohort": "indeterminate",
        "nonComparableCohort": "indeterminate",
        "strictOrderingEvidence": "timestamped_run_bound_receipt",
        "missingMeasurements": "remain_missing",
    }


def test_benchmark_contract_rejects_ambiguous_or_swapped_arms() -> None:
    module = load_eval_module()
    document = module.load_json(
        REPO_ROOT / "evals/rhize-context-manager/benchmark_contracts.json"
    )
    malformed = copy.deepcopy(document)
    malformed["skills"][0]["armA"]["implementation"] = "Use an unspecified baseline."
    malformed["skills"][0]["armA"]["variant"] = malformed["skills"][0]["armB"]["variant"]
    result = module.validate_benchmark_contracts(malformed)
    assert result["ok"] is False
    assert any("exact non-plugin path" in problem for problem in result["problems"])
    assert any("variants must be distinct" in problem for problem in result["problems"])


def test_benchmark_contract_preserves_natural_evidence_indeterminacy() -> None:
    module = load_eval_module()
    document = module.load_json(
        REPO_ROOT / "evals/rhize-context-manager/benchmark_contracts.json"
    )
    malformed = copy.deepcopy(document)
    malformed["naturalCaptureRules"]["dateOnlyOrdering"] = "strict"
    malformed["naturalCaptureRules"]["nonComparableCohort"] = "exclude"
    result = module.validate_benchmark_contracts(malformed)
    assert result["ok"] is False
    assert any("dateOnlyOrdering" in problem for problem in result["problems"])
    assert any("nonComparableCohort" in problem for problem in result["problems"])

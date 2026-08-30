from __future__ import annotations

import sys
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL_ROOT))

from run_native_context_evals import build_report, evaluate_gate, load_cases  # noqa: E402


def test_native_corpus_covers_required_language_and_risk_classes() -> None:
    cases = load_cases(EVAL_ROOT / "native_cases.json")["cases"]
    assert len(cases) == 5
    assert {case["languageClass"] for case in cases} == {
        "typescript", "javascript", "python", "mixed", "javascript-dynamic"
    }
    assert any(case["expectedAccepted"] is False for case in cases)


def test_native_gate_requires_noninferiority_and_material_reduction() -> None:
    passing = [
        {"acceptedForUse": True, "passed": True, "criticalEntriesMissing": [], "reductionPercent": 40.0}
        for _ in range(4)
    ]
    passing.append(
        {"acceptedForUse": False, "passed": True, "criticalEntriesMissing": [], "reductionPercent": 0.0}
    )
    assert evaluate_gate(passing)["decision"] == "continue_to_explicit_dogfood"
    passing[0]["criticalEntriesMissing"] = ["critical.ts"]
    assert evaluate_gate(passing)["decision"] == "pause"


def test_real_native_provider_passes_the_fixed_corpus() -> None:
    report = build_report(EVAL_ROOT / "native_cases.json")
    assert report["provider"]["ready"] is True
    assert report["corpus"]["totalCompiledContextCaseCount"] == 14
    assert report["gate"]["decision"] == "continue_to_explicit_dogfood"
    assert all(row["providerRevision"] == "rhize-native-context-pack-v2" for row in report["results"])

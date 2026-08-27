from __future__ import annotations

import sys
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL_ROOT))

from run_context_evals import evaluate_gate, load_cases, resolve_repository  # noqa: E402


def test_phase_three_cases_cover_supported_and_adversarial_dependency_patterns() -> None:
    cases = load_cases(EVAL_ROOT / "cases.json")
    assert len(cases) == 9
    assert {case["kind"] for case in cases} == {"supported", "adversarial"}
    assert {case["fixture"] for case in cases if case["fixture"]} == {
        "static-alias",
        "static-direct",
        "duplicate-names",
        "dynamic-dispatch",
        "decorator-event",
        "callback-registration",
        "unsupported-syntax",
    }


def test_phase_three_gate_requires_real_supported_success_and_safe_adversarial_handling() -> None:
    passing = [
        {
            "id": "supported",
            "kind": "supported",
            "passed": True,
            "acceptedForInjection": True,
            "reproduciblePack": True,
            "criticalEntriesMissing": [],
        },
        {
            "id": "adversarial",
            "kind": "adversarial",
            "passed": True,
            "acceptedForInjection": False,
            "reproduciblePack": True,
            "criticalEntriesMissing": ["hidden.py"],
        },
    ]
    assert evaluate_gate(passing)["decision"] == "continue_to_phase_4"

    unsafe = [*passing[:1], {**passing[1], "passed": False, "acceptedForInjection": True}]
    assert evaluate_gate(unsafe)["decision"] == "pause"


def test_invalid_python_fixture_is_materialized_only_in_the_temporary_eval_repository() -> None:
    case = next(
        case
        for case in load_cases(EVAL_ROOT / "cases.json")
        if case["id"] == "fixture-unsupported-syntax-fallback"
    )
    source = EVAL_ROOT / "fixtures" / "context-compiler" / "unsupported-syntax"
    assert not (source / "legacy_broken.py").exists()

    with resolve_repository(case, Path("/unused-upstream")) as (repo, snapshot):
        assert (repo / "legacy_broken.py").read_text(encoding="utf-8") == "def incomplete(\n"
        assert snapshot.startswith("fixture-")

    assert not (source / "legacy_broken.py").exists()

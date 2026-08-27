"""Non-benchmark tests for retrieval receipt parsing, math, and corpus validation.

The command outputs below are fixtures only. They never execute a retrieval provider and
must not be counted as Phase 1.5 benchmark or dogfood evidence.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPO_ROOT / "evals" / "context-tools" / "run_retrieval_evals.py"
CASES_PATH = REPO_ROOT / "evals" / "context-tools" / "retrieval_cases.json"

SPEC = importlib.util.spec_from_file_location("run_retrieval_evals", RUNNER_PATH)
assert SPEC and SPEC.loader
retrieval_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = retrieval_eval
SPEC.loader.exec_module(retrieval_eval)


# Sanitized command-output fixtures only; these are not benchmark results.
NON_BENCHMARK_RG_OUTPUT = b"\n".join(
    [
        b'{"type":"begin","data":{"path":{"text":"src/router.py"}}}',
        b'{"type":"match","data":{"path":{"text":"src/router.py"},"lines":{"text":"fixture source that must be discarded\\n"},"line_number":12,"absolute_offset":42,"submatches":[]}}',
        b'{"type":"match","data":{"path":{"text":"src/router.py"},"lines":{"text":"another fixture line\\n"},"line_number":18,"absolute_offset":99,"submatches":[]}}',
        b'{"type":"match","data":{"path":{"text":"tests/test_router.py"},"lines":{"text":"fixture test body\\n"},"line_number":7,"absolute_offset":14,"submatches":[]}}',
        b'{"type":"end","data":{"path":{"text":"tests/test_router.py"},"binary_offset":null,"stats":{}}}',
    ]
)

def test_checked_in_corpus_is_reviewed_and_all_fixture_paths_exist() -> None:
    document = retrieval_eval.load_corpus(CASES_PATH, REPO_ROOT)
    assert document["review"]["status"] == "reviewed"
    assert len(document["cases"]) == 6
    assert all(case["baselineRgGlobs"] for case in document["cases"])
    assert all(case["baselineRgPatterns"] for case in document["cases"])
    assert all(case["groundTruth"] for case in document["cases"])


def test_corpus_validation_rejects_absolute_ground_truth_paths() -> None:
    document = json.loads(CASES_PATH.read_text())
    invalid = copy.deepcopy(document)
    invalid["cases"][0]["groundTruth"][0]["path"] = "/private/source.py"
    with pytest.raises(retrieval_eval.CorpusError, match="repository-relative"):
        retrieval_eval.validate_corpus(invalid, REPO_ROOT)


def test_corpus_validation_rejects_private_looking_intent() -> None:
    document = json.loads(CASES_PATH.read_text())
    invalid = copy.deepcopy(document)
    invalid["cases"][0]["intent"] = "Find the provider call with api_key=fixture-secret-value"
    with pytest.raises(retrieval_eval.CorpusError, match="private-looking"):
        retrieval_eval.validate_corpus(invalid, REPO_ROOT)


def test_parse_rg_command_fixture_deduplicates_paths_and_drops_source() -> None:
    candidates = retrieval_eval.parse_rg_json(NON_BENCHMARK_RG_OUTPUT, REPO_ROOT)
    assert candidates == [
        {"path": "src/router.py", "lineStart": 12, "lineEnd": 12},
        {"path": "tests/test_router.py", "lineStart": 7, "lineEnd": 7},
    ]
    serialized = json.dumps(candidates)
    assert "fixture source" not in serialized
    assert "fixture test body" not in serialized


def test_grepai_eval_uses_reviewed_adapter_and_retains_metadata_only() -> None:
    observed = {}

    class CandidateFixture:
        def to_dict(self):
            return {"path": "src/router.py", "score": 0.875, "startLine": 10, "endLine": 20}

    class AdapterFixture:
        def search(self, repo, query, *, limit, timeout):
            observed.update(repo=repo, query=query, limit=limit, timeout=timeout)
            return SimpleNamespace(candidates=(CandidateFixture(),), result_bytes=321)

    row = retrieval_eval.run_grepai_case(
        {
            "id": "fixture-case",
            "intent": "Public fixture intent for command-output unit testing",
            "groundTruth": [{"path": "src/router.py", "critical": True}],
        },
        REPO_ROOT,
        AdapterFixture(),
        "grepai fixture",
        {"commit": "a" * 40, "dirtyTreeHash": None},
        5,
        30,
    )
    assert row["status"] == "completed"
    assert row["resultBytes"] == 321
    assert row["candidates"] == [
        {"path": "src/router.py", "score": 0.875, "startLine": 10, "endLine": 20}
    ]
    assert observed == {
        "repo": REPO_ROOT,
        "query": row["query"],
        "limit": 5,
        "timeout": 30,
    }


def test_grepai_adapter_failure_produces_failed_non_evidence() -> None:
    class FailingAdapter:
        def search(self, *args, **kwargs):
            raise RuntimeError("private provider detail")

    row = retrieval_eval.run_grepai_case(
        {
            "id": "fixture-case",
            "intent": "Public fixture intent for adapter failure testing",
            "groundTruth": [{"path": "src/router.py", "critical": True}],
        },
        REPO_ROOT,
        FailingAdapter(),
        "grepai fixture",
        {"commit": "a" * 40, "dirtyTreeHash": None},
        5,
        30,
    )
    assert row["status"] == "failed"
    assert row["errorReason"] == "provider_search_failed"
    assert row["candidateCount"] is None
    assert "private provider detail" not in json.dumps(row)


def test_top_k_math_uses_k_as_precision_denominator_and_reports_misses() -> None:
    candidates = retrieval_eval.parse_rg_json(NON_BENCHMARK_RG_OUTPUT, REPO_ROOT)
    truth = [
        {"path": "src/router.py", "critical": True},
        {"path": "src/missing.py", "critical": True},
        {"path": "tests/test_router.py", "critical": False},
    ]
    metrics = retrieval_eval.top_k_metrics(candidates, truth, 5)
    assert metrics == {
        "topK": 5,
        "returnedAtK": 2,
        "relevantAtK": 2,
        "precisionAtK": 0.4,
        "recallAtK": 0.666667,
        "misses": ["src/missing.py"],
        "criticalMisses": ["src/missing.py"],
    }


def test_skipped_provider_is_not_aggregated_as_evidence() -> None:
    snapshot = {"commit": "a" * 40, "dirtyTreeHash": None}
    case = {
        "id": "fixture-case",
        "intent": "Public fixture intent for parser-only unit testing",
    }
    baseline = {
        **retrieval_eval._base_row(
            case, retrieval_eval.PROVIDER_SPECS["baseline"], "ripgrep fixture", snapshot
        ),
        "status": "completed",
        "elapsedMs": 12.5,
        "precisionAtK": 0.4,
        "recallAtK": 1.0,
        "criticalMisses": [],
    }
    skipped = retrieval_eval.skipped_row(
        case,
        retrieval_eval.PROVIDER_SPECS["grepai"],
        "grepai fixture",
        snapshot,
        "provider_unavailable",
    )
    summary = retrieval_eval.summarize_results([baseline, skipped])
    assert summary["evidenceRows"] == 1
    assert summary["skippedRows"] == 1
    by_provider = {row["provider"]: row for row in summary["byProvider"]}
    assert by_provider["ripgrep"]["completedCases"] == 1
    assert by_provider["grepai-local"]["completedCases"] == 0
    assert by_provider["grepai-local"]["meanRecallAtK"] is None


def test_local_correctness_gate_pauses_on_critical_miss() -> None:
    summary = {
        "byProvider": [
            {
                "arm": "A",
                "provider": "ripgrep",
                "completedCases": 6,
                "failedCases": 0,
                "skippedCases": 0,
                "meanRecallAtK": 1.0,
                "totalCriticalMisses": 0,
            },
            {
                "arm": "B-local",
                "provider": "grepai-local",
                "completedCases": 6,
                "failedCases": 0,
                "skippedCases": 0,
                "meanRecallAtK": 0.25,
                "totalCriticalMisses": 5,
            },
        ]
    }

    gate = retrieval_eval.evaluate_local_correctness_gate(summary)

    assert gate["decision"] == "pause"
    assert gate["reasons"] == [
        "candidate_has_critical_misses",
        "candidate_recall_below_baseline",
    ]


def test_local_correctness_gate_refuses_incomplete_pair() -> None:
    gate = retrieval_eval.evaluate_local_correctness_gate({"byProvider": []})
    assert gate == {
        "policyVersion": retrieval_eval.LOCAL_GATE_POLICY_VERSION,
        "decision": "not_evaluable",
        "reasons": ["paired_provider_evidence_missing"],
    }


def test_rendered_report_is_stably_sorted_and_newline_terminated() -> None:
    report = {"z": 1, "a": {"d": 2, "b": 1}}
    first = retrieval_eval.render_report(report)
    second = retrieval_eval.render_report(report)
    assert first == second
    assert first.startswith('{\n  "a"')
    assert first.endswith("\n")

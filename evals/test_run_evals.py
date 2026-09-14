"""Offline contract tests for the live Claude eval harness."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

EVALS_DIR = Path(__file__).parent
sys.path.insert(0, str(EVALS_DIR))
import aggregate_results  # noqa: E402
import run_evals  # noqa: E402


def terminal(*, result="done", usage=None, model="claude-test"):
    payload = {"type": "result", "result": result, "num_turns": 2, "model": model}
    if usage is not None:
        payload["usage"] = usage
    return json.dumps(payload) + "\n"


def test_run_claude_preserves_reported_zero_usage():
    usage = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0}
    completed = subprocess.CompletedProcess(["claude"], 0, terminal(usage=usage), "")
    with patch.object(run_evals.subprocess, "run", return_value=completed):
        result = run_evals.run_claude("hello", "/tmp", extra_args=["--model", "test-model", "--variant", "candidate"])
    assert result["valid"] is True
    assert result["tokens"] == 0
    assert result["tokens_unavailable_reason"] is None
    assert result["metadata"]["model"] == "claude-test"
    assert result["metadata"]["requested_model"] == "test-model"
    assert result["metadata"]["variant"] == "candidate"
    assert len(result["metadata"]["prompt_sha256"]) == 64


def test_run_claude_marks_nonzero_exit_without_terminal_invalid():
    completed = subprocess.CompletedProcess(["claude"], 1, "", "fixture authentication failure")
    with patch.object(run_evals.subprocess, "run", return_value=completed):
        result = run_evals.run_claude("hello", "/tmp")
    assert result["valid"] is False
    assert result["invalid_reason"] == "nonzero_exit:1"
    assert result["tokens"] is None
    assert result["tokens_unavailable_reason"] == "missing_terminal_result"


def test_run_claude_marks_timeout_and_missing_or_malformed_terminal_invalid():
    with patch.object(run_evals.subprocess, "run", side_effect=subprocess.TimeoutExpired(["claude"], 300)):
        timeout = run_evals.run_claude("hello", "/tmp")
    assert timeout["valid"] is False
    assert timeout["invalid_reason"] == "timeout"
    assert timeout["tokens"] is None

    completed = subprocess.CompletedProcess(["claude"], 0, '{"type":"result"\n', "")
    with patch.object(run_evals.subprocess, "run", return_value=completed):
        malformed = run_evals.run_claude("hello", "/tmp")
    assert malformed["valid"] is False
    assert malformed["invalid_reason"] == "missing_terminal_result"

    incomplete = subprocess.CompletedProcess(["claude"], 0, json.dumps({"type": "result", "num_turns": 1}) + "\n", "")
    with patch.object(run_evals.subprocess, "run", return_value=incomplete):
        malformed_terminal = run_evals.run_claude("hello", "/tmp")
    assert malformed_terminal["valid"] is False
    assert malformed_terminal["invalid_reason"] == "malformed_terminal_result"


def test_run_claude_keeps_valid_run_when_usage_is_not_exposed():
    completed = subprocess.CompletedProcess(["claude"], 0, terminal(), "")
    with patch.object(run_evals.subprocess, "run", return_value=completed):
        result = run_evals.run_claude("hello", "/tmp")
    assert result["valid"] is True
    assert result["tokens"] is None
    assert result["tokens_unavailable_reason"] == "missing_usage"


def test_trigger_metrics_exclude_invalid_negative_runs(monkeypatch):
    invalid = {"output": "", "tool_calls": [], "duration_ms": 1, "tokens": None, "num_turns": None, "error": "failed", "valid": False, "invalid_reason": "nonzero_exit:1", "tokens_unavailable_reason": "missing_terminal_result", "metadata": {}}
    monkeypatch.setattr(run_evals, "run_claude", lambda *args, **kwargs: invalid)
    result = run_evals.run_trigger_evals([{"id": "negative", "prompt": "x", "target_skill": "skill", "should_trigger": False}], 1, None, False)
    case = result["evals"][0]
    stats = result["summary"]["skill"]
    assert case["trigger_rate"] is None and case["correct"] is None
    assert stats["true_negatives"] == 0
    assert stats["precision"] is None and stats["recall"] is None


def test_quality_metrics_exclude_partial_and_all_invalid_runs(monkeypatch):
    valid = {"output": "yes", "tool_calls": [], "duration_ms": 10, "tokens": 0, "num_turns": 1, "error": None, "valid": True, "invalid_reason": None, "tokens_unavailable_reason": None, "metadata": {}}
    invalid = {**valid, "valid": False, "tokens": None, "invalid_reason": "timeout", "tokens_unavailable_reason": "timeout"}
    responses = iter([valid, invalid])
    monkeypatch.setattr(run_evals, "run_claude", lambda *args, **kwargs: next(responses))
    result = run_evals.run_quality_evals([{"id": "quality", "prompt": "x", "assertions": [{"type": "contains", "value": "yes"}]}], 2, None, False, False)
    config = result["evals"][0]["configs"]["with_plugin"]
    assert config["mean_pass_rate"] == 1.0
    assert config["mean_tokens"] == 0
    assert config["coverage"] == {"total_runs": 2, "valid_runs": 1, "invalid_runs": 1}

    monkeypatch.setattr(run_evals, "run_claude", lambda *args, **kwargs: invalid)
    all_invalid = run_evals.run_quality_evals([{"id": "quality", "prompt": "x", "assertions": []}], 1, None, False, False)
    assert all_invalid["summary"]["with_plugin"]["overall_pass_rate"] is None


def test_reports_and_aggregate_accept_legacy_and_unavailable_metrics():
    trigger = {"evals": [{"id": "old", "correct": True, "trigger_rate": 1.0, "should_trigger": True}], "summary": {"skill": {"precision": None, "recall": None, "f1": None, "true_positives": 0, "false_positives": 0, "true_negatives": 0, "false_negatives": 0}}}
    quality = {"evals": [{"id": "q", "prompt": "x", "configs": {"with_plugin": {"mean_pass_rate": None, "mean_duration_ms": None, "mean_tokens": None, "runs": [{"grading": None}]}}}], "summary": {"with_plugin": {"overall_pass_rate": None}}}
    report = aggregate_results.generate_aggregate_report(trigger, quality, ["legacy.json"], "now")
    assert "unavailable" in report
    legacy = aggregate_results.merge_quality_results([
        {"quality": {"evals": [], "summary": {"with_plugin": {"overall_pass_rate": 0}}}}
    ])
    assert legacy["summary"]["with_plugin"]["overall_pass_rate"] == 0
    current = aggregate_results.merge_quality_results([
        {"plugins": {"plugin": {"quality": {"evals": [], "summary": {"with_plugin": {"overall_pass_rate": 1}}}}}}
    ])
    assert current["summary"]["with_plugin"]["overall_pass_rate"] == 1

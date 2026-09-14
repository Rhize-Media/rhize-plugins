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
    with patch.object(run_evals.subprocess, "run", return_value=completed) as mocked_run:
        result = run_evals.run_claude(
            "hello",
            "/tmp",
            extra_args=["--model", "test-model", "--effort", "high"],
            eval_metadata={"variant": "candidate"},
        )
    assert result["valid"] is True
    assert result["tokens"] == 0
    assert result["tokens_unavailable_reason"] is None
    assert result["metadata"]["model"] == "claude-test"
    assert result["metadata"]["requested_model"] == "test-model"
    assert result["metadata"]["requested_reasoning"] == "high"
    assert result["metadata"]["variant"] == "candidate"
    assert len(result["metadata"]["prompt_sha256"]) == 64
    assert "--variant" not in mocked_run.call_args.args[0]


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
    assert malformed["invalid_reason"] == "malformed_stream_event"

    incomplete = subprocess.CompletedProcess(["claude"], 0, json.dumps({"type": "result", "num_turns": 1}) + "\n", "")
    with patch.object(run_evals.subprocess, "run", return_value=incomplete):
        malformed_terminal = run_evals.run_claude("hello", "/tmp")
    assert malformed_terminal["valid"] is False
    assert malformed_terminal["invalid_reason"] == "malformed_terminal_result"


def test_run_claude_invalidates_malformed_json_and_explicit_terminal_failures():
    success = json.loads(terminal())
    malformed_json = subprocess.CompletedProcess(["claude"], 0, "{not json}\n" + json.dumps(success) + "\n", "")
    with patch.object(run_evals.subprocess, "run", return_value=malformed_json):
        result = run_evals.run_claude("hello", "/tmp")
    assert result["valid"] is False
    assert result["invalid_reason"] == "malformed_stream_event"

    max_turns = {**success, "subtype": "error_max_turns", "is_error": False}
    completed = subprocess.CompletedProcess(["claude"], 0, json.dumps(max_turns) + "\n", "")
    with patch.object(run_evals.subprocess, "run", return_value=completed):
        result = run_evals.run_claude("hello", "/tmp")
    assert result["valid"] is False
    assert result["invalid_reason"] == "non_success_terminal:error_max_turns"

    error_then_success = {**success, "is_error": True, "subtype": "error"}
    completed = subprocess.CompletedProcess(["claude"], 0, json.dumps(error_then_success) + "\n" + json.dumps(success) + "\n", "")
    with patch.object(run_evals.subprocess, "run", return_value=completed):
        result = run_evals.run_claude("hello", "/tmp")
    assert result["valid"] is False
    assert result["invalid_reason"] == "non_success_terminal:is_error"


def test_run_claude_keeps_valid_run_when_usage_is_not_exposed():
    completed = subprocess.CompletedProcess(["claude"], 0, terminal(), "")
    with patch.object(run_evals.subprocess, "run", return_value=completed):
        result = run_evals.run_claude("hello", "/tmp")
    assert result["valid"] is True
    assert result["tokens"] is None
    assert result["tokens_unavailable_reason"] == "missing_usage"


@pytest.mark.parametrize("stream", ["null\n", "[]\n", json.dumps({"type": "assistant", "message": []}) + "\n"])
def test_run_claude_marks_non_object_stream_events_invalid_without_crashing(stream):
    usage = {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}
    completed = subprocess.CompletedProcess(["claude"], 0, stream + terminal(usage=usage), "")
    with patch.object(run_evals.subprocess, "run", return_value=completed):
        result = run_evals.run_claude("hello", "/tmp")
    assert result["valid"] is False
    assert result["invalid_reason"] == "malformed_stream_event"


def test_run_claude_marks_process_launch_error_invalid_with_numeric_duration():
    with patch.object(run_evals.subprocess, "run", side_effect=FileNotFoundError("claude missing")):
        result = run_evals.run_claude("hello", "/tmp")
    assert result["valid"] is False
    assert result["invalid_reason"] == "launch_error"
    assert result["tokens"] is None
    assert isinstance(result["duration_ms"], int)
    assert result["duration_ms"] >= 0


def test_trigger_metrics_exclude_invalid_negative_runs(monkeypatch):
    invalid = {"output": "", "tool_calls": [], "duration_ms": 1, "tokens": None, "num_turns": None, "error": "failed", "valid": False, "invalid_reason": "nonzero_exit:1", "tokens_unavailable_reason": "missing_terminal_result", "metadata": {}}
    monkeypatch.setattr(run_evals, "run_claude", lambda *args, **kwargs: invalid)
    result = run_evals.run_trigger_evals([{"id": "negative", "prompt": "x", "target_skill": "skill", "should_trigger": False}], 1, None, False)
    case = result["evals"][0]
    stats = result["summary"]["skill"]
    assert case["trigger_rate"] is None and case["correct"] is None
    assert stats["true_negatives"] == 0
    assert stats["precision"] is None and stats["recall"] is None


def test_trigger_f1_is_measured_zero_when_precision_and_recall_are_zero(monkeypatch):
    valid_trigger = {"output": "", "tool_calls": [{"name": "Skill", "input": {"skill": "skill"}}], "duration_ms": 1, "tokens": 1, "num_turns": 1, "error": None, "valid": True, "invalid_reason": None, "tokens_unavailable_reason": None, "metadata": {}}
    valid_non_trigger = {**valid_trigger, "tool_calls": []}
    responses = iter([valid_non_trigger, valid_trigger])
    monkeypatch.setattr(run_evals, "run_claude", lambda *args, **kwargs: next(responses))
    result = run_evals.run_trigger_evals([
        {"id": "positive", "prompt": "x", "target_skill": "skill", "should_trigger": True},
        {"id": "negative", "prompt": "x", "target_skill": "skill", "should_trigger": False},
    ], 1, None, False)
    stats = result["summary"]["skill"]
    assert stats["precision"] == 0
    assert stats["recall"] == 0
    assert stats["f1"] == 0


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


def test_quality_delta_requires_matched_valid_cases(monkeypatch):
    valid_pass = {"output": "yes", "tool_calls": [], "duration_ms": 1, "tokens": 1, "num_turns": 1, "error": None, "valid": True, "invalid_reason": None, "tokens_unavailable_reason": None, "metadata": {}}
    valid_fail = {**valid_pass, "output": "no"}
    invalid = {**valid_pass, "valid": False, "tokens": None, "invalid_reason": "timeout", "tokens_unavailable_reason": "timeout"}
    responses = iter([valid_pass, invalid, invalid, valid_fail])
    monkeypatch.setattr(run_evals, "run_claude", lambda *args, **kwargs: next(responses))
    result = run_evals.run_quality_evals([
        {"id": "case-a", "prompt": "x", "assertions": [{"type": "contains", "value": "yes"}]},
        {"id": "case-b", "prompt": "x", "assertions": [{"type": "contains", "value": "yes"}]},
    ], 1, None, True, False)
    assert result["summary"]["with_plugin"]["overall_pass_rate"] == 1
    assert result["summary"]["without_plugin"]["overall_pass_rate"] == 0
    assert result["summary"]["delta"] is None
    assert result["summary"]["delta_coverage"] == {"total_evals": 2, "matched_evals": 0, "unmatched_evals": 2}


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
    zero_f1 = {"evals": [], "summary": {"skill": {"precision": 0, "recall": 0, "f1": 0, "true_positives": 0, "false_positives": 1, "true_negatives": 0, "false_negatives": 1}}}
    assert "| **TOTAL** | **0.00** | **0.00** | **0.00** |" in aggregate_results.generate_aggregate_report(zero_f1, {"evals": [], "summary": {}}, [], "now")


def test_aggregate_combines_repeated_skill_counts_and_weights_quality_cases():
    trigger = aggregate_results.merge_trigger_results([
        {"trigger": {"evals": [], "summary": {"skill": {"true_positives": 1, "false_positives": 0, "true_negatives": 0, "false_negatives": 0}}}},
        {"plugins": {"plugin": {"trigger": {"evals": [], "summary": {"skill": {"true_positives": 0, "false_positives": 1, "true_negatives": 0, "false_negatives": 1}}}}}},
    ])
    assert trigger["summary"]["skill"] == {"true_positives": 1, "false_positives": 1, "true_negatives": 0, "false_negatives": 1, "precision": 0.5, "recall": 0.5, "f1": 0.5}

    quality = aggregate_results.merge_quality_results([
        {"quality": {"evals": [{"configs": {"with_plugin": {"mean_pass_rate": 1}}} for _ in range(10)], "summary": {"with_plugin": {"overall_pass_rate": 1}}}},
        {"quality": {"evals": [{"configs": {"with_plugin": {"mean_pass_rate": 0}}}], "summary": {"with_plugin": {"overall_pass_rate": 0}}}},
    ])
    assert quality["summary"]["with_plugin"]["overall_pass_rate"] == round(10 / 11, 3)

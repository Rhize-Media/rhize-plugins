"""Duplicate-control budget accounting; no coding-agent run is started here."""
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "evals/typed-decision/task_trials.py"
spec = importlib.util.spec_from_file_location("task_trials", SCRIPT)
trials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trials)


def files(tmp_path, verdict="accepted", quality=80):
    host = tmp_path / "host-limit.json"
    host.write_text('{"max_tokens":900000}')
    outcome = tmp_path / "outcome.json"
    outcome.write_text(json.dumps({
        "schema": "rhize-typed-task-outcome-v1", "outcome": verdict,
        "quality_score": quality, "required_checks_passed": verdict == "accepted",
        "independent_review_passed": verdict == "accepted",
        "critical_failure_count": 0, "rework_count": 0, "rubric_sha256": "e" * 64,
    }))
    return host, outcome


def test_reservation_enforces_cap_and_missing_usage_keeps_full_liability(tmp_path):
    host, outcome = files(tmp_path, verdict="undetermined", quality=None)
    db_path = tmp_path / "private" / "trial.sqlite3"
    db = trials.database(db_path)
    try:
        first = trials.reserve_control(db, "a" * 64, "b" * 64, 900000, host)
        assert first["remainingTokens"] == 100000
        with pytest.raises(ValueError, match="ceiling"):
            trials.reserve_control(db, "c" * 64, "b" * 64, 100001, host)
        final = trials.finish(db, first["runId"], "A_control", "incomplete", None, None,
                              None, "host_usage_unavailable", "undetermined", outcome, None)
        assert final["usedTokens"] is None and final["budgetUsedOrReserved"] == 900000
        assert trials.report(db)["missingUsage"] == 1
        second = trials.reserve_control(db, "c" * 64, "b" * 64, 100000, host)
        assert second["remainingTokens"] == 0
        with pytest.raises(ValueError, match="ceiling"):
            trials.reserve_control(db, "d" * 64, "b" * 64, 1, host)
    finally:
        db.close()
    assert db_path.stat().st_mode & 0o777 == 0o600


def test_reported_usage_releases_unused_reservation_and_single_arm_is_free_of_duplicate_cap(tmp_path):
    host, outcome = files(tmp_path)
    usage = tmp_path / "usage.json"
    usage.write_text(json.dumps({"input_tokens": 120, "output_tokens": 30,
                                 "cache_read_tokens": None, "cache_write_tokens": None,
                                 "reasoning_tokens": None}))
    db = trials.database(tmp_path / "private" / "trial.sqlite3")
    try:
        control = trials.reserve_control(db, "a" * 64, "b" * 64, 500, host)
        settled = trials.finish(db, control["runId"], "A_control", "completed", None, None,
                                usage, None, "accepted", outcome, 1000)
        assert settled["usedTokens"] == 150 and settled["remainingTokens"] == trials.CAP - 150
        treated = trials.finish(db, "treatment-1", "B_treatment", "completed", "a" * 64,
                                "b" * 64, usage, None, "accepted", outcome, 900)
        assert treated["budgetUsedOrReserved"] == 150
        single = trials.finish(db, "single-1", "B_single", "completed", "c" * 64,
                               "b" * 64, usage, None, "accepted", outcome, 800)
        assert single["budgetUsedOrReserved"] == 150
        report = trials.report(db)
        assert report["pairedGroups"] == 1 and report["singleExecutionGroups"] == 1
        assert report["evaluablePairs"] == 1 and report["evaluableSingleRuns"] == 1
        assert report["pairedMeanDeltaBMinusA"] == {"qualityScore": 0, "codingTokens": 0, "wallMs": -100}
    finally:
        db.close()


def test_invalid_usage_is_not_a_zero_cost_run(tmp_path):
    host, outcome = files(tmp_path)
    usage = tmp_path / "bad-usage.json"
    usage.write_text('{"input_tokens":0,"output_tokens":0}')
    db = trials.database(tmp_path / "private" / "trial.sqlite3")
    try:
        control = trials.reserve_control(db, "a" * 64, "b" * 64, 100, host)
        with pytest.raises(ValueError, match="five recorded"):
            trials.finish(db, control["runId"], "A_control", "completed", None, None,
                          usage, None, "accepted", outcome, 10)
        assert trials.report(db)["budgetUsedOrReserved"] == 100
    finally:
        db.close()


def test_same_task_fixture_arm_cannot_be_reserved_twice(tmp_path):
    host, _ = files(tmp_path)
    db = trials.database(tmp_path / "private" / "trial.sqlite3")
    try:
        trials.reserve_control(db, "a" * 64, "b" * 64, 100, host)
        with pytest.raises(sqlite3.IntegrityError):
            trials.reserve_control(db, "a" * 64, "b" * 64, 100, host)
        assert trials.report(db)["budgetUsedOrReserved"] == 100
    finally:
        db.close()


def test_incomplete_or_rubric_mismatched_pair_is_not_evaluable(tmp_path):
    host, outcome = files(tmp_path)
    usage = tmp_path / "usage.json"
    usage.write_text(json.dumps({"input_tokens": 40, "output_tokens": 10,
                                 "cache_read_tokens": None, "cache_write_tokens": None,
                                 "reasoning_tokens": None}))
    db = trials.database(tmp_path / "private" / "trial.sqlite3")
    try:
        control = trials.reserve_control(db, "a" * 64, "b" * 64, 100, host)
        trials.finish(db, control["runId"], "A_control", "incomplete", None, None,
                      usage, None, "accepted", outcome, 100)
        trials.finish(db, "treatment", "B_treatment", "completed", "a" * 64,
                      "b" * 64, usage, None, "accepted", outcome, 90)
        summary = trials.report(db)
        assert summary["pairedGroups"] == 1 and summary["evaluablePairs"] == 0
        assert summary["pairedMeanDeltaBMinusA"] is None
    finally:
        db.close()


def test_different_frozen_rubrics_do_not_form_an_evaluable_pair(tmp_path):
    host, outcome = files(tmp_path)
    usage = tmp_path / "usage.json"
    usage.write_text(json.dumps({"input_tokens": 40, "output_tokens": 10,
                                 "cache_read_tokens": None, "cache_write_tokens": None,
                                 "reasoning_tokens": None}))
    db = trials.database(tmp_path / "private" / "trial.sqlite3")
    try:
        control = trials.reserve_control(db, "a" * 64, "b" * 64, 100, host)
        trials.finish(db, control["runId"], "A_control", "completed", None, None,
                      usage, None, "accepted", outcome, 100)
        other = json.loads(outcome.read_text())
        other["rubric_sha256"] = "f" * 64
        outcome.write_text(json.dumps(other))
        trials.finish(db, "treatment", "B_treatment", "completed", "a" * 64,
                      "b" * 64, usage, None, "accepted", outcome, 90)
        assert trials.report(db)["evaluablePairs"] == 0
    finally:
        db.close()


def test_accepted_outcome_requires_review_and_quality(tmp_path):
    _, outcome = files(tmp_path, quality=None)
    with pytest.raises(ValueError, match="accepted outcome"):
        trials.outcome_from_file(outcome, "accepted")

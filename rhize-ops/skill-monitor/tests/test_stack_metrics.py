"""Tests for stack_metrics.py — the trust-tagged stack-metrics collector.

Run: python3 -m pytest tests/test_stack_metrics.py -q   (from the repo root)

Covers, per parser: well-formed input, missing file, empty file, and a
malformed row/content case — plus the two things the whole module exists to
guarantee:
  1. costs.jsonl's cumulative-rows trap is not fallen into (latest row per
     session, never summed across a session's own rows).
  2. sum_measured() structurally refuses anything not tagged exactly
     TrustClass.MEASURED.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import cost_metrics  # noqa: E402
import stack_metrics  # noqa: E402


def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _sqlite(path: Path, ddl: str, rows: list[tuple] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(ddl)
    if rows:
        placeholders = ",".join("?" * len(rows[0]))
        table = ddl.split()[2].split("(")[0]
        conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
    conn.commit()
    conn.close()


def _recent_ts(hours_ago: float = 0, minutes_ago: float = 0) -> str:
    """ISO-8601 UTC timestamp relative to *now* (with a 'Z' suffix), for any
    fixture row a loader's `days`-based cutoff will inspect.

    Every loader here filters rows with `datetime.now(timezone.utc) -
    timedelta(days=N)`. A fixture that hardcodes an absolute calendar date
    (e.g. "2026-08-20T00:00:00Z") silently drifts outside that window as real
    time passes — that is what made 12 tests in this file go red while the
    fixture-injection mechanism they were meant to exercise worked correctly
    the whole time. Always build a timestamp a loader will filter on from
    this helper, never as a literal. See
    test_no_hardcoded_absolute_date_literals_in_fixtures below, which fails
    the suite if this rule is violated again.
    """
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago, minutes=minutes_ago)
    return dt.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# THE central requirement: sum_measured structurally refuses non-measured
# ---------------------------------------------------------------------------

def _metric(trust, value=10, name="m", unit="tokens", basis=None):
    return stack_metrics.Metric(
        name=name, value=value, unit=unit, trust=trust, source="test", scope="window",
        basis=basis,
    )


def test_sum_measured_sums_measured_only():
    metrics = [
        _metric(stack_metrics.TrustClass.MEASURED, value=3, name="a"),
        _metric(stack_metrics.TrustClass.MEASURED, value=4, name="b"),
    ]
    assert stack_metrics.sum_measured(metrics) == 7


def test_sum_measured_refuses_measured_caveated():
    metrics = [
        _metric(stack_metrics.TrustClass.MEASURED, value=3),
        _metric(stack_metrics.TrustClass.MEASURED_CAVEATED, value=100),
    ]
    with pytest.raises(stack_metrics.TrustClassError):
        stack_metrics.sum_measured(metrics)


def test_sum_measured_refuses_indicative():
    metrics = [_metric(stack_metrics.TrustClass.INDICATIVE, value=100)]
    with pytest.raises(stack_metrics.TrustClassError):
        stack_metrics.sum_measured(metrics)


def test_sum_measured_refuses_self_reported():
    metrics = [_metric(stack_metrics.TrustClass.SELF_REPORTED, value=100)]
    with pytest.raises(stack_metrics.TrustClassError):
        stack_metrics.sum_measured(metrics)


def test_sum_measured_refusal_message_names_offending_metric():
    metrics = [_metric(stack_metrics.TrustClass.INDICATIVE, value=1, name="sneaky")]
    with pytest.raises(stack_metrics.TrustClassError, match="sneaky"):
        stack_metrics.sum_measured(metrics)


def test_metric_to_dict_serializes_trust_as_plain_string():
    m = _metric(stack_metrics.TrustClass.SELF_REPORTED)
    d = m.to_dict()
    assert d["trust"] == "self_reported"
    json.dumps(d)  # must be JSON-serializable on its own


def test_metric_to_dict_serializes_basis_as_plain_string_or_none():
    m = _metric(stack_metrics.TrustClass.MEASURED, basis=stack_metrics.Basis.SAVINGS)
    assert m.to_dict()["basis"] == "savings"
    m2 = _metric(stack_metrics.TrustClass.MEASURED)
    assert m2.to_dict()["basis"] is None


# ---------------------------------------------------------------------------
# sum_measured — the second, orthogonal basis check (billed vs. raw vs.
# savings). Trust class alone is not enough: all three metrics below are
# tagged MEASURED, and the old code summed them anyway.
# ---------------------------------------------------------------------------

def test_sum_measured_refuses_mixed_basis():
    """The exact real-world combination that produced the defective
    totals['measured_tokens'] = 10,700,100,905: claude_code_tokens (billed
    spend), session_transcript_tokens (raw usage, re-covers the same turns
    via cache reads), and headroom_tokens_saved (a savings figure). All
    three are trust=MEASURED — the trust-class guard alone lets them
    through. The basis guard must refuse this exact trio."""
    metrics = [
        _metric(
            stack_metrics.TrustClass.MEASURED, value=1_744_795_867,
            name="claude_code_tokens", basis=stack_metrics.Basis.BILLED_CONSUMPTION,
        ),
        _metric(
            stack_metrics.TrustClass.MEASURED, value=8_955_305_038,
            name="session_transcript_tokens", basis=stack_metrics.Basis.RAW_CONSUMPTION,
        ),
        _metric(
            stack_metrics.TrustClass.MEASURED, value=0,
            name="headroom_tokens_saved", basis=stack_metrics.Basis.SAVINGS,
        ),
    ]
    with pytest.raises(stack_metrics.BasisMismatchError):
        stack_metrics.sum_measured(metrics)


def test_sum_measured_refuses_two_of_the_three_mixed_bases():
    """Refuses even a pairwise mismatch, not just the full three-way mix."""
    metrics = [
        _metric(
            stack_metrics.TrustClass.MEASURED, value=100,
            name="claude_code_tokens", basis=stack_metrics.Basis.BILLED_CONSUMPTION,
        ),
        _metric(
            stack_metrics.TrustClass.MEASURED, value=5,
            name="headroom_tokens_saved", basis=stack_metrics.Basis.SAVINGS,
        ),
    ]
    with pytest.raises(stack_metrics.BasisMismatchError):
        stack_metrics.sum_measured(metrics)


def test_sum_measured_refuses_basis_tagged_mixed_with_untagged():
    """A basis=None metric silently mixed with a basis-tagged metric is
    exactly the kind of accidental cross-basis sum this guard exists to
    catch — it must not be treated as a free pass."""
    metrics = [
        _metric(
            stack_metrics.TrustClass.MEASURED, value=100,
            name="claude_code_tokens", basis=stack_metrics.Basis.BILLED_CONSUMPTION,
        ),
        _metric(stack_metrics.TrustClass.MEASURED, value=5, name="untagged"),
    ]
    with pytest.raises(stack_metrics.BasisMismatchError):
        stack_metrics.sum_measured(metrics)


def test_sum_measured_allows_same_basis():
    metrics = [
        _metric(
            stack_metrics.TrustClass.MEASURED, value=3, name="a",
            basis=stack_metrics.Basis.BILLED_CONSUMPTION,
        ),
        _metric(
            stack_metrics.TrustClass.MEASURED, value=4, name="b",
            basis=stack_metrics.Basis.BILLED_CONSUMPTION,
        ),
    ]
    assert stack_metrics.sum_measured(metrics) == 7


def test_sum_measured_allows_all_untagged_basis():
    """basis=None metrics are still summable with each other — the axis is
    exempt, not forbidden, for metrics with no consumption/savings
    ambiguity (e.g. a count)."""
    metrics = [
        _metric(stack_metrics.TrustClass.MEASURED, value=3, name="a"),
        _metric(stack_metrics.TrustClass.MEASURED, value=4, name="b"),
    ]
    assert stack_metrics.sum_measured(metrics) == 7


def test_sum_measured_trust_check_still_fires_before_basis_check():
    """Do not weaken the existing trust-class guard: a non-MEASURED metric
    must still raise TrustClassError, even when basis is homogeneous."""
    metrics = [
        _metric(
            stack_metrics.TrustClass.MEASURED, value=3, name="a",
            basis=stack_metrics.Basis.SAVINGS,
        ),
        _metric(
            stack_metrics.TrustClass.INDICATIVE, value=4, name="b",
            basis=stack_metrics.Basis.SAVINGS,
        ),
    ]
    with pytest.raises(stack_metrics.TrustClassError):
        stack_metrics.sum_measured(metrics)


# ---------------------------------------------------------------------------
# sum_measured — the third, orthogonal unit check. Trust class and basis
# alone are not enough: two metrics can both be trust=MEASURED and share a
# basis (or both omit one) and still be nonsense added together if their
# units differ (tokens vs. usd).
# ---------------------------------------------------------------------------

def test_sum_measured_refuses_mixed_unit():
    """The exact repro from the task brief: a tokens metric and a usd
    metric, both trust=MEASURED, both basis=BILLED_CONSUMPTION — neither
    the trust check nor the basis check catches this, so the old code
    returned 3.0 (1 token + 2 dollars). The unit check must refuse it."""
    metrics = [
        _metric(
            stack_metrics.TrustClass.MEASURED, value=1, name="x", unit="tokens",
            basis=stack_metrics.Basis.BILLED_CONSUMPTION,
        ),
        _metric(
            stack_metrics.TrustClass.MEASURED, value=2, name="y", unit="usd",
            basis=stack_metrics.Basis.BILLED_CONSUMPTION,
        ),
    ]
    with pytest.raises(stack_metrics.UnitMismatchError):
        stack_metrics.sum_measured(metrics)


def test_sum_measured_allows_same_unit():
    """No regression: metrics that already share a unit must still sum."""
    metrics = [
        _metric(stack_metrics.TrustClass.MEASURED, value=3, name="a", unit="tokens"),
        _metric(stack_metrics.TrustClass.MEASURED, value=4, name="b", unit="tokens"),
    ]
    assert stack_metrics.sum_measured(metrics) == 7


def test_sum_measured_trust_and_basis_checks_still_fire_independently_of_unit_check():
    """The unit check must not weaken or reorder the existing two guards:
    a non-MEASURED metric still raises TrustClassError, and a mixed-basis
    pair still raises BasisMismatchError, even when units are homogeneous."""
    non_measured = [
        _metric(stack_metrics.TrustClass.MEASURED, value=3, name="a", unit="tokens"),
        _metric(stack_metrics.TrustClass.INDICATIVE, value=4, name="b", unit="tokens"),
    ]
    with pytest.raises(stack_metrics.TrustClassError):
        stack_metrics.sum_measured(non_measured)

    mixed_basis = [
        _metric(
            stack_metrics.TrustClass.MEASURED, value=3, name="a", unit="tokens",
            basis=stack_metrics.Basis.BILLED_CONSUMPTION,
        ),
        _metric(
            stack_metrics.TrustClass.MEASURED, value=4, name="b", unit="tokens",
            basis=stack_metrics.Basis.SAVINGS,
        ),
    ]
    with pytest.raises(stack_metrics.BasisMismatchError):
        stack_metrics.sum_measured(mixed_basis)


# ---------------------------------------------------------------------------
# load_claude_code_spend (costs.jsonl, via cost_metrics.py)
# ---------------------------------------------------------------------------

def test_costs_missing_file(tmp_path):
    result = stack_metrics.load_claude_code_spend(7, costs_path=tmp_path / "nope.jsonl")
    assert result["available"] is False
    assert "not found" in result["error"]
    assert result["metrics"] == []


def test_costs_empty_file(tmp_path):
    p = tmp_path / "costs.jsonl"
    p.write_text("", encoding="utf-8")
    result = stack_metrics.load_claude_code_spend(7, costs_path=p)
    assert result["available"] is True
    assert result["session_count"] == 0
    assert result["total_cost_usd"] == 0
    assert result["event_count"] == 0


def test_costs_malformed_row_is_skipped_not_fatal(tmp_path):
    p = tmp_path / "costs.jsonl"
    _write_jsonl(p, [
        "{not valid json",
        json.dumps({
            "timestamp": _recent_ts(hours_ago=1), "session_id": "s1",
            "estimated_cost_usd": 1.5, "input_tokens": 10, "output_tokens": 5,
            "cache_write_tokens": 0, "cache_read_tokens": 0,
        }),
    ])
    result = stack_metrics.load_claude_code_spend(7, costs_path=p)
    assert result["available"] is True
    assert result["session_count"] == 1
    assert result["total_cost_usd"] == 1.5


def test_costs_well_formed(tmp_path):
    p = tmp_path / "costs.jsonl"
    _write_jsonl(p, [
        json.dumps({
            "timestamp": _recent_ts(hours_ago=2), "session_id": "s1",
            "estimated_cost_usd": 2.0, "input_tokens": 100, "output_tokens": 50,
            "cache_write_tokens": 0, "cache_read_tokens": 0,
        }),
        json.dumps({
            "timestamp": _recent_ts(hours_ago=1), "session_id": "s2",
            "estimated_cost_usd": 3.0, "input_tokens": 200, "output_tokens": 25,
            "cache_write_tokens": 0, "cache_read_tokens": 0,
        }),
    ])
    result = stack_metrics.load_claude_code_spend(7, costs_path=p)
    assert result["session_count"] == 2
    assert result["total_cost_usd"] == 5.0
    tokens_metric = next(m for m in result["metrics"] if m.name == "claude_code_tokens")
    assert tokens_metric.trust is stack_metrics.TrustClass.MEASURED
    assert tokens_metric.value == 375  # 100+50 + 200+25


def test_costs_cumulative_rows_trap(tmp_path):
    """costs.jsonl rows are CUMULATIVE snapshots for one session. Three rows
    for the SAME session must yield the LATEST row's values, never the sum —
    this is the exact trap cost_metrics.py exists to avoid."""
    p = tmp_path / "costs.jsonl"
    _write_jsonl(p, [
        json.dumps({
            "timestamp": _recent_ts(minutes_ago=10), "session_id": "s1",
            "estimated_cost_usd": 1.0, "input_tokens": 10, "output_tokens": 5,
            "cache_write_tokens": 0, "cache_read_tokens": 0,
        }),
        json.dumps({
            "timestamp": _recent_ts(minutes_ago=5), "session_id": "s1",
            "estimated_cost_usd": 2.5, "input_tokens": 25, "output_tokens": 12,
            "cache_write_tokens": 0, "cache_read_tokens": 0,
        }),
        json.dumps({
            "timestamp": _recent_ts(minutes_ago=0), "session_id": "s1",
            "estimated_cost_usd": 4.0, "input_tokens": 40, "output_tokens": 20,
            "cache_write_tokens": 0, "cache_read_tokens": 0,
        }),
    ])
    result = stack_metrics.load_claude_code_spend(7, costs_path=p)
    assert result["session_count"] == 1
    # Latest row only: cost 4.0, tokens 40+20=60. The WRONG (summed) answer
    # would be cost 7.5, tokens 112 — assert those are NOT produced.
    assert result["total_cost_usd"] == 4.0
    assert result["total_tokens"] == 60
    assert result["total_cost_usd"] != 1.0 + 2.5 + 4.0
    assert result["total_tokens"] != (10 + 5) + (25 + 12) + (40 + 20)


# ---------------------------------------------------------------------------
# load_session_transcripts
# ---------------------------------------------------------------------------

def test_transcripts_missing_dir(tmp_path):
    result = stack_metrics.load_session_transcripts(7, transcripts_dir=tmp_path / "nope")
    assert result["available"] is False
    assert result["metrics"] == []


def test_transcripts_empty_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    result = stack_metrics.load_session_transcripts(7, transcripts_dir=d)
    assert result["available"] is True
    assert result["turn_count"] == 0
    assert result["event_count"] == 0


def test_transcripts_malformed_row_is_skipped_not_fatal(tmp_path):
    d = tmp_path / "projects" / "proj1"
    f = d / "session1.jsonl"
    _write_jsonl(f, [
        "{not valid json",
        json.dumps({"type": "user", "timestamp": _recent_ts(hours_ago=1)}),  # not assistant
        json.dumps({
            "type": "assistant", "timestamp": _recent_ts(hours_ago=1),
            "message": {"usage": {
                "input_tokens": 5, "output_tokens": 10,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            }},
        }),
    ])
    result = stack_metrics.load_session_transcripts(7, transcripts_dir=tmp_path / "projects")
    assert result["available"] is True
    assert result["turn_count"] == 1
    assert result["total_tokens"] == 15


def test_transcripts_well_formed_sums_per_turn_deltas(tmp_path):
    """Unlike costs.jsonl, transcript usage rows are per-turn deltas, so
    summing across turns IS correct here."""
    d = tmp_path / "projects" / "proj1"
    f = d / "session1.jsonl"
    _write_jsonl(f, [
        json.dumps({
            "type": "assistant", "timestamp": _recent_ts(minutes_ago=1),
            "message": {"usage": {
                "input_tokens": 10, "output_tokens": 20,
                "cache_creation_input_tokens": 1, "cache_read_input_tokens": 2,
            }},
        }),
        json.dumps({
            "type": "assistant", "timestamp": _recent_ts(minutes_ago=0),
            "message": {"usage": {
                "input_tokens": 5, "output_tokens": 8,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            }},
        }),
    ])
    result = stack_metrics.load_session_transcripts(7, transcripts_dir=tmp_path / "projects")
    assert result["turn_count"] == 2
    assert result["input_tokens"] == 15
    assert result["output_tokens"] == 28
    assert result["total_tokens"] == 15 + 28 + 1 + 2
    tok_metric = next(m for m in result["metrics"] if m.name == "session_transcript_tokens")
    assert tok_metric.trust is stack_metrics.TrustClass.MEASURED


# ---------------------------------------------------------------------------
# load_headroom
# ---------------------------------------------------------------------------

def test_headroom_missing_both_files(tmp_path):
    result = stack_metrics.load_headroom(
        7, proxy_path=tmp_path / "nope1.json", events_path=tmp_path / "nope2.jsonl"
    )
    assert result["available"] is False
    assert result["metrics"] == []


def test_headroom_empty_files(tmp_path):
    proxy = tmp_path / "proxy_savings.json"
    events = tmp_path / "savings_events.jsonl"
    _write_json(proxy, {"history": []})
    events.write_text("", encoding="utf-8")
    result = stack_metrics.load_headroom(7, proxy_path=proxy, events_path=events)
    assert result["available"] is True
    assert result["window_tokens_saved"] == 0
    assert result["event_count"] == 0


def test_headroom_malformed_proxy_file(tmp_path):
    proxy = tmp_path / "proxy_savings.json"
    events = tmp_path / "savings_events.jsonl"
    proxy.write_text("{not valid json", encoding="utf-8")
    _write_jsonl(events, [json.dumps({"ts": _recent_ts(hours_ago=1), "saved": 5})])
    result = stack_metrics.load_headroom(7, proxy_path=proxy, events_path=events)
    # proxy is broken but events parsed fine -> overall still available via events
    assert result["available"] is True
    assert result["proxy_available"] is False
    assert result["events_available"] is True


def test_headroom_well_formed(tmp_path):
    proxy = tmp_path / "proxy_savings.json"
    events = tmp_path / "savings_events.jsonl"
    _write_json(proxy, {"history": [
        {"timestamp": _recent_ts(hours_ago=1), "total_tokens_saved": 100,
         "compression_savings_usd": 0.5},
    ]})
    _write_jsonl(events, [json.dumps({"ts": _recent_ts(hours_ago=1), "saved": 5})])
    result = stack_metrics.load_headroom(7, proxy_path=proxy, events_path=events)
    assert result["window_tokens_saved"] == 100
    tok_metric = next(m for m in result["metrics"] if m.name == "headroom_tokens_saved")
    assert tok_metric.trust is stack_metrics.TrustClass.MEASURED


# ---------------------------------------------------------------------------
# load_procedural_memory
# ---------------------------------------------------------------------------

def test_procedural_memory_missing_dir(tmp_path):
    result = stack_metrics.load_procedural_memory(7, runs_dir=tmp_path / "nope")
    assert result["available"] is False
    assert result["metrics"] == []


def test_procedural_memory_empty_dir(tmp_path):
    d = tmp_path / "runs"
    d.mkdir()
    result = stack_metrics.load_procedural_memory(7, runs_dir=d)
    assert result["available"] is True
    assert result["run_count"] == 0


def test_procedural_memory_malformed_row_is_skipped_not_fatal(tmp_path):
    d = tmp_path / "runs"
    f = d / "2026-08-20.jsonl"
    _write_jsonl(f, [
        "{not valid json",
        json.dumps({"started_at": _recent_ts(hours_ago=1), "ok": True, "duration_ms": 50}),
    ])
    result = stack_metrics.load_procedural_memory(7, runs_dir=d)
    assert result["run_count"] == 1
    assert result["ok_count"] == 1


def test_procedural_memory_well_formed(tmp_path):
    d = tmp_path / "runs"
    f = d / "2026-08-20.jsonl"
    _write_jsonl(f, [
        json.dumps({"started_at": _recent_ts(minutes_ago=1), "ok": True, "duration_ms": 50}),
        json.dumps({"started_at": _recent_ts(minutes_ago=0), "ok": False, "duration_ms": 30}),
    ])
    result = stack_metrics.load_procedural_memory(7, runs_dir=d)
    assert result["run_count"] == 2
    assert result["ok_count"] == 1
    assert result["total_duration_ms"] == 80
    run_metric = next(m for m in result["metrics"] if m.name == "procedural_memory_run_count")
    assert run_metric.trust is stack_metrics.TrustClass.MEASURED


# ---------------------------------------------------------------------------
# load_skill_invocations
# ---------------------------------------------------------------------------

def test_skill_invocations_missing_file(tmp_path):
    result = stack_metrics.load_skill_invocations(7, usage_path=tmp_path / "nope.json")
    assert result["available"] is False
    assert result["metrics"] == []


def test_skill_invocations_empty_events(tmp_path):
    p = tmp_path / "skill-usage.json"
    _write_json(p, {"events": []})
    result = stack_metrics.load_skill_invocations(7, usage_path=p)
    assert result["available"] is True
    assert result["window_event_count"] == 0


def test_skill_invocations_malformed_events_field(tmp_path):
    p = tmp_path / "skill-usage.json"
    _write_json(p, {"events": "not-a-list"})
    result = stack_metrics.load_skill_invocations(7, usage_path=p)
    assert result["available"] is False
    assert "malformed" in result["error"]


def test_skill_invocations_well_formed(tmp_path):
    p = tmp_path / "skill-usage.json"
    _write_json(p, {"events": [
        {"skill": "foo", "timestamp": _recent_ts(hours_ago=1)},
        {"skill": "bar", "timestamp": "2020-01-01T00:00:00Z"},  # outside window
    ]})
    result = stack_metrics.load_skill_invocations(7, usage_path=p)
    assert result["all_time_event_count"] == 2
    assert result["window_event_count"] == 1
    inv_metric = next(m for m in result["metrics"] if m.name == "skill_invocation_count")
    assert inv_metric.trust is stack_metrics.TrustClass.MEASURED


# ---------------------------------------------------------------------------
# load_rtk (SQLite, MEASURED_CAVEATED)
# ---------------------------------------------------------------------------

RTK_DDL = (
    "CREATE TABLE commands (id INTEGER PRIMARY KEY, timestamp TEXT, "
    "original_cmd TEXT, rtk_cmd TEXT, input_tokens INTEGER, "
    "output_tokens INTEGER, saved_tokens INTEGER, savings_pct REAL, "
    "exec_time_ms INTEGER DEFAULT 0, project_path TEXT DEFAULT '')"
)


def test_rtk_missing_file(tmp_path):
    result = stack_metrics.load_rtk(7, db_path=tmp_path / "nope.db")
    assert result["available"] is False
    assert result["metrics"] == []


def test_rtk_empty_db(tmp_path):
    p = tmp_path / "history.db"
    _sqlite(p, RTK_DDL)
    result = stack_metrics.load_rtk(7, db_path=p)
    assert result["available"] is True
    assert result["window_command_count"] == 0
    assert result["event_count"] == 0
    assert result["last_event_ts"] is None


def test_rtk_malformed_db_file(tmp_path):
    p = tmp_path / "history.db"
    p.write_bytes(b"this is not a sqlite database, just garbage bytes" * 4)
    result = stack_metrics.load_rtk(7, db_path=p)
    assert result["available"] is False
    assert result["error"]


def test_rtk_malformed_row_null_numeric_fields(tmp_path):
    p = tmp_path / "history.db"
    _sqlite(p, RTK_DDL, rows=[
        (1, _recent_ts(hours_ago=1), "ls", "rtk ls", None, None, None, None, 0, ""),
    ])
    result = stack_metrics.load_rtk(7, db_path=p)
    assert result["available"] is True
    assert result["window_input_tokens"] == 0  # COALESCE handles NULLs


def test_rtk_well_formed_and_tagged_measured_caveated(tmp_path):
    p = tmp_path / "history.db"
    _sqlite(p, RTK_DDL, rows=[
        (1, _recent_ts(minutes_ago=1), "cat x", "rtk read", 10, 5, 2, 20.0, 3, "/repo"),
        (2, _recent_ts(minutes_ago=0), "grep y", "rtk grep", 8, 4, 1, 12.5, 1, "/repo"),
    ])
    result = stack_metrics.load_rtk(7, db_path=p)
    assert result["window_command_count"] == 2
    assert result["window_input_tokens"] == 18
    assert result["window_saved_tokens"] == 3
    for m in result["metrics"]:
        assert m.trust is stack_metrics.TrustClass.MEASURED_CAVEATED
        assert m.caveat and "summary" in m.caveat.lower()


# ---------------------------------------------------------------------------
# load_claude_mem (SQLite, INDICATIVE)
# ---------------------------------------------------------------------------

CLAUDE_MEM_DDL = (
    "CREATE TABLE session_summaries (id INTEGER PRIMARY KEY, "
    "discovery_tokens INTEGER DEFAULT 0, created_at TEXT, created_at_epoch INTEGER)"
)


def test_claude_mem_missing_file(tmp_path):
    result = stack_metrics.load_claude_mem(7, db_path=tmp_path / "nope.db")
    assert result["available"] is False
    assert result["metrics"] == []


def test_claude_mem_empty_db(tmp_path):
    p = tmp_path / "claude-mem.db"
    _sqlite(p, CLAUDE_MEM_DDL)
    result = stack_metrics.load_claude_mem(7, db_path=p)
    assert result["available"] is True
    assert result["window_summary_count"] == 0


def test_claude_mem_malformed_db_file(tmp_path):
    p = tmp_path / "claude-mem.db"
    p.write_bytes(b"garbage, not a real sqlite file" * 4)
    result = stack_metrics.load_claude_mem(7, db_path=p)
    assert result["available"] is False


def test_claude_mem_well_formed_and_tagged_indicative(tmp_path):
    import time
    epoch_now_ms = int(time.time() * 1000)
    p = tmp_path / "claude-mem.db"
    _sqlite(p, CLAUDE_MEM_DDL, rows=[
        (1, 500, _recent_ts(minutes_ago=1), epoch_now_ms),
        (2, 300, _recent_ts(minutes_ago=0), epoch_now_ms),
    ])
    result = stack_metrics.load_claude_mem(7, db_path=p)
    assert result["window_discovery_tokens_sum"] == 800
    m = result["metrics"][0]
    assert m.trust is stack_metrics.TrustClass.INDICATIVE
    assert m.note and "LLM-estimated" in m.note


# ---------------------------------------------------------------------------
# load_openwolf (SELF_REPORTED)
# ---------------------------------------------------------------------------

def test_openwolf_no_dev_local_root(tmp_path):
    result = stack_metrics.load_openwolf(7, dev_local_root=tmp_path / "nope")
    assert result["available"] is False
    assert result["metrics"] == []


def test_openwolf_wolf_dir_with_no_ledger_file(tmp_path):
    root = tmp_path / "dev-local"
    (root / "repo1" / ".wolf").mkdir(parents=True)
    result = stack_metrics.load_openwolf(7, dev_local_root=root)
    assert result["missing_ledger_count"] == 1
    assert result["usable_repo_count"] == 0
    assert result["repos"]["repo1"]["available"] is False


def test_openwolf_stub_ledger_reported_honestly(tmp_path):
    root = tmp_path / "dev-local"
    ledger = root / "repo1" / ".wolf" / "token-ledger.json"
    _write_json(ledger, {"version": 1, "lifetime": {"total_sessions": 22}})
    result = stack_metrics.load_openwolf(7, dev_local_root=root)
    assert result["stub_repo_count"] == 1
    assert result["usable_repo_count"] == 0
    assert result["repos"]["repo1"]["stub"] is True


def test_openwolf_malformed_ledger_json(tmp_path):
    root = tmp_path / "dev-local"
    ledger = root / "repo1" / ".wolf" / "token-ledger.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("{not valid json", encoding="utf-8")
    result = stack_metrics.load_openwolf(7, dev_local_root=root)
    assert result["repos"]["repo1"]["available"] is False
    assert result["usable_repo_count"] == 0


def test_openwolf_well_formed_and_tagged_self_reported(tmp_path):
    root = tmp_path / "dev-local"
    ledger = root / "repo1" / ".wolf" / "token-ledger.json"
    _write_json(ledger, {
        "version": 1,
        "lifetime": {"anatomy_hits": 500, "estimated_savings_vs_bare_cli": 12345},
        "sessions": [
            {"started": _recent_ts(minutes_ago=10), "ended": _recent_ts(minutes_ago=0)},
        ],
    })
    result = stack_metrics.load_openwolf(7, dev_local_root=root)
    assert result["usable_repo_count"] == 1
    assert result["repos"]["repo1"]["window_session_count"] == 1
    m = result["metrics"][0]
    assert m.trust is stack_metrics.TrustClass.SELF_REPORTED
    assert m.value == 12345
    assert "uncross-checked" in m.caveat


# ---------------------------------------------------------------------------
# load_codex_trial_log (SELF_REPORTED, row-count only)
# ---------------------------------------------------------------------------

def test_codex_log_missing_file(tmp_path):
    result = stack_metrics.load_codex_trial_log(vault_path=tmp_path / "nope.md")
    assert result["available"] is False
    assert result["metrics"] == []


def test_codex_log_empty_file(tmp_path):
    p = tmp_path / "log.md"
    p.write_text("", encoding="utf-8")
    result = stack_metrics.load_codex_trial_log(vault_path=p)
    assert result["available"] is True
    assert result["row_count"] == 0
    assert result["metrics"][0].value == 0


def test_codex_log_well_formed_counts_rows_only(tmp_path):
    p = tmp_path / "log.md"
    p.write_text(
        "| Date | Task type | Outcome |\n"
        "|------|-----------|---------|\n"
        "| 2026-07-13 | planning | win |\n"
        "| 2026-07-17 | review | strong win |\n",
        encoding="utf-8",
    )
    result = stack_metrics.load_codex_trial_log(vault_path=p)
    assert result["row_count"] == 2
    m = result["metrics"][0]
    assert m.trust is stack_metrics.TrustClass.SELF_REPORTED
    assert m.unit == "rows"
    assert "no quantitative savings" in m.note


def test_codex_log_never_manufactures_a_savings_metric(tmp_path):
    """The log is qualitative prose with no $ or token figures. The loader
    must emit exactly one metric (a row count) and never invent a second,
    numeric 'savings' metric out of the prose."""
    p = tmp_path / "log.md"
    p.write_text(
        "| 2026-07-13 | planning | huge win, saved a ton of time |\n",
        encoding="utf-8",
    )
    result = stack_metrics.load_codex_trial_log(vault_path=p)
    assert len(result["metrics"]) == 1
    assert result["metrics"][0].unit == "rows"


# ---------------------------------------------------------------------------
# build_snapshot — never crashes even when every source is unavailable
# ---------------------------------------------------------------------------

def test_build_snapshot_never_crashes_with_all_sources_missing(tmp_path, monkeypatch):
    nope = tmp_path / "nope"
    monkeypatch.setattr(cost_metrics, "COSTS_JSONL", nope / "costs.jsonl")
    monkeypatch.setattr(stack_metrics, "DEFAULT_TRANSCRIPTS_DIR", nope / "projects")
    monkeypatch.setattr(stack_metrics, "DEFAULT_PROXY_SAVINGS", nope / "proxy.json")
    monkeypatch.setattr(stack_metrics, "DEFAULT_SAVINGS_EVENTS", nope / "events.jsonl")
    monkeypatch.setattr(stack_metrics, "DEFAULT_PROCEDURAL_MEMORY_DIR", nope / "runs")
    monkeypatch.setattr(stack_metrics, "DEFAULT_SKILL_USAGE_PATH", nope / "skill-usage.json")
    monkeypatch.setattr(stack_metrics, "DEFAULT_RTK_DB", nope / "history.db")
    monkeypatch.setattr(stack_metrics, "DEFAULT_CLAUDE_MEM_DB", nope / "claude-mem.db")
    monkeypatch.setattr(stack_metrics, "DEFAULT_OPENWOLF_ROOT", nope / "dev-local")
    monkeypatch.setattr(stack_metrics, "DEFAULT_CODEX_LOG_PATH", nope / "log.md")

    snapshot = stack_metrics.build_snapshot(days=1)

    assert set(snapshot["sources"]) == {
        "claude_code_spend", "session_transcripts", "headroom", "procedural_memory",
        "skill_invocations", "rtk", "claude_mem", "openwolf", "codex_trial_log",
    }
    for name, result in snapshot["sources"].items():
        assert result["available"] is False, f"{name} should be unavailable"
        assert result["error"], f"{name} should carry a reason"
    assert snapshot["metrics"] == []
    assert snapshot["totals"] == {}
    # every source dict must be JSON-serializable on its own (metrics already
    # converted to plain dicts, not left as Metric objects)
    json.dumps(snapshot)


# ---------------------------------------------------------------------------
# build_snapshot — basis-partitioned totals (the actual defect this task
# fixes: claude_code_tokens + session_transcript_tokens + headroom_tokens_saved
# used to be summed into one meaningless totals["measured_tokens"])
# ---------------------------------------------------------------------------

def test_build_snapshot_totals_are_basis_partitioned_not_cross_basis(tmp_path, monkeypatch):
    """End-to-end: with real (well-formed) costs.jsonl, transcripts, and
    headroom data available, build_snapshot() must emit one total PER BASIS
    and must NOT emit the old ambiguous cross-basis 'measured_tokens' key."""
    nope = tmp_path / "nope"

    costs = tmp_path / "costs.jsonl"
    _write_jsonl(costs, [json.dumps({
        "timestamp": _recent_ts(hours_ago=1), "session_id": "s1",
        "estimated_cost_usd": 1.0, "input_tokens": 100, "output_tokens": 50,
        "cache_write_tokens": 0, "cache_read_tokens": 0,
    })])
    monkeypatch.setattr(cost_metrics, "COSTS_JSONL", costs)

    transcripts = tmp_path / "projects" / "proj1"
    _write_jsonl(transcripts / "session1.jsonl", [json.dumps({
        "type": "assistant", "timestamp": _recent_ts(hours_ago=1),
        "message": {"usage": {
            "input_tokens": 10, "output_tokens": 20,
            "cache_creation_input_tokens": 1, "cache_read_input_tokens": 2,
        }},
    })])
    monkeypatch.setattr(stack_metrics, "DEFAULT_TRANSCRIPTS_DIR", tmp_path / "projects")

    proxy = tmp_path / "proxy_savings.json"
    _write_json(proxy, {"history": [
        {"timestamp": _recent_ts(hours_ago=1), "total_tokens_saved": 7,
         "compression_savings_usd": 0.1},
    ]})
    monkeypatch.setattr(stack_metrics, "DEFAULT_PROXY_SAVINGS", proxy)
    monkeypatch.setattr(stack_metrics, "DEFAULT_SAVINGS_EVENTS", nope / "events.jsonl")

    monkeypatch.setattr(stack_metrics, "DEFAULT_PROCEDURAL_MEMORY_DIR", nope / "runs")
    monkeypatch.setattr(stack_metrics, "DEFAULT_SKILL_USAGE_PATH", nope / "skill-usage.json")
    monkeypatch.setattr(stack_metrics, "DEFAULT_RTK_DB", nope / "history.db")
    monkeypatch.setattr(stack_metrics, "DEFAULT_CLAUDE_MEM_DB", nope / "claude-mem.db")
    monkeypatch.setattr(stack_metrics, "DEFAULT_OPENWOLF_ROOT", nope / "dev-local")
    monkeypatch.setattr(stack_metrics, "DEFAULT_CODEX_LOG_PATH", nope / "log.md")

    snapshot = stack_metrics.build_snapshot(days=7)

    assert "measured_tokens" not in snapshot["totals"], (
        "the old ambiguous cross-basis total must be gone"
    )
    assert snapshot["totals"]["measured_tokens_billed_consumption"]["value"] == 150
    assert snapshot["totals"]["measured_tokens_billed_consumption"]["from_metrics"] == [
        "claude_code_tokens"
    ]
    assert snapshot["totals"]["measured_tokens_raw_consumption"]["value"] == 10 + 20 + 1 + 2
    assert snapshot["totals"]["measured_tokens_raw_consumption"]["from_metrics"] == [
        "session_transcript_tokens"
    ]
    assert snapshot["totals"]["measured_tokens_savings"]["value"] == 7
    assert snapshot["totals"]["measured_tokens_savings"]["from_metrics"] == [
        "headroom_tokens_saved"
    ]
    # every total must itself be JSON-serializable as part of the snapshot
    json.dumps(snapshot)


# ---------------------------------------------------------------------------
# Standing regression: injection must keep reaching the actual read, per
# loader. Each test injects a fixture holding a deliberately implausible
# sentinel value and asserts that exact value comes back — not a plausible
# rounded number, so a loader silently falling back to a default/global path
# is caught immediately rather than passing by coincidence. All timestamps
# use _recent_ts so these tests cannot themselves become time bombs.
# ---------------------------------------------------------------------------

def test_injection_sentinel_load_claude_code_spend(tmp_path):
    p = tmp_path / "costs.jsonl"
    _write_jsonl(p, [json.dumps({
        "timestamp": _recent_ts(hours_ago=1), "session_id": "sentinel-session",
        "estimated_cost_usd": 0.0, "input_tokens": 8675309, "output_tokens": 0,
        "cache_write_tokens": 0, "cache_read_tokens": 0,
    })])
    result = stack_metrics.load_claude_code_spend(7, costs_path=p)
    assert result["total_tokens"] == 8675309


def test_injection_sentinel_load_session_transcripts(tmp_path):
    f = tmp_path / "projects" / "proj1" / "session1.jsonl"
    _write_jsonl(f, [json.dumps({
        "type": "assistant", "timestamp": _recent_ts(hours_ago=1),
        "message": {"usage": {
            "input_tokens": 9137331, "output_tokens": 0,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        }},
    })])
    result = stack_metrics.load_session_transcripts(7, transcripts_dir=tmp_path / "projects")
    assert result["input_tokens"] == 9137331


def test_injection_sentinel_load_headroom(tmp_path):
    proxy = tmp_path / "proxy_savings.json"
    events = tmp_path / "savings_events.jsonl"
    _write_json(proxy, {"history": [
        {"timestamp": _recent_ts(hours_ago=1), "total_tokens_saved": 8246611,
         "compression_savings_usd": 0.0},
    ]})
    events.write_text("", encoding="utf-8")
    result = stack_metrics.load_headroom(7, proxy_path=proxy, events_path=events)
    assert result["window_tokens_saved"] == 8246611


def test_injection_sentinel_load_procedural_memory(tmp_path):
    d = tmp_path / "runs"
    f = d / "today.jsonl"
    _write_jsonl(f, [json.dumps({
        "started_at": _recent_ts(hours_ago=1), "ok": True, "duration_ms": 7352941,
    })])
    result = stack_metrics.load_procedural_memory(7, runs_dir=d)
    assert result["total_duration_ms"] == 7352941


def test_injection_sentinel_load_skill_invocations(tmp_path):
    p = tmp_path / "skill-usage.json"
    _write_json(p, {"events": [{"skill": "sentinel", "timestamp": _recent_ts(hours_ago=1)}] * 647})
    result = stack_metrics.load_skill_invocations(7, usage_path=p)
    assert result["window_event_count"] == 647


def test_injection_sentinel_load_rtk(tmp_path):
    p = tmp_path / "history.db"
    _sqlite(p, RTK_DDL, rows=[
        (1, _recent_ts(hours_ago=1), "ls", "rtk ls", 5551212, 0, 0, 0.0, 0, ""),
    ])
    result = stack_metrics.load_rtk(7, db_path=p)
    assert result["window_input_tokens"] == 5551212


def test_injection_sentinel_load_claude_mem(tmp_path):
    p = tmp_path / "claude-mem.db"
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    _sqlite(p, CLAUDE_MEM_DDL, rows=[
        (1, 4442221, _recent_ts(hours_ago=1), now_ms),
    ])
    result = stack_metrics.load_claude_mem(7, db_path=p)
    assert result["window_discovery_tokens_sum"] == 4442221


def test_injection_sentinel_load_openwolf(tmp_path):
    root = tmp_path / "dev-local"
    ledger = root / "repo1" / ".wolf" / "token-ledger.json"
    _write_json(ledger, {
        "version": 1,
        "lifetime": {"anatomy_hits": 1, "estimated_savings_vs_bare_cli": 3133731},
        "sessions": [{"started": _recent_ts(hours_ago=1), "ended": _recent_ts(hours_ago=1)}],
    })
    result = stack_metrics.load_openwolf(7, dev_local_root=root)
    assert result["metrics"][0].value == 3133731


def test_injection_sentinel_load_codex_trial_log(tmp_path):
    p = tmp_path / "log.md"
    rows = "\n".join(f"| 2026-08-2{i % 7} | sentinel row {i} |" for i in range(271))
    p.write_text("| date | note |\n|---|---|\n" + rows, encoding="utf-8")
    result = stack_metrics.load_codex_trial_log(vault_path=p)
    assert result["row_count"] == 271


# ---------------------------------------------------------------------------
# Guard against reintroducing the class of bug that made 12 tests in this
# file go red: a fixture timestamp hardcoded to a specific calendar date
# silently drifts outside a days-based cutoff window as real time passes,
# and reads as a loader defect rather than a stale fixture. This scans the
# test file's own source rather than relying on remembering the rule.
# ---------------------------------------------------------------------------

def test_no_hardcoded_absolute_date_literals_in_fixtures():
    """Any ISO-8601 date+time literal ("YYYY-MM-DDTHH:MM:SS...") dated 2025
    or later found in this file's own source — outside `_recent_ts`'s own
    docstring, which uses one only as a worked example of what NOT to do —
    is exactly the bug that made 12 tests here go red while the injection
    mechanism they were meant to exercise worked correctly the whole time.
    Use `_recent_ts(...)` instead. Dates before 2025 (e.g. the deliberate
    "outside window" sentinel in test_skill_invocations_well_formed, or the
    codex-trial-log's plain YYYY-MM-DD markdown dates, which have no time
    component and are never checked against a days-cutoff) are unambiguously
    far enough from "now" — or not used for windowing at all — to be exempt.
    """
    source = Path(__file__).read_text(encoding="utf-8")

    marker = "def _recent_ts("
    start = source.index(marker)
    rest = source[start + len(marker):]
    next_def = re.search(r"\ndef ", rest)
    end = start + len(marker) + (next_def.start() if next_def else len(rest))
    scanned = source[:start] + source[end:]

    violations = [
        m.group(0)
        for m in re.finditer(r'"20(2[5-9]|[3-9]\d)-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^"]*"', scanned)
    ]
    assert not violations, (
        "hardcoded absolute-date fixture literal(s) found — use _recent_ts(...) "
        f"instead so this file doesn't silently go stale-and-red again: {violations}"
    )

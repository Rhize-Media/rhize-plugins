"""Tests for benchmark_status.py — the procedural-memory benchmark watchdog.

Run: python3 -m pytest tests/test_benchmark_status.py -q   (from the repo root)
"""
from __future__ import annotations

import copy
import json
import hashlib
import os
import stat
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import benchmark_status as bs  # noqa: E402


# --- fixtures: synthetic notes -----------------------------------------------

NOTE_ZERO_ROWS = """---
type: benchmark
---

# Procedural Memory Benchmark — Fixture

## Arms

- stuff

## Metrics log

| date | arm | wall_total_s | notes |
|---|---|---|---|
"""

NOTE_ONE_ARM_ONLY = """# Procedural Memory Benchmark — Fixture

## Metrics log

| date | arm | wall_total_s | notes |
|---|---|---|---|
| 2026-08-20 | A | 100 | first |
| 2026-08-22 | A | 110 | second |
| 2026-08-24 | A | 90 | third |
"""

NOTE_PAIRED_ROWS = """# Procedural Memory Benchmark — Fixture

## Metrics log

| date | arm | wall_total_s | notes |
|---|---|---|---|
| 2026-08-24 | A | 100 | real |
| 2026-08-24 | B | 12 | dry-run |
"""

NOTE_MALFORMED_ROW = """# Procedural Memory Benchmark — Fixture

## Metrics log

| date | arm | wall_total_s | notes |
|---|---|---|---|
| 2026-08-24 | A | 100 | fine |
| 2026-08-25 | B | only-two-cells |
| 2026-08-26 | A | 90 | also fine |
"""

NOTE_NO_SECTION = """# Procedural Memory Benchmark — Fixture

## Arms

- Arm A — baseline
- Arm B — retrieval

No metrics log heading anywhere in this note.
"""

NOTE_DIFFERENT_COLUMNS = """# Procedural Memory Benchmark — Fixture

## Metrics log

| date | arm | surface | outline_s | delegate_s |
|---|---|---|---|---|
| 2026-08-23 | A | cowork | 500 | 0 |
"""

NOTE_BAD_DATE = """# Procedural Memory Benchmark — Fixture

## Metrics log

| date | arm | wall_total_s |
|---|---|---|
| not-a-date | A | 100 |
| 2026-08-24 | A | 90 |
"""


# --- parser: zero rows --------------------------------------------------------


def test_parser_zero_rows():
    s = bs.summarize_note(NOTE_ZERO_ROWS)
    assert s["error"] is None
    assert s["total_rows"] == 0
    assert s["rows_by_arm"] == {}
    assert s["newest_row_date"] is None
    assert s["columns"] == ["date", "arm", "wall_total_s", "notes"]
    assert s["malformed_rows"] == []


# --- parser: one arm only -----------------------------------------------------


def test_parser_one_arm_only():
    s = bs.summarize_note(NOTE_ONE_ARM_ONLY)
    assert s["error"] is None
    assert s["total_rows"] == 3
    assert s["rows_by_arm"] == {"A": 3}
    assert s["newest_row_date"] == date(2026, 8, 24)
    assert s["newest_row_date_by_arm"] == {"A": date(2026, 8, 24)}


# --- parser: paired A/B rows --------------------------------------------------


def test_parser_paired_rows():
    s = bs.summarize_note(NOTE_PAIRED_ROWS)
    assert s["error"] is None
    assert s["total_rows"] == 2
    assert s["rows_by_arm"] == {"A": 1, "B": 1}
    assert s["newest_row_date"] == date(2026, 8, 24)
    assert s["newest_row_date_by_arm"] == {"A": date(2026, 8, 24), "B": date(2026, 8, 24)}
    assert hashlib.sha256(b"| 2026-08-24 | A | 100 | real |").hexdigest() in s[
        "row_evidence"
    ]


# --- parser: malformed row ----------------------------------------------------


def test_parser_malformed_row_excluded_and_recorded():
    s = bs.summarize_note(NOTE_MALFORMED_ROW)
    assert s["error"] is None
    # The 2-cell row must be excluded from totals, not crash the parse.
    assert s["total_rows"] == 2
    assert s["rows_by_arm"] == {"A": 2}
    assert len(s["malformed_rows"]) == 1
    assert "expected 4 columns, got 3" in s["malformed_rows"][0]["reason"]
    # The well-formed rows on either side of the bad one still parse.
    assert s["newest_row_date"] == date(2026, 8, 26)


# --- parser: missing '## Metrics log' section ---------------------------------


def test_parser_missing_metrics_log_section():
    s = bs.summarize_note(NOTE_NO_SECTION)
    assert s["error"] is not None
    assert "Metrics log" in s["error"]
    assert s["total_rows"] == 0
    assert s["columns"] == []


# --- parser: different column sets across notes -------------------------------


def test_parser_reports_each_notes_own_columns():
    a = bs.summarize_note(NOTE_ONE_ARM_ONLY)
    b = bs.summarize_note(NOTE_DIFFERENT_COLUMNS)
    assert a["columns"] == ["date", "arm", "wall_total_s", "notes"]
    assert b["columns"] == ["date", "arm", "surface", "outline_s", "delegate_s"]
    assert a["columns"] != b["columns"]
    assert b["total_rows"] == 1
    assert b["rows_by_arm"] == {"A": 1}


# --- parser: unparseable date in an otherwise well-formed row -----------------


def test_parser_unparseable_date_recorded_but_row_still_counted():
    s = bs.summarize_note(NOTE_BAD_DATE)
    assert s["error"] is None
    assert s["total_rows"] == 2  # both rows have the right column count
    assert len(s["unparseable_dates"]) == 1
    assert s["unparseable_dates"][0]["date_raw"] == "not-a-date"
    # Only the parseable date contributes to newest_row_date.
    assert s["newest_row_date"] == date(2026, 8, 24)


# --- note-level: missing file --------------------------------------------------


def test_missing_note_file_does_not_crash(tmp_path):
    missing = tmp_path / "does-not-exist" / "Procedural Memory Benchmark.md"
    s = bs.load_note_summary(missing)
    assert s["exists"] is False
    assert "file not found" in s["error"]
    assert s["total_rows"] == 0


def test_existing_note_file_read_end_to_end(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    note.write_text(NOTE_PAIRED_ROWS, encoding="utf-8")
    s = bs.load_note_summary(note)
    assert s["exists"] is True
    assert s["error"] is None
    assert s["total_rows"] == 2


# --- run telemetry: empty runs dir ---------------------------------------------


def test_empty_runs_dir_no_crash(tmp_path):
    empty_dir = tmp_path / "runs"
    empty_dir.mkdir()
    result = bs.load_run_telemetry(empty_dir)
    assert result["available"] is True
    assert result["error"] is None
    assert result["artifacts"] == {}
    assert result["files_read"] == 0


def test_missing_runs_dir_no_crash(tmp_path):
    result = bs.load_run_telemetry(tmp_path / "does-not-exist")
    assert result["available"] is False
    assert "not found" in result["error"]


def test_run_telemetry_streams_and_aggregates(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "2026-08-26.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"name": "bench-append", "ok": True, "started_at": "2026-08-26T17:55:54+00:00"}),
                json.dumps({"name": "bench-append", "ok": False, "started_at": "2026-08-26T17:56:06+00:00"}),
                "",  # trailing blank line must not break parsing
                "{not valid json",  # a corrupt line must not crash the stream
                json.dumps({"name": "vault-orphan-linker", "ok": True, "started_at": "2026-08-26T17:53:16+00:00"}),
            ]
        ),
        encoding="utf-8",
    )
    result = bs.load_run_telemetry(runs_dir)
    assert result["available"] is True
    assert result["files_read"] == 1
    bench = result["artifacts"]["bench-append"]
    assert bench["runs"] == 2
    assert bench["ok"] == 1
    assert bench["fail"] == 1
    assert bench["newest_started_at"] == "2026-08-26T17:56:06+00:00"
    assert result["artifacts"]["vault-orphan-linker"]["runs"] == 1


def test_run_telemetry_indexes_bench_append_runs_for_receipt_binding(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "2026-08-28.jsonl").write_text(
        json.dumps(
            {
                "name": "bench-append",
                "ok": True,
                "run_id": "capture-run",
                "started_at": "2026-08-28T00:10:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = bs.load_run_telemetry(runs)

    assert result["capture_runs"] == {
        "capture-run": {
            "ok": True,
            "started_at": "2026-08-28T00:10:00+00:00",
        }
    }


# --- health sidecars ------------------------------------------------------------


def test_health_sidecars_missing_dir_no_crash(tmp_path):
    result = bs.load_health_sidecars(tmp_path / "does-not-exist")
    assert result["available"] is False
    assert "not found" in result["error"]


def test_health_sidecars_read_nested(tmp_path):
    health_dir = tmp_path / ".health"
    (health_dir / "skill").mkdir(parents=True)
    (health_dir / "function" / "graphify").mkdir(parents=True)
    (health_dir / "skill" / "bench-append@1.0.0.json").write_text(
        json.dumps({"health": "ok", "last_verified": "2026-08-24"}), encoding="utf-8"
    )
    (health_dir / "function" / "graphify" / "extract@1.0.0.json").write_text(
        json.dumps({"health": "ok", "last_verified": "2026-08-24"}), encoding="utf-8"
    )
    result = bs.load_health_sidecars(health_dir)
    assert result["available"] is True
    assert result["artifacts"]["skill/bench-append@1.0.0"]["health"] == "ok"
    assert result["artifacts"]["function/graphify/extract@1.0.0"]["health"] == "ok"


# --- scheduler: unreadable/malformed JSON --------------------------------------


def test_scheduler_missing_dirs_no_crash(tmp_path):
    result = bs.load_scheduler_status(
        tmp_path / "no-cli-dir",
        tmp_path / "no-sessions-root",
    )
    assert "not found" in result["cli_scheduled_tasks_error"]
    assert "not found" in result["desktop_registry_error"]
    assert result["desktop_tasks"] == []


def test_scheduler_malformed_json_recorded_not_raised(tmp_path):
    cli_dir = tmp_path / "scheduled-tasks"
    cli_dir.mkdir()
    (cli_dir / "some-task").mkdir()

    sessions_root = tmp_path / "sessions"
    account_dir = sessions_root / "acct" / "space"
    account_dir.mkdir(parents=True)
    (account_dir / "scheduled-tasks.json").write_text("{not valid json", encoding="utf-8")

    result = bs.load_scheduler_status(cli_dir, sessions_root)
    assert result["cli_scheduled_tasks"] == ["some-task"]
    assert result["cli_scheduled_tasks_error"] is None
    assert len(result["desktop_tasks"]) == 1
    assert "error" in result["desktop_tasks"][0]


def test_scheduler_reads_valid_json(tmp_path):
    sessions_root = tmp_path / "sessions"
    account_dir = sessions_root / "acct" / "space"
    account_dir.mkdir(parents=True)
    (account_dir / "scheduled-tasks.json").write_text(
        json.dumps(
            {
                "scheduledTasks": [
                    {"id": "vault-inbox-processor", "enabled": True, "lastRunAt": "2026-08-22T18:04:33.327Z"},
                ]
            }
        ),
        encoding="utf-8",
    )
    result = bs.load_scheduler_status(tmp_path / "no-cli-dir", sessions_root)
    assert result["desktop_registry_error"] is None
    assert len(result["desktop_tasks"]) == 1
    assert result["desktop_tasks"][0]["id"] == "vault-inbox-processor"


# --- routine-state: scheduler-independent run-start signal (GAP 2) ------------


def _routine_state_file(
    dir_path: Path,
    routine_id: str,
    started_at_epoch_ms: int,
    *,
    append_completed: bool = True,
    scheduler_run_id: str | None = None,
    name: str,
) -> Path:
    payload = {
        "schemaVersion": 1,
        "routineId": routine_id,
        "schedulerRunId": scheduler_run_id or f"{routine_id}-run",
        "startedAtEpochMs": started_at_epoch_ms,
        "steps": [],
        "appendCompleted": append_completed,
    }
    path = dir_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_routine_state_missing_dir_no_crash(tmp_path):
    result = bs.load_routine_state_runs(tmp_path / "does-not-exist")
    assert result["available"] is False
    assert "not found" in result["error"]
    assert result["routines"] == {}


def test_routine_state_picks_newest_per_routine(tmp_path):
    state_dir = tmp_path / "routine-state"
    state_dir.mkdir()
    _routine_state_file(state_dir, "daily-completed-summary", 1_000_000, name="daily-completed-summary-a.json")
    _routine_state_file(state_dir, "daily-completed-summary", 2_000_000, name="daily-completed-summary-b.json")
    _routine_state_file(state_dir, "weekly-skill-audit", 1_500_000, name="weekly-skill-audit-a.json")

    result = bs.load_routine_state_runs(state_dir)

    assert result["available"] is True
    assert result["error"] is None
    dcs = result["routines"]["daily-completed-summary"]
    assert dcs["state_file"] == "daily-completed-summary-b.json"
    assert dcs["run_count"] == 2
    assert dcs["append_completed"] is True
    assert "/" not in dcs["state_file"] and "\\" not in dcs["state_file"]
    wsa = result["routines"]["weekly-skill-audit"]
    assert wsa["run_count"] == 1


def test_routine_state_skips_sibling_and_dotfiles(tmp_path):
    state_dir = tmp_path / "routine-state"
    state_dir.mkdir()
    _routine_state_file(state_dir, "weekly-skill-audit", 1_000_000, name="weekly-skill-audit-a.json")
    # Sibling metadata/input files share the routine id and carry a later
    # startedAtEpochMs, but must never be read as run records.
    (state_dir / "weekly-skill-audit-a.metadata.json").write_text(
        json.dumps({"schemaVersion": 1, "routineId": "weekly-skill-audit", "startedAtEpochMs": 9_000_000}),
        encoding="utf-8",
    )
    (state_dir / "weekly-skill-audit-a.input.json").write_text("{}", encoding="utf-8")
    (state_dir / ".weekly-skill-audit-a.json.lock").write_text("", encoding="utf-8")

    result = bs.load_routine_state_runs(state_dir)

    wsa = result["routines"]["weekly-skill-audit"]
    assert wsa["run_count"] == 1
    assert wsa["state_file"] == "weekly-skill-audit-a.json"


def test_routine_state_tolerates_malformed_and_wrong_schema(tmp_path):
    state_dir = tmp_path / "routine-state"
    state_dir.mkdir()
    _routine_state_file(state_dir, "weekly-skill-audit", 1_000_000, name="weekly-skill-audit-a.json")
    (state_dir / "corrupt.json").write_text("{not valid json", encoding="utf-8")
    (state_dir / "wrong-schema.json").write_text(
        json.dumps({"schemaVersion": 2, "routineId": "weekly-skill-audit", "startedAtEpochMs": 9_000_000}),
        encoding="utf-8",
    )

    result = bs.load_routine_state_runs(state_dir)

    assert result["available"] is True
    assert result["skipped"] == 2
    assert result["routines"]["weekly-skill-audit"]["run_count"] == 1


# --- liveness: one test per status value ----------------------------------------


def _note(total_rows=0, newest_row_date=None, error=None):
    return {"error": error, "total_rows": total_rows, "newest_row_date": newest_row_date}


def test_liveness_ok_when_row_covers_last_run():
    # The date-only fallback is retained only for history from before receipt
    # enforcement existed.
    note = _note(total_rows=1, newest_row_date=date(2026, 8, 25))
    lookup = {"matched": True, "last_run_at": datetime(2026, 8, 24, 19, 1, 37)}
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "ok"


def test_liveness_requires_receipt_even_when_a_later_row_exists():
    note = _note(total_rows=2, newest_row_date=date(2026, 8, 29))
    lookup = {
        "matched": True,
        "last_run_at": datetime.fromisoformat("2026-08-28T19:01:37.956+00:00"),
    }

    verdict = bs.classify_liveness(note, lookup)

    assert verdict["status"] == "receipt_missing"
    assert "later row" in verdict["reason"]
    assert "no fresh run-bound receipt" in verdict["reason"]


def test_liveness_indeterminate_same_day_when_run_and_row_share_a_date():
    # The exact false-negative this module used to produce: the scheduler's
    # last run and the newest logged row share a calendar date. Rows carry
    # only a date, not a time, so whether the row was written before or
    # after that day's run cannot be proven either way — this must NOT be
    # reported as "ok" (this was previously asserted as "ok" — that
    # assertion documented the bug, not a spec).
    note = _note(total_rows=1, newest_row_date=date(2026, 8, 28))
    lookup = {"matched": True, "last_run_at": datetime(2026, 8, 28, 19, 1, 37)}
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "indeterminate_same_day"
    assert "2026-08-28" in v["reason"]
    assert "cannot be determined" in v["reason"]


def test_liveness_marks_pre_enforcement_same_day_history_unverifiable():
    note = _note(total_rows=1, newest_row_date=date(2026, 8, 24))
    lookup = {
        "matched": True,
        "last_run_at": datetime.fromisoformat("2026-08-24T19:01:37.956+00:00"),
    }

    verdict = bs.classify_liveness(note, lookup)

    assert verdict["status"] == "legacy_unverifiable"
    assert "before timestamped receipt enforcement" in verdict["reason"]
    assert "not reconstructed" in verdict["reason"]


def test_liveness_keeps_post_enforcement_same_day_history_actionable():
    note = _note(total_rows=1, newest_row_date=date(2026, 8, 28))
    lookup = {
        "matched": True,
        "last_run_at": datetime.fromisoformat("2026-08-28T19:01:37.956+00:00"),
    }

    verdict = bs.classify_liveness(note, lookup)

    assert verdict["status"] == "indeterminate_same_day"


def test_liveness_uses_new_york_date_for_utc_scheduler_instant():
    # The scheduler stores instants in UTC while benchmark notes record the
    # America/New_York calendar date. 00:01 UTC is still the prior local day.
    note = _note(total_rows=2, newest_row_date=date(2026, 8, 28))
    lookup = {
        "matched": True,
        "last_run_at": datetime.fromisoformat("2026-08-29T00:01:20.025+00:00"),
    }
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "indeterminate_same_day"
    assert "2026-08-28" in v["reason"]


def test_liveness_still_flags_a_later_new_york_calendar_date():
    note = _note(total_rows=2, newest_row_date=date(2026, 8, 28))
    lookup = {
        "matched": True,
        "last_run_at": datetime.fromisoformat("2026-08-29T05:00:00+00:00"),
    }
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "row_missing"
    assert "2026-08-29" in v["reason"]


def test_liveness_row_missing_when_run_postdates_newest_row():
    # This is the case the whole module exists to catch: the scheduler shows a
    # run that happened AFTER the newest row was logged.
    note = _note(total_rows=3, newest_row_date=date(2026, 8, 20))
    lookup = {"matched": True, "last_run_at": datetime(2026, 8, 23, 21, 0, 41)}
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "row_missing"
    assert "2026-08-23" in v["reason"]
    assert "2026-08-20" in v["reason"]


def test_liveness_row_missing_when_zero_rows_but_scheduler_has_run():
    # Mirrors the real, live 'daily-completed-summary' case: the oneoff
    # benchmark trigger ran, but the note's Metrics log table has zero rows.
    note = _note(total_rows=0, newest_row_date=None)
    lookup = {"matched": True, "last_run_at": datetime(2026, 8, 23, 21, 0, 41)}
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "row_missing"
    assert "zero rows" in v["reason"]


def test_liveness_never_run():
    note = _note(total_rows=0, newest_row_date=None)
    lookup = {"matched": True, "last_run_at": None}
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "never_run"


def test_liveness_unknown_when_scheduler_unmatched():
    note = _note(total_rows=2, newest_row_date=date(2026, 8, 23))
    lookup = {"matched": False, "reason": "no desktop scheduler entry matched keys [...]"}
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "unknown"
    assert "no desktop scheduler entry" in v["reason"]


def test_liveness_unknown_when_note_unreadable():
    note = _note(error="file not found: /nope")
    lookup = {"matched": True, "last_run_at": datetime(2026, 8, 24, 0, 0, 0)}
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "unknown"
    assert "could not read/parse note" in v["reason"]


def test_liveness_unknown_when_scheduler_has_no_timestamp_but_rows_exist():
    note = _note(total_rows=2, newest_row_date=date(2026, 8, 23))
    lookup = {"matched": True, "last_run_at": None}
    v = bs.classify_liveness(note, lookup)
    assert v["status"] == "unknown"


def test_all_seven_liveness_statuses_are_reachable():
    # A whole-suite sanity check: every status value this module defines can
    # actually be produced. A watchdog that can only ever emit 'ok' is useless.
    statuses = {
        "ok": test_liveness_ok_when_row_covers_last_run,
        "legacy_unverifiable": test_liveness_marks_pre_enforcement_same_day_history_unverifiable,
        "indeterminate_same_day": test_liveness_indeterminate_same_day_when_run_and_row_share_a_date,
        "receipt_missing": test_liveness_requires_receipt_even_when_a_later_row_exists,
        "row_missing": test_liveness_row_missing_when_run_postdates_newest_row,
        "never_run": test_liveness_never_run,
        "unknown": test_liveness_unknown_when_scheduler_unmatched,
    }
    assert set(statuses) == set(bs.LIVENESS_STATUSES)


# --- find_scheduler_last_run: matching + on-demand routine ----------------------


def test_find_scheduler_last_run_matches_by_substring():
    scheduler_status = {
        "desktop_tasks": [
            {"id": "vault-inbox-processor", "lastRunAt": "2026-08-22T18:04:33.327Z"},
            {"id": "ai-stack-version-drift", "lastRunAt": "2026-08-24T19:01:37.956Z"},
        ]
    }
    lookup = bs.find_scheduler_last_run("Vault Inbox Processor", scheduler_status)
    assert lookup["matched"] is True
    assert lookup["last_run_at"] == datetime.fromisoformat("2026-08-22T18:04:33.327+00:00")


def test_find_scheduler_last_run_picks_newest_among_multiple_matches():
    scheduler_status = {
        "desktop_tasks": [
            {"id": "daily-completed-summary", "lastRunAt": "2026-07-16T00:01:49.927Z"},
            {"id": "oneoff-daily-summary-benchmark-run", "lastRunAt": "2026-08-23T21:00:41.115Z"},
        ]
    }
    lookup = bs.find_scheduler_last_run("Daily Completed Summary", scheduler_status)
    assert lookup["matched"] is True
    assert lookup["last_run_at"] == datetime.fromisoformat("2026-08-23T21:00:41.115+00:00")
    assert set(lookup["matched_ids"]) == {"daily-completed-summary", "oneoff-daily-summary-benchmark-run"}


def test_find_scheduler_last_run_content_engine_is_on_demand():
    lookup = bs.find_scheduler_last_run("Content Engine", {"desktop_tasks": []})
    assert lookup["matched"] is False
    assert "on-demand" in lookup["reason"]


def test_find_scheduler_last_run_routine_state_only_when_no_scheduler_keys():
    # Weekly Skill Audit: ROUTINE_SCHEDULER_KEYS is deliberately empty (its
    # canonical scheduler persists no on-disk lastRunAt), so recency must come
    # entirely from the routine-state signal.
    scheduler_status = {"desktop_tasks": []}
    routine_state_runs = {
        "available": True,
        "error": None,
        "routines": {
            "weekly-skill-audit": {
                "started_at": "2026-08-31T22:35:44Z",
                "state_file": "weekly-skill-audit-20260831T223544Z-37960689.json",
                "append_completed": True,
                "run_count": 1,
            }
        },
    }

    lookup = bs.find_scheduler_last_run("Weekly Skill Audit", scheduler_status, routine_state_runs)

    assert lookup["matched"] is True
    assert lookup["sources"] == ["routine-state"]
    assert lookup["last_run_at"] == datetime.fromisoformat("2026-08-31T22:35:44+00:00")
    assert lookup["routine_state_started_at"] == "2026-08-31T22:35:44Z"


def test_find_scheduler_last_run_combines_desktop_and_routine_state_newest_wins():
    scheduler_status = {
        "desktop_tasks": [
            {"id": "daily-completed-summary", "enabled": True, "lastRunAt": "2026-09-01T00:02:28Z"},
        ]
    }
    routine_state_runs = {
        "available": True,
        "error": None,
        "routines": {
            "daily-completed-summary": {
                "started_at": "2026-09-03T00:03:47Z",
                "state_file": "daily-completed-summary-20260903T000347Z-8bfa5cfc.json",
                "append_completed": False,
                "run_count": 5,
            }
        },
    }

    lookup = bs.find_scheduler_last_run("Daily Completed Summary", scheduler_status, routine_state_runs)

    assert lookup["matched"] is True
    assert set(lookup["sources"]) == {"desktop", "routine-state"}
    assert lookup["last_run_at"] == datetime.fromisoformat("2026-09-03T00:03:47+00:00")


def test_find_scheduler_last_run_desktop_newer_than_routine_state():
    scheduler_status = {
        "desktop_tasks": [
            {"id": "daily-completed-summary", "enabled": True, "lastRunAt": "2026-09-03T12:00:00Z"},
        ]
    }
    routine_state_runs = {
        "available": True,
        "error": None,
        "routines": {
            "daily-completed-summary": {
                "started_at": "2026-09-01T00:02:28Z",
                "state_file": "daily-completed-summary-20260901T000228Z-3ed3ccc2.json",
                "append_completed": False,
                "run_count": 1,
            }
        },
    }

    lookup = bs.find_scheduler_last_run("Daily Completed Summary", scheduler_status, routine_state_runs)

    assert lookup["matched"] is True
    assert set(lookup["sources"]) == {"desktop", "routine-state"}
    assert lookup["last_run_at"] == datetime.fromisoformat("2026-09-03T12:00:00+00:00")


# --- integration: row_missing fires end-to-end via build_snapshot ---------------


def test_build_snapshot_end_to_end_row_missing(tmp_path):
    """Full fixture tree reproducing the real daily-completed-summary defect:
    a note with zero rows, plus a scheduler registry entry whose lastRunAt
    postdates the note. Must classify as row_missing without touching any real
    filesystem path outside tmp_path."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    note_path = notes_dir / "Procedural Memory Benchmark.md"
    note_path.write_text(NOTE_ZERO_ROWS, encoding="utf-8")

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    health_dir = tmp_path / ".health"
    health_dir.mkdir()

    cli_dir = tmp_path / "scheduled-tasks"
    cli_dir.mkdir()

    sessions_root = tmp_path / "sessions"
    account_dir = sessions_root / "acct" / "space"
    account_dir.mkdir(parents=True)
    (account_dir / "scheduled-tasks.json").write_text(
        json.dumps(
            {
                "scheduledTasks": [
                    {
                        "id": "daily-completed-summary",
                        "enabled": False,
                        "lastRunAt": "2026-07-16T00:01:49.927Z",
                    },
                    {
                        "id": "oneoff-daily-summary-benchmark-run",
                        "enabled": False,
                        "lastRunAt": "2026-08-23T21:00:41.115Z",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = bs.build_snapshot(
        notes={"Daily Completed Summary": note_path},
        runs_dir=runs_dir,
        health_dir=health_dir,
        scheduled_tasks_dir=cli_dir,
        sessions_root=sessions_root,
    )

    assert snapshot["liveness"]["Daily Completed Summary"]["status"] == "row_missing"
    assert snapshot["notes"]["Daily Completed Summary"]["total_rows"] == 0


def test_build_snapshot_row_missing_from_routine_state_only_signal(tmp_path):
    """Weekly Skill Audit has no Desktop lastRunAt to trust (its canonical
    scheduler persists none on disk; the paused Desktop copy's manual runs
    never append per the routine's own contract). Liveness must still fire
    row_missing when the routine-state run-start signal (GAP 2) is newer than
    the newest note row."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    note_path = notes_dir / "Procedural Memory Benchmark.md"
    note_path.write_text(NOTE_ZERO_ROWS, encoding="utf-8")

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    health_dir = tmp_path / ".health"
    health_dir.mkdir()
    cli_dir = tmp_path / "scheduled-tasks"
    cli_dir.mkdir()
    sessions_root = tmp_path / "sessions"
    (sessions_root / "acct" / "space").mkdir(parents=True)
    (sessions_root / "acct" / "space" / "scheduled-tasks.json").write_text(
        json.dumps({"scheduledTasks": []}), encoding="utf-8"
    )
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    state_dir = tmp_path / "routine-state"
    state_dir.mkdir()
    _routine_state_file(
        state_dir,
        "weekly-skill-audit",
        1_788_215_744_357,
        name="weekly-skill-audit-20260831T223544Z-37960689.json",
    )

    snapshot = bs.build_snapshot(
        notes={"Weekly Skill Audit": note_path},
        runs_dir=runs_dir,
        health_dir=health_dir,
        scheduled_tasks_dir=cli_dir,
        sessions_root=sessions_root,
        receipts_dir=receipts_dir,
        routine_state_dir=state_dir,
    )

    assert snapshot["liveness"]["Weekly Skill Audit"]["status"] == "row_missing"
    assert snapshot["liveness"]["Weekly Skill Audit"]["sources"] == ["routine-state"]
    assert snapshot["routine_state"]["routines"]["weekly-skill-audit"]["run_count"] == 1


# --- live data: real vault notes must match verified ground truth ---------------


def test_live_vault_notes_parse_with_consistent_structure():
    """Runs the real parser against the real vault notes.

    Deliberately asserts STRUCTURAL INVARIANTS, not specific row counts. An
    earlier version of this test hard-coded the counts verified by hand on
    2026-08-26 (Vault Inbox 2, Drift 1, Daily Summary 0, Content Engine 2) and
    broke within hours when a peer session legitimately appended a Content
    Engine Arm-B row. A test that fails because the system did exactly what it
    is supposed to do is not protecting anything — it just trains people to
    deselect it. The invariants below stay true as rows accumulate.
    """
    import pytest

    for path in bs.BENCHMARK_NOTES.values():
        if not path.exists():
            pytest.skip(f"vault not mounted on this machine: {path}")

    summaries = bs.load_all_note_summaries()
    assert set(summaries) == set(bs.BENCHMARK_NOTES), "every configured note must be summarised"

    for name, summary in summaries.items():
        assert summary.get("error") is None, f"{name} failed to parse: {summary.get('error')}"
        assert summary.get("columns"), f"{name} produced no column header"
        assert summary["columns"][0] == "date" and summary["columns"][1] == "arm", (
            f"{name}: every benchmark table starts date|arm — got {summary['columns'][:2]}"
        )
        total = summary.get("total_rows", 0)
        by_arm = summary.get("rows_by_arm", {}) or {}
        assert sum(by_arm.values()) == total, (
            f"{name}: rows_by_arm {by_arm} does not account for all {total} rows"
        )
        assert not summary.get("malformed_rows"), f"{name} has malformed rows"
        assert not summary.get("unparseable_dates"), f"{name} has unparseable dates"
        if total:
            assert summary.get("newest_row_date"), f"{name} has rows but no newest date"


# --- timestamped capture receipts ---------------------------------------------


def _capture_receipt(note: Path, **overrides):
    row = overrides.pop("row", "| 2026-08-28 | A | 100 | real |")
    value = {
        "schemaVersion": 1,
        "capturedAt": "2026-08-29T00:12:17.873185+00:00",
        "runId": "a5b94939-73ef-4062-be41-3325ad512618",
        "noteId": bs.note_identity(note),
        "rowSha256": hashlib.sha256(row.encode()).hexdigest(),
        "rowDate": "2026-08-28",
        "arm": "A",
        "beforeCount": 4,
        "afterCount": 5,
    }
    value.update(overrides)
    return value


def _strict_capture_receipt(note: Path, **overrides):
    row = overrides.pop("row", "| 2026-08-28 | A | 100 | real |")
    run_id = "a5b94939-73ef-4062-be41-3325ad512618"
    note_id = bs.note_identity(note)
    row_digest = hashlib.sha256(row.encode()).hexdigest()
    value = {
        "schemaVersion": 2,
        "capturedAt": "2026-08-29T00:12:17.873Z",
        "schema_version": "procedural-engineering-eval/v2",
        "record_type": "routine_run",
        "observed_at": "2026-08-29T00:10:01.000Z",
        "baseline_sha": "a" * 40,
        "variant": "A",
        "arm": "A",
        "environment": "cowork",
        "routine_id": "daily-completed-summary",
        "scheduler_run_id": "daily-completed-summary-20260829T000000Z",
        "artifact_run_id": run_id,
        "task_scope": {
            "scope_id": "one-window",
            "source_classes": ["git", "jira"],
            "source_count": 2,
            "parameter_keys": ["window-end", "window-start"],
        },
        "input_fingerprint": "b" * 64,
        "definition_digest": "c" * 64,
        "artifact_digest": "d" * 64,
        "started_at": "2026-08-29T00:10:00.000Z",
        "ended_at": "2026-08-29T00:10:01.000Z",
        "duration_ms": 1000,
        "expected_steps": ["collect"],
        "completed_steps": ["collect"],
        "steps": [
            {
                "step_id": "collect",
                "status": "completed",
                "started_at": "2026-08-29T00:10:00.000Z",
                "ended_at": "2026-08-29T00:10:01.000Z",
                "duration_ms": 1000,
            }
        ],
        "outputs": [{"output_id": "summary-note", "output_type": "note"}],
        "effects": [
            {
                "effect_id": "summary-note-write",
                "effect_type": "note-write",
                "status": "completed",
            }
        ],
        "failure_classes": [],
        "retry_count": 0,
        "approval_cycles": 0,
        "correctness": {
            "schema_valid": True,
            "source_failures_present": False,
            "human_correction_required": False,
            "unsafe_effect_prevented": False,
            "fabricated_clean_detected": False,
        },
        "benchmark": {
            "row_id": "daily-completed-summary-20260829T000000Z-row",
            "row_sha256": row_digest,
            "note_id": note_id,
            "projection": {
                "before_count": 4,
                "after_count": 5,
                "row_delta": 1,
                "row_is_last": True,
                "append_assertion": "passed",
            },
        },
        "duration_reconciliation": {
            "step_total_ms": 1000,
            "unattributed_ms": 0,
            "timestamps_reconciled": True,
        },
        "comparable": True,
        "comparability_reasons": [],
        "rowDate": "2026-08-28",
        "rowDateSource": "row",
        "noteId": note_id,
        "rowSha256": row_digest,
        "beforeCount": 4,
        "afterCount": 5,
        "runId": run_id,
    }
    value.update(overrides)
    return value


def test_capture_receipts_are_strict_timestamped_and_note_bound(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    path = receipt_dir / "receipt.json"
    path.write_text(json.dumps(_capture_receipt(note)), encoding="utf-8")
    os.chmod(path, 0o600)

    result = bs.load_benchmark_receipts(receipt_dir)

    assert result["available"] is True
    assert result["malformed"] == []
    receipts = result["by_note_id"][bs.note_identity(note)]
    assert len(receipts) == 1
    assert receipts[0]["arm"] == "A"
    assert receipts[0]["captured_at"] == datetime.fromisoformat(
        "2026-08-29T00:12:17.873185+00:00"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_capture_receipts_accept_strict_v2_lifecycle_evidence(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    path = receipt_dir / "strict.json"
    path.write_text(json.dumps(_strict_capture_receipt(note)), encoding="utf-8")
    os.chmod(path, 0o600)

    result = bs.load_benchmark_receipts(receipt_dir)

    assert result["valid"] == 1
    assert result["malformed"] == []
    assert result["by_variant"] == {"A": 1}
    assert result["by_schema_version"] == {"2": 1}
    receipt = result["by_note_id"][bs.note_identity(note)][0]
    assert receipt["routine_id"] == "daily-completed-summary"
    assert receipt["runId"] == receipt["artifact_run_id"]


def test_capture_receipts_keep_strict_v2_noncomparable_runs_as_capture_evidence(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    receipt = _strict_capture_receipt(note)
    receipt["steps"][0]["status"] = "partial"
    receipt["completed_steps"] = []
    receipt["failure_classes"] = ["source-partial"]
    receipt["correctness"]["source_failures_present"] = True
    receipt["comparable"] = False
    receipt["comparability_reasons"] = ["source-partial"]
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    path = receipt_dir / "strict-noncomparable.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    os.chmod(path, 0o600)

    result = bs.load_benchmark_receipts(receipt_dir)

    assert result["valid"] == 1
    assert result["malformed"] == []
    loaded = result["by_note_id"][bs.note_identity(note)][0]
    assert loaded["comparable"] is False
    assert loaded["comparability_reasons"] == ["source-partial"]


@pytest.mark.parametrize(
    "mutation, expected_reason",
    [
        (lambda value: value.update({"runId": "different-run"}), "runId must match artifact_run_id"),
        (
            lambda value: value["benchmark"]["projection"].update({"row_delta": 2}),
            "benchmark projection must prove the same exact one-row append",
        ),
        (
            lambda value: value["benchmark"].update({"row_sha256": "e" * 64}),
            "benchmark digests must match the top-level row and note digests",
        ),
        (lambda value: value.update({"unexpected": True}), "receipt fields do not match schema version 2"),
    ],
)
def test_capture_receipts_reject_invalid_strict_v2_evidence(
    tmp_path, mutation, expected_reason
):
    note = tmp_path / "Procedural Memory Benchmark.md"
    receipt = copy.deepcopy(_strict_capture_receipt(note))
    mutation(receipt)
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    path = receipt_dir / "strict-invalid.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    os.chmod(path, 0o600)

    result = bs.load_benchmark_receipts(receipt_dir)

    assert result["valid"] == 0
    assert result["malformed"] == [
        {"file": "strict-invalid.json", "reason": expected_reason}
    ]


def test_capture_receipts_accept_graph_variant_without_counting_it_as_ab(tmp_path):
    note = tmp_path / "Graph Benchmark.md"
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    path = receipt_dir / "graph.json"
    path.write_text(
        json.dumps(
            _capture_receipt(
                note,
                arm="G1",
                variant="G1",
                rowDateSource="captured_local_date",
            )
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)

    result = bs.load_benchmark_receipts(receipt_dir)

    assert result["valid"] == 1
    assert result["malformed"] == []
    assert result["by_variant"] == {"G1": 1}
    assert result["by_note_id"][bs.note_identity(note)][0]["variant"] == "G1"


@pytest.mark.parametrize(
    "overrides, expected_reason",
    [
        ({"variant": "G1"}, "variant must match arm"),
        (
            {"rowDateSource": "captured_local_date"},
            "captured_local_date is valid only for graph variants",
        ),
        (
            {
                "arm": "G1",
                "variant": "G1",
                "rowDateSource": "captured_local_date",
                "runId": None,
            },
            "captured_local_date requires runId",
        ),
    ],
)
def test_capture_receipt_rejects_cross_variant_metadata(tmp_path, overrides, expected_reason):
    note = tmp_path / "Procedural Memory Benchmark.md"
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    path = receipt_dir / "invalid.json"
    path.write_text(json.dumps(_capture_receipt(note, **overrides)), encoding="utf-8")
    os.chmod(path, 0o600)

    result = bs.load_benchmark_receipts(receipt_dir)

    assert result["valid"] == 0
    assert result["malformed"] == [{"file": "invalid.json", "reason": expected_reason}]


def test_capture_receipt_validation_surfaces_corrupt_and_invalid_files(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    (receipt_dir / "broken.json").write_text("{not-json", encoding="utf-8")
    (receipt_dir / "wrong-arm.json").write_text(
        json.dumps(_capture_receipt(note, arm="C")), encoding="utf-8"
    )
    (receipt_dir / "wrong-delta.json").write_text(
        json.dumps(_capture_receipt(note, beforeCount=4, afterCount=6)), encoding="utf-8"
    )
    for path in receipt_dir.glob("*.json"):
        os.chmod(path, 0o600)

    result = bs.load_benchmark_receipts(receipt_dir)

    assert result["by_note_id"] == {}
    assert {item["file"] for item in result["malformed"]} == {
        "broken.json",
        "wrong-arm.json",
        "wrong-delta.json",
    }
    assert all("/" not in item["file"] for item in result["malformed"])


def test_capture_receipt_resolves_same_day_liveness(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    summary = _note(total_rows=2, newest_row_date=date(2026, 8, 28))
    lookup = {
        "matched": True,
        "last_run_at": datetime.fromisoformat("2026-08-29T00:01:20.025+00:00"),
    }
    receipt = _capture_receipt(note)
    receipt["captured_at"] = datetime.fromisoformat(receipt.pop("capturedAt"))

    verdict = bs.classify_liveness(summary, lookup, [receipt])

    assert verdict["status"] == "ok"
    assert "timestamped capture receipt" in verdict["reason"]


def test_capture_receipt_resolves_a_short_cross_midnight_run(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    summary = _note(total_rows=2, newest_row_date=date(2026, 8, 29))
    lookup = {
        "matched": True,
        "last_run_at": datetime.fromisoformat("2026-08-29T03:59:00+00:00"),
    }
    receipt = _capture_receipt(
        note,
        rowDate="2026-08-29",
        capturedAt="2026-08-29T04:05:00+00:00",
    )
    receipt["captured_at"] = datetime.fromisoformat(receipt.pop("capturedAt"))

    verdict = bs.classify_liveness(summary, lookup, [receipt])

    assert verdict["status"] == "ok"


def test_capture_receipt_older_than_scheduler_run_does_not_hide_missing_row(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    summary = _note(total_rows=2, newest_row_date=date(2026, 8, 28))
    lookup = {
        "matched": True,
        "last_run_at": datetime.fromisoformat("2026-08-29T00:30:00+00:00"),
    }
    receipt = _capture_receipt(note)
    receipt["captured_at"] = datetime.fromisoformat(receipt.pop("capturedAt"))

    verdict = bs.classify_liveness(summary, lookup, [receipt])

    assert verdict["status"] == "indeterminate_same_day"


def _build_receipt_snapshot(
    tmp_path, *, receipt_overrides=None, include_run=True, schema_version=1
):
    note = tmp_path / "Procedural Memory Benchmark.md"
    note.write_text(NOTE_PAIRED_ROWS.replace("2026-08-24", "2026-08-28"), encoding="utf-8")
    receipt_factory = _strict_capture_receipt if schema_version == 2 else _capture_receipt
    receipt = receipt_factory(note, **(receipt_overrides or {}))
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    (receipt_dir / "capture.json").write_text(json.dumps(receipt), encoding="utf-8")
    os.chmod(receipt_dir / "capture.json", 0o600)
    sessions = tmp_path / "sessions" / "acct" / "space"
    sessions.mkdir(parents=True)
    (sessions / "scheduled-tasks.json").write_text(
        json.dumps(
            {
                "scheduledTasks": [
                    {
                        "id": "daily-completed-summary",
                        "enabled": True,
                        "lastRunAt": "2026-08-29T00:01:20.025Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    runs.mkdir()
    if include_run:
        (runs / "capture.jsonl").write_text(
            json.dumps(
                {
                    "name": "bench-append",
                    "ok": True,
                    "run_id": receipt["runId"],
                    "started_at": "2026-08-29T00:10:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )
    health = tmp_path / "health"
    health.mkdir()
    scheduled = tmp_path / "scheduled"
    scheduled.mkdir()

    return bs.build_snapshot(
        notes={"Daily Completed Summary": note},
        runs_dir=runs,
        health_dir=health,
        scheduled_tasks_dir=scheduled,
        sessions_root=tmp_path / "sessions",
        receipts_dir=receipt_dir,
        # Isolated (nonexistent) on purpose: without this, build_snapshot's
        # routine_state_dir default reads the real machine's
        # ~/.rhize/procedural-memory/routine-state, which can contain a real
        # 'daily-completed-summary' run newer than this fixture's controlled
        # scheduler/note dates and change the liveness verdict under test.
        routine_state_dir=tmp_path / "routine-state",
    )


def test_build_snapshot_includes_receipt_health_and_uses_it(tmp_path):
    snapshot = _build_receipt_snapshot(tmp_path)

    assert snapshot["capture_receipts"]["valid"] == 1
    assert snapshot["liveness"]["Daily Completed Summary"]["status"] == "ok"


def test_build_snapshot_binds_strict_v2_receipt_to_successful_artifact_run(tmp_path):
    snapshot = _build_receipt_snapshot(tmp_path, schema_version=2)

    assert snapshot["capture_receipts"]["valid"] == 1
    assert snapshot["capture_receipts"]["by_schema_version"] == {"2": 1}
    assert snapshot["capture_receipts"]["unbound"] == []
    assert snapshot["liveness"]["Daily Completed Summary"]["status"] == "ok"


def test_build_snapshot_rejects_strict_v2_receipt_for_wrong_routine(tmp_path):
    snapshot = _build_receipt_snapshot(
        tmp_path,
        schema_version=2,
        receipt_overrides={"routine_id": "vault-inbox-processor"},
    )

    assert snapshot["liveness"]["Daily Completed Summary"]["status"] == "indeterminate_same_day"
    assert snapshot["capture_receipts"]["unbound"] == [
        {
            "arm": "A",
            "file": "capture.json",
            "reason": "strict receipt routine id does not match the benchmark routine",
            "routine": "Daily Completed Summary",
        }
    ]


def test_build_snapshot_rejects_strict_v2_receipt_without_artifact_run(tmp_path):
    snapshot = _build_receipt_snapshot(
        tmp_path,
        schema_version=2,
        include_run=False,
    )

    assert snapshot["liveness"]["Daily Completed Summary"]["status"] == "indeterminate_same_day"
    assert snapshot["capture_receipts"]["unbound"] == [
        {
            "arm": "A",
            "file": "capture.json",
            "reason": "receipt runId does not match bench-append run telemetry",
            "routine": "Daily Completed Summary",
        }
    ]


def test_build_snapshot_keeps_graph_receipt_out_of_ab_liveness(tmp_path):
    snapshot = _build_receipt_snapshot(
        tmp_path,
        receipt_overrides={
            "arm": "G1",
            "variant": "G1",
            "rowDateSource": "captured_local_date",
        },
    )

    assert snapshot["capture_receipts"]["valid"] == 1
    assert snapshot["capture_receipts"]["by_variant"] == {"G1": 1}
    assert snapshot["capture_receipts"]["unbound"] == []
    assert snapshot["liveness"]["Daily Completed Summary"]["status"] == "indeterminate_same_day"


def test_build_snapshot_rejects_a_receipt_without_matching_run_telemetry(tmp_path):
    snapshot = _build_receipt_snapshot(tmp_path, include_run=False)

    assert snapshot["liveness"]["Daily Completed Summary"]["status"] == "indeterminate_same_day"
    assert snapshot["capture_receipts"]["unbound"] == [
        {
            "arm": "A",
            "file": "capture.json",
            "reason": "receipt runId does not match bench-append run telemetry",
            "routine": "Daily Completed Summary",
        }
    ]
    finding = next(
        item for item in bs.actionable_findings(snapshot) if item["status"] == "unbound_receipt"
    )
    assert finding["arm"] == "A"


# --- render_human: names which source(s) supplied each routine's run instant ---


def test_render_human_shows_source_for_each_routine():
    snapshot = {
        "liveness": {
            "Weekly Skill Audit": {
                "status": "row_missing",
                "reason": "a run happened and no row landed",
                "sources": ["routine-state"],
            },
            "Daily Completed Summary": {
                "status": "ok",
                "reason": "newest row covers scheduler's last run",
                "sources": ["desktop", "routine-state"],
            },
            "Content Engine": {
                "status": "unknown",
                "reason": "on-demand routine by design",
                "sources": [],
            },
        },
        "notes": {},
        "run_telemetry": {"available": False, "error": "n/a"},
        "health": {"available": False, "error": "n/a"},
    }

    output = bs.render_human(snapshot)

    assert "Weekly Skill Audit (via routine-state)" in output
    assert "Daily Completed Summary (via desktop+routine-state)" in output
    assert "Content Engine —" in output  # no sources -> no "(via ...)" suffix


# --- actionable eval findings + Sentry event transport -------------------------


def test_actionable_findings_cover_missing_unverifiable_and_malformed_evidence():
    snapshot = {
        "generated_at": "2026-08-28T00:30:00+00:00",
        "liveness": {
            "Missing": {
                "status": "row_missing",
                "reason": "a run happened and no row landed",
                "scheduler_matched_ids": ["missing-task"],
                "scheduler_last_run_at": "2026-08-28T00:01:00+00:00",
            },
            "Same Day": {
                "status": "indeterminate_same_day",
                "reason": "cannot be determined",
                "scheduler_matched_ids": ["same-day-task"],
                "scheduler_last_run_at": "2026-08-28T00:02:00+00:00",
            },
            "Receipt Missing": {
                "status": "receipt_missing",
                "reason": "later row cannot replace a run-bound receipt",
                "scheduler_matched_ids": ["receipt-missing-task"],
                "scheduler_last_run_at": "2026-08-28T00:03:00+00:00",
            },
            "Legacy": {
                "status": "legacy_unverifiable",
                "reason": "predates timestamped receipt enforcement",
                "scheduler_matched_ids": ["legacy-task"],
                "scheduler_last_run_at": "2026-08-24T19:01:37+00:00",
            },
            "On Demand": {
                "status": "unknown",
                "reason": "on-demand routine by design",
                "scheduler_matched_ids": [],
                "scheduler_last_run_at": None,
            },
        },
        "capture_receipts": {
            "available": True,
            "malformed": [{"file": "bad.json", "reason": "invalid arm"}],
        },
    }

    findings = bs.actionable_findings(snapshot)

    assert {(item["routine"], item["status"]) for item in findings} == {
        ("Missing", "row_missing"),
        ("Same Day", "indeterminate_same_day"),
        ("Receipt Missing", "receipt_missing"),
        ("capture-receipts", "malformed_receipt"),
    }


def test_missing_receipt_store_is_an_actionable_measurement_failure():
    findings = bs.actionable_findings(
        {
            "liveness": {},
            "capture_receipts": {
                "available": False,
                "error": "receipt dir not found",
                "malformed": [],
                "unbound": [],
            },
        }
    )

    assert [(item["routine"], item["status"]) for item in findings] == [
        ("capture-receipts", "receipt_store_unavailable")
    ]


def test_sentry_event_has_stable_fingerprint_and_scrubs_absolute_paths():
    finding = {
        "routine": "Daily Completed Summary",
        "status": "row_missing",
        "reason": "could not read /Users/example/Secret Vault/note.md",
        "scheduler_matched_ids": ["daily-completed-summary"],
        "scheduler_last_run_at": "2026-08-28T00:01:00+00:00",
    }

    first = bs.build_sentry_event(finding, "2026-08-28T00:30:00+00:00", "rhize-ops@test")
    second = bs.build_sentry_event(finding, "2026-08-28T00:31:00+00:00", "rhize-ops@test")

    assert first["fingerprint"] == second["fingerprint"] == [
        "rhize-agent-evals",
        "benchmark-status",
        "daily-completed-summary",
        "global",
        "row-missing",
    ]
    assert first["tags"]["benchmark.status"] == "row_missing"
    assert first["tags"]["benchmark.measurement_required"] == "true"
    assert first["tags"]["alert.kind"] == "measurement-unavailable"
    assert "/Users/" not in json.dumps(first)
    assert first["level"] == "error"


def test_sentry_store_transport_uses_public_dsn_without_leaking_it():
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id":"event-id"}'

    def opener(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    result = bs.send_sentry_event(
        {"event_id": "a" * 32, "message": "capture failed"},
        "https://public-key@o1.ingest.us.sentry.io/12345",
        opener=opener,
    )

    request = captured["request"]
    assert request.full_url == "https://o1.ingest.us.sentry.io/api/12345/store/"
    assert "public-key" in request.headers["X-sentry-auth"]
    assert b"public-key" not in request.data
    assert captured["timeout"] == 10
    assert result == {"status": "sent", "event_id": "event-id"}


def test_sentry_delivery_failure_is_reported_not_raised():
    def failing_opener(_request, timeout):
        assert timeout == 10
        raise OSError("network unavailable")

    result = bs.send_sentry_event(
        {"event_id": "a" * 32, "message": "capture failed"},
        "https://public-key@o1.ingest.us.sentry.io/12345",
        opener=failing_opener,
    )

    assert result["status"] == "failed"
    assert "network unavailable" in result["error"]
    assert "public-key" not in json.dumps(result)


def test_receipt_with_broad_permissions_is_rejected(tmp_path):
    note = tmp_path / "Procedural Memory Benchmark.md"
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    path = receipt_dir / "receipt.json"
    path.write_text(json.dumps(_capture_receipt(note)), encoding="utf-8")
    os.chmod(path, 0o644)

    result = bs.load_benchmark_receipts(receipt_dir)

    assert result["valid"] == 0
    assert result["malformed"] == [
        {"file": "receipt.json", "reason": "receipt permissions must be 0600"}
    ]


def test_context_capture_health_runs_real_command_and_preserves_arm_findings(tmp_path):
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json\n"
        "print(json.dumps({'ok': False, 'issues': [{"
        "'kind': 'missing_arm_capture', 'capability': 'compiled-context', "
        "'missingArms': ['A'], 'path': 'receipts/e.json'}]}))\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )

    health = bs.run_context_capture_health(runner)
    findings = bs.actionable_findings(
        {
            "liveness": {},
            "capture_receipts": {"malformed": [], "unbound": []},
            "context_capture_health": health,
        }
    )

    assert health["available"] is True
    assert [(item["status"], item["arm"]) for item in findings] == [
        ("missing_arm_capture", "A")
    ]


def test_context_capture_health_prefers_affected_arms_for_sentry_grouping(tmp_path):
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json\n"
        "print(json.dumps({'ok': False, 'issues': [{"
        "'kind': 'stale_pending_selection', 'capability': 'compiledContext', "
        "'affectedArms': ['A', 'B'], 'missingArms': [], "
        "'path': 'pending/session.json'}]}))\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )

    health = bs.run_context_capture_health(runner)
    findings = bs.actionable_findings(
        {
            "liveness": {},
            "capture_receipts": {"malformed": [], "unbound": []},
            "context_capture_health": health,
        }
    )

    assert [(item["status"], item["arm"]) for item in findings] == [
        ("stale_pending_selection", "A"),
        ("stale_pending_selection", "B"),
    ]


def test_context_capture_health_command_failure_is_actionable(tmp_path):
    runner = tmp_path / "runner.py"
    runner.write_text("raise SystemExit(9)\n", encoding="utf-8")

    health = bs.run_context_capture_health(runner)
    findings = bs.actionable_findings(
        {
            "liveness": {},
            "capture_receipts": {"malformed": [], "unbound": []},
            "context_capture_health": health,
        }
    )

    assert health["available"] is False
    assert [(item["routine"], item["status"]) for item in findings] == [
        ("context-capture-health", "evaluator_unavailable")
    ]


def test_sentry_cron_checkin_uses_dsn_derived_ingest_url():
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b""

    def opener(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        return Response()

    result = bs.send_sentry_checkin(
        "https://public-key@o1.ingest.us.sentry.io/12345",
        "rhize-agent-evals-capture-watchdog",
        opener=opener,
    )

    assert captured == {
        "url": (
            "https://o1.ingest.us.sentry.io/api/12345/crons/"
            "rhize-agent-evals-capture-watchdog/public-key/"
        ),
        "timeout": 10,
    }
    assert result == {
        "status": "sent",
        "monitor_slug": "rhize-agent-evals-capture-watchdog",
    }


def test_cli_refuses_a_healthy_checkin_without_alert_delivery(tmp_path):
    with pytest.raises(SystemExit) as raised:
        bs.main(
            [
                "--sentry-checkin-slug",
                "watchdog",
                "--output",
                str(tmp_path / "snapshot.json"),
            ]
        )

    assert raised.value.code == 2
    assert not (tmp_path / "snapshot.json").exists()

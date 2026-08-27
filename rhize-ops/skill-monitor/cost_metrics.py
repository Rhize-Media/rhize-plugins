#!/usr/bin/env python3
"""
cost_metrics.py — shared helper for reading ~/.claude/metrics/costs.jsonl.

Used by savings_scorecard.py and skill_roi.py (mirrors the git_sync.py pattern:
a small importable helper alongside the single-file monitor.py/dashboard.py
scripts, not a package restructure).

costs.jsonl rows are CUMULATIVE-PER-SESSION SNAPSHOTS — one row is written per
assistant turn, and each row carries the running total for that session so far.
Summing rows double/triple/N-counts a session. The only correct read is: take
the LATEST row per session_id (by timestamp) and treat its token/cost fields as
that session's total as of that moment. Never sum rows across a session.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
COSTS_JSONL = HOME / ".claude" / "metrics" / "costs.jsonl"


def parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp (with trailing 'Z' or an offset) to aware UTC."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_latest_costs_per_session(
    days: int | None = None,
    session_ids: set[str] | None = None,
    costs_path: Path | None = None,
) -> dict:
    """Read costs.jsonl and return the latest row per session_id.

    - `days`: if set, only rows with timestamp >= (now - days) are considered
      when picking each session's "latest" row. A session whose only activity
      predates the window is excluded entirely (this is a window over EVENTS,
      not a lookup of "all sessions that ever existed").
    - `session_ids`: if set, restrict to only these session_ids (still applying
      the `days` cutoff, if any). Used by skill_roi.py to look up costs for a
      known set of sessions without scanning the whole file's history twice.
    - `costs_path`: if set, read from this path instead of the module-level
      `COSTS_JSONL` default — the explicit way callers (tests, stack_metrics.py)
      inject a fixture file. When omitted (the default, and what every existing
      caller in savings_scorecard.py/skill_roi.py does today), behavior is
      unchanged: reads `COSTS_JSONL`.

    Returns:
        {
          "available": bool,
          "error": str | None,
          "sessions": {session_id: row_dict, ...},   # latest-in-window row
          "all_time_row_count": int,
          "last_event_ts": datetime | None,           # across the WHOLE file,
                                                        # regardless of `days`
        }
    """
    path = costs_path if costs_path is not None else COSTS_JSONL
    if not path.exists():
        return {
            "available": False,
            "error": f"not found: {path}",
            "sessions": {},
            "all_time_row_count": 0,
            "last_event_ts": None,
        }

    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    latest: dict[str, dict] = {}
    latest_ts: dict[str, datetime] = {}
    all_time_row_count = 0
    last_event_ts: datetime | None = None

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                all_time_row_count += 1
                ts = row.get("timestamp")
                if not ts:
                    continue
                try:
                    dt = parse_iso(ts)
                except ValueError:
                    continue
                if last_event_ts is None or dt > last_event_ts:
                    last_event_ts = dt
                if cutoff is not None and dt < cutoff:
                    continue
                sid = row.get("session_id")
                if not sid:
                    continue
                if session_ids is not None and sid not in session_ids:
                    continue
                prev_ts = latest_ts.get(sid)
                if prev_ts is None or dt > prev_ts:
                    latest_ts[sid] = dt
                    latest[sid] = row
    except OSError as e:
        return {
            "available": False,
            "error": str(e),
            "sessions": {},
            "all_time_row_count": all_time_row_count,
            "last_event_ts": last_event_ts,
        }

    return {
        "available": True,
        "error": None,
        "sessions": latest,
        "all_time_row_count": all_time_row_count,
        "last_event_ts": last_event_ts,
    }


def session_cost_usd(row: dict) -> float:
    return float(row.get("estimated_cost_usd") or 0.0)


def session_total_tokens(row: dict) -> int:
    return int(
        (row.get("input_tokens") or 0)
        + (row.get("output_tokens") or 0)
        + (row.get("cache_write_tokens") or 0)
        + (row.get("cache_read_tokens") or 0)
    )

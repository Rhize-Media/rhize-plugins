#!/usr/bin/env python3
"""
stack_metrics.py — trust-tagged JSON snapshot of what Jim's AI tooling stack
actually delivers, across the local agent-harness stack (Claude Code spend,
session transcripts, Headroom, procedural-memory, skill invocations, rtk,
claude-mem, OpenWolf, the Codex trial log).

THE CENTRAL REQUIREMENT (this is the whole point of this module): every
metric this module emits is tagged with exactly one TrustClass —

  MEASURED           a real counter from a real event. Safe to sum/compare.
  MEASURED_CAVEATED  a real counter from a tool with a known reliability
                      defect. Usable, but the caveat travels with the number.
  INDICATIVE         LLM-estimated or heuristic. Display, never sum.
  SELF_REPORTED      the tool's own uncross-checked claim about its own
                      benefit. Display with provenance, never sum, never
                      headline.

This is enforced STRUCTURALLY, not by comment: `sum_measured()` raises
TrustClassError if handed anything that is not tagged exactly MEASURED. See
test_stack_metrics.py::test_sum_measured_refuses_non_measured.

A SECOND, ORTHOGONAL axis: TrustClass says how much to trust a number; it
says nothing about whether two trustworthy numbers measure the same THING.
`totals.measured_tokens` used to sum claude_code_tokens (billed spend) +
session_transcript_tokens (raw per-turn usage, which re-covers the same
turns via cache reads — not the same quantity as billed spend) +
headroom_tokens_saved (a savings figure, not consumption at all). All three
are trust=MEASURED, so the trust-class guard let them through; the sum was
still meaningless. Every Metric therefore also carries an optional `basis`
(see the Basis enum below) — billed-consumption vs. raw-consumption vs.
savings — and `sum_measured()` refuses to combine metrics whose bases
differ, exactly the way it refuses to combine metrics across trust classes.
The two checks are independent: passing the trust-class check does not
exempt a set of metrics from the basis check. See
test_stack_metrics.py::test_sum_measured_refuses_mixed_basis.

A THIRD, also orthogonal check: `sum_measured()` refuses to combine metrics
whose `unit` differs (e.g. "tokens" vs. "usd"), exactly the way it refuses
mismatched trust classes or bases. Passing both of those checks is not
permission to sum across units. See
test_stack_metrics.py::test_sum_measured_refuses_mixed_unit.

Idiom note: this mirrors savings_scorecard.py's measured-vs-estimated split
(same project, same intent — an explicit tier that structurally prevents
estimated figures being summed into a measured total) but generalizes it to
four tiers instead of two, and makes the sum-refusal a callable guard rather
than a convention enforced by which section of the file a loader lives in.
savings_scorecard.py is being edited concurrently by another session, so this
module is self-contained rather than importing from it — except for
cost_metrics.py, an existing shared helper already designed for reuse, whose
cumulative-per-session-snapshot logic (see its docstring) is exactly the kind
of trap that should have only one implementation.

Sources -> classes:
  Claude Code spend      ~/.claude/metrics/costs.jsonl              MEASURED
  Session transcripts    ~/.claude/projects/**/*.jsonl              MEASURED
  Headroom               ~/.headroom/{proxy_savings.json,
                          savings_events.jsonl}                     MEASURED
  Procedural memory      ~/.rhize/procedural-memory/runs/*.jsonl    MEASURED
  Skill invocations      rhize-ops/skill-monitor/data/
                          skill-usage.json                          MEASURED
  rtk                    ~/Library/Application Support/rtk/
                          history.db (SQLite)                       MEASURED_CAVEATED
  claude-mem              ~/.claude-mem/claude-mem.db (SQLite)      INDICATIVE
  OpenWolf                <repo>/.wolf/token-ledger.json            SELF_REPORTED
  Codex trial log         Obsidian vault win/loss log (markdown)    SELF_REPORTED
                                                                     (row count only)

Every source gets a coverage line (last event timestamp + event count) so a
dead integration reads "no data", not "no savings". No source ever raises out
of its own loader — a missing/malformed source is recorded as unavailable
with a reason, never a crash.

Usage:
  python3 stack_metrics.py                # human-readable, writes JSON snapshot
  python3 stack_metrics.py --json          # JSON to stdout, still writes snapshot
  python3 stack_metrics.py --days 28
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable

import cost_metrics
import paths

HOME = Path.home()
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = paths.data_dir()
DEFAULT_OUT_PATH = DATA_DIR / "stack-metrics.json"

HEADROOM_DIR = HOME / ".headroom"
DEFAULT_PROXY_SAVINGS = HEADROOM_DIR / "proxy_savings.json"
DEFAULT_SAVINGS_EVENTS = HEADROOM_DIR / "savings_events.jsonl"

DEFAULT_TRANSCRIPTS_DIR = HOME / ".claude" / "projects"
DEFAULT_PROCEDURAL_MEMORY_DIR = HOME / ".rhize" / "procedural-memory" / "runs"
DEFAULT_SKILL_USAGE_PATH = DATA_DIR / "skill-usage.json"
DEFAULT_RTK_DB = HOME / "Library" / "Application Support" / "rtk" / "history.db"
DEFAULT_CLAUDE_MEM_DB = HOME / ".claude-mem" / "claude-mem.db"
# The OpenWolf bounded-recursive scan (_find_wolf_ledgers, below) walks ONE
# root looking for nested .wolf/ dirs (depth <= 5) — a workspace-style
# ~/dev-local/RHIZE containing many repos, in the original design. With no
# hardcoded ~/dev-local literal, this uses the parent of the first configured
# RHIZE_REPO_ROOTS entry (so pointing at one repo still scans its siblings,
# matching the old behavior); a nonexistent placeholder when nothing is
# configured, so load_openwolf() reports "unavailable" exactly as it did
# before ~/dev-local/RHIZE existed on a fresh machine.
_configured_repo_roots = paths.repo_roots()
DEFAULT_OPENWOLF_ROOT = (
    _configured_repo_roots[0].parent if _configured_repo_roots
    else HOME / ".rhize" / "skill-monitor" / "openwolf-scan-root-unconfigured"
)
# None when no single vault could be resolved (see paths.vault_root()).
_vault_root = paths.vault_root()
DEFAULT_CODEX_LOG_PATH = (
    _vault_root
    / "Projects"
    / "Rhize Media"
    / "Rhize Tools"
    / "Scheduled Agent Routines & Automations"
    / "Plans"
    / "Model Cost Reduction — Codex Trial Win-Loss Log.md"
) if _vault_root else None

# rtk's known, upstream-acknowledged summary-text fabrication bugs (see
# ~/.claude/RTK.md). The numeric columns in history.db are deterministic
# counters written independently of the summary text rtk prints to stdout —
# only the printed sentence lies. This caveat travels with every rtk metric.
RTK_CAVEAT = (
    "rtk's own printed summary text has open upstream bugs (rtk-ai/rtk "
    "#2878, #3220, #2317) where it renders a success sentence regardless of "
    "the wrapped tool's real exit code/output (e.g. 'All files formatted "
    "correctly' against 19 failing files). The numeric fields read here "
    "(input/output/saved tokens) are separate deterministic counters, not "
    "derived from that summary text, and are usable. Never surface an rtk "
    "summary SENTENCE as evidence of anything."
)

CLAUDE_MEM_NOTE = (
    "discovery_tokens is an LLM-estimated figure claude-mem assigns itself "
    "at write time, not a measured token count from the model API."
)

OPENWOLF_NOTE = (
    "OpenWolf's own heuristic (anatomy_hits×200 + chars÷4), "
    "uncross-checked against any real token count."
)

CODEX_LOG_NOTE = (
    "row count of a hand-written, undated qualitative log; the trial window "
    "closed 2026-07-27. The log contains no quantitative savings figures — "
    "this is a count of entries, not a savings measurement. Do not sum or "
    "headline."
)


# ---------------------------------------------------------------------------
# Trust classes — the structural gate
# ---------------------------------------------------------------------------

class TrustClass(str, Enum):
    MEASURED = "measured"
    MEASURED_CAVEATED = "measured_caveated"
    INDICATIVE = "indicative"
    SELF_REPORTED = "self_reported"


class TrustClassError(ValueError):
    """Raised when a metric outside the MEASURED trust class is handed to a
    function that sums/totals metrics together."""


class Basis(str, Enum):
    """What a token/dollar figure actually represents — orthogonal to
    TrustClass (which says how much to trust the number). Two metrics can
    both be trust=MEASURED and still be meaningless summed together: a
    billed-consumption total and a raw-transcript total measure different
    quantities over overlapping requests, and a savings figure is not
    consumption at all. `sum_measured()` enforces that every metric it sums
    shares the same basis, in addition to (never instead of) its existing
    trust-class enforcement.

    A Metric with `basis=None` (the default) is a count/duration that has no
    consumption-vs-savings ambiguity (e.g. a turn count, a run count) — such
    metrics are exempt from this axis. Only metrics that plausibly could be
    summed with another same-unit MEASURED metric need a basis assigned.
    """

    BILLED_CONSUMPTION = "billed_consumption"  # what was actually billed
    RAW_CONSUMPTION = "raw_consumption"  # raw usage, e.g. incl. cache reads
    SAVINGS = "savings"  # tokens/dollars saved — not consumption at all


class BasisMismatchError(ValueError):
    """Raised when sum_measured() is handed metrics that are all trust=MEASURED
    but do not all share the same `basis` — the orthogonal counterpart to
    TrustClassError. This is what catches the real defect this module used to
    ship: totals['measured_tokens'] summed claude_code_tokens
    (billed_consumption) + session_transcript_tokens (raw_consumption) +
    headroom_tokens_saved (savings) — all three trust=MEASURED, none of that
    trio combinable."""


class UnitMismatchError(ValueError):
    """Raised when sum_measured() is handed metrics that don't all share the
    same `unit` — a THIRD guard, orthogonal to both TrustClassError and
    BasisMismatchError. Passing the trust-class and basis checks is not
    permission to sum: a Metric tagged unit="tokens" and one tagged
    unit="usd" can both be trust=MEASURED and share (or both omit) a basis
    and still be nonsense added together. Unlike basis, `unit` has no
    legitimate exempt/None case — every Metric carries one — so this is a
    plain "more than one distinct unit present" refusal."""


@dataclass(frozen=True)
class Metric:
    name: str
    value: float | int | None
    unit: str
    trust: TrustClass
    source: str
    scope: str  # "window" | "lifetime" | "snapshot"
    caveat: str | None = None
    note: str | None = None
    basis: Basis | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "trust": self.trust.value,
            "source": self.source,
            "scope": self.scope,
            "caveat": self.caveat,
            "note": self.note,
            "basis": self.basis.value if self.basis is not None else None,
        }


def sum_measured(metrics: Iterable[Metric]) -> float:
    """Sum metric values. Refuses (raises TrustClassError) if ANY metric in
    `metrics` is not tagged exactly TrustClass.MEASURED — measured_caveated,
    indicative, and self_reported are all rejected, not just estimated tiers.

    Second, orthogonal check: refuses (raises BasisMismatchError) if the
    metrics don't all share the same `basis` — e.g. billed spend and a
    savings figure are both trust=MEASURED but must never be added together.
    Metrics with basis=None are only combinable with other basis=None
    metrics (silently mixing a basis-tagged and an untagged metric is
    exactly the kind of accidental cross-basis sum this guard exists to
    catch).

    Third, orthogonal check: refuses (raises UnitMismatchError) if the
    metrics don't all share the same `unit` — e.g. a metric measured in
    tokens and one measured in dollars can both be trust=MEASURED and share
    a basis and still be meaningless added together. Passing the trust-class
    and basis checks is never a free pass on this one.

    This is the single point every "total" in this module must pass through.
    """
    metrics = list(metrics)
    for m in metrics:
        if m.trust is not TrustClass.MEASURED:
            raise TrustClassError(
                f"refusing to sum metric {m.name!r} from source {m.source!r}: "
                f"tagged {m.trust.value!r}, not measured. Only metrics tagged "
                "exactly 'measured' may be summed or compared as a total."
            )

    bases = {m.basis for m in metrics}
    if len(bases) > 1:
        by_basis: dict[Basis | None, list[str]] = {}
        for m in metrics:
            by_basis.setdefault(m.basis, []).append(m.name)
        grouping = "; ".join(
            f"{b.value if b is not None else 'none'}={names}"
            for b, names in sorted(by_basis.items(), key=lambda kv: kv[0].value if kv[0] else "")
        )
        raise BasisMismatchError(
            f"refusing to sum metrics with different bases: {grouping}. "
            "Metrics must share one semantic basis (billed-consumption vs. "
            "raw-consumption vs. savings) before they can be summed, even "
            "when all are trust-class MEASURED."
        )

    units = {m.unit for m in metrics}
    if len(units) > 1:
        by_unit: dict[str, list[str]] = {}
        for m in metrics:
            by_unit.setdefault(m.unit, []).append(m.name)
        grouping = "; ".join(
            f"{u}={names}" for u, names in sorted(by_unit.items())
        )
        raise UnitMismatchError(
            f"refusing to sum metrics with different units: {grouping}. "
            "Metrics must share one unit before they can be summed, even "
            "when all are trust-class MEASURED and share a basis."
        )

    total = 0.0
    for m in metrics:
        if m.value is not None:
            total += m.value
    return total


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# MEASURED sources
# ---------------------------------------------------------------------------

def load_claude_code_spend(days: int, costs_path: Path | None = None) -> dict:
    """The spend denominator, via cost_metrics.py's cumulative-per-session
    reader: rows in costs.jsonl are CUMULATIVE snapshots, so only the latest
    row per session_id is used — never summed across a session's own rows.
    """
    result = cost_metrics.load_latest_costs_per_session(days=days, costs_path=costs_path)

    if not result["available"]:
        return {
            "available": False,
            "error": result.get("error"),
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }
    sessions = result["sessions"]
    total_cost = sum(cost_metrics.session_cost_usd(r) for r in sessions.values())
    total_tokens = sum(cost_metrics.session_total_tokens(r) for r in sessions.values())
    last_ts = result["last_event_ts"]
    metrics = [
        Metric(
            name="claude_code_spend_usd",
            value=total_cost,
            unit="usd",
            trust=TrustClass.MEASURED,
            source="claude_code_spend",
            scope="window",
        ),
        Metric(
            name="claude_code_tokens",
            value=total_tokens,
            unit="tokens",
            trust=TrustClass.MEASURED,
            source="claude_code_spend",
            scope="window",
            basis=Basis.BILLED_CONSUMPTION,
        ),
    ]
    return {
        "available": True,
        "error": None,
        "session_count": len(sessions),
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "last_event_ts": _iso(last_ts),
        "event_count": len(sessions),
        "all_time_row_count": result["all_time_row_count"],
        "metrics": metrics,
    }


def load_session_transcripts(days: int, transcripts_dir: Path | None = None) -> dict:
    """Per-turn usage from ~/.claude/projects/**/*.jsonl assistant entries.

    Unlike costs.jsonl, these rows are PER-TURN deltas, not cumulative
    snapshots — summing them across a session's turns is correct here (the
    opposite windowing rule from load_claude_code_spend, by design).

    Never read wholesale: files are pre-filtered by mtime (an append-only
    JSONL's mtime is its last write, so mtime < cutoff means every line in
    the file predates the window and it can be skipped without opening it),
    then streamed line by line rather than loaded into memory.
    """
    root = transcripts_dir if transcripts_dir is not None else DEFAULT_TRANSCRIPTS_DIR
    if not root.exists():
        return {
            "available": False,
            "error": f"not found: {root}",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    files_scanned = 0
    files_skipped_by_mtime = 0
    files_unreadable = 0
    turn_count = 0
    input_sum = output_sum = cache_write_sum = cache_read_sum = 0
    last_ts: datetime | None = None

    try:
        all_files = list(root.glob("**/*.jsonl"))
    except OSError as e:
        return {
            "available": False,
            "error": str(e),
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    for f in all_files:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except OSError:
            files_unreadable += 1
            continue
        if mtime < cutoff:
            files_skipped_by_mtime += 1
            continue
        files_scanned += 1
        try:
            with f.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("type") != "assistant":
                        continue
                    message = row.get("message")
                    usage = message.get("usage") if isinstance(message, dict) else None
                    if not usage:
                        continue
                    ts_raw = row.get("timestamp")
                    if not ts_raw:
                        continue
                    try:
                        dt = parse_iso(ts_raw)
                    except ValueError:
                        continue
                    if dt < cutoff:
                        continue
                    if last_ts is None or dt > last_ts:
                        last_ts = dt
                    turn_count += 1
                    input_sum += usage.get("input_tokens") or 0
                    output_sum += usage.get("output_tokens") or 0
                    cache_write_sum += usage.get("cache_creation_input_tokens") or 0
                    cache_read_sum += usage.get("cache_read_input_tokens") or 0
        except OSError:
            files_unreadable += 1
            continue

    total_tokens = input_sum + output_sum + cache_write_sum + cache_read_sum
    metrics = [
        Metric(
            name="session_transcript_tokens",
            value=total_tokens,
            unit="tokens",
            trust=TrustClass.MEASURED,
            source="session_transcripts",
            scope="window",
            basis=Basis.RAW_CONSUMPTION,
        ),
        Metric(
            name="session_transcript_turns",
            value=turn_count,
            unit="turns",
            trust=TrustClass.MEASURED,
            source="session_transcripts",
            scope="window",
        ),
    ]
    return {
        "available": True,
        "error": None,
        "files_scanned": files_scanned,
        "files_skipped_by_mtime": files_skipped_by_mtime,
        "files_unreadable": files_unreadable,
        "turn_count": turn_count,
        "input_tokens": input_sum,
        "output_tokens": output_sum,
        "cache_write_tokens": cache_write_sum,
        "cache_read_tokens": cache_read_sum,
        "total_tokens": total_tokens,
        "last_event_ts": _iso(last_ts),
        "event_count": turn_count,
        "metrics": metrics,
    }


def load_headroom(
    days: int,
    proxy_path: Path | None = None,
    events_path: Path | None = None,
) -> dict:
    """Measured input-side compression from Headroom's proxy-measured
    before/after on real requests."""
    proxy_path = proxy_path if proxy_path is not None else DEFAULT_PROXY_SAVINGS
    events_path = events_path if events_path is not None else DEFAULT_SAVINGS_EVENTS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    window_tokens_saved = 0
    window_compression_usd = 0.0
    window_event_count = 0
    all_time_event_count = 0
    last_ts: datetime | None = None
    proxy_available = False
    proxy_error = None

    if not proxy_path.exists():
        proxy_error = f"not found: {proxy_path}"
    else:
        try:
            data = json.loads(proxy_path.read_text(encoding="utf-8", errors="replace"))
            history = data.get("history", [])
            all_time_event_count += len(history)
            for h in history:
                ts_raw = h.get("timestamp")
                if not ts_raw:
                    continue
                try:
                    dt = parse_iso(ts_raw)
                except ValueError:
                    continue
                if last_ts is None or dt > last_ts:
                    last_ts = dt
                if dt < cutoff:
                    continue
                window_event_count += 1
                window_tokens_saved += h.get("total_tokens_saved", 0) or 0
                window_compression_usd += h.get("compression_savings_usd", 0.0) or 0.0
            proxy_available = True
        except (json.JSONDecodeError, OSError) as e:
            proxy_error = str(e)

    events_available = False
    events_error = None
    events_all_time = 0
    if not events_path.exists():
        events_error = f"not found: {events_path}"
    else:
        try:
            with events_path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    events_all_time += 1
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts_raw = row.get("ts")
                    if not ts_raw:
                        continue
                    try:
                        dt = parse_iso(ts_raw)
                    except ValueError:
                        continue
                    if last_ts is None or dt > last_ts:
                        last_ts = dt
            events_available = True
        except OSError as e:
            events_error = str(e)

    available = proxy_available or events_available
    metrics = []
    if available:
        metrics.append(
            Metric(
                name="headroom_tokens_saved",
                value=window_tokens_saved,
                unit="tokens",
                trust=TrustClass.MEASURED,
                source="headroom",
                scope="window",
                basis=Basis.SAVINGS,
            )
        )
        metrics.append(
            Metric(
                name="headroom_compression_savings_usd",
                value=window_compression_usd,
                unit="usd",
                trust=TrustClass.MEASURED,
                source="headroom",
                scope="window",
            )
        )
    return {
        "available": available,
        "error": None if available else f"{proxy_error}; {events_error}",
        "proxy_available": proxy_available,
        "proxy_error": proxy_error,
        "events_available": events_available,
        "events_all_time_count": events_all_time,
        "window_tokens_saved": window_tokens_saved,
        "window_compression_usd": window_compression_usd,
        "window_event_count": window_event_count,
        "all_time_event_count": all_time_event_count,
        "last_event_ts": _iso(last_ts),
        "event_count": window_event_count,
        "metrics": metrics,
    }


def load_procedural_memory(days: int, runs_dir: Path | None = None) -> dict:
    """Real exit codes / wall times from ~/.rhize/procedural-memory/runs/*.jsonl
    (one file per UTC day)."""
    root = runs_dir if runs_dir is not None else DEFAULT_PROCEDURAL_MEMORY_DIR
    if not root.exists():
        return {
            "available": False,
            "error": f"not found: {root}",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    run_count = 0
    ok_count = 0
    total_duration_ms = 0
    last_ts: datetime | None = None
    files_unreadable = 0

    try:
        files = sorted(root.glob("*.jsonl"))
    except OSError as e:
        return {
            "available": False,
            "error": str(e),
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    for f in files:
        try:
            with f.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts_raw = row.get("started_at")
                    if not ts_raw:
                        continue
                    try:
                        dt = parse_iso(ts_raw)
                    except ValueError:
                        continue
                    if last_ts is None or dt > last_ts:
                        last_ts = dt
                    if dt < cutoff:
                        continue
                    run_count += 1
                    if row.get("ok"):
                        ok_count += 1
                    total_duration_ms += row.get("duration_ms") or 0
        except OSError:
            files_unreadable += 1
            continue

    if run_count == 0 and files_unreadable == len(files) and files:
        return {
            "available": False,
            "error": f"all {len(files)} run file(s) unreadable",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    metrics = [
        Metric(
            name="procedural_memory_run_count",
            value=run_count,
            unit="runs",
            trust=TrustClass.MEASURED,
            source="procedural_memory",
            scope="window",
        ),
        Metric(
            name="procedural_memory_ok_count",
            value=ok_count,
            unit="runs",
            trust=TrustClass.MEASURED,
            source="procedural_memory",
            scope="window",
        ),
        Metric(
            name="procedural_memory_duration_ms",
            value=total_duration_ms,
            unit="ms",
            trust=TrustClass.MEASURED,
            source="procedural_memory",
            scope="window",
        ),
    ]
    return {
        "available": True,
        "error": None,
        "run_count": run_count,
        "ok_count": ok_count,
        "total_duration_ms": total_duration_ms,
        "files_unreadable": files_unreadable,
        "last_event_ts": _iso(last_ts),
        "event_count": run_count,
        "metrics": metrics,
    }


def load_skill_invocations(days: int, usage_path: Path | None = None) -> dict:
    """Real skill-invocation events from
    rhize-ops/skill-monitor/data/skill-usage.json."""
    path = usage_path if usage_path is not None else DEFAULT_SKILL_USAGE_PATH
    if not path.exists():
        return {
            "available": False,
            "error": f"not found: {path}",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as e:
        return {
            "available": False,
            "error": str(e),
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    events = data.get("events", [])
    if not isinstance(events, list):
        return {
            "available": False,
            "error": "malformed skill-usage.json: 'events' is not a list",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    window_count = 0
    all_time_count = 0
    last_ts: datetime | None = None
    for e in events:
        if not isinstance(e, dict):
            continue
        all_time_count += 1
        ts_raw = e.get("timestamp")
        if not ts_raw:
            continue
        try:
            dt = parse_iso(ts_raw)
        except ValueError:
            continue
        if last_ts is None or dt > last_ts:
            last_ts = dt
        if dt >= cutoff:
            window_count += 1

    metrics = [
        Metric(
            name="skill_invocation_count",
            value=window_count,
            unit="invocations",
            trust=TrustClass.MEASURED,
            source="skill_invocations",
            scope="window",
        ),
    ]
    return {
        "available": True,
        "error": None,
        "window_event_count": window_count,
        "all_time_event_count": all_time_count,
        "last_event_ts": _iso(last_ts),
        "event_count": window_count,
        "metrics": metrics,
    }


def _connect_readonly(path: Path, busy_timeout_ms: int = 5000) -> sqlite3.Connection:
    """Open a SQLite file strictly read-only (mode=ro URI — refuses to
    create a missing file, refuses to write) with a short busy timeout so a
    concurrent writer on the live store doesn't hang the read."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=busy_timeout_ms / 1000)
    conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    return conn


# ---------------------------------------------------------------------------
# MEASURED_CAVEATED source — rtk
# ---------------------------------------------------------------------------

def load_rtk(days: int, db_path: Path | None = None) -> dict:
    """rtk history.db numeric counters (input/output/saved tokens). These
    columns are deterministic per-command counters written independently of
    rtk's own printed summary sentence, which has open upstream bugs — see
    RTK_CAVEAT. The caveat travels with every metric this loader emits."""
    path = db_path if db_path is not None else DEFAULT_RTK_DB
    if not path.exists():
        return {
            "available": False,
            "error": f"not found: {path}",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        conn = _connect_readonly(path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(input_tokens),0), "
                "COALESCE(SUM(output_tokens),0), COALESCE(SUM(saved_tokens),0), "
                "MAX(timestamp) FROM commands WHERE timestamp >= ?",
                (cutoff_iso,),
            )
            window_count, input_sum, output_sum, saved_sum, window_last = cur.fetchone()
            cur.execute("SELECT COUNT(*), MAX(timestamp) FROM commands")
            all_time_count, all_time_last = cur.fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return {
            "available": False,
            "error": str(e),
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    metrics = [
        Metric(
            name="rtk_input_tokens",
            value=input_sum,
            unit="tokens",
            trust=TrustClass.MEASURED_CAVEATED,
            source="rtk",
            scope="window",
            caveat=RTK_CAVEAT,
        ),
        Metric(
            name="rtk_output_tokens",
            value=output_sum,
            unit="tokens",
            trust=TrustClass.MEASURED_CAVEATED,
            source="rtk",
            scope="window",
            caveat=RTK_CAVEAT,
        ),
        Metric(
            name="rtk_saved_tokens",
            value=saved_sum,
            unit="tokens",
            trust=TrustClass.MEASURED_CAVEATED,
            source="rtk",
            scope="window",
            caveat=RTK_CAVEAT,
        ),
    ]
    return {
        "available": True,
        "error": None,
        "window_command_count": window_count,
        "window_input_tokens": input_sum,
        "window_output_tokens": output_sum,
        "window_saved_tokens": saved_sum,
        "all_time_command_count": all_time_count,
        "last_event_ts": window_last or all_time_last,
        "event_count": window_count,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# INDICATIVE source — claude-mem
# ---------------------------------------------------------------------------

def load_claude_mem(days: int, db_path: Path | None = None) -> dict:
    """claude-mem's own claimed discovery_tokens — LLM-estimated at write
    time, not a measured API token count. See CLAUDE_MEM_NOTE."""
    path = db_path if db_path is not None else DEFAULT_CLAUDE_MEM_DB
    if not path.exists():
        return {
            "available": False,
            "error": f"not found: {path}",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    cutoff_epoch = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    try:
        conn = _connect_readonly(path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(discovery_tokens),0), MAX(created_at) "
                "FROM session_summaries WHERE created_at_epoch >= ?",
                (cutoff_epoch,),
            )
            window_count, window_discovery_sum, window_last = cur.fetchone()
            cur.execute("SELECT COUNT(*), MAX(created_at) FROM session_summaries")
            all_time_count, all_time_last = cur.fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return {
            "available": False,
            "error": str(e),
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    metrics = [
        Metric(
            name="claude_mem_discovery_tokens",
            value=window_discovery_sum,
            unit="tokens",
            trust=TrustClass.INDICATIVE,
            source="claude_mem",
            scope="window",
            note=CLAUDE_MEM_NOTE,
        ),
    ]
    return {
        "available": True,
        "error": None,
        "window_summary_count": window_count,
        "window_discovery_tokens_sum": window_discovery_sum,
        "all_time_summary_count": all_time_count,
        "last_event_ts": window_last or all_time_last,
        "event_count": window_count,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# SELF_REPORTED sources — OpenWolf, Codex trial log
# ---------------------------------------------------------------------------

_WOLF_PRUNE_DIRS = {"node_modules", ".git", "worktrees"}
_WOLF_MAX_DEPTH = 5


def _find_wolf_ledgers(root: Path) -> list[tuple[Path, Path, bool]]:
    """Bounded, pruned directory walk for <repo>/.wolf/token-ledger.json.

    A naive `root.glob('**/.wolf/token-ledger.json')` over ~/dev-local takes
    ~26s (measured) because it descends into every node_modules/.git tree in
    every repo. This walk prunes those directory names and caps depth, which
    brings the same discovery under ~/dev-local/RHIZE to ~0.1s.

    Returns (repo_dir, ledger_path, ledger_exists) for every `.wolf` dir
    found — including one with no token-ledger.json inside, so a repo with
    OpenWolf enabled but no ledger yet is reported as a coverage gap rather
    than silently absent.
    """
    if not root.exists():
        return []
    root = root.resolve()
    results: list[tuple[Path, Path, bool]] = []
    for dirpath, dirnames, _filenames in os.walk(root):
        p = Path(dirpath)
        if p.name == ".wolf":
            ledger = p / "token-ledger.json"
            results.append((p.parent, ledger, ledger.exists()))
            dirnames[:] = []
            continue
        rel = p.relative_to(root)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth >= _WOLF_MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [
            d for d in dirnames if d not in _WOLF_PRUNE_DIRS and not d.startswith(".claude")
        ]
    return results


def load_openwolf(days: int, dev_local_root: Path | None = None) -> dict:
    """OpenWolf per-repo token-ledger.json. Self-reported heuristic estimate
    (anatomy_hits×200 + chars÷4), uncross-checked. Coverage is reported
    honestly: a repo with a `.wolf/` dir but no ledger file, or a ledger with
    no session-level data (a stub), is distinguished from a fully usable
    ledger rather than silently omitted."""
    root = dev_local_root if dev_local_root is not None else DEFAULT_OPENWOLF_ROOT
    found = _find_wolf_ledgers(root)

    repos: dict = {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    usable_count = 0
    stub_count = 0
    missing_count = 0
    window_session_count_sum = 0
    lifetime_anatomy_hits_sum = 0
    lifetime_estimated_savings_sum = 0
    last_ts: datetime | None = None

    for repo_dir, ledger_path, exists in found:
        repo_name = str(repo_dir.relative_to(root)) if root in repo_dir.parents or repo_dir == root else repo_dir.name
        if not exists:
            missing_count += 1
            repos[repo_name] = {"available": False, "error": f"not found: {ledger_path}"}
            continue
        try:
            data = json.loads(ledger_path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError) as e:
            repos[repo_name] = {"available": False, "error": str(e)}
            continue

        sessions = data.get("sessions")
        lifetime = data.get("lifetime", {}) if isinstance(data.get("lifetime"), dict) else {}
        if not isinstance(sessions, list) or not sessions:
            stub_count += 1
            repos[repo_name] = {
                "available": True,
                "error": None,
                "stub": True,
                "note": "no session-level data (lifetime totals only, if present)",
                "lifetime_total_sessions": lifetime.get("total_sessions"),
                "lifetime_estimated_savings_vs_bare_cli": lifetime.get(
                    "estimated_savings_vs_bare_cli"
                ),
            }
            lifetime_estimated_savings_sum += lifetime.get("estimated_savings_vs_bare_cli") or 0
            continue

        usable_count += 1
        windowed = []
        for s in sessions:
            ts_raw = s.get("ended") or s.get("started")
            if not ts_raw:
                continue
            try:
                dt = parse_iso(ts_raw)
            except ValueError:
                continue
            if last_ts is None or dt > last_ts:
                last_ts = dt
            if dt >= cutoff:
                windowed.append(s)
        anatomy_hits = lifetime.get("anatomy_hits") or 0
        window_session_count_sum += len(windowed)
        lifetime_anatomy_hits_sum += anatomy_hits
        lifetime_estimated_savings_sum += lifetime.get("estimated_savings_vs_bare_cli") or 0
        repos[repo_name] = {
            "available": True,
            "error": None,
            "stub": False,
            "window_session_count": len(windowed),
            "all_time_session_count": len(sessions),
            "lifetime_anatomy_hits": anatomy_hits,
            "lifetime_estimated_savings_vs_bare_cli": lifetime.get(
                "estimated_savings_vs_bare_cli"
            ),
        }

    total_repos = len(found)
    coverage_note = (
        f"{usable_count} of {total_repos} repos have a usable ledger with "
        f"session-level data; {stub_count} are stub-only (lifetime totals, "
        f"no sessions); {missing_count} have a .wolf/ dir but no ledger file."
    )

    metrics = []
    if total_repos:
        metrics.append(
            Metric(
                name="openwolf_lifetime_estimated_savings_vs_bare_cli",
                value=lifetime_estimated_savings_sum,
                unit="tokens",
                trust=TrustClass.SELF_REPORTED,
                source="openwolf",
                scope="lifetime",
                caveat=OPENWOLF_NOTE,
                note=coverage_note,
            )
        )

    return {
        "available": total_repos > 0,
        "error": None if total_repos else f"no .wolf directories found under {root}",
        "repos": repos,
        "total_repos_found": total_repos,
        "usable_repo_count": usable_count,
        "stub_repo_count": stub_count,
        "missing_ledger_count": missing_count,
        "coverage_note": coverage_note,
        "window_session_count": window_session_count_sum,
        "lifetime_anatomy_hits_sum": lifetime_anatomy_hits_sum,
        "last_event_ts": _iso(last_ts),
        "event_count": window_session_count_sum,
        "metrics": metrics,
    }


_CODEX_DATED_ROW_RE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.MULTILINE)


def load_codex_trial_log(vault_path: Path | None = None) -> dict:
    """Count dated markdown-table rows in the Codex trial win/loss log. The
    trial window is closed and the log is hand-written with no per-row
    timestamps beyond a date column, so this is a row COUNT — not a savings
    metric. See CODEX_LOG_NOTE: do not manufacture a $ or token figure from
    qualitative prose."""
    path = vault_path if vault_path is not None else DEFAULT_CODEX_LOG_PATH
    if path is None:
        return {
            "available": False,
            "error": "no single Obsidian vault could be resolved (see paths.vault_root())",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }
    if not path.exists():
        return {
            "available": False,
            "error": f"not found: {path}",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {
            "available": False,
            "error": str(e),
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }

    dated_rows = _CODEX_DATED_ROW_RE.findall(text)
    row_count = len(dated_rows)
    last_date = max(dated_rows) if dated_rows else None

    metrics = [
        Metric(
            name="codex_trial_log_row_count",
            value=row_count,
            unit="rows",
            trust=TrustClass.SELF_REPORTED,
            source="codex_trial_log",
            scope="lifetime",
            note=CODEX_LOG_NOTE,
        ),
    ]
    return {
        "available": True,
        "error": None,
        "row_count": row_count,
        "last_event_ts": last_date,
        "event_count": row_count,
        "metrics": metrics,
        "finding": (
            "the log yields no usable quantitative savings metric — only a "
            "count of hand-written delegation rows" if row_count else
            "no dated rows found in the log"
        ),
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------

SOURCE_LOADERS = (
    ("claude_code_spend", load_claude_code_spend),
    ("session_transcripts", load_session_transcripts),
    ("headroom", load_headroom),
    ("procedural_memory", load_procedural_memory),
    ("skill_invocations", load_skill_invocations),
    ("rtk", load_rtk),
    ("claude_mem", load_claude_mem),
)


def build_snapshot(days: int = 7) -> dict:
    """Run every source loader, never letting one source's failure take down
    the snapshot, and assemble a flat trust-tagged metrics list alongside
    the per-source raw detail."""
    sources: dict = {}
    all_metrics: list[Metric] = []

    for key, loader in SOURCE_LOADERS:
        try:
            result = loader(days)
        except Exception as e:  # noqa: BLE001 - a source must never crash the snapshot
            result = {
                "available": False,
                "error": f"unexpected: {type(e).__name__}: {e}",
                "last_event_ts": None,
                "event_count": 0,
                "metrics": [],
            }
        all_metrics.extend(result.get("metrics", []))
        result["metrics"] = [m.to_dict() for m in result.get("metrics", [])]
        sources[key] = result

    # OpenWolf and the Codex trial log aren't windowed the same way as the
    # measured sources (OpenWolf is lifetime-scoped, the Codex log is
    # unwindowed by design) — call them without `days` semantics leaking in.
    try:
        openwolf_result = load_openwolf(days)
    except Exception as e:  # noqa: BLE001
        openwolf_result = {
            "available": False,
            "error": f"unexpected: {type(e).__name__}: {e}",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }
    all_metrics.extend(openwolf_result.get("metrics", []))
    openwolf_result["metrics"] = [m.to_dict() for m in openwolf_result.get("metrics", [])]
    sources["openwolf"] = openwolf_result

    try:
        codex_result = load_codex_trial_log()
    except Exception as e:  # noqa: BLE001
        codex_result = {
            "available": False,
            "error": f"unexpected: {type(e).__name__}: {e}",
            "last_event_ts": None,
            "event_count": 0,
            "metrics": [],
        }
    all_metrics.extend(codex_result.get("metrics", []))
    codex_result["metrics"] = [m.to_dict() for m in codex_result.get("metrics", [])]
    sources["codex_trial_log"] = codex_result

    # Total measured tokens — but ONLY within one basis at a time. This used
    # to be a single totals["measured_tokens"] summed across every trust=
    # MEASURED "tokens" metric regardless of what each one measured, which is
    # exactly the defect basis exists to prevent (see the Basis docstring
    # above): claude_code_tokens (billed) + session_transcript_tokens (raw,
    # re-covers the same turns via cache reads) + headroom_tokens_saved
    # (savings, not consumption) summed to a number with no coherent
    # meaning. Group by basis FIRST so every call into sum_measured() here is
    # basis-homogeneous by construction — the guard inside sum_measured() is
    # the structural backstop, not the only line of defense. A "tokens"
    # metric with basis=None is excluded from totaling (ambiguous by
    # definition) rather than silently pooled. See test_stack_metrics.py for
    # the adversarial case proving refusal on exactly this real combination.
    token_metrics = [
        m for m in all_metrics
        if m.trust is TrustClass.MEASURED and m.unit == "tokens"
    ]
    totals = {}
    by_basis: dict[Basis, list[Metric]] = {}
    for m in token_metrics:
        if m.basis is None:
            continue
        by_basis.setdefault(m.basis, []).append(m)
    for basis, group in by_basis.items():
        totals[f"measured_tokens_{basis.value}"] = {
            "value": sum_measured(group),
            "unit": "tokens",
            "basis": basis.value,
            "from_metrics": [m.name for m in group],
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "sources": sources,
        "metrics": [m.to_dict() for m in all_metrics],
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt(n) -> str:
    if n is None:
        return "n/a"
    if isinstance(n, float):
        return f"{n:,.4f}"
    return f"{n:,}"


def _coverage_line(label: str, result: dict) -> str:
    if not result.get("available"):
        return f"- **{label}** — UNAVAILABLE ({result.get('error')})"
    ts = result.get("last_event_ts") or "no data"
    return f"- **{label}** — last event: `{ts}` · events: {_fmt(result.get('event_count'))}"


def render_text(snapshot: dict) -> str:
    lines: list[str] = []
    lines.append(f"stack-metrics snapshot — {snapshot['generated_at']} (window: {snapshot['window_days']}d)")
    lines.append("")
    lines.append("Coverage:")
    labels = {
        "claude_code_spend": "Claude Code spend (measured)",
        "session_transcripts": "Session transcripts (measured)",
        "headroom": "Headroom (measured)",
        "procedural_memory": "Procedural memory (measured)",
        "skill_invocations": "Skill invocations (measured)",
        "rtk": "rtk (measured_caveated)",
        "claude_mem": "claude-mem (indicative)",
        "openwolf": "OpenWolf (self_reported)",
        "codex_trial_log": "Codex trial log (self_reported)",
    }
    for key, label in labels.items():
        lines.append(_coverage_line(label, snapshot["sources"][key]))

    lines.append("")
    lines.append("Metrics by trust class:")
    by_trust: dict[str, list[dict]] = {}
    for m in snapshot["metrics"]:
        by_trust.setdefault(m["trust"], []).append(m)
    for trust in (tc.value for tc in TrustClass):
        metrics = by_trust.get(trust, [])
        if not metrics:
            continue
        lines.append(f"\n[{trust}]")
        for m in metrics:
            val = _fmt(m["value"])
            line = f"  {m['name']}: {val} {m['unit']} ({m['scope']}, source={m['source']})"
            lines.append(line)
            if m.get("caveat"):
                lines.append(f"    caveat: {m['caveat']}")
            if m.get("note"):
                lines.append(f"    note: {m['note']}")

    if snapshot.get("totals"):
        lines.append("\nTotals (measured-only, same-basis, via sum_measured):")
        for name, t in snapshot["totals"].items():
            basis_note = f", basis={t['basis']}" if t.get("basis") else ""
            lines.append(
                f"  {name}: {_fmt(t['value'])} {t['unit']}{basis_note} "
                f"(from: {', '.join(t['from_metrics'])})"
            )

    if snapshot["sources"].get("openwolf", {}).get("available"):
        lines.append(f"\nOpenWolf coverage: {snapshot['sources']['openwolf']['coverage_note']}")
    if snapshot["sources"].get("codex_trial_log", {}).get("available"):
        lines.append(f"Codex trial log: {snapshot['sources']['codex_trial_log']['finding']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="window size in days (default: 7)")
    parser.add_argument("--json", action="store_true", help="print the snapshot as JSON to stdout")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_PATH,
        help=f"where to write the JSON snapshot (default: {DEFAULT_OUT_PATH})",
    )
    args = parser.parse_args(argv)

    snapshot = build_snapshot(days=args.days)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(snapshot, indent=2))
    else:
        print(render_text(snapshot))
        print(f"\n(snapshot written to {args.out})")

    return 0


if __name__ == "__main__":
    sys.exit(main())

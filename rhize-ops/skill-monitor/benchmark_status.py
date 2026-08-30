#!/usr/bin/env python3
"""
benchmark_status.py — procedural-memory benchmark watchdog.

Answers a question that used to require opening four Obsidian notes by hand:
did each benchmark-instrumented routine's capture step actually land a row this
run, or did it silently no-op? The capture pipeline (`bench-append`) has already
failed silently at least once — this module exists to turn "did it land?" into a
queryable JSON snapshot instead of something discovered by eyeballing a table.

Five local data sources:
  1. The four benchmark notes' `## Metrics log` markdown tables (vault paths
     below). The four notes have DIFFERENT column sets — this module does not
     assume a shared schema; it reports each note's own header verbatim.
  2. `~/.rhize/procedural-memory/runs/*.jsonl` run telemetry (streamed, never
     loaded wholesale).
  3. `~/dev-local/RHIZE/procedural-memory/registry/.health/**/*.json` health
     sidecars — the OFFLINE-AUTHORITATIVE health record. Deliberately does NOT
     read `health` out of `*.provenance.json` (that field is stale there by
     design — health is excluded from the digest-hashed provenance document).
  4. Scheduler state: `~/.claude/scheduled-tasks/*/` (Claude Code CLI scheduler
     — existence only, no run-time log) and the Desktop app's registry JSON at
     `~/Library/Application Support/Claude/local-agent-mode-sessions/*/*/
     scheduled-tasks.json` (has real `lastRunAt` timestamps keyed by task id).
  5. Private timestamped `bench-append` receipts (legacy v1 and strict routine
     v2) and, when `--context-runner` is supplied, the context experiment's
     strict `capture-health` report.

The default run is local-only. `--alert-sentry` explicitly sends stable,
path-redacted measurement incidents using an on-demand env/Keychain DSN, and
`--sentry-checkin-slug` closes the run with a Sentry Cron check-in only after
evaluation and incident delivery complete.

The `liveness` section is the actual point of this module: per routine, did the
routine run (per the scheduler) more recently than the newest row logged in its
note? If so, a run happened and produced no row — `row_missing`. That is the
finding this module exists to surface, made unmissable in both JSON and the
human-readable report. After receipt enforcement began, no Markdown row can
substitute for a fresh, exact-row, run-bound receipt: same-day ambiguity remains
`indeterminate_same_day`, a later row without a receipt is `receipt_missing`,
and an older or absent row is `row_missing`. The one exception is a
same-day run from before timestamped receipt enforcement existed; that history
is reported as `legacy_unverifiable` instead of repeatedly alerting on evidence
that cannot be reconstructed. Scheduler instants are converted to the benchmark
program's America/New_York calendar before that date-only comparison.

System python3 here is 3.14 and has no `jsonschema` — this module deliberately
imports nothing beyond the standard library.

Run as: python3 benchmark_status.py [--json] [--context-runner PATH]
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import parse, request
from zoneinfo import ZoneInfo

HOME = Path.home()
BENCHMARK_TIMEZONE = ZoneInfo("America/New_York")
# Timestamped, run-bound benchmark receipts shipped with the capture reliability
# release (5f7fb049a33f3b366fc83f239bdc67747dad35f4). Earlier same-day
# scheduler/row ordering cannot be reconstructed honestly, so the cutoff is
# explicit and applies to every routine equally.
RECEIPT_ENFORCEMENT_STARTED_AT = datetime.fromisoformat(
    "2026-08-27T23:11:36-04:00"
).astimezone(BENCHMARK_TIMEZONE)

# --- Data source locations -------------------------------------------------

_VAULT_ROOT = (
    HOME
    / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"
    / "Projects/Rhize Media/Rhize Tools"
)
_SCHEDULED_ROUTINES_DIR = _VAULT_ROOT / "Scheduled Agent Routines & Automations"

BENCHMARK_NOTES: dict[str, Path] = {
    "Vault Inbox Processor": _SCHEDULED_ROUTINES_DIR
    / "Vault Inbox Processor"
    / "Procedural Memory Benchmark.md",
    "AI-Stack-Version-Drift": _SCHEDULED_ROUTINES_DIR
    / "AI-Stack-Version-Drift"
    / "Procedural Memory Benchmark.md",
    "Daily Completed Summary": _SCHEDULED_ROUTINES_DIR
    / "Daily Completed Summary"
    / "Procedural Memory Benchmark.md",
    "Content Engine": _VAULT_ROOT / "Content Engine" / "Procedural Memory Benchmark.md",
}

RUNS_DIR = HOME / ".rhize" / "procedural-memory" / "runs"
HEALTH_DIR = HOME / "dev-local" / "RHIZE" / "procedural-memory" / "registry" / ".health"
SCHEDULED_TASKS_DIR = HOME / ".claude" / "scheduled-tasks"
DESKTOP_SESSIONS_ROOT = HOME / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_PATH = DATA_DIR / "benchmark-status.json"
BENCHMARK_RECEIPTS_DIR = HOME / ".rhize" / "procedural-memory" / "benchmark-receipts"
SENTRY_KEYCHAIN_SERVICE = "Rhize Agent Evals Sentry DSN"
SENTRY_CRON_SLUG = "rhize-agent-evals-capture-watchdog"

# Substrings (case-insensitive) matched against Desktop scheduler task `id`s to
# find the entry(ies) that correspond to each benchmark-instrumented routine.
# "Content Engine" is deliberately on-demand (see its own note's prose) and has
# no scheduler entry by design — an empty list means "don't guess."
ROUTINE_SCHEDULER_KEYS: dict[str, list[str]] = {
    "Vault Inbox Processor": ["vault-inbox-processor"],
    "AI-Stack-Version-Drift": ["ai-stack-version-drift", "drift-benchmark"],
    "Daily Completed Summary": ["daily-completed-summary", "daily-summary-benchmark"],
    "Content Engine": [],
}
ROUTINE_RECEIPT_IDS: dict[str, str] = {
    "Vault Inbox Processor": "vault-inbox-processor",
    "AI-Stack-Version-Drift": "ai-stack-version-drift",
    "Daily Completed Summary": "daily-completed-summary",
    "Content Engine": "content-engine",
}


# --- 1. Benchmark note parsing ---------------------------------------------

_SECTION_RE = re.compile(r"^#{1,6}\s*Metrics log\s*$", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"^\|?[\s\-:|]+\|?$")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")


def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in _CELL_SPLIT_RE.split(s)]


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _find_col(columns: list[str], name: str) -> str | None:
    for c in columns:
        if c.strip().lower() == name:
            return c
    return None


def parse_metrics_table(text: str) -> dict[str, Any]:
    """Parse the '## Metrics log' markdown table out of a benchmark note's text.

    Returns a dict with: error (str|None), columns (list[str]), raw_rows
    (list[dict[str,str]]), malformed_rows (list[dict]).
    """
    lines = text.splitlines()

    start = None
    for i, line in enumerate(lines):
        if _SECTION_RE.match(line.strip()):
            start = i
            break
    if start is None:
        return {
            "error": "no '## Metrics log' section found",
            "columns": [],
            "raw_rows": [],
            "raw_row_hashes": [],
            "malformed_rows": [],
        }

    # Don't let a table from a LATER section bleed in.
    section_end = len(lines)
    for k in range(start + 1, len(lines)):
        if lines[k].strip().startswith("#"):
            section_end = k
            break

    header_idx = None
    for k in range(start + 1, section_end):
        if lines[k].strip().startswith("|"):
            header_idx = k
            break
    if header_idx is None:
        return {
            "error": "'## Metrics log' section found but no table under it",
            "columns": [],
            "raw_rows": [],
            "raw_row_hashes": [],
            "malformed_rows": [],
        }

    columns = _split_table_row(lines[header_idx])

    data_start = header_idx + 1
    if data_start < section_end and _SEPARATOR_RE.match(lines[data_start].strip()) and "-" in lines[data_start]:
        data_start += 1  # skip the |---|---| separator row

    raw_rows: list[dict[str, str]] = []
    raw_row_hashes: list[str] = []
    malformed_rows: list[dict[str, Any]] = []
    k = data_start
    while k < section_end:
        line = lines[k]
        stripped = line.strip()
        if not stripped or not stripped.startswith("|"):
            break
        cells = _split_table_row(line)
        if len(cells) != len(columns):
            malformed_rows.append(
                {
                    "line_no": k + 1,
                    "raw": line,
                    "reason": f"expected {len(columns)} columns, got {len(cells)}",
                }
            )
        else:
            raw_rows.append(dict(zip(columns, cells)))
            raw_row_hashes.append(hashlib.sha256(stripped.encode()).hexdigest())
        k += 1

    return {
        "error": None,
        "columns": columns,
        "raw_rows": raw_rows,
        "raw_row_hashes": raw_row_hashes,
        "malformed_rows": malformed_rows,
    }


def summarize_note(text: str) -> dict[str, Any]:
    """Turn parse_metrics_table()'s output into the per-note summary this module reports:
    total rows, rows by arm, newest row date (overall + per arm), column schema.
    """
    parsed = parse_metrics_table(text)
    if parsed["error"]:
        return {
            "error": parsed["error"],
            "columns": [],
            "total_rows": 0,
            "rows_by_arm": {},
            "newest_row_date": None,
            "newest_row_date_by_arm": {},
            "row_evidence": {},
            "malformed_rows": parsed["malformed_rows"],
            "unparseable_dates": [],
        }

    columns = parsed["columns"]
    date_col = _find_col(columns, "date")
    arm_col = _find_col(columns, "arm")

    rows_by_arm: dict[str, int] = {}
    newest_by_arm: dict[str, date] = {}
    newest_overall: date | None = None
    unparseable_dates: list[dict[str, Any]] = []
    row_evidence: dict[str, dict[str, str]] = {}

    for idx, (rec, row_sha256) in enumerate(
        zip(parsed["raw_rows"], parsed["raw_row_hashes"], strict=True)
    ):
        arm_key = (rec.get(arm_col, "").strip() if arm_col else "") or "<unknown>"
        row_evidence[row_sha256] = {
            "arm": arm_key,
            "date": rec.get(date_col, "").strip() if date_col else "",
        }
        rows_by_arm[arm_key] = rows_by_arm.get(arm_key, 0) + 1

        if date_col is None:
            continue
        d = _parse_date(rec.get(date_col, ""))
        if d is None:
            unparseable_dates.append({"row_index": idx, "date_raw": rec.get(date_col, "")})
            continue
        if arm_key not in newest_by_arm or d > newest_by_arm[arm_key]:
            newest_by_arm[arm_key] = d
        if newest_overall is None or d > newest_overall:
            newest_overall = d

    return {
        "error": None,
        "columns": columns,
        "total_rows": len(parsed["raw_rows"]),
        "rows_by_arm": rows_by_arm,
        "newest_row_date": newest_overall,
        "newest_row_date_by_arm": newest_by_arm,
        "row_evidence": row_evidence,
        "malformed_rows": parsed["malformed_rows"],
        "unparseable_dates": unparseable_dates,
    }


def load_note_summary(path: Path) -> dict[str, Any]:
    """Read + summarize one benchmark note. Never raises — a missing/unreadable
    file becomes exists=False + an error string."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "exists": False,
            "error": f"file not found: {path}",
            "columns": [],
            "total_rows": 0,
            "rows_by_arm": {},
            "newest_row_date": None,
            "newest_row_date_by_arm": {},
            "row_evidence": {},
            "malformed_rows": [],
            "unparseable_dates": [],
        }
    except OSError as e:
        return {
            "exists": False,
            "error": f"could not read {path}: {e}",
            "columns": [],
            "total_rows": 0,
            "rows_by_arm": {},
            "newest_row_date": None,
            "newest_row_date_by_arm": {},
            "row_evidence": {},
            "malformed_rows": [],
            "unparseable_dates": [],
        }
    summary = summarize_note(text)
    summary["exists"] = True
    return summary


def load_all_note_summaries(notes: dict[str, Path] = BENCHMARK_NOTES) -> dict[str, dict[str, Any]]:
    return {name: load_note_summary(path) for name, path in notes.items()}


# --- Timestamped capture receipts --------------------------------------------

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_REQUIRED_FIELDS = {
    "schemaVersion",
    "capturedAt",
    "noteId",
    "rowSha256",
    "rowDate",
    "arm",
    "beforeCount",
    "afterCount",
}
_RECEIPT_OPTIONAL_FIELDS = {"runId", "variant", "rowDateSource"}
_STRICT_RECEIPT_FIELDS = {
    "schemaVersion",
    "capturedAt",
    "schema_version",
    "record_type",
    "observed_at",
    "baseline_sha",
    "variant",
    "arm",
    "environment",
    "routine_id",
    "scheduler_run_id",
    "artifact_run_id",
    "task_scope",
    "input_fingerprint",
    "definition_digest",
    "artifact_digest",
    "started_at",
    "ended_at",
    "duration_ms",
    "expected_steps",
    "completed_steps",
    "steps",
    "outputs",
    "effects",
    "failure_classes",
    "retry_count",
    "approval_cycles",
    "correctness",
    "benchmark",
    "duration_reconciliation",
    "comparable",
    "comparability_reasons",
    "rowDate",
    "rowDateSource",
    "noteId",
    "rowSha256",
    "beforeCount",
    "afterCount",
    "runId",
}
_CAPTURE_VARIANTS = {"A", "B", "G", "G1", "G2", "G3"}
_GRAPH_CAPTURE_VARIANTS = _CAPTURE_VARIANTS - {"A", "B"}
_SAFE_RECEIPT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_STRICT_ENVIRONMENTS = {"cowork", "claude-code", "codex", "local", "split"}
_STEP_STATUSES = {"completed", "failed", "partial", "skipped"}
_EFFECT_STATUSES = {"completed", "failed", "prevented", "skipped"}
_MAX_RECEIPT_LAG = timedelta(hours=24)


def note_identity(path: Path) -> str:
    """Stable note identity shared with bench-append; never exposes the path."""
    canonical = str(path.expanduser().resolve(strict=False))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _capture_timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _capture_utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be a UTC ISO timestamp ending in Z")
    parsed = _capture_timestamp(value, field)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must be UTC")
    return parsed


def _duration_milliseconds(start: datetime, end: datetime, field: str) -> int:
    delta = end - start
    microseconds = ((delta.days * 86400 + delta.seconds) * 1_000_000) + delta.microseconds
    if microseconds < 0 or microseconds % 1000:
        raise ValueError(f"{field} timestamps must produce whole non-negative milliseconds")
    return microseconds // 1000


def _safe_receipt_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_RECEIPT_ID_RE.fullmatch(value):
        raise ValueError(f"{field} must be a redacted identifier")
    return value


def _safe_receipt_ids(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of redacted identifiers")
    result = [_safe_receipt_id(item, f"{field}[]") for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{field} contains duplicates")
    return result


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _exact_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{field} fields do not match the strict receipt schema")
    return value


def _validate_capture_receipt_v2(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != _STRICT_RECEIPT_FIELDS:
        raise ValueError("receipt fields do not match schema version 2")
    if value.get("schema_version") != "procedural-engineering-eval/v2":
        raise ValueError("schema_version must be procedural-engineering-eval/v2")
    if value.get("record_type") != "routine_run":
        raise ValueError("record_type must be routine_run")
    variant = value.get("variant")
    if variant not in {"A", "B"} or value.get("arm") != variant:
        raise ValueError("strict receipt variant and arm must match A or B")
    if value.get("rowDateSource") != "row":
        raise ValueError("strict receipt rowDateSource must be row")

    for field in ("noteId", "rowSha256", "input_fingerprint", "definition_digest", "artifact_digest"):
        if not _SHA256_RE.fullmatch(str(value.get(field))):
            raise ValueError(f"{field} must be a SHA-256 digest")
    if not _SHA40_RE.fullmatch(str(value.get("baseline_sha"))):
        raise ValueError("baseline_sha must be a 40-character lowercase Git SHA")
    routine_id = _safe_receipt_id(value.get("routine_id"), "routine_id")
    scheduler_run_id = _safe_receipt_id(value.get("scheduler_run_id"), "scheduler_run_id")
    artifact_run_id = _safe_receipt_id(value.get("artifact_run_id"), "artifact_run_id")
    run_id = _safe_receipt_id(value.get("runId"), "runId")
    if run_id != artifact_run_id:
        raise ValueError("runId must match artifact_run_id")
    if scheduler_run_id == artifact_run_id:
        raise ValueError("scheduler_run_id must differ from artifact_run_id")
    if value.get("environment") not in _STRICT_ENVIRONMENTS:
        raise ValueError("environment is not recognized")

    captured_at = _capture_utc_timestamp(value.get("capturedAt"), "capturedAt")
    observed_at = _capture_utc_timestamp(value.get("observed_at"), "observed_at")
    started_at = _capture_utc_timestamp(value.get("started_at"), "started_at")
    ended_at = _capture_utc_timestamp(value.get("ended_at"), "ended_at")
    if observed_at != ended_at or started_at > ended_at or captured_at < ended_at:
        raise ValueError("strict receipt timestamps do not reconcile")
    duration_ms = _nonnegative_integer(value.get("duration_ms"), "duration_ms")
    if _duration_milliseconds(started_at, ended_at, "whole-run") != duration_ms:
        raise ValueError("duration_ms does not reconcile started_at and ended_at")

    row_date = _parse_date(value.get("rowDate"))
    if row_date is None:
        raise ValueError("rowDate must be YYYY-MM-DD")
    before_count = _nonnegative_integer(value.get("beforeCount"), "beforeCount")
    after_count = _nonnegative_integer(value.get("afterCount"), "afterCount")
    if after_count - before_count != 1:
        raise ValueError("append counts must prove a delta of exactly 1")

    scope = _exact_keys(
        value.get("task_scope"),
        {"scope_id", "source_classes", "source_count", "parameter_keys"},
        "task_scope",
    )
    _safe_receipt_id(scope.get("scope_id"), "task_scope.scope_id")
    _safe_receipt_ids(scope.get("source_classes"), "task_scope.source_classes")
    _nonnegative_integer(scope.get("source_count"), "task_scope.source_count")
    _safe_receipt_ids(scope.get("parameter_keys"), "task_scope.parameter_keys")

    expected_steps = _safe_receipt_ids(value.get("expected_steps"), "expected_steps")
    completed_steps = _safe_receipt_ids(value.get("completed_steps"), "completed_steps")
    if not expected_steps or not set(completed_steps).issubset(expected_steps):
        raise ValueError("completed_steps must be a subset of non-empty expected_steps")
    steps = value.get("steps")
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")
    step_total_ms = 0
    step_ids: list[str] = []
    completed_from_status: list[str] = []
    previous_end: datetime | None = None
    for index, step_value in enumerate(steps):
        step = _exact_keys(
            step_value,
            {"step_id", "status", "started_at", "ended_at", "duration_ms"},
            f"steps[{index}]",
        )
        step_id = _safe_receipt_id(step.get("step_id"), f"steps[{index}].step_id")
        if step_id not in expected_steps:
            raise ValueError("steps contains an undeclared step")
        status = step.get("status")
        if status not in _STEP_STATUSES:
            raise ValueError("step status is not recognized")
        step_started = _capture_utc_timestamp(step.get("started_at"), "step.started_at")
        step_ended = _capture_utc_timestamp(step.get("ended_at"), "step.ended_at")
        step_duration = _nonnegative_integer(step.get("duration_ms"), "step.duration_ms")
        if step_started < started_at or step_ended > ended_at or step_started > step_ended:
            raise ValueError("step timestamps are outside the whole-run interval")
        if previous_end is not None and step_started < previous_end:
            raise ValueError("step timestamps overlap")
        if _duration_milliseconds(step_started, step_ended, "step") != step_duration:
            raise ValueError("step duration does not reconcile")
        previous_end = step_ended
        step_total_ms += step_duration
        step_ids.append(step_id)
        if status == "completed":
            completed_from_status.append(step_id)
    if len(step_ids) != len(set(step_ids)) or completed_steps != completed_from_status:
        raise ValueError("step identities or completed_steps do not reconcile")

    for field, keys, id_key, type_key in (
        ("outputs", {"output_id", "output_type"}, "output_id", "output_type"),
        ("effects", {"effect_id", "effect_type", "status"}, "effect_id", "effect_type"),
    ):
        records = value.get(field)
        if not isinstance(records, list):
            raise ValueError(f"{field} must be a list")
        seen: set[str] = set()
        for index, record_value in enumerate(records):
            record = _exact_keys(record_value, keys, f"{field}[{index}]")
            identifier = _safe_receipt_id(record.get(id_key), f"{field}[{index}].{id_key}")
            if identifier in seen:
                raise ValueError(f"{field} contains duplicate identifiers")
            seen.add(identifier)
            _safe_receipt_id(record.get(type_key), f"{field}[{index}].{type_key}")
            if field == "effects" and record.get("status") not in _EFFECT_STATUSES:
                raise ValueError("effect status is not recognized")

    failure_classes = _safe_receipt_ids(value.get("failure_classes"), "failure_classes")
    _nonnegative_integer(value.get("retry_count"), "retry_count")
    _nonnegative_integer(value.get("approval_cycles"), "approval_cycles")
    correctness = _exact_keys(
        value.get("correctness"),
        {"schema_valid", "source_failures_present", "human_correction_required", "unsafe_effect_prevented", "fabricated_clean_detected"},
        "correctness",
    )
    if any(not isinstance(item, bool) for item in correctness.values()):
        raise ValueError("correctness values must be booleans")

    benchmark = _exact_keys(
        value.get("benchmark"),
        {"row_id", "row_sha256", "note_id", "projection"},
        "benchmark",
    )
    _safe_receipt_id(benchmark.get("row_id"), "benchmark.row_id")
    if benchmark.get("row_sha256") != value.get("rowSha256") or benchmark.get("note_id") != value.get("noteId"):
        raise ValueError("benchmark digests must match the top-level row and note digests")
    projection = _exact_keys(
        benchmark.get("projection"),
        {"before_count", "after_count", "row_delta", "row_is_last", "append_assertion"},
        "benchmark.projection",
    )
    if (
        projection.get("before_count") != before_count
        or projection.get("after_count") != after_count
        or projection.get("row_delta") != 1
        or projection.get("row_is_last") is not True
        or projection.get("append_assertion") != "passed"
    ):
        raise ValueError("benchmark projection must prove the same exact one-row append")

    reconciliation = _exact_keys(
        value.get("duration_reconciliation"),
        {"step_total_ms", "unattributed_ms", "timestamps_reconciled"},
        "duration_reconciliation",
    )
    reconciliation_step_total = _nonnegative_integer(
        reconciliation.get("step_total_ms"), "duration_reconciliation.step_total_ms"
    )
    reconciliation_unattributed = _nonnegative_integer(
        reconciliation.get("unattributed_ms"), "duration_reconciliation.unattributed_ms"
    )
    if (
        reconciliation_step_total != step_total_ms
        or reconciliation_unattributed != duration_ms - step_total_ms
        or reconciliation.get("timestamps_reconciled") is not True
    ):
        raise ValueError("duration reconciliation does not match the strict lifecycle")
    comparable = value.get("comparable")
    if not isinstance(comparable, bool):
        raise ValueError("comparable must be a boolean")
    comparability_reasons = _safe_receipt_ids(
        value.get("comparability_reasons"), "comparability_reasons"
    )
    if comparable and (
        comparability_reasons
        or completed_steps != expected_steps
        or step_ids != expected_steps
        or failure_classes
        or correctness.get("schema_valid") is not True
        or any(
            correctness.get(field) is not False
            for field in correctness
            if field != "schema_valid"
        )
    ):
        raise ValueError("comparable strict receipt has incomplete or failed evidence")
    if not comparable and not comparability_reasons:
        raise ValueError("non-comparable strict receipt requires a comparability reason")

    return {
        **value,
        "variant": variant,
        "runId": run_id,
        "routine_id": routine_id,
        "captured_at": captured_at,
        "routine_started_at": started_at,
        "row_date": row_date,
    }


def _validate_capture_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("receipt must be an object")
    if value.get("schemaVersion") == 2:
        return _validate_capture_receipt_v2(value)
    fields = set(value)
    if (
        not _RECEIPT_REQUIRED_FIELDS.issubset(fields)
        or fields - _RECEIPT_REQUIRED_FIELDS - _RECEIPT_OPTIONAL_FIELDS
    ):
        raise ValueError("receipt fields do not match schema version 1")
    if value["schemaVersion"] != 1:
        raise ValueError("schemaVersion must be 1")
    arm = value["arm"]
    if arm not in _CAPTURE_VARIANTS:
        raise ValueError("arm must be A, B, G, G1, G2, or G3")
    variant = value.get("variant", arm)
    if variant not in _CAPTURE_VARIANTS:
        raise ValueError("variant must be A, B, G, G1, G2, or G3")
    if variant != arm:
        raise ValueError("variant must match arm")
    if not _SHA256_RE.fullmatch(str(value["noteId"])):
        raise ValueError("noteId must be a SHA-256 digest")
    if not _SHA256_RE.fullmatch(str(value["rowSha256"])):
        raise ValueError("rowSha256 must be a SHA-256 digest")
    run_id = value.get("runId")
    if run_id is not None and (
        not isinstance(run_id, str) or not run_id
    ):
        raise ValueError("runId must be null or a non-empty string")
    row_date_source = value.get("rowDateSource", "row")
    if row_date_source not in {"row", "captured_local_date"}:
        raise ValueError("rowDateSource must be row or captured_local_date")
    if row_date_source == "captured_local_date":
        if variant not in _GRAPH_CAPTURE_VARIANTS:
            raise ValueError("captured_local_date is valid only for graph variants")
        if run_id is None:
            raise ValueError("captured_local_date requires runId")
    if isinstance(value["beforeCount"], bool) or not isinstance(value["beforeCount"], int):
        raise ValueError("beforeCount must be an integer")
    if isinstance(value["afterCount"], bool) or not isinstance(value["afterCount"], int):
        raise ValueError("afterCount must be an integer")
    if value["afterCount"] - value["beforeCount"] != 1:
        raise ValueError("append counts must prove a delta of exactly 1")
    row_date = _parse_date(value["rowDate"])
    if row_date is None:
        raise ValueError("rowDate must be YYYY-MM-DD")
    captured_at = _capture_timestamp(value["capturedAt"], "capturedAt")
    return {
        **value,
        "variant": variant,
        "rowDateSource": row_date_source,
        "runId": run_id,
        "captured_at": captured_at,
        "row_date": row_date,
    }


def load_benchmark_receipts(receipts_dir: Path = BENCHMARK_RECEIPTS_DIR) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": True,
        "error": None,
        "valid": 0,
        "by_variant": {},
        "by_schema_version": {},
        "by_note_id": {},
        "malformed": [],
    }
    if not receipts_dir.exists():
        result["available"] = False
        result["error"] = f"receipt dir not found: {receipts_dir}"
        return result
    try:
        paths = sorted(receipts_dir.glob("*.json"))
    except OSError as error:
        result["available"] = False
        result["error"] = str(error)
        return result
    for path in paths:
        try:
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise ValueError("receipt permissions must be 0600")
            receipt = _validate_capture_receipt(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            result["malformed"].append({"file": path.name, "reason": str(error)})
            continue
        receipt["source_file"] = path.name
        result["valid"] += 1
        variant = receipt["variant"]
        result["by_variant"][variant] = result["by_variant"].get(variant, 0) + 1
        schema_version = str(receipt["schemaVersion"])
        result["by_schema_version"][schema_version] = (
            result["by_schema_version"].get(schema_version, 0) + 1
        )
        result["by_note_id"].setdefault(receipt["noteId"], []).append(receipt)
    for receipts in result["by_note_id"].values():
        receipts.sort(key=lambda item: item["captured_at"])
    return result


# --- 2. Run telemetry --------------------------------------------------------


def load_run_telemetry(runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    """Stream every runs_dir/*.jsonl line-by-line, aggregate per-artifact counts.
    Never loads a file wholesale; never raises on a missing dir or a bad line."""
    result: dict[str, Any] = {
        "available": True,
        "error": None,
        "files_read": 0,
        "files_error": [],
        "artifacts": {},
        "capture_runs": {},
    }
    if not runs_dir.exists():
        result["available"] = False
        result["error"] = f"runs dir not found: {runs_dir}"
        return result

    for fp in sorted(runs_dir.glob("*.jsonl")):
        try:
            with fp.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # skip a corrupt telemetry line, don't crash
                    name = rec.get("name") or "<unknown>"
                    entry = result["artifacts"].setdefault(
                        name, {"runs": 0, "ok": 0, "fail": 0, "newest_started_at": None}
                    )
                    entry["runs"] += 1
                    if rec.get("ok"):
                        entry["ok"] += 1
                    else:
                        entry["fail"] += 1
                    started = rec.get("started_at")
                    if started and (
                        entry["newest_started_at"] is None or started > entry["newest_started_at"]
                    ):
                        entry["newest_started_at"] = started
                    run_id = rec.get("run_id")
                    if (
                        name == "bench-append"
                        and isinstance(run_id, str)
                        and run_id
                        and isinstance(started, str)
                        and started
                    ):
                        result["capture_runs"][run_id] = {
                            "ok": rec.get("ok") is True,
                            "started_at": started,
                        }
            result["files_read"] += 1
        except OSError as e:
            result["files_error"].append({"file": str(fp), "error": str(e)})

    return result


# --- 3. Health sidecars -------------------------------------------------------


def load_health_sidecars(health_dir: Path = HEALTH_DIR) -> dict[str, Any]:
    """Read every health_dir/**/*.json sidecar. This is the offline-authoritative
    health record — deliberately NOT the (stale) health field inside
    *.provenance.json."""
    result: dict[str, Any] = {"available": True, "error": None, "artifacts": {}}
    if not health_dir.exists():
        result["available"] = False
        result["error"] = f"health dir not found: {health_dir}"
        return result

    for fp in sorted(health_dir.rglob("*.json")):
        artifact_id = str(fp.relative_to(health_dir).with_suffix(""))
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            result["artifacts"][artifact_id] = {
                "health": data.get("health"),
                "last_verified": data.get("last_verified"),
            }
        except (OSError, json.JSONDecodeError) as e:
            result["artifacts"][artifact_id] = {"error": str(e)}

    return result


# --- 4. Scheduler state -------------------------------------------------------


def load_scheduler_status(
    scheduled_tasks_dir: Path = SCHEDULED_TASKS_DIR,
    sessions_root: Path = DESKTOP_SESSIONS_ROOT,
) -> dict[str, Any]:
    """Best-effort scheduler reader. Never raises — an unresolvable path or an
    unreadable/malformed JSON file is recorded as an error, not a crash."""
    result: dict[str, Any] = {
        "cli_scheduled_tasks": [],
        "cli_scheduled_tasks_error": None,
        "desktop_tasks": [],
        "desktop_registry_error": None,
    }

    try:
        if scheduled_tasks_dir.exists():
            result["cli_scheduled_tasks"] = sorted(
                p.name for p in scheduled_tasks_dir.iterdir() if p.is_dir()
            )
        else:
            result["cli_scheduled_tasks_error"] = f"not found: {scheduled_tasks_dir}"
    except OSError as e:
        result["cli_scheduled_tasks_error"] = str(e)

    try:
        if sessions_root.exists():
            found_any = False
            for fp in sorted(sessions_root.glob("*/*/scheduled-tasks.json")):
                found_any = True
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as e:
                    result["desktop_tasks"].append({"source_file": str(fp), "error": str(e)})
                    continue
                for t in data.get("scheduledTasks", []):
                    result["desktop_tasks"].append(
                        {
                            "id": t.get("id"),
                            "enabled": t.get("enabled"),
                            "lastRunAt": t.get("lastRunAt"),
                            "cronExpression": t.get("cronExpression"),
                            "source_file": str(fp),
                        }
                    )
            if not found_any:
                result["desktop_registry_error"] = f"no scheduled-tasks.json found under {sessions_root}"
        else:
            result["desktop_registry_error"] = f"not found: {sessions_root}"
    except OSError as e:
        result["desktop_registry_error"] = str(e)

    return result


def find_scheduler_last_run(routine_name: str, scheduler_status: dict[str, Any]) -> dict[str, Any]:
    """Match a routine's known id-substrings against the Desktop registry's task
    ids, and return the MOST RECENT lastRunAt among all matches."""
    keys = ROUTINE_SCHEDULER_KEYS.get(routine_name, [])
    if not keys:
        return {
            "matched": False,
            "last_run_at": None,
            "matched_ids": [],
            "reason": f"no scheduler keys configured for '{routine_name}' (on-demand routine by design)",
        }

    matches = [
        t
        for t in scheduler_status["desktop_tasks"]
        if t.get("id") and any(key in t["id"].lower() for key in keys)
    ]
    if not matches:
        return {
            "matched": False,
            "last_run_at": None,
            "matched_ids": [],
            "reason": f"no desktop scheduler entry matched keys {keys}",
        }

    parsed: list[tuple[datetime, dict]] = []
    for m in matches:
        lra = m.get("lastRunAt")
        if not lra:
            continue
        try:
            parsed.append((datetime.fromisoformat(lra.replace("Z", "+00:00")), m))
        except ValueError:
            continue

    matched_ids = [m.get("id") for m in matches]
    enabled = any(m.get("enabled") is True for m in matches)
    if not parsed:
        return {
            "matched": True,
            "last_run_at": None,
            "matched_ids": matched_ids,
            "enabled": enabled,
            "reason": None,
        }

    parsed.sort(key=lambda x: x[0])
    newest_dt, _ = parsed[-1]
    return {
        "matched": True,
        "last_run_at": newest_dt,
        "matched_ids": matched_ids,
        "enabled": enabled,
        "reason": None,
    }


# --- 5. Liveness classification ----------------------------------------------

LIVENESS_STATUSES = (
    "ok",
    "legacy_unverifiable",
    "indeterminate_same_day",
    "receipt_missing",
    "row_missing",
    "never_run",
    "unknown",
)


def _receipt_covers_scheduler_run(receipt: dict[str, Any], last_run_at: datetime) -> bool:
    captured_at = receipt.get("captured_at")
    if not isinstance(captured_at, datetime) or captured_at.tzinfo is None:
        return False
    captured_at = captured_at.astimezone(BENCHMARK_TIMEZONE)
    elapsed = captured_at - last_run_at
    if elapsed < timedelta(0) or elapsed > _MAX_RECEIPT_LAG:
        return False
    receipt_row_date = receipt.get("row_date") or _parse_date(receipt.get("rowDate"))
    return receipt_row_date in {last_run_at.date(), captured_at.date()}


def classify_liveness(
    note_summary: dict[str, Any],
    scheduler_lookup: dict[str, Any],
    capture_receipts: list[dict[str, Any]] | None = None,
    *,
    receipt_enforcement_started_at: datetime = RECEIPT_ENFORCEMENT_STARTED_AT,
) -> dict[str, Any]:
    """The watchdog's actual verdict: did the routine run, and did a row land?

    ok                     — a valid timestamped receipt is bound to the latest
                             post-enforcement scheduler run, or a demonstrably
                             later row covers a pre-enforcement run.
    indeterminate_same_day — the newest row and the scheduler's last run share
                             a calendar date. Rows carry only a DATE, not a
                             time, so whether that row was written before or
                             after that day's run cannot be determined either
                             way from this data. Reporting this as `ok` was
                             the exact false-negative this module used to
                             produce: a run that landed no row still reads as
                             covered as long as some earlier row exists from
                             the same day. Never fabricate a time to resolve
                             this — report the genuine indeterminacy instead.
    legacy_unverifiable    — the same date-only ambiguity, but the scheduler run
                             predates timestamped receipt enforcement. Keep the
                             uncertainty visible without alerting forever on
                             evidence that could not have been captured.
    receipt_missing        — a later-dated row exists, but a post-enforcement
                             scheduler run has no fresh bound receipt. The row
                             cannot substitute for required run evidence.
    row_missing            — scheduler shows a run that postdates the newest
                             row (or the note has zero rows despite a recorded
                             run). THE finding this module exists to surface.
    never_run              — scheduler entry exists but has no recorded run,
                             and the note has zero rows.
    unknown                — can't determine; `reason` names the missing
                             input.
    """
    if note_summary.get("error"):
        return {"status": "unknown", "reason": f"could not read/parse note: {note_summary['error']}"}

    if not scheduler_lookup["matched"]:
        return {"status": "unknown", "reason": scheduler_lookup["reason"]}

    last_run_at = scheduler_lookup.get("last_run_at")
    newest_row_date = note_summary.get("newest_row_date")
    total_rows = note_summary.get("total_rows", 0)

    if last_run_at is None:
        if total_rows == 0:
            return {
                "status": "never_run",
                "reason": "scheduler entry found but has no recorded run, and the note has zero rows",
            }
        return {
            "status": "unknown",
            "reason": "scheduler entry found but lastRunAt is missing; note has rows so recency can't be verified",
        }

    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=BENCHMARK_TIMEZONE)
    else:
        last_run_at = last_run_at.astimezone(BENCHMARK_TIMEZONE)
    if receipt_enforcement_started_at.tzinfo is None:
        raise ValueError("receipt_enforcement_started_at must include a timezone")
    receipt_enforcement_started_at = receipt_enforcement_started_at.astimezone(
        BENCHMARK_TIMEZONE
    )
    last_run_date = last_run_at.date()
    for receipt in capture_receipts or []:
        if _receipt_covers_scheduler_run(receipt, last_run_at):
            return {
                "status": "ok",
                "reason": (
                    "timestamped capture receipt is fresh for the scheduler run and "
                    "bound to an exact benchmark row"
                ),
            }
    if newest_row_date is None:
        return {
            "status": "row_missing",
            "reason": f"scheduler last ran {last_run_date.isoformat()} but the note has zero rows",
        }
    if last_run_date > newest_row_date:
        return {
            "status": "row_missing",
            "reason": (
                f"scheduler last ran {last_run_date.isoformat()}, "
                f"newest row is {newest_row_date.isoformat()} — a run happened and no row landed"
            ),
        }
    if last_run_date == newest_row_date:
        if last_run_at < receipt_enforcement_started_at:
            return {
                "status": "legacy_unverifiable",
                "reason": (
                    f"scheduler last ran {last_run_date.isoformat()} and the newest row is "
                    f"also dated {newest_row_date.isoformat()}, before timestamped receipt "
                    "enforcement began — historical ordering remains unverifiable and is "
                    "not reconstructed"
                ),
            }
        return {
            "status": "indeterminate_same_day",
            "reason": (
                f"scheduler last ran {last_run_date.isoformat()} and the newest row is "
                f"also dated {newest_row_date.isoformat()} — rows carry only a date, not "
                "a time, so whether this row postdates the run cannot be determined"
            ),
        }
    if last_run_at >= receipt_enforcement_started_at:
        return {
            "status": "receipt_missing",
            "reason": (
                f"scheduler last ran {last_run_date.isoformat()} and a later row dated "
                f"{newest_row_date.isoformat()} exists, but no fresh run-bound receipt "
                "proves capture for the scheduler run"
            ),
        }
    return {
        "status": "ok",
        "reason": f"newest row {newest_row_date.isoformat()} covers scheduler's last run {last_run_date.isoformat()}",
    }


# --- Orchestration -------------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def run_context_capture_health(
    runner_path: Path | None,
    *,
    command_runner: Any = subprocess.run,
) -> dict[str, Any]:
    if runner_path is None:
        return {"configured": False, "available": False, "error": None, "report": None}
    try:
        result = command_runner(
            [sys.executable, str(runner_path), "capture-health"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode not in {0, 2}:
            raise ValueError(f"capture-health exited {result.returncode}")
        report = json.loads(result.stdout)
        if (
            not isinstance(report, dict)
            or not isinstance(report.get("ok"), bool)
            or not isinstance(report.get("issues"), list)
        ):
            raise ValueError("capture-health output does not match its report contract")
        if (result.returncode == 0) != report["ok"]:
            raise ValueError("capture-health exit code disagrees with report.ok")
        return {
            "configured": True,
            "available": True,
            "error": None,
            "exit_code": result.returncode,
            "report": report,
        }
    except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError) as error:
        return {
            "configured": True,
            "available": False,
            "error": _safe_event_text(error),
            "report": None,
        }


def build_snapshot(
    notes: dict[str, Path] = BENCHMARK_NOTES,
    runs_dir: Path = RUNS_DIR,
    health_dir: Path = HEALTH_DIR,
    scheduled_tasks_dir: Path = SCHEDULED_TASKS_DIR,
    sessions_root: Path = DESKTOP_SESSIONS_ROOT,
    receipts_dir: Path = BENCHMARK_RECEIPTS_DIR,
    context_runner: Path | None = None,
) -> dict[str, Any]:
    note_summaries = load_all_note_summaries(notes)
    run_telemetry = load_run_telemetry(runs_dir)
    health = load_health_sidecars(health_dir)
    scheduler_status = load_scheduler_status(scheduled_tasks_dir, sessions_root)
    capture_receipts = load_benchmark_receipts(receipts_dir)
    capture_receipts["unbound"] = []
    context_capture_health = run_context_capture_health(context_runner)

    liveness: dict[str, Any] = {}
    for routine_name in notes:
        lookup = find_scheduler_last_run(routine_name, scheduler_status)
        candidate_receipts = [
            receipt
            for receipt in capture_receipts["by_note_id"].get(
                note_identity(notes[routine_name]), []
            )
            if receipt["variant"] in {"A", "B"}
        ]
        row_evidence = note_summaries[routine_name].get("row_evidence", {})
        receipts = []
        for receipt in candidate_receipts:
            evidence = row_evidence.get(receipt["rowSha256"])
            capture_run = run_telemetry["capture_runs"].get(receipt.get("runId"))
            binding_error = None
            if evidence != {"arm": receipt["arm"], "date": receipt["rowDate"]}:
                binding_error = "receipt does not match an exact row in the benchmark note"
            elif (
                receipt["schemaVersion"] == 2
                and receipt.get("routine_id") != ROUTINE_RECEIPT_IDS.get(routine_name)
            ):
                binding_error = "strict receipt routine id does not match the benchmark routine"
            elif capture_run is None:
                binding_error = "receipt runId does not match bench-append run telemetry"
            elif capture_run.get("ok") is not True:
                binding_error = "receipt runId belongs to a failed bench-append run"
            else:
                try:
                    run_started_at = datetime.fromisoformat(
                        str(capture_run["started_at"]).replace("Z", "+00:00")
                    )
                except (KeyError, ValueError):
                    binding_error = "receipt run telemetry has an invalid started_at"
                else:
                    if run_started_at.tzinfo is None:
                        binding_error = "receipt run telemetry started_at lacks a timezone"
                    elif receipt["captured_at"] < run_started_at:
                        binding_error = "receipt timestamp predates its bench-append run"
            if binding_error is None:
                receipts.append(receipt)
            else:
                capture_receipts["unbound"].append(
                    {
                        "arm": receipt["arm"],
                        "file": receipt["source_file"],
                        "routine": routine_name,
                        "reason": binding_error,
                    }
                )
        verdict = classify_liveness(note_summaries[routine_name], lookup, receipts)
        liveness[routine_name] = {
            "status": verdict["status"],
            "reason": verdict["reason"],
            "scheduler_matched_ids": lookup.get("matched_ids", []),
            "scheduler_last_run_at": lookup.get("last_run_at"),
            "scheduler_enabled": lookup.get("enabled"),
        }

    snapshot = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "notes": note_summaries,
        "run_telemetry": run_telemetry,
        "health": health,
        "scheduler": scheduler_status,
        "capture_receipts": capture_receipts,
        "context_capture_health": context_capture_health,
        "liveness": liveness,
    }
    return _jsonable(snapshot)


def actionable_findings(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    receipt_store = snapshot.get("capture_receipts", {})
    if receipt_store.get("available") is False:
        findings.append(
            {
                "routine": "capture-receipts",
                "status": "receipt_store_unavailable",
                "reason": receipt_store.get("error") or "capture receipt store unavailable",
                "scheduler_matched_ids": [],
                "scheduler_last_run_at": None,
                "component": "benchmark-status",
                "system": "procedural-memory",
                "arm": "global",
            }
        )
    for routine, value in snapshot.get("liveness", {}).items():
        status = value.get("status")
        reason = str(value.get("reason") or "")
        if status not in {
            "row_missing",
            "indeterminate_same_day",
            "receipt_missing",
            "never_run",
            "unknown",
        }:
            continue
        if status == "unknown" and "on-demand routine by design" in reason:
            continue
        if status == "never_run" and value.get("scheduler_enabled") is not True:
            continue
        findings.append(
            {
                "routine": routine,
                "status": status,
                "reason": reason,
                "component": "benchmark-status",
                "system": "procedural-memory",
                "arm": "global",
                "scheduler_matched_ids": value.get("scheduler_matched_ids", []),
                "scheduler_last_run_at": value.get("scheduler_last_run_at"),
            }
        )
    for malformed in snapshot.get("capture_receipts", {}).get("malformed", []):
        findings.append(
            {
                "routine": "capture-receipts",
                "status": "malformed_receipt",
                "reason": f"{malformed.get('file')}: {malformed.get('reason')}",
                "scheduler_matched_ids": [],
                "scheduler_last_run_at": None,
                "component": "benchmark-status",
                "system": "procedural-memory",
                "arm": "global",
            }
        )
    for unbound in snapshot.get("capture_receipts", {}).get("unbound", []):
        findings.append(
            {
                "routine": unbound.get("routine", "capture-receipts"),
                "status": "unbound_receipt",
                "reason": f"{unbound.get('file')}: {unbound.get('reason')}",
                "scheduler_matched_ids": [],
                "scheduler_last_run_at": None,
                "component": "benchmark-status",
                "system": "procedural-memory",
                "arm": str(unbound.get("arm") or "global"),
            }
        )

    context = snapshot.get("context_capture_health", {})
    if context.get("configured") and not context.get("available"):
        findings.append(
            {
                "routine": "context-capture-health",
                "status": "evaluator_unavailable",
                "reason": context.get("error") or "capture-health report unavailable",
                "scheduler_matched_ids": [],
                "scheduler_last_run_at": None,
                "component": "context-capture-health",
                "system": "context-experiments",
                "arm": "global",
            }
        )
    elif context.get("available"):
        seen: set[tuple[str, str, str]] = set()
        for issue in context.get("report", {}).get("issues", []):
            capability = str(issue.get("capability") or "global")
            affected_arms = (
                issue.get("affectedArms") or issue.get("missingArms") or ["global"]
            )
            for arm in affected_arms:
                key = (capability, str(arm), str(issue.get("kind") or "unknown"))
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    {
                        "routine": f"context:{capability}",
                        "status": key[2],
                        "reason": (
                            f"{issue.get('path', 'capture artifact')}: "
                            f"{issue.get('error') or issue.get('status') or key[2]}"
                        ),
                        "scheduler_matched_ids": [],
                        "scheduler_last_run_at": None,
                        "component": "context-capture-health",
                        "system": "context-experiments",
                        "arm": str(arm),
                    }
                )
    return findings


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


def _safe_event_text(value: Any) -> str:
    text = str(value)
    text = text.replace(str(HOME), "[home]")
    return re.sub(r"/(?:Users|private|var|tmp|Volumes)/.*", "[local path redacted]", text)


def build_sentry_event(
    finding: dict[str, Any], generated_at: str, release: str | None
) -> dict[str, Any]:
    routine = str(finding["routine"])
    status = str(finding["status"])
    component = str(finding.get("component") or "benchmark-status")
    system = str(finding.get("system") or "procedural-memory")
    arm = str(finding.get("arm") or "global")
    event = {
        "event_id": secrets.token_hex(16),
        "timestamp": generated_at,
        "platform": "python",
        "level": "warning" if status == "indeterminate_same_day" else "error",
        "logger": "rhize.benchmark-capture",
        "message": f"Benchmark measurement unavailable: {_slug(routine)}",
        "fingerprint": [
            "rhize-agent-evals",
            _slug(component),
            _slug(routine),
            _slug(arm),
            _slug(status),
        ],
        "environment": os.environ.get("RHIZE_BENCHMARK_ENVIRONMENT", "production"),
        "tags": {
            "alert.kind": "measurement-unavailable",
            "benchmark.routine": _slug(routine),
            "benchmark.status": status,
            "benchmark.measurement_required": "true",
            "component": component,
            "eval.system": system,
            "eval.failure": status,
            "eval.arm": arm,
        },
        "extra": {
            "reason": _safe_event_text(finding.get("reason", "")),
            "scheduler_ids": [
                _safe_event_text(item) for item in finding.get("scheduler_matched_ids", [])
            ],
            "scheduler_last_run_at": finding.get("scheduler_last_run_at"),
        },
    }
    if release:
        event["release"] = release
    return event


def _sentry_endpoint_parts(dsn: str) -> tuple[str, str, str]:
    parsed = parse.urlsplit(dsn)
    project_id = parsed.path.strip("/")
    public_key = parsed.username
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Sentry DSN must use HTTP(S) and include a host")
    if not project_id or not public_key:
        raise ValueError("Sentry DSN must include a public key and project id")
    base = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        base += f":{parsed.port}"
    return base, project_id, public_key


def send_sentry_event(
    event: dict[str, Any], dsn: str, *, opener: Any = request.urlopen
) -> dict[str, Any]:
    try:
        base, project_id, public_key = _sentry_endpoint_parts(dsn)
        endpoint = f"{base}/api/{project_id}/store/"
        auth = (
            "Sentry sentry_version=7, sentry_client=rhize-benchmark-status/1.0, "
            f"sentry_key={public_key}"
        )
        req = request.Request(
            endpoint,
            data=json.dumps(event, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json", "X-Sentry-Auth": auth},
            method="POST",
        )
        with opener(req, timeout=10) as response:
            payload = json.loads(response.read().decode() or "{}")
        return {"status": "sent", "event_id": payload.get("id", event.get("event_id"))}
    except Exception as error:
        return {"status": "failed", "error": _safe_event_text(error)}


def send_sentry_checkin(
    dsn: str,
    monitor_slug: str,
    *,
    opener: Any = request.urlopen,
) -> dict[str, Any]:
    try:
        base, project_id, public_key = _sentry_endpoint_parts(dsn)
        endpoint = (
            f"{base}"
            f"/api/{project_id}/crons/{parse.quote(monitor_slug, safe='')}/"
            f"{parse.quote(public_key, safe='')}/"
        )
        with opener(request.Request(endpoint, method="GET"), timeout=10) as response:
            response.read()
        return {"status": "sent", "monitor_slug": monitor_slug}
    except Exception as error:
        return {"status": "failed", "error": _safe_event_text(error)}


def resolve_sentry_dsn(service: str = SENTRY_KEYCHAIN_SERVICE) -> str | None:
    configured = os.environ.get("RHIZE_BENCHMARK_SENTRY_DSN")
    if configured:
        return configured.strip() or None
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                getpass.getuser(),
                "-s",
                service,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def dispatch_sentry_alerts(
    snapshot: dict[str, Any], dsn: str | None, *, sender: Any = send_sentry_event
) -> dict[str, Any]:
    findings = actionable_findings(snapshot)
    if not findings:
        return {"status": "not_needed", "findings": 0, "deliveries": []}
    if not dsn:
        return {"status": "not_configured", "findings": len(findings), "deliveries": []}
    release = os.environ.get("RHIZE_BENCHMARK_RELEASE") or os.environ.get("SENTRY_RELEASE")
    deliveries = [
        sender(build_sentry_event(item, snapshot["generated_at"], release), dsn)
        for item in findings
    ]
    status = "sent" if all(item.get("status") == "sent" for item in deliveries) else "failed"
    return {"status": status, "findings": len(findings), "deliveries": deliveries}


def render_human(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    row_missing = [name for name, v in snapshot["liveness"].items() if v["status"] == "row_missing"]

    if row_missing:
        lines.append("!!! ROW_MISSING — capture ran but no row landed !!!")
        for name in row_missing:
            lines.append(f"  - {name}: {snapshot['liveness'][name]['reason']}")
        lines.append("")

    lines.append("Liveness by routine:")
    for name, v in snapshot["liveness"].items():
        lines.append(f"  [{v['status']:>11}] {name} — {v['reason']}")
    lines.append("")

    lines.append("Benchmark notes:")
    for name, s in snapshot["notes"].items():
        if s.get("error"):
            lines.append(f"  - {name}: ERROR — {s['error']}")
            continue
        by_arm = ", ".join(f"{arm}={n}" for arm, n in sorted(s["rows_by_arm"].items())) or "none"
        lines.append(
            f"  - {name}: {s['total_rows']} rows ({by_arm}), newest row {s['newest_row_date'] or 'n/a'}, "
            f"{len(s['columns'])} columns"
        )
        if s.get("malformed_rows"):
            lines.append(f"      malformed rows: {len(s['malformed_rows'])}")

    lines.append("")
    lines.append("Run telemetry (~/.rhize/procedural-memory/runs/*.jsonl):")
    if snapshot["run_telemetry"]["available"]:
        for artifact, counts in sorted(snapshot["run_telemetry"]["artifacts"].items()):
            lines.append(
                f"  - {artifact}: {counts['runs']} runs (ok={counts['ok']}, fail={counts['fail']}), "
                f"newest {counts['newest_started_at']}"
            )
    else:
        lines.append(f"  UNAVAILABLE — {snapshot['run_telemetry']['error']}")

    lines.append("")
    lines.append("Health sidecars:")
    if snapshot["health"]["available"]:
        for artifact, info in sorted(snapshot["health"]["artifacts"].items()):
            lines.append(f"  - {artifact}: {info}")
    else:
        lines.append(f"  UNAVAILABLE — {snapshot['health']['error']}")

    findings = actionable_findings(snapshot)
    lines.append("")
    lines.append(f"Capture eval: {len(findings)} actionable finding(s)")
    if snapshot.get("alerting"):
        lines.append(f"Alerting: {snapshot['alerting']['status']}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print the full JSON snapshot to stdout")
    ap.add_argument("--output", default=str(OUTPUT_PATH), help="where to write the JSON snapshot")
    ap.add_argument(
        "--receipts-dir",
        default=str(BENCHMARK_RECEIPTS_DIR),
        help="timestamped bench-append receipt directory",
    )
    ap.add_argument(
        "--alert-sentry",
        action="store_true",
        help="send actionable capture findings to Sentry using env/Keychain DSN",
    )
    ap.add_argument(
        "--context-runner",
        help="path to the context experiment runner whose capture-health eval should run",
    )
    ap.add_argument(
        "--sentry-checkin-slug",
        nargs="?",
        const=SENTRY_CRON_SLUG,
        default=None,
        help="send an OK check-in only after the watchdog and alert delivery complete",
    )
    args = ap.parse_args(argv)
    if args.sentry_checkin_slug and not args.alert_sentry:
        ap.error("--sentry-checkin-slug requires --alert-sentry")

    snapshot = build_snapshot(
        receipts_dir=Path(args.receipts_dir).expanduser(),
        context_runner=(Path(args.context_runner).expanduser() if args.context_runner else None),
    )
    dsn = resolve_sentry_dsn() if args.alert_sentry or args.sentry_checkin_slug else None
    if args.alert_sentry:
        snapshot["alerting"] = dispatch_sentry_alerts(snapshot, dsn)
    if args.sentry_checkin_slug:
        alert_status = snapshot.get("alerting", {}).get("status", "not_needed")
        if alert_status in {"sent", "not_needed"} and dsn:
            snapshot["watchdog_checkin"] = send_sentry_checkin(
                dsn, args.sentry_checkin_slug
            )
        else:
            snapshot["watchdog_checkin"] = {
                "status": "failed",
                "error": "alert delivery incomplete or Sentry DSN unavailable",
            }

    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(snapshot, indent=2))
    else:
        print(render_human(snapshot))
        print(f"\n→ JSON snapshot written to {output_path}")

    alert_failed = args.alert_sentry and snapshot["alerting"]["status"] in {
        "not_configured",
        "failed",
    }
    checkin_failed = args.sentry_checkin_slug and snapshot["watchdog_checkin"]["status"] != "sent"
    if alert_failed or checkin_failed:
        return 3
    return 2 if actionable_findings(snapshot) else 0


if __name__ == "__main__":
    sys.exit(main())

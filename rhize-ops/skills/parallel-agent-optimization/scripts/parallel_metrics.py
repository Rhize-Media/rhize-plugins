#!/usr/bin/env python3
"""Reserve, finalize, audit, and summarize privacy-safe parallel-routing receipts."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
EVIDENCE_CLASSES = ("observational", "controlled")
VARIANTS = ("baseline", "rhize")
LEGACY_VARIANTS = ("baseline", "ecc", "superpowers", "rhize")
TASK_DECISIONS = {
    "parallel_read": "parallel",
    "disjoint_write": "parallel",
    "shared_state": "sequential",
    "dependency_chain": "sequential",
    "mixed_verification": "parallel",
    "gated_live": "gated",
    "other": None,
}
DECISIONS = ("parallel", "sequential", "gated")
TERMINAL_STATUSES = ("completed", "failed", "incomplete")
AGENT_STATUSES = ("completed", "failed", "cancelled")
UNAVAILABLE_REASONS = ("host_not_exposed", "partial_host_coverage", "not_measured")
TOKEN_KEYS = ("input", "output", "cache_read", "cache_write")
BEGIN_KEYS = {
    "schema_version",
    "evidence_class",
    "variant",
    "task_class",
    "started_at",
    "isolated",
    "live_mutation",
    "one_writer_enforced",
    "comparison_id",
}
FINAL_KEYS = {
    "schema_version",
    "status",
    "completed_at",
    "decision",
    "lanes_planned",
    "agents",
    "tool_calls",
    "tool_calls_unavailable_reason",
    "tokens",
    "tokens_unavailable_reason",
    "verification",
    "collisions",
    "rework_events",
    "correctness_pass",
    "task_graph",
}
AGENT_KEYS = {"started_at", "completed_at", "status"}
VERIFICATION_KEYS = {"required", "completed", "passed"}
TASK_GRAPH_KEYS = (
    "planned",
    "required",
    "required_completed",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
    "blocked_dependency",
    "skipped_optional",
    "cleanup_failed",
    "fan_in_levels",
    "declared_concurrency_cap",
)
DEFAULT_STORE = Path.home() / ".rhize" / "parallel-agent-optimization"
MAX_RECORD_BYTES = 65_536
STALE_AFTER_SECONDS = 24 * 60 * 60
MIN_REPEATS_PER_TASK = 3
READINESS_THRESHOLDS = {
    "minimum_repeats_per_task_variant": MIN_REPEATS_PER_TASK,
    "correctness_pass_rate": 1.0,
    "verification_completeness": 1.0,
    "routing_appropriateness_rate": 1.0,
    "maximum_collisions": 0,
    "maximum_rework_increase_vs_baseline": 0,
    "minimum_parallel_elapsed_improvement": 0.15,
    "minimum_parallel_overlap_rate": 1.0,
    "minimum_agents_for_parallel_rhize_run": 2,
}


class ReceiptError(ValueError):
    """A lifecycle record violates the strict telemetry contract."""


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing={missing}")
        if unknown:
            details.append(f"unknown={unknown}")
        raise ReceiptError(f"{label} keys invalid: {', '.join(details)}")


def require_enum(value: Any, allowed: tuple[str, ...], label: str) -> str:
    if value not in allowed:
        raise ReceiptError(f"{label} must be one of {', '.join(allowed)}")
    return value


def require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReceiptError(f"{label} must be a non-negative integer")
    return value


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ReceiptError(f"{label} must be a boolean")
    return value


def parse_timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ReceiptError(f"{label} must be an ISO 8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReceiptError(f"{label} must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReceiptError(f"{label} must include a timezone offset")
    return parsed


def require_uuid4(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ReceiptError(f"{label} must be a UUIDv4 string")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ReceiptError(f"{label} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ReceiptError(f"{label} must be a canonical lowercase UUIDv4 string")
    return value


def validate_measurement(value: Any, reason: Any, label: str) -> None:
    if value is None:
        require_enum(reason, UNAVAILABLE_REASONS, f"{label}_unavailable_reason")
    else:
        require_int(value, label)
        if reason is not None:
            raise ReceiptError(f"{label}_unavailable_reason must be null when measured")


def interval_metrics(intervals: list[tuple[dt.datetime, dt.datetime]]) -> tuple[bool, int, int]:
    events: list[tuple[dt.datetime, int]] = []
    for started, completed in intervals:
        events.extend(((started, 1), (completed, -1)))
    events.sort(key=lambda item: (item[0], item[1]))
    concurrent_ms = 0.0
    concurrency = 0
    maximum = 0
    previous: dt.datetime | None = None
    for moment, delta in events:
        if previous is not None and concurrency >= 2:
            concurrent_ms += (moment - previous).total_seconds() * 1000
        concurrency += delta
        maximum = max(maximum, concurrency)
        previous = moment
    return maximum >= 2, round(concurrent_ms), maximum


def validate_task_graph(value: Any, status: str) -> dict[str, int] | None:
    if value is None:
        if status == "completed":
            raise ReceiptError("completed status requires task_graph")
        return None
    if not isinstance(value, dict):
        raise ReceiptError("task_graph must be an object or null for a non-completed run")
    require_exact_keys(value, set(TASK_GRAPH_KEYS), "task_graph")
    graph = {key: require_int(value[key], f"task_graph.{key}") for key in TASK_GRAPH_KEYS}
    if graph["declared_concurrency_cap"] == 0:
        raise ReceiptError("task_graph.declared_concurrency_cap must be positive")
    terminal_total = sum(
        graph[key]
        for key in (
            "completed",
            "failed",
            "cancelled",
            "timed_out",
            "blocked_dependency",
            "skipped_optional",
        )
    )
    if terminal_total != graph["planned"]:
        raise ReceiptError("task_graph terminal counts must equal planned")
    if graph["required"] > graph["planned"]:
        raise ReceiptError("task_graph.required cannot exceed planned")
    if graph["required_completed"] > graph["required"]:
        raise ReceiptError("task_graph.required_completed cannot exceed required")
    if graph["required_completed"] > graph["completed"]:
        raise ReceiptError("task_graph.required_completed cannot exceed completed")
    optional_terminal_success = (
        graph["completed"] - graph["required_completed"] + graph["skipped_optional"]
    )
    if optional_terminal_success > graph["planned"] - graph["required"]:
        raise ReceiptError("task_graph optional completions and skips exceed optional nodes")
    return graph


def validate_begin(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ReceiptError("begin input must be a JSON object")
    require_exact_keys(raw, BEGIN_KEYS, "begin input")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ReceiptError(f"schema_version must be {SCHEMA_VERSION}")
    evidence = require_enum(raw["evidence_class"], EVIDENCE_CLASSES, "evidence_class")
    require_enum(raw["variant"], VARIANTS, "variant")
    task_class = require_enum(raw["task_class"], tuple(TASK_DECISIONS), "task_class")
    parse_timestamp(raw["started_at"], "started_at")
    require_bool(raw["isolated"], "isolated")
    require_bool(raw["live_mutation"], "live_mutation")
    require_bool(raw["one_writer_enforced"], "one_writer_enforced")
    if evidence == "controlled":
        require_uuid4(raw["comparison_id"], "comparison_id")
        if task_class == "other":
            raise ReceiptError("controlled evidence requires a deterministic task class")
        if not raw["isolated"] or raw["live_mutation"] or not raw["one_writer_enforced"]:
            raise ReceiptError(
                "controlled begin requires isolated=true, live_mutation=false, "
                "and one_writer_enforced=true"
            )
    elif raw["comparison_id"] is not None:
        raise ReceiptError("observational begin requires comparison_id=null")
    reservation = dict(raw)
    reservation.update(
        {
            "run_id": str(uuid.uuid4()),
            "status": "pending",
            "expected_decision": TASK_DECISIONS[task_class],
            "reserved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    return reservation


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise ReceiptError(f"store path is not a real directory: {path}")
    path.chmod(0o700)


def open_private_file(path: Path, *, readable: bool = False) -> int:
    access = os.O_RDWR if readable else os.O_WRONLY
    flags = access | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    return descriptor


def write_record(descriptor: int, record: dict[str, Any]) -> None:
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(payload) > MAX_RECORD_BYTES:
        raise ReceiptError(f"record exceeds {MAX_RECORD_BYTES} byte limit")
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("append made no progress")
        offset += written
    os.fsync(descriptor)


def append_record(path: Path, record: dict[str, Any]) -> None:
    ensure_private_directory(path.parent)
    descriptor = open_private_file(path)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        write_record(descriptor, record)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink():
        raise ReceiptError(f"refusing symlinked data file: {path}")
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReceiptError(f"invalid JSON in {path.name}:{number}") from exc
        if not isinstance(row, dict):
            raise ReceiptError(f"invalid record in {path.name}:{number}")
        rows.append(row)
    return rows


def parse_comparison_reservations(store: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(store / "comparison-reservations.jsonl")
    parsed = []
    for row in rows:
        version = row.get("schema_version", 1)
        if version == 1:
            if set(row) != {"comparison_id", "created_at", "order"}:
                raise ReceiptError("invalid legacy comparison reservation")
            require_uuid4(row["comparison_id"], "comparison_id")
            if sorted(row["order"]) != sorted(LEGACY_VARIANTS):
                raise ReceiptError("invalid legacy comparison order")
        elif version == 2:
            if set(row) != {"schema_version", "comparison_id", "created_at", "order"}:
                raise ReceiptError("invalid v2 comparison reservation")
            require_uuid4(row["comparison_id"], "comparison_id")
            if sorted(row["order"]) != sorted(VARIANTS):
                raise ReceiptError("invalid v2 comparison order")
        else:
            raise ReceiptError("unsupported comparison reservation schema_version")
        parse_timestamp(row["created_at"], "comparison created_at")
        parsed.append(row)
    return parsed


def new_comparison(store: Path) -> dict[str, Any]:
    ensure_private_directory(store)
    target = store / "comparison-reservations.jsonl"
    descriptor = open_private_file(target, readable=True)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        content = b""
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            content += chunk
        v2_count = 0
        for line in content.decode().splitlines():
            row = json.loads(line)
            if row.get("schema_version", 1) == 2:
                v2_count += 1
        offset = v2_count % len(VARIANTS)
        reservation = {
            "schema_version": 2,
            "comparison_id": str(uuid.uuid4()),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "order": list(VARIANTS[offset:] + VARIANTS[:offset]),
        }
        os.lseek(descriptor, 0, os.SEEK_END)
        write_record(descriptor, reservation)
        return reservation
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def read_run_reservations(store: Path) -> list[dict[str, Any]]:
    return read_jsonl(store / "run-reservations.jsonl")


def begin_run(raw: Any, store: Path) -> dict[str, Any]:
    reservation = validate_begin(raw)
    if reservation["evidence_class"] == "controlled":
        comparisons = {
            row["comparison_id"]: row
            for row in parse_comparison_reservations(store)
            if row.get("schema_version", 1) == 2
        }
        comparison = comparisons.get(reservation["comparison_id"])
        if comparison is None:
            raise ReceiptError("controlled begin requires a v2 comparison reservation")
        if reservation["variant"] not in comparison["order"]:
            raise ReceiptError("variant is not part of the comparison reservation")
    target = store / "run-reservations.jsonl"
    ensure_private_directory(store)
    descriptor = open_private_file(target, readable=True)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        existing = []
        content = b""
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            content += chunk
        for line in content.decode().splitlines():
            existing.append(json.loads(line))
        if reservation["evidence_class"] == "controlled" and any(
            row.get("comparison_id") == reservation["comparison_id"]
            and row.get("variant") == reservation["variant"]
            for row in existing
        ):
            raise ReceiptError("comparison variant is already reserved")
        os.lseek(descriptor, 0, os.SEEK_END)
        write_record(descriptor, reservation)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return reservation


def read_receipt_rows(
    store: Path, evidence: str = "all"
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    selected = EVIDENCE_CLASSES if evidence == "all" else (evidence,)
    current = {name: [] for name in selected}
    legacy = []
    for evidence_class in selected:
        directory = store / evidence_class
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            for row in read_jsonl(path):
                if row.get("evidence_class") != evidence_class:
                    raise ReceiptError(f"evidence class mismatch in {path.name}")
                if row.get("schema_version") == 2:
                    current[evidence_class].append(row)
                elif row.get("schema_version") == 1:
                    legacy.append(row)
                else:
                    raise ReceiptError(f"unsupported receipt schema in {path.name}")
    return current, legacy


def validate_final(raw: Any, reservation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ReceiptError("final input must be a JSON object")
    require_exact_keys(raw, FINAL_KEYS, "final input")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ReceiptError(f"schema_version must be {SCHEMA_VERSION}")
    status = require_enum(raw["status"], TERMINAL_STATUSES, "status")
    started = parse_timestamp(reservation["started_at"], "started_at")
    completed = parse_timestamp(raw["completed_at"], "completed_at")
    if completed < started:
        raise ReceiptError("completed_at must not precede started_at")
    decision = raw["decision"]
    if decision is not None:
        decision = require_enum(decision, DECISIONS, "decision")
    for field in ("lanes_planned", "collisions", "rework_events"):
        if raw[field] is None:
            if status == "completed":
                raise ReceiptError(f"completed status requires {field}")
        else:
            require_int(raw[field], field)
    if raw["correctness_pass"] is not None:
        require_bool(raw["correctness_pass"], "correctness_pass")
    task_graph = validate_task_graph(raw["task_graph"], status)
    if task_graph is not None:
        if raw["lanes_planned"] is not None and raw["lanes_planned"] != task_graph["planned"]:
            raise ReceiptError("lanes_planned must equal task_graph.planned")
        if task_graph["cleanup_failed"] and raw["correctness_pass"] is True:
            raise ReceiptError("cleanup failure cannot claim correctness_pass=true")
        if (
            raw["correctness_pass"] is True
            and task_graph["required_completed"] != task_graph["required"]
        ):
            raise ReceiptError(
                "correctness_pass=true requires every required node completed"
            )

    agents = raw["agents"]
    if agents is None and status == "completed":
        raise ReceiptError("completed status requires agents")
    if agents is not None and not isinstance(agents, list):
        raise ReceiptError("agents must be a list or null for a non-completed run")
    intervals = []
    statuses: Counter[str] = Counter()
    for index, agent in enumerate(agents or []):
        if not isinstance(agent, dict):
            raise ReceiptError(f"agents[{index}] must be an object")
        require_exact_keys(agent, AGENT_KEYS, f"agents[{index}]")
        agent_started = parse_timestamp(agent["started_at"], f"agents[{index}].started_at")
        agent_completed = parse_timestamp(agent["completed_at"], f"agents[{index}].completed_at")
        if agent_completed < agent_started:
            raise ReceiptError(f"agents[{index}] completes before it starts")
        if agent_started < started or agent_completed > completed:
            raise ReceiptError(f"agents[{index}] interval must be inside the run interval")
        agent_status = require_enum(agent["status"], AGENT_STATUSES, f"agents[{index}].status")
        intervals.append((agent_started, agent_completed))
        statuses[agent_status] += 1

    validate_measurement(raw["tool_calls"], raw["tool_calls_unavailable_reason"], "tool_calls")
    tokens = raw["tokens"]
    if not isinstance(tokens, dict):
        raise ReceiptError("tokens must be an object")
    require_exact_keys(tokens, set(TOKEN_KEYS), "tokens")
    missing_tokens = False
    for key in TOKEN_KEYS:
        if tokens[key] is None:
            missing_tokens = True
        else:
            require_int(tokens[key], f"tokens.{key}")
    if missing_tokens:
        require_enum(raw["tokens_unavailable_reason"], UNAVAILABLE_REASONS, "tokens_unavailable_reason")
    elif raw["tokens_unavailable_reason"] is not None:
        raise ReceiptError("tokens_unavailable_reason must be null when all tokens are measured")

    verification = raw["verification"]
    if verification is None:
        if status == "completed":
            raise ReceiptError("completed status requires verification")
        required = completed_checks = passed = None
    else:
        if not isinstance(verification, dict):
            raise ReceiptError("verification must be an object or null for a non-completed run")
        require_exact_keys(verification, VERIFICATION_KEYS, "verification")
        required = require_int(verification["required"], "verification.required")
        completed_checks = require_int(verification["completed"], "verification.completed")
        passed = require_int(verification["passed"], "verification.passed")
        if not 0 <= passed <= completed_checks <= required:
            raise ReceiptError("verification must satisfy 0 <= passed <= completed <= required")
    if status == "completed" and (
        decision is None
        or raw["correctness_pass"] is None
        or required is None
        or required == 0
        or completed_checks != required
    ):
        raise ReceiptError(
            "completed status requires a decision, correctness result, and complete non-empty verification"
        )

    actual_overlap, concurrent_ms, max_concurrency = interval_metrics(intervals)
    if task_graph is not None and max_concurrency > task_graph["declared_concurrency_cap"]:
        raise ReceiptError("observed concurrency exceeds task_graph.declared_concurrency_cap")
    stored = dict(reservation)
    stored.pop("reserved_at", None)
    stored.update(raw)
    stored.update(
        {
            "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "elapsed_ms": round((completed - started).total_seconds() * 1000),
            "actual_overlap": actual_overlap,
            "concurrent_agent_ms": concurrent_ms,
            "max_concurrency": max_concurrency,
            "agent_count": len(agents) if agents is not None else None,
            "agent_status_counts": {name: statuses[name] for name in AGENT_STATUSES},
            "verification_completeness": (
                None if required is None else (1.0 if required == 0 else completed_checks / required)
            ),
            "routing_appropriate": (
                None if decision is None or reservation["expected_decision"] is None
                else decision == reservation["expected_decision"]
            ),
        }
    )
    return stored


def finalize_run(run_id: str, raw: Any, store: Path) -> dict[str, Any]:
    require_uuid4(run_id, "run_id")
    ensure_private_directory(store)
    lock_path = store / ".finalize.lock"
    descriptor = open_private_file(lock_path)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        reservations = [row for row in read_run_reservations(store) if row.get("run_id") == run_id]
        if len(reservations) != 1:
            raise ReceiptError("run_id has no unique reservation")
        current, _ = read_receipt_rows(store, "all")
        if any(row.get("run_id") == run_id for rows in current.values() for row in rows):
            raise ReceiptError("run_id is already finalized")
        stored = validate_final(raw, reservations[0])
        evidence_dir = store / stored["evidence_class"]
        target = evidence_dir / f"{stored['recorded_at'][:7]}.jsonl"
        append_record(target, stored)
        return stored
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def pending_audit(
    store: Path,
    *,
    now: dt.datetime | None = None,
    stale_after_seconds: int = STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    if stale_after_seconds < 0:
        raise ReceiptError("stale_after_seconds must be non-negative")
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ReceiptError("audit now must be timezone-aware")
    current, _ = read_receipt_rows(store, "all")
    terminal_ids = {row.get("run_id") for rows in current.values() for row in rows}
    pending = [row for row in read_run_reservations(store) if row.get("run_id") not in terminal_ids]
    stale = [
        row
        for row in pending
        if (now - parse_timestamp(row["started_at"], "started_at")).total_seconds()
        >= stale_after_seconds
    ]
    return {
        "schema_version": 2,
        "pending_count": len(pending),
        "stale_count": len(stale),
        "stale_after_seconds": stale_after_seconds,
        "stale_run_ids": sorted(row["run_id"] for row in stale),
    }


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def summarize_variant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    measured_tools = [row["tool_calls"] for row in completed if row.get("tool_calls") is not None]
    measured_tokens = [
        sum(row["tokens"].values())
        for row in completed
        if all(value is not None for value in row.get("tokens", {}).values())
    ]
    task_graph_totals = {
        key: sum(row["task_graph"][key] for row in completed) for key in TASK_GRAPH_KEYS
    }
    return {
        "runs": len(completed),
        "correctness_pass_rate": ratio(sum(row["correctness_pass"] for row in completed), len(completed)),
        "routing_appropriate_rate": ratio(sum(row["routing_appropriate"] for row in completed), len(completed)),
        "verification_completeness_mean": (
            statistics.fmean(row["verification_completeness"] for row in completed)
            if completed else None
        ),
        "elapsed_ms_median": statistics.median(row["elapsed_ms"] for row in completed) if completed else None,
        "actual_overlap_runs": sum(bool(row["actual_overlap"]) for row in completed),
        "agent_count_total": sum(row["agent_count"] for row in completed),
        "collisions_total": sum(row["collisions"] for row in completed),
        "rework_events_total": sum(row["rework_events"] for row in completed),
        "tool_calls_measured_runs": len(measured_tools),
        "tokens_measured_runs": len(measured_tokens),
        "task_graph_totals": task_graph_totals,
    }


def complete_comparison_groups(
    rows: list[dict[str, Any]], reservations: list[dict[str, Any]]
) -> tuple[list[list[dict[str, Any]]], dict[str, int]]:
    reservations_by_id = {
        row["comparison_id"]: row for row in reservations if row.get("schema_version", 1) == 2
    }
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("comparison_id"):
            groups[row["comparison_id"]].append(row)
    complete = []
    counts = Counter()
    for comparison_id, group in groups.items():
        reservation = reservations_by_id.get(comparison_id)
        if reservation is None:
            counts["unreserved"] += 1
            continue
        variants = Counter(row.get("variant") for row in group)
        if any(value > 1 for value in variants.values()):
            counts["duplicate"] += 1
            continue
        if variants != Counter({"baseline": 1, "rhize": 1}):
            counts["incomplete"] += 1
            continue
        if any(row.get("task_graph") is None for row in group):
            counts["pre_task_graph_v2"] += 1
            continue
        if any("required_completed" not in row["task_graph"] for row in group):
            counts["pre_required_closure_v2"] += 1
            continue
        if any(row.get("status") != "completed" for row in group):
            counts["noncompleted"] += 1
            continue
        contracts = {
            (row.get("task_class"), row.get("expected_decision"), row.get("verification", {}).get("required"))
            for row in group
        }
        if len(contracts) != 1:
            counts["contract_mismatch"] += 1
            continue
        by_variant = {row["variant"]: row for row in group}
        ordered = [by_variant[variant] for variant in reservation["order"]]
        intervals = [
            (parse_timestamp(row["started_at"], "started_at"), parse_timestamp(row["completed_at"], "completed_at"))
            for row in ordered
        ]
        if not all(intervals[index][1] <= intervals[index + 1][0] for index in range(len(intervals) - 1)):
            counts["order_or_overlap"] += 1
            continue
        complete.append(group)
    counts["total"] = len(groups)
    counts["complete"] = len(complete)
    return complete, dict(counts)


def metric(status: str, actual: Any, threshold: Any) -> dict[str, Any]:
    return {"status": status, "actual": actual, "threshold": threshold}


def build_readiness(groups: list[list[dict[str, Any]]]) -> dict[str, Any]:
    rows = [row for group in groups for row in group]
    by_variant = {variant: [row for row in rows if row["variant"] == variant] for variant in VARIANTS}
    task_counts = {
        task: min(
            sum(row["task_class"] == task for row in by_variant["baseline"]),
            sum(row["task_class"] == task for row in by_variant["rhize"]),
        )
        for task in TASK_DECISIONS
        if task != "other"
    }
    coverage_pass = all(value >= MIN_REPEATS_PER_TASK for value in task_counts.values())
    required: dict[str, dict[str, Any]] = {
        "repeated_task_coverage": metric(
            "pass" if coverage_pass else "fail", task_counts, MIN_REPEATS_PER_TASK
        )
    }
    if not rows:
        for name in (
            "correctness",
            "verification",
            "routing",
            "collisions",
            "rework",
            "elapsed",
            "actual_overlap",
            "agent_count",
        ):
            required[name] = metric("unavailable", None, READINESS_THRESHOLDS)
    else:
        correctness = all(row["correctness_pass"] for row in rows)
        verification = all(row["verification_completeness"] == 1.0 for row in rows)
        routing = all(row["routing_appropriate"] for row in rows)
        collisions = sum(row["collisions"] for row in rows)
        baseline_rework = sum(row["rework_events"] for row in by_variant["baseline"])
        rhize_rework = sum(row["rework_events"] for row in by_variant["rhize"])
        baseline_parallel = [row["elapsed_ms"] for row in by_variant["baseline"] if row["expected_decision"] == "parallel"]
        rhize_parallel = [row["elapsed_ms"] for row in by_variant["rhize"] if row["expected_decision"] == "parallel"]
        improvement = None
        if baseline_parallel and rhize_parallel and statistics.median(baseline_parallel):
            improvement = (
                statistics.median(baseline_parallel) - statistics.median(rhize_parallel)
            ) / statistics.median(baseline_parallel)
        rhize_parallel_rows = [row for row in by_variant["rhize"] if row["expected_decision"] == "parallel"]
        overlap_rate = ratio(sum(row["actual_overlap"] for row in rhize_parallel_rows), len(rhize_parallel_rows))
        agents_ok = bool(rhize_parallel_rows) and all(
            row["agent_count"] >= READINESS_THRESHOLDS["minimum_agents_for_parallel_rhize_run"]
            for row in rhize_parallel_rows
        )
        required.update(
            {
                "correctness": metric("pass" if correctness else "fail", correctness, 1.0),
                "verification": metric("pass" if verification else "fail", verification, 1.0),
                "routing": metric("pass" if routing else "fail", routing, 1.0),
                "collisions": metric("pass" if collisions == 0 else "fail", collisions, 0),
                "rework": metric("pass" if rhize_rework <= baseline_rework else "fail", rhize_rework - baseline_rework, 0),
                "elapsed": metric(
                    "pass" if improvement is not None and improvement >= READINESS_THRESHOLDS["minimum_parallel_elapsed_improvement"] else "fail",
                    improvement,
                    READINESS_THRESHOLDS["minimum_parallel_elapsed_improvement"],
                ),
                "actual_overlap": metric(
                    "pass" if overlap_rate is not None and overlap_rate >= READINESS_THRESHOLDS["minimum_parallel_overlap_rate"] else "fail",
                    overlap_rate,
                    READINESS_THRESHOLDS["minimum_parallel_overlap_rate"],
                ),
                "agent_count": metric(
                    "pass" if agents_ok else "fail",
                    [row["agent_count"] for row in rhize_parallel_rows],
                    READINESS_THRESHOLDS["minimum_agents_for_parallel_rhize_run"],
                ),
            }
        )
    optional = {}
    for name, measured_key in (("tool_calls", "tool_calls"), ("tokens", "tokens")):
        if name == "tool_calls":
            measured = sum(row.get(measured_key) is not None for row in rows)
        else:
            measured = sum(all(value is not None for value in row.get("tokens", {}).values()) for row in rows)
        optional[name] = {
            "status": "unavailable" if measured == 0 else ("measured" if measured == len(rows) else "partial"),
            "measured_runs": measured,
            "total_runs": len(rows),
            "required_for_decision": False,
        }
    if not coverage_pass:
        decision = "insufficient_evidence"
    else:
        decision = "ready" if all(item["status"] == "pass" for item in required.values()) else "not_ready"
    return {
        "decision": decision,
        "thresholds": READINESS_THRESHOLDS,
        "required_metrics": required,
        "optional_metrics": optional,
    }


def build_report(store: Path, evidence: str) -> dict[str, Any]:
    receipts, legacy = read_receipt_rows(store, evidence)
    report: dict[str, Any] = {
        "schema_version": 2,
        "evidence": {},
        "legacy_v1": {
            "stored_runs": len(legacy),
            "variants": dict(sorted(Counter(row.get("variant") for row in legacy).items())),
            "comparable_with_v2": False,
            "classification": "legacy_screening_only",
        },
    }
    complete_groups: list[list[dict[str, Any]]] = []
    for evidence_class, rows in receipts.items():
        analyzed = [
            row
            for row in rows
            if row.get("status") == "completed"
            and row.get("task_graph") is not None
            and "required_completed" in row["task_graph"]
        ]
        comparison_counts = None
        if evidence_class == "controlled":
            complete_groups, comparison_counts = complete_comparison_groups(
                rows, parse_comparison_reservations(store)
            )
            analyzed = [row for group in complete_groups for row in group]
        by_variant = {variant: [row for row in analyzed if row.get("variant") == variant] for variant in VARIANTS}
        section = {
            "stored_runs": len(rows),
            "analyzed_runs": len(analyzed),
            "pre_task_graph_v2_runs": sum(row.get("task_graph") is None for row in rows),
            "pre_required_closure_v2_runs": sum(
                row.get("task_graph") is not None
                and "required_completed" not in row["task_graph"]
                for row in rows
            ),
            "terminal_status_counts": {
                status: sum(row.get("status") == status for row in rows) for status in TERMINAL_STATUSES
            },
            "variants": {variant: summarize_variant(by_variant[variant]) for variant in VARIANTS},
        }
        if comparison_counts is not None:
            section["comparisons"] = comparison_counts
        report["evidence"][evidence_class] = section
    report["pending_audit"] = pending_audit(store)
    report["decision_readiness"] = build_readiness(complete_groups)
    return report


def format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Parallel-routing evidence", ""]
    for evidence_class in EVIDENCE_CLASSES:
        section = report["evidence"].get(evidence_class)
        if section is None:
            continue
        lines.extend(
            [
                f"## {evidence_class.title()}",
                "",
                f"Stored terminal receipts: {section['stored_runs']}; analyzed completed runs: {section['analyzed_runs']}",
                f"Pre-task-graph v2 receipts retained but excluded: {section['pre_task_graph_v2_runs']}",
                f"Pre-required-closure v2 receipts retained but excluded: {section['pre_required_closure_v2_runs']}",
                "",
                "| Variant | Runs | Correctness | Routing | Verification | Median ms | Overlap | Agents | Collisions | Rework | Tools | Tokens |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for variant in VARIANTS:
            data = section["variants"][variant]
            lines.append(
                f"| {variant} | {data['runs']} | {format_rate(data['correctness_pass_rate'])} | "
                f"{format_rate(data['routing_appropriate_rate'])} | {format_rate(data['verification_completeness_mean'])} | "
                f"{data['elapsed_ms_median'] or 'n/a'} | {data['actual_overlap_runs']} | {data['agent_count_total']} | "
                f"{data['collisions_total']} | {data['rework_events_total']} | "
                f"{data['tool_calls_measured_runs']}/{data['runs']} | {data['tokens_measured_runs']}/{data['runs']} |"
            )
        lines.append("")
    readiness = report["decision_readiness"]
    lines.extend(
        [
            "## Decision readiness",
            "",
            f"Decision: **{readiness['decision']}**. Token and tool coverage are optional and remain visible below.",
            "",
            f"Pending reservations: {report['pending_audit']['pending_count']}; stale: {report['pending_audit']['stale_count']}.",
            f"Legacy v1 screening receipts: {report['legacy_v1']['stored_runs']} (not comparable with v2).",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("new-comparison")
    begin_parser = subparsers.add_parser("begin")
    begin_parser.add_argument("--input", type=Path, required=True)
    final_parser = subparsers.add_parser("finalize")
    final_parser.add_argument("--run-id", required=True)
    final_parser.add_argument("--input", type=Path, required=True)
    audit_parser = subparsers.add_parser("audit-pending")
    audit_parser.add_argument("--stale-after-seconds", type=int, default=STALE_AFTER_SECONDS)
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--evidence", choices=("all",) + EVIDENCE_CLASSES, default="all")
    report_parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "new-comparison":
            result = new_comparison(args.store)
        elif args.command == "begin":
            result = begin_run(json.loads(args.input.read_text(encoding="utf-8")), args.store)
        elif args.command == "finalize":
            result = finalize_run(
                args.run_id, json.loads(args.input.read_text(encoding="utf-8")), args.store
            )
        elif args.command == "audit-pending":
            result = pending_audit(args.store, stale_after_seconds=args.stale_after_seconds)
        else:
            result = build_report(args.store, args.evidence)
            if args.format == "markdown":
                print(render_markdown(result), end="")
                return 0
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ReceiptError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

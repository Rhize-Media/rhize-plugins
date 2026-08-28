#!/usr/bin/env python3
"""Append and summarize privacy-safe parallel-agent optimization receipts."""

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


SCHEMA_VERSION = 1
EVIDENCE_CLASSES = ("observational", "controlled")
VARIANTS = ("baseline", "ecc", "superpowers", "rhize")
RESOURCES = ("none", "ecc", "superpowers")
TASK_CLASSES = (
    "parallel_read",
    "disjoint_write",
    "shared_state",
    "dependency_chain",
    "mixed_verification",
    "gated_live",
    "other",
)
DECISIONS = ("parallel", "sequential", "gated")
AGENT_STATUSES = ("completed", "failed", "cancelled")
UNAVAILABLE_REASONS = ("host_not_exposed", "partial_host_coverage", "not_measured")
TOKEN_KEYS = ("input", "output", "cache_read", "cache_write")
INPUT_KEYS = {
    "schema_version",
    "evidence_class",
    "variant",
    "resource_used",
    "task_class",
    "started_at",
    "completed_at",
    "decision",
    "expected_decision",
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
    "isolated",
    "live_mutation",
    "one_writer_enforced",
    "comparison_id",
}
AGENT_KEYS = {"started_at", "completed_at", "status"}
VERIFICATION_KEYS = {"required", "completed", "passed"}
DEFAULT_STORE = Path.home() / ".rhize" / "parallel-agent-optimization"
MAX_RECEIPT_BYTES = 65_536


class ReceiptError(ValueError):
    """A receipt violates the strict telemetry contract."""


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
    events.sort(key=lambda item: (item[0], item[1]))  # End before start at equal timestamps.
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


def validate_receipt(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ReceiptError("receipt must be a JSON object")
    require_exact_keys(raw, INPUT_KEYS, "receipt")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ReceiptError(f"schema_version must be {SCHEMA_VERSION}")

    evidence_class = require_enum(raw["evidence_class"], EVIDENCE_CLASSES, "evidence_class")
    variant = require_enum(raw["variant"], VARIANTS, "variant")
    resource = require_enum(raw["resource_used"], RESOURCES, "resource_used")
    require_enum(raw["task_class"], TASK_CLASSES, "task_class")
    decision = require_enum(raw["decision"], DECISIONS, "decision")
    expected = raw["expected_decision"]
    if expected is not None:
        expected = require_enum(expected, DECISIONS, "expected_decision")

    allowed_resources = {
        "baseline": {"none"},
        "ecc": {"ecc", "none"},
        "superpowers": {"superpowers", "none"},
        "rhize": set(RESOURCES),
    }
    if resource not in allowed_resources[variant]:
        raise ReceiptError(f"variant {variant} cannot use resource {resource}")
    if evidence_class == "controlled" and variant in {"ecc", "superpowers"} and resource != variant:
        raise ReceiptError(f"controlled variant {variant} requires resource {variant}")

    started = parse_timestamp(raw["started_at"], "started_at")
    completed = parse_timestamp(raw["completed_at"], "completed_at")
    if completed < started:
        raise ReceiptError("completed_at must not precede started_at")

    require_int(raw["lanes_planned"], "lanes_planned")
    require_int(raw["collisions"], "collisions")
    require_int(raw["rework_events"], "rework_events")
    require_bool(raw["isolated"], "isolated")
    require_bool(raw["live_mutation"], "live_mutation")
    require_bool(raw["one_writer_enforced"], "one_writer_enforced")
    if raw["correctness_pass"] is not None:
        require_bool(raw["correctness_pass"], "correctness_pass")

    agents = raw["agents"]
    if not isinstance(agents, list):
        raise ReceiptError("agents must be a list")
    intervals = []
    statuses: Counter[str] = Counter()
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            raise ReceiptError(f"agents[{index}] must be an object")
        require_exact_keys(agent, AGENT_KEYS, f"agents[{index}]")
        agent_started = parse_timestamp(agent["started_at"], f"agents[{index}].started_at")
        agent_completed = parse_timestamp(agent["completed_at"], f"agents[{index}].completed_at")
        if agent_completed < agent_started:
            raise ReceiptError(f"agents[{index}] completes before it starts")
        if agent_started < started or agent_completed > completed:
            raise ReceiptError(f"agents[{index}] interval must be inside the run interval")
        status = require_enum(agent["status"], AGENT_STATUSES, f"agents[{index}].status")
        intervals.append((agent_started, agent_completed))
        statuses[status] += 1

    validate_measurement(raw["tool_calls"], raw["tool_calls_unavailable_reason"], "tool_calls")
    tokens = raw["tokens"]
    if not isinstance(tokens, dict):
        raise ReceiptError("tokens must be an object")
    require_exact_keys(tokens, set(TOKEN_KEYS), "tokens")
    missing_tokens = False
    for key in TOKEN_KEYS:
        value = tokens[key]
        if value is None:
            missing_tokens = True
        else:
            require_int(value, f"tokens.{key}")
    if missing_tokens:
        require_enum(raw["tokens_unavailable_reason"], UNAVAILABLE_REASONS, "tokens_unavailable_reason")
    elif raw["tokens_unavailable_reason"] is not None:
        raise ReceiptError("tokens_unavailable_reason must be null when all token fields are measured")

    verification = raw["verification"]
    if not isinstance(verification, dict):
        raise ReceiptError("verification must be an object")
    require_exact_keys(verification, VERIFICATION_KEYS, "verification")
    required = require_int(verification["required"], "verification.required")
    completed_checks = require_int(verification["completed"], "verification.completed")
    passed = require_int(verification["passed"], "verification.passed")
    if not 0 <= passed <= completed_checks <= required:
        raise ReceiptError("verification must satisfy 0 <= passed <= completed <= required")

    comparison_id = raw["comparison_id"]
    if evidence_class == "controlled":
        require_uuid4(comparison_id, "comparison_id")
        if (
            raw["isolated"] is not True
            or raw["live_mutation"] is not False
            or raw["one_writer_enforced"] is not True
        ):
            raise ReceiptError(
                "controlled receipts require isolated=true, live_mutation=false, "
                "and one_writer_enforced=true"
            )
        if expected is None:
            raise ReceiptError("controlled receipts require expected_decision")
        if raw["correctness_pass"] is None:
            raise ReceiptError("controlled receipts require correctness_pass")
        if required == 0:
            raise ReceiptError("controlled receipts require at least one verification check")
    elif comparison_id is not None:
        raise ReceiptError("observational receipts require comparison_id=null")

    actual_overlap, concurrent_ms, max_concurrency = interval_metrics(intervals)
    elapsed_ms = round((completed - started).total_seconds() * 1000)
    verification_completeness = 1.0 if required == 0 else completed_checks / required
    routing_appropriate = None if expected is None else decision == expected

    stored = dict(raw)
    stored.update(
        {
            "run_id": str(uuid.uuid4()),
            "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "elapsed_ms": elapsed_ms,
            "actual_overlap": actual_overlap,
            "concurrent_agent_ms": concurrent_ms,
            "max_concurrency": max_concurrency,
            "agent_count": len(agents),
            "agent_status_counts": {status: statuses[status] for status in AGENT_STATUSES},
            "verification_completeness": verification_completeness,
            "routing_appropriate": routing_appropriate,
        }
    )
    return stored


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


def write_all_locked(descriptor: int, payload: bytes) -> None:
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ReceiptError(f"record exceeds {MAX_RECEIPT_BYTES} byte limit")
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("append made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


def append_receipt(receipt: dict[str, Any], store: Path) -> Path:
    ensure_private_directory(store)
    evidence_dir = store / receipt["evidence_class"]
    ensure_private_directory(evidence_dir)
    month = receipt["recorded_at"][:7]
    target = evidence_dir / f"{month}.jsonl"
    descriptor = open_private_file(target)
    try:
        payload = json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
        write_all_locked(descriptor, payload.encode("utf-8"))
    finally:
        os.close(descriptor)
    return target


def read_receipts(store: Path, evidence: str = "all") -> dict[str, list[dict[str, Any]]]:
    selected = EVIDENCE_CLASSES if evidence == "all" else (evidence,)
    rows: dict[str, list[dict[str, Any]]] = {name: [] for name in selected}
    for evidence_class in selected:
        directory = store / evidence_class
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            if path.is_symlink():
                raise ReceiptError(f"refusing symlinked receipt file: {path}")
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ReceiptError(f"invalid JSON in {path.name}:{line_number}") from exc
                if row.get("evidence_class") != evidence_class:
                    raise ReceiptError(f"evidence class mismatch in {path.name}:{line_number}")
                rows[evidence_class].append(row)
    return rows


def choose_observational_variant(store: Path) -> dict[str, Any]:
    rows = read_receipts(store, "observational")["observational"]
    counts = Counter(row.get("variant") for row in rows if row.get("variant") in VARIANTS)
    variant = min(VARIANTS, key=lambda item: (counts[item], VARIANTS.index(item)))
    return {"variant": variant, "counts": {item: counts[item] for item in VARIANTS}}


def parse_reservations(content: bytes) -> list[dict[str, Any]]:
    reservations = []
    for line_number, line in enumerate(content.decode("utf-8").splitlines(), 1):
        try:
            reservation = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReceiptError(f"invalid reservation JSON at line {line_number}") from exc
        if set(reservation) != {"comparison_id", "created_at", "order"}:
            raise ReceiptError(f"invalid reservation keys at line {line_number}")
        require_uuid4(reservation["comparison_id"], "reservation comparison_id")
        if sorted(reservation["order"]) != sorted(VARIANTS):
            raise ReceiptError(f"invalid reservation order at line {line_number}")
        parse_timestamp(reservation["created_at"], "reservation created_at")
        reservations.append(reservation)
    return reservations


def read_reservations(store: Path) -> list[dict[str, Any]]:
    target = store / "comparison-reservations.jsonl"
    if not target.exists():
        return []
    if target.is_symlink():
        raise ReceiptError(f"refusing symlinked reservation file: {target}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(target, flags)
    fcntl.flock(descriptor, fcntl.LOCK_SH)
    try:
        chunks = []
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            chunks.append(chunk)
        return parse_reservations(b"".join(chunks))
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def new_comparison(store: Path) -> dict[str, Any]:
    ensure_private_directory(store)
    target = store / "comparison-reservations.jsonl"
    descriptor = open_private_file(target, readable=True)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        existing = b""
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            existing += chunk
        reservations = parse_reservations(existing)

        offset = len(reservations) % len(VARIANTS)
        reservation = {
            "comparison_id": str(uuid.uuid4()),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "order": list(VARIANTS[offset:] + VARIANTS[:offset]),
        }
        payload = (json.dumps(reservation, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        if len(payload) > MAX_RECEIPT_BYTES:
            raise ReceiptError(f"reservation exceeds {MAX_RECEIPT_BYTES} byte limit")
        os.lseek(descriptor, 0, os.SEEK_END)
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("reservation append made no progress")
            written += count
        os.fsync(descriptor)
        return reservation
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def summarize_variant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    known_correctness = [row["correctness_pass"] for row in rows if row.get("correctness_pass") is not None]
    known_routing = [row["routing_appropriate"] for row in rows if row.get("routing_appropriate") is not None]
    measured_tools = [row["tool_calls"] for row in rows if row.get("tool_calls") is not None]
    measured_tokens = [
        sum(row["tokens"].values())
        for row in rows
        if isinstance(row.get("tokens"), dict) and all(value is not None for value in row["tokens"].values())
    ]
    return {
        "runs": len(rows),
        "correctness_known": len(known_correctness),
        "correctness_pass_rate": ratio(sum(known_correctness), len(known_correctness)),
        "routing_known": len(known_routing),
        "routing_appropriate_rate": ratio(sum(known_routing), len(known_routing)),
        "verification_completeness_mean": statistics.fmean(row["verification_completeness"] for row in rows) if rows else None,
        "elapsed_ms_median": statistics.median(row["elapsed_ms"] for row in rows) if rows else None,
        "actual_overlap_runs": sum(bool(row["actual_overlap"]) for row in rows),
        "agent_count_total": sum(row["agent_count"] for row in rows),
        "collisions_total": sum(row["collisions"] for row in rows),
        "rework_events_total": sum(row["rework_events"] for row in rows),
        "tool_calls_measured_runs": len(measured_tools),
        "tool_calls_total_measured": sum(measured_tools),
        "tokens_measured_runs": len(measured_tokens),
        "tokens_total_measured": sum(measured_tokens),
    }


def build_report(store: Path, evidence: str) -> dict[str, Any]:
    receipts = read_receipts(store, evidence)
    report: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "evidence": {}}
    for evidence_class, rows in receipts.items():
        stored_rows = rows
        comparison_fields: dict[str, Any] = {}
        if evidence_class == "controlled":
            groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                if row.get("comparison_id"):
                    groups[row["comparison_id"]].append(row)
            complete_groups = []
            incomplete_groups = 0
            duplicate_groups = 0
            invalid_groups = 0
            unreserved_groups = 0
            reservations_by_id = {
                reservation["comparison_id"]: reservation
                for reservation in read_reservations(store)
            }
            expected_counts = Counter({variant: 1 for variant in VARIANTS})
            for comparison_id, group_rows in groups.items():
                counts = Counter(row.get("variant") for row in group_rows)
                if comparison_id not in reservations_by_id:
                    unreserved_groups += 1
                elif any(count > 1 for count in counts.values()):
                    duplicate_groups += 1
                elif counts != expected_counts:
                    incomplete_groups += 1
                else:
                    contracts = {
                        (
                            row.get("task_class"),
                            row.get("expected_decision"),
                            row.get("verification", {}).get("required"),
                        )
                        for row in group_rows
                    }
                    if len(contracts) != 1:
                        invalid_groups += 1
                    else:
                        by_group_variant = {row["variant"]: row for row in group_rows}
                        ordered_rows = [
                            by_group_variant[variant]
                            for variant in reservations_by_id[comparison_id]["order"]
                        ]
                        intervals = [
                            (
                                parse_timestamp(row["started_at"], "controlled started_at"),
                                parse_timestamp(row["completed_at"], "controlled completed_at"),
                            )
                            for row in ordered_rows
                        ]
                        sequential = all(
                            intervals[index][1] <= intervals[index + 1][0]
                            for index in range(len(intervals) - 1)
                        )
                        if not sequential:
                            invalid_groups += 1
                        else:
                            complete_groups.append(group_rows)
            rows = [row for group_rows in complete_groups for row in group_rows]
            comparison_fields = {
                "comparison_count": len(groups),
                "complete_comparison_count": len(complete_groups),
                "incomplete_comparison_count": incomplete_groups,
                "duplicate_comparison_count": duplicate_groups,
                "invalid_comparison_count": invalid_groups,
                "unreserved_comparison_count": unreserved_groups,
                "excluded_receipt_count": len(stored_rows) - len(rows),
            }
        by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("variant") in VARIANTS:
                by_variant[row["variant"]].append(row)
        section: dict[str, Any] = {
            "runs": len(rows),
            "stored_runs": len(stored_rows),
            "variants": {variant: summarize_variant(by_variant[variant]) for variant in VARIANTS},
        }
        section.update(comparison_fields)
        report["evidence"][evidence_class] = section
    return report


def format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def format_number(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    return str(round(value, 2))


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Parallel-agent optimization evidence", ""]
    for evidence_class in EVIDENCE_CLASSES:
        section = report["evidence"].get(evidence_class)
        if section is None:
            continue
        lines.extend(
            (
                f"## {evidence_class.title()}",
                "",
                f"Stored receipts: {section['stored_runs']}; analyzed runs: {section['runs']}",
            )
        )
        if evidence_class == "controlled":
            lines.append(
                f"Comparisons: {section['comparison_count']} total; "
                f"{section['complete_comparison_count']} complete; "
                f"{section['incomplete_comparison_count']} incomplete; "
                f"{section['duplicate_comparison_count']} duplicate-arm; "
                f"{section['invalid_comparison_count']} contract-mismatch; "
                f"{section['unreserved_comparison_count']} unreserved; "
                f"{section['excluded_receipt_count']} receipts excluded from metrics"
            )
        lines.extend(
            (
                "",
                "| Variant | Runs | Correctness | Routing | Verification | Median ms | Overlap | Agents | Collisions | Rework | Tools measured | Tokens measured |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            )
        )
        for variant in VARIANTS:
            metrics = section["variants"][variant]
            lines.append(
                "| " + " | ".join(
                    (
                        variant,
                        str(metrics["runs"]),
                        format_rate(metrics["correctness_pass_rate"]),
                        format_rate(metrics["routing_appropriate_rate"]),
                        format_rate(metrics["verification_completeness_mean"]),
                        format_number(metrics["elapsed_ms_median"]),
                        str(metrics["actual_overlap_runs"]),
                        str(metrics["agent_count_total"]),
                        str(metrics["collisions_total"]),
                        str(metrics["rework_events_total"]),
                        f"{metrics['tool_calls_measured_runs']}/{metrics['runs']}",
                        f"{metrics['tokens_measured_runs']}/{metrics['runs']}",
                    )
                ) + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("assign")
    subparsers.add_parser("new-comparison")
    append_parser = subparsers.add_parser("append")
    append_parser.add_argument("--input", type=Path, required=True)
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--evidence", choices=("all",) + EVIDENCE_CLASSES, default="all")
    report_parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "assign":
            print(json.dumps(choose_observational_variant(args.store), sort_keys=True))
        elif args.command == "new-comparison":
            print(json.dumps(new_comparison(args.store), sort_keys=True))
        elif args.command == "append":
            raw = json.loads(args.input.read_text(encoding="utf-8"))
            receipt = validate_receipt(raw)
            append_receipt(receipt, args.store)
            print(json.dumps(receipt, sort_keys=True))
        else:
            report = build_report(args.store, args.evidence)
            if args.format == "json":
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(render_markdown(report), end="")
    except (OSError, json.JSONDecodeError, ReceiptError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

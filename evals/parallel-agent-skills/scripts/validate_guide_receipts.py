#!/usr/bin/env python3
"""Validate isolated guide receipts and compare each guide to the same baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("baseline", "superpowers", "rhize")
REASONS = {"host_not_exposed", "partial_host_coverage", "not_measured"}
RESERVATION_FIELDS = {
    "schema_version", "comparison_id", "task_id", "task_class", "repetition", "status",
    "started_at", "order", "guide_sha256", "isolated", "live_mutation",
    "feeds_rhize_v2_readiness",
}
CONTEXT_FIELDS = {
    "schema_version", "run_id", "comparison_id", "variant", "guide_sha256", "task_id",
    "task_class", "repetition", "order_position", "expected_decision", "isolated",
    "live_mutation", "feeds_rhize_v2_readiness",
}


def timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def nonnegative(value: Any, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def validate_reservation(
    reservation: dict[str, Any],
    tasks: dict[str, dict[str, Any]],
    order_by_repetition: dict[str, list[str]],
) -> list[str]:
    errors: list[str] = []
    if set(reservation) != RESERVATION_FIELDS:
        errors.append("fields")
    if reservation.get("schema_version") != "rhize-guide-comparison-reservation-v1":
        errors.append("schema_version")
    try:
        if str(uuid.UUID(reservation["comparison_id"])) != reservation["comparison_id"].lower():
            errors.append("comparison_id")
    except (KeyError, ValueError, AttributeError):
        errors.append("comparison_id")
    task = tasks.get(reservation.get("task_id"))
    if task is None:
        errors.append("task_id")
    elif reservation.get("task_class") != task["task_class"]:
        errors.append("task_class")
    repetition = reservation.get("repetition")
    expected_order = order_by_repetition.get(str(repetition))
    if expected_order is None:
        errors.append("repetition")
    elif reservation.get("order") != expected_order:
        errors.append("order")
    guide_hashes = reservation.get("guide_sha256")
    if not isinstance(guide_hashes, dict) or set(guide_hashes) != set(VARIANTS):
        errors.append("guide_sha256")
    else:
        if guide_hashes.get("baseline") is not None:
            errors.append("guide_sha256")
        for variant in ("superpowers", "rhize"):
            value = guide_hashes.get(variant)
            if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                errors.append("guide_sha256")
    if reservation.get("isolated") is not True:
        errors.append("isolated")
    if reservation.get("live_mutation") is not False:
        errors.append("live_mutation")
    if reservation.get("feeds_rhize_v2_readiness") is not False:
        errors.append("feeds_rhize_v2_readiness")
    return sorted(set(errors))


def validate_context(
    context: dict[str, Any], reservation: dict[str, Any], task: dict[str, Any] | None
) -> list[str]:
    errors: list[str] = []
    if set(context) != CONTEXT_FIELDS:
        errors.append("fields")
    if context.get("schema_version") != "rhize-guide-comparison-context-v1":
        errors.append("schema_version")
    try:
        if str(uuid.UUID(context["run_id"])) != context["run_id"].lower():
            errors.append("run_id")
    except (KeyError, ValueError, AttributeError):
        errors.append("run_id")
    for key in ("comparison_id", "task_id", "task_class", "repetition", "isolated", "live_mutation", "feeds_rhize_v2_readiness"):
        if context.get(key) != reservation.get(key):
            errors.append(key)
    variant = context.get("variant")
    position = context.get("order_position")
    order = reservation.get("order")
    if variant not in VARIANTS:
        errors.append("variant")
    if not isinstance(position, int) or isinstance(position, bool) or not 1 <= position <= len(VARIANTS):
        errors.append("order_position")
    elif not isinstance(order, list) or len(order) < position or order[position - 1] != variant:
        errors.append("order")
    guide_hashes = reservation.get("guide_sha256")
    expected_hash = guide_hashes.get(variant) if isinstance(guide_hashes, dict) else None
    if context.get("guide_sha256") != expected_hash:
        errors.append("guide_sha256")
    if task is None or context.get("expected_decision") != task.get("expected_decision"):
        errors.append("expected_decision")
    if context.get("isolated") is not True:
        errors.append("isolated")
    if context.get("live_mutation") is not False:
        errors.append("live_mutation")
    if context.get("feeds_rhize_v2_readiness") is not False:
        errors.append("feeds_rhize_v2_readiness")
    return sorted(set(errors))


def validate_receipt(receipt: dict[str, Any], context: dict[str, Any], allowed_fields: set[str]) -> list[str]:
    errors: list[str] = []
    if set(receipt) != allowed_fields:
        errors.append("fields")
    for key in ("run_id", "comparison_id", "variant", "guide_sha256", "task_id", "task_class", "repetition", "order_position", "expected_decision"):
        if receipt.get(key) != context.get(key):
            errors.append(key)
    if receipt.get("schema_version") != "rhize-guide-comparison-v1":
        errors.append("schema_version")
    for key in ("run_id", "comparison_id"):
        try:
            if str(uuid.UUID(receipt[key])) != receipt[key].lower():
                errors.append(key)
        except (KeyError, ValueError, AttributeError):
            errors.append(key)
    try:
        started = timestamp(receipt.get("started_at"))
        completed = timestamp(receipt.get("completed_at"))
        if completed < started:
            errors.append("completed_at")
    except (ValueError, TypeError):
        errors.append("timestamps")
    status = receipt.get("status")
    if status not in {"completed", "failed", "incomplete"}:
        errors.append("status")
    if receipt.get("decision") not in {"parallel", "sequential", "gated", None}:
        errors.append("decision")

    correctness = receipt.get("correctness", {})
    routing = receipt.get("routing", {})
    tokens = receipt.get("tokens", {})
    if set(correctness) != {"passed", "total", "accuracy"}:
        errors.append("correctness")
    if set(routing) != {"true_positives", "false_positives", "false_negatives", "precision", "recall"}:
        errors.append("routing")
    if set(tokens) != {"input", "output", "cache_read", "cache_write"}:
        errors.append("tokens")
    for key in ("latency_ms", "follow_up_reads", "corrections", "rework_events", "failures", "refusals", "collisions"):
        if not nonnegative(receipt.get(key), nullable=status != "completed"):
            errors.append(key)
    if not nonnegative(receipt.get("tool_calls"), nullable=True):
        errors.append("tool_calls")
    for key in ("input", "output", "cache_read", "cache_write"):
        if not nonnegative(tokens.get(key), nullable=True):
            errors.append(f"tokens.{key}")
    token_missing = any(tokens.get(key) is None for key in ("input", "output", "cache_read", "cache_write"))
    if token_missing != (receipt.get("tokens_unavailable_reason") in REASONS):
        errors.append("tokens_unavailable_reason")
    if (receipt.get("tool_calls") is None) != (receipt.get("tool_calls_unavailable_reason") in REASONS):
        errors.append("tool_calls_unavailable_reason")

    if status == "completed":
        passed, total, accuracy = correctness.get("passed"), correctness.get("total"), correctness.get("accuracy")
        if not nonnegative(passed) or not isinstance(total, int) or total <= 0 or passed > total or not isinstance(accuracy, (int, float)) or not math.isclose(accuracy, passed / total):
            errors.append("correctness_values")
        tp, fp, fn = routing.get("true_positives"), routing.get("false_positives"), routing.get("false_negatives")
        if not all(nonnegative(value) for value in (tp, fp, fn)):
            errors.append("routing_counts")
        else:
            precision, recall = routing.get("precision"), routing.get("recall")
            if not isinstance(precision, (int, float)) or not isinstance(recall, (int, float)) or not math.isclose(precision, ratio(tp, tp + fp)) or not math.isclose(recall, ratio(tp, tp + fn)):
                errors.append("routing_values")
        if receipt.get("decision") is None or receipt.get("agents") is None:
            errors.append("completed_fields")
        if receipt.get("decision") != receipt.get("expected_decision"):
            errors.append("decision_expected")
    agents = receipt.get("agents")
    if agents is not None:
        if not isinstance(agents, list):
            errors.append("agents")
        else:
            for agent in agents:
                if set(agent) != {"started_at", "completed_at", "status"} or agent.get("status") not in {"completed", "failed", "cancelled"}:
                    errors.append("agent")
                    continue
                try:
                    agent_started = timestamp(agent["started_at"])
                    agent_completed = timestamp(agent["completed_at"])
                    if agent_completed < agent_started:
                        errors.append("agent_interval")
                    receipt_started = timestamp(receipt.get("started_at"))
                    receipt_completed = timestamp(receipt.get("completed_at"))
                    if agent_started < receipt_started or agent_completed > receipt_completed:
                        errors.append("agent_bounds")
                except (ValueError, TypeError):
                    errors.append("agent_interval")
    return sorted(set(errors))


def overlap_metrics(agents: list[dict[str, Any]]) -> dict[str, int | bool]:
    events: dict[datetime, int] = defaultdict(int)
    for agent in agents:
        events[timestamp(agent["started_at"])] += 1
        events[timestamp(agent["completed_at"])] -= 1
    active = 0
    maximum = 0
    concurrent_ms = 0.0
    previous: datetime | None = None
    for moment in sorted(events):
        if previous is not None and active >= 2:
            concurrent_ms += (moment - previous).total_seconds() * 1000
        active += events[moment]
        maximum = max(maximum, active)
        previous = moment
    rounded = round(concurrent_ms)
    return {
        "actual_overlap": rounded > 0,
        "concurrent_agent_milliseconds": rounded,
        "maximum_concurrency": maximum,
        "agent_count": len(agents),
    }


def load_groups(root: Path, require_complete_cohort: bool) -> tuple[list[dict[str, Any]], list[str]]:
    schema = json.loads((ROOT / "guide-comparison-receipt.schema.json").read_text())
    allowed_fields = set(schema["properties"])
    comparison_manifest = json.loads((ROOT / "guide-comparison.manifest.json").read_text())
    fixture_manifest = json.loads((ROOT / comparison_manifest["fixture_manifest"]).read_text())
    tasks = {item["id"]: item for item in fixture_manifest["tasks"]}
    order_by_repetition = comparison_manifest["order_by_repetition"]
    groups = sorted(root.rglob("GROUP_RESERVATION.json"))
    if not groups:
        raise ValueError("no guide comparison reservations found")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    cells: set[tuple[str, int]] = set()
    for reservation_path in groups:
        group_dir = reservation_path.parent
        reservation = json.loads(reservation_path.read_text())
        label = f"{reservation.get('task_id', 'unknown')}:{reservation.get('repetition', 'unknown')}"
        reservation_errors = validate_reservation(reservation, tasks, order_by_repetition)
        errors.extend(f"{label}:reservation:{item}" for item in reservation_errors)
        cell = (reservation.get("task_id"), reservation.get("repetition"))
        if cell in cells:
            errors.append(f"{label}:duplicate-group")
        cells.add(cell)
        task = tasks.get(reservation.get("task_id"))
        seen: set[str] = set()
        for run_dir in sorted(path for path in group_dir.iterdir() if path.is_dir()):
            context_path = run_dir / "RUN_CONTEXT.json"
            receipt_path = run_dir / "receipt.json"
            if not context_path.exists():
                errors.append(f"{label}:missing-context")
                continue
            context = json.loads(context_path.read_text())
            context_errors = validate_context(context, reservation, task)
            errors.extend(f"{label}:{context.get('variant', 'unknown')}:context:{item}" for item in context_errors)
            snapshot_path = run_dir / "GUIDE_SNAPSHOT.md"
            if context.get("variant") == "baseline":
                if snapshot_path.exists():
                    errors.append(f"{label}:baseline:context:unexpected-guide-snapshot")
            elif not snapshot_path.is_file():
                errors.append(f"{label}:{context.get('variant', 'unknown')}:context:missing-guide-snapshot")
            else:
                snapshot_hash = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
                if snapshot_hash != context.get("guide_sha256"):
                    errors.append(f"{label}:{context.get('variant', 'unknown')}:context:guide-snapshot-hash")
            if not receipt_path.exists():
                errors.append(f"{label}:{context.get('variant', 'unknown')}:missing-receipt")
                continue
            receipt = json.loads(receipt_path.read_text())
            seen.add(receipt.get("variant", ""))
            receipt_errors = validate_receipt(receipt, context, allowed_fields)
            errors.extend(f"{label}:{context.get('variant', 'unknown')}:receipt:{item}" for item in receipt_errors)
            rows.append(receipt)
        if seen != set(VARIANTS):
            errors.append(f"{label}:variants")
    if require_complete_cohort:
        fixture = json.loads((ROOT / "manifest.json").read_text())
        expected = {(task["id"], repetition) for task in fixture["tasks"] for repetition in range(1, 4)}
        if cells != expected:
            errors.append("incomplete-18-group-cohort")
    return rows, errors


def build_summary(rows: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    by_variant = defaultdict(list)
    for row in completed:
        by_variant[row["variant"]].append(row)

    def median(variant: str, getter) -> float | None:
        values = [getter(row) for row in by_variant[variant] if getter(row) is not None]
        return statistics.median(values) if values else None

    variants = {}
    for variant in VARIANTS:
        interval_metrics = [overlap_metrics(row["agents"]) for row in by_variant[variant]]
        variants[variant] = {
            "runs": len(by_variant[variant]),
            "correctness_accuracy_median": median(variant, lambda row: row["correctness"]["accuracy"]),
            "routing_precision_median": median(variant, lambda row: row["routing"]["precision"]),
            "routing_recall_median": median(variant, lambda row: row["routing"]["recall"]),
            "latency_ms_median": median(variant, lambda row: row["latency_ms"]),
            "tool_calls_median": median(variant, lambda row: row["tool_calls"]),
            "follow_up_reads_median": median(variant, lambda row: row["follow_up_reads"]),
            "corrections": sum(row["corrections"] for row in by_variant[variant]),
            "rework_events": sum(row["rework_events"] for row in by_variant[variant]),
            "failures": sum(row["failures"] for row in by_variant[variant]),
            "refusals": sum(row["refusals"] for row in by_variant[variant]),
            "actual_overlap_runs": sum(item["actual_overlap"] for item in interval_metrics),
            "concurrent_agent_milliseconds": sum(item["concurrent_agent_milliseconds"] for item in interval_metrics),
            "maximum_concurrency": max((item["maximum_concurrency"] for item in interval_metrics), default=0),
            "agent_count": sum(item["agent_count"] for item in interval_metrics),
            "collision_totals": sum(row["collisions"] for row in by_variant[variant]),
        }
    comparisons = {}
    for candidate in ("superpowers", "rhize"):
        comparisons[f"baseline_vs_{candidate}"] = {
            metric: None if variants["baseline"][metric] is None or variants[candidate][metric] is None else variants[candidate][metric] - variants["baseline"][metric]
            for metric in ("correctness_accuracy_median", "routing_precision_median", "routing_recall_median", "latency_ms_median", "tool_calls_median", "follow_up_reads_median")
        }
    return {
        "schema_version": 1,
        "evaluation": "superpowers-rhize-isolated-guide-comparison",
        "status": "pass" if not errors else "fail",
        "runs": len(rows),
        "variants": variants,
        "comparisons": comparisons,
        "errors": errors,
        "evidence_boundary": "Separate isolated evidence; never pooled into canonical Rhize v2 readiness.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--require-complete-cohort", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        rows, errors = load_groups(args.root, args.require_complete_cohort)
        result = build_summary(rows, errors)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        result = {"schema_version": 1, "evaluation": "superpowers-rhize-isolated-guide-comparison", "status": "fail", "errors": [str(exc)]}
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

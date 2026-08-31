#!/usr/bin/env python3
"""Validate isolated guide receipts and compare each guide to the same baseline."""

from __future__ import annotations

import argparse
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


def timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def nonnegative(value: Any, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


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
                    if timestamp(agent["completed_at"]) < timestamp(agent["started_at"]):
                        errors.append("agent_interval")
                except (ValueError, TypeError):
                    errors.append("agent_interval")
    return sorted(set(errors))


def load_groups(root: Path, require_complete_cohort: bool) -> tuple[list[dict[str, Any]], list[str]]:
    schema = json.loads((ROOT / "guide-comparison-receipt.schema.json").read_text())
    allowed_fields = set(schema["properties"])
    groups = sorted(root.rglob("GROUP_RESERVATION.json"))
    if not groups:
        raise ValueError("no guide comparison reservations found")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    cells: set[tuple[str, int]] = set()
    for reservation_path in groups:
        group_dir = reservation_path.parent
        reservation = json.loads(reservation_path.read_text())
        order = reservation["order"]
        cells.add((reservation["task_id"], reservation["repetition"]))
        seen: set[str] = set()
        for run_dir in sorted(path for path in group_dir.iterdir() if path.is_dir()):
            context_path = run_dir / "RUN_CONTEXT.json"
            receipt_path = run_dir / "receipt.json"
            if not context_path.exists() or not receipt_path.exists():
                errors.append(f"{reservation['task_id']}:{reservation['repetition']}:missing-receipt")
                continue
            context = json.loads(context_path.read_text())
            receipt = json.loads(receipt_path.read_text())
            seen.add(receipt.get("variant", ""))
            if order[context["order_position"] - 1] != context["variant"]:
                errors.append(f"{context['task_id']}:{context['repetition']}:order")
            receipt_errors = validate_receipt(receipt, context, allowed_fields)
            errors.extend(f"{context['task_id']}:{context['repetition']}:{context['variant']}:{item}" for item in receipt_errors)
            rows.append(receipt)
        if seen != set(VARIANTS):
            errors.append(f"{reservation['task_id']}:{reservation['repetition']}:variants")
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

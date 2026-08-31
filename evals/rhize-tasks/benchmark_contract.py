#!/usr/bin/env python3
"""Reserve and validate isolated Rhize Tasks baseline-versus-skill benefit pairs."""

from __future__ import annotations

import argparse
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REASONS = {"host_not_exposed", "partial_host_coverage", "not_measured"}


def canonical_uuid(value: str) -> str:
    parsed = uuid.UUID(value)
    if str(parsed) != value.lower():
        raise ValueError("comparison-id must be canonical lowercase")
    return value


def reserve(args: argparse.Namespace) -> int:
    manifest = json.loads((ROOT / "benefit-benchmark.json").read_text())
    skills = [item["id"] for item in manifest["skills"]]
    if args.skill not in skills:
        raise ValueError(f"unknown skill: {args.skill}")
    if not 1 <= args.repetition <= manifest["repetitions"]:
        raise ValueError("repetition must be 1, 2, or 3")
    comparison_id = canonical_uuid(args.comparison_id)
    if args.output.exists():
        raise ValueError(f"output already exists: {args.output}")
    skill_index = skills.index(args.skill)
    order = ["baseline", "rhize"] if (skill_index + args.repetition) % 2 else ["rhize", "baseline"]
    args.output.mkdir(parents=True)
    reservation = {
        "schema_version": "rhize-tasks-benefit-reservation-v1",
        "comparison_id": comparison_id,
        "skill": args.skill,
        "repetition": args.repetition,
        "order": order,
        "status": "pending",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "arm_a": manifest["arms"]["baseline"],
        "arm_b": manifest["arms"]["rhize"],
        "network": False,
        "live_mutation": False,
    }
    (args.output / "PAIR_RESERVATION.json").write_text(json.dumps(reservation, indent=2) + "\n")
    for position, variant in enumerate(order, 1):
        run_dir = args.output / f"{position}-{variant}"
        run_dir.mkdir()
        context = {
            "run_id": str(uuid.uuid4()), "comparison_id": comparison_id, "skill": args.skill,
            "variant": variant, "arm_actual": "A" if variant == "baseline" else "B",
            "repetition": args.repetition, "order_position": position,
        }
        (run_dir / "RUN_CONTEXT.json").write_text(json.dumps(context, indent=2) + "\n")
        (run_dir / "RUN_INSTRUCTIONS.md").write_text(
            f"Run the `{variant}` arm actually assigned for `{args.skill}` in a fresh local fixture. "
            "No network or live mutation. Record only factual common metrics in receipt.json; unknown counters stay null with a reason.\n"
        )
    return 0


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def validate_receipt(receipt: dict[str, Any], context: dict[str, Any], fields: set[str]) -> list[str]:
    errors = []
    if set(receipt) != fields:
        errors.append("fields")
    for key, value in context.items():
        if receipt.get(key) != value:
            errors.append(key)
    if receipt.get("schema_version") != "rhize-tasks-benefit-v1":
        errors.append("schema_version")
    for key in ("run_id", "comparison_id"):
        try:
            uuid.UUID(receipt[key])
        except (KeyError, ValueError, TypeError):
            errors.append(key)
    status = receipt.get("status")
    if status not in {"completed", "failed", "incomplete"}:
        errors.append("status")
    try:
        started = datetime.fromisoformat(str(receipt.get("started_at")).replace("Z", "+00:00"))
        completed = datetime.fromisoformat(str(receipt.get("completed_at")).replace("Z", "+00:00"))
        if started.tzinfo is None or completed.tzinfo is None or completed < started:
            errors.append("timestamps")
    except ValueError:
        errors.append("timestamps")
    for key in ("latency_ms", "follow_up_reads", "corrections", "rework_events", "failures", "refusals"):
        value = receipt.get(key)
        if status == "completed" and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            errors.append(key)
    correctness = receipt.get("correctness", {})
    routing = receipt.get("routing", {})
    if status == "completed":
        passed, total, accuracy = correctness.get("passed"), correctness.get("total"), correctness.get("accuracy")
        if not isinstance(total, int) or total <= 0 or not isinstance(passed, int) or not 0 <= passed <= total or not isinstance(accuracy, (int, float)) or not math.isclose(accuracy, passed / total):
            errors.append("correctness")
        tp, fp, fn = routing.get("true_positives"), routing.get("false_positives"), routing.get("false_negatives")
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (tp, fp, fn)):
            errors.append("routing")
        else:
            precision, recall = routing.get("precision"), routing.get("recall")
            if not isinstance(precision, (int, float)) or not isinstance(recall, (int, float)) or not math.isclose(precision, ratio(tp, tp + fp)) or not math.isclose(recall, ratio(tp, tp + fn)):
                errors.append("routing")
    tokens = receipt.get("tokens", {})
    missing_tokens = any(tokens.get(key) is None for key in ("input", "output", "cache_read", "cache_write"))
    if missing_tokens != (receipt.get("tokens_unavailable_reason") in REASONS):
        errors.append("tokens_unavailable_reason")
    if (receipt.get("tool_calls") is None) != (receipt.get("tool_calls_unavailable_reason") in REASONS):
        errors.append("tool_calls_unavailable_reason")
    return sorted(set(errors))


def validate(args: argparse.Namespace) -> int:
    schema = json.loads((ROOT / "benefit-receipt.schema.json").read_text())
    fields = set(schema["properties"])
    reservations = sorted(args.root.rglob("PAIR_RESERVATION.json"))
    errors = []
    rows = 0
    cells = set()
    for path in reservations:
        reservation = json.loads(path.read_text())
        cells.add((reservation["skill"], reservation["repetition"]))
        seen = set()
        for run_dir in sorted(item for item in path.parent.iterdir() if item.is_dir()):
            context = json.loads((run_dir / "RUN_CONTEXT.json").read_text())
            receipt_path = run_dir / "receipt.json"
            if not receipt_path.exists():
                errors.append(f"{reservation['skill']}:{reservation['repetition']}:missing")
                continue
            receipt = json.loads(receipt_path.read_text())
            rows += 1
            seen.add(receipt.get("variant"))
            errors.extend(f"{reservation['skill']}:{reservation['repetition']}:{item}" for item in validate_receipt(receipt, context, fields))
        if seen != {"baseline", "rhize"}:
            errors.append(f"{reservation['skill']}:{reservation['repetition']}:variants")
    if args.require_complete_cohort:
        manifest = json.loads((ROOT / "benefit-benchmark.json").read_text())
        expected = {(skill["id"], repetition) for skill in manifest["skills"] for repetition in range(1, 4)}
        if cells != expected:
            errors.append("incomplete-18-pair-cohort")
    result = {"status": "pass" if reservations and not errors else "fail", "pairs": len(reservations), "receipts": rows, "errors": errors}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("reserve")
    create.add_argument("--skill", required=True)
    create.add_argument("--repetition", type=int, required=True)
    create.add_argument("--comparison-id", required=True)
    create.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("validate")
    check.add_argument("root", type=Path)
    check.add_argument("--require-complete-cohort", action="store_true")
    args = parser.parse_args()
    try:
        return reserve(args) if args.command == "reserve" else validate(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

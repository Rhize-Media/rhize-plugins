#!/usr/bin/env python3
"""Reserve and validate pre/post evolve non-inferiority evidence without adoption."""

from __future__ import annotations

import argparse
import json
import statistics
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
METRICS = {
    "correctness_accuracy", "routing_precision", "routing_recall", "tokens_input", "tokens_output",
    "tokens_cache_read", "tokens_cache_write", "latency_ms", "tool_calls", "follow_up_reads",
    "corrections", "rework_events", "failures", "refusals"
}
RESERVATION_FIELDS = {
    "schema_version", "comparison_id", "repetition", "order", "digests", "arm_a", "arm_b",
    "adopt", "network",
}
CONTEXT_FIELDS = {
    "run_id", "comparison_id", "variant", "arm_actual", "digest", "repetition",
    "order_position",
}


def canonical_uuid(value: str, label: str) -> str:
    parsed = uuid.UUID(value)
    if str(parsed) != value.lower():
        raise ValueError(f"{label} must be a canonical lowercase UUID")
    return value


def valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def reserve(args: argparse.Namespace) -> int:
    manifest = json.loads((ROOT / "evolve-benchmark.json").read_text())
    if args.repetition not in (1, 2, 3):
        raise ValueError("repetition must be 1, 2, or 3")
    canonical_uuid(args.comparison_id, "comparison-id")
    for digest in (args.pre_digest, args.post_digest):
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("digests must be lowercase SHA-256")
    if args.output.exists():
        raise ValueError("output already exists")
    args.output.mkdir(parents=True)
    order = manifest["order_by_repetition"][str(args.repetition)]
    reservation = {
        "schema_version": "skill-forge-evolve-reservation-v1", "comparison_id": args.comparison_id,
        "repetition": args.repetition, "order": order, "digests": {"pre": args.pre_digest, "post": args.post_digest},
        "arm_a": manifest["arm_a"], "arm_b": manifest["arm_b"], "adopt": False, "network": False
    }
    (args.output / "PAIR_RESERVATION.json").write_text(json.dumps(reservation, indent=2) + "\n")
    for position, variant in enumerate(order, 1):
        run = args.output / f"{position}-{variant}"
        run.mkdir()
        (run / "RUN_CONTEXT.json").write_text(json.dumps({
            "run_id": str(uuid.uuid4()), "comparison_id": args.comparison_id, "variant": variant,
            "arm_actual": "A" if variant == "pre" else "B", "digest": reservation["digests"][variant],
            "repetition": args.repetition, "order_position": position
        }, indent=2) + "\n")
    return 0


def validate(args: argparse.Namespace) -> int:
    manifest = json.loads((ROOT / "evolve-benchmark.json").read_text())
    expected_repetitions = set(range(1, manifest["repetitions"] + 1))
    rows = []
    errors = []
    repetitions = set()
    digest_sets = set()
    for reservation_path in sorted(args.root.rglob("PAIR_RESERVATION.json")):
        reservation = json.loads(reservation_path.read_text())
        if set(reservation) != RESERVATION_FIELDS:
            errors.append("reservation-fields")
            continue
        repetition = reservation.get("repetition")
        if not isinstance(repetition, int) or isinstance(repetition, bool):
            errors.append("reservation-repetition")
            continue
        if repetition in repetitions:
            errors.append("duplicate-repetition")
        repetitions.add(repetition)
        if repetition not in expected_repetitions:
            errors.append("reservation-repetition")
        expected_order = manifest["order_by_repetition"].get(str(repetition))
        if reservation.get("order") != expected_order:
            errors.append("reservation-order")
        if reservation.get("schema_version") != "skill-forge-evolve-reservation-v1":
            errors.append("reservation-schema")
        try:
            canonical_uuid(reservation.get("comparison_id"), "comparison_id")
        except (ValueError, TypeError, AttributeError):
            errors.append("reservation-comparison-id")
        digests = reservation.get("digests")
        if (
            not isinstance(digests, dict)
            or set(digests) != {"pre", "post"}
            or not all(valid_digest(digests[variant]) for variant in ("pre", "post"))
        ):
            errors.append("reservation-digests")
            digests = {}
        else:
            digest_sets.add((digests["pre"], digests["post"]))
        if reservation.get("arm_a") != manifest["arm_a"] or reservation.get("arm_b") != manifest["arm_b"]:
            errors.append("reservation-arms")
        if reservation.get("adopt") is not False or reservation.get("network") is not False:
            errors.append("reservation-boundary")
        seen = set()
        for run in sorted(path for path in reservation_path.parent.iterdir() if path.is_dir()):
            context = json.loads((run / "RUN_CONTEXT.json").read_text())
            if set(context) != CONTEXT_FIELDS:
                errors.append("context-fields")
                continue
            if context.get("comparison_id") != reservation.get("comparison_id") or context.get("repetition") != repetition:
                errors.append("context-reservation")
            variant = context.get("variant")
            position = context.get("order_position")
            if variant not in {"pre", "post"} or not isinstance(position, int) or isinstance(position, bool):
                errors.append("context-order")
            elif not isinstance(expected_order, list) or not 1 <= position <= 2 or expected_order[position - 1] != variant:
                errors.append("context-order")
            expected_arm = "A" if variant == "pre" else "B"
            if context.get("arm_actual") != expected_arm or context.get("digest") != digests.get(variant):
                errors.append("context-arm")
            try:
                canonical_uuid(context.get("run_id"), "run_id")
            except (ValueError, TypeError, AttributeError):
                errors.append("context-run-id")
            receipt_path = run / "receipt.json"
            if not receipt_path.exists():
                errors.append("missing-receipt")
                continue
            receipt = json.loads(receipt_path.read_text())
            if set(receipt) != CONTEXT_FIELDS | {"metrics"} or any(receipt.get(key) != value for key, value in context.items()) or set(receipt.get("metrics", {})) != METRICS:
                errors.append("receipt-contract")
                continue
            metrics = receipt["metrics"]
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 for value in metrics.values()):
                errors.append("metric-values")
                continue
            if any(metrics[key] > 1 for key in ("correctness_accuracy", "routing_precision", "routing_recall")):
                errors.append("metric-ratios")
                continue
            seen.add(variant)
            rows.append(receipt)
        if seen != {"pre", "post"}:
            errors.append("missing-arm")
    if repetitions != expected_repetitions:
        errors.append("incomplete-three-pair-cohort")
    if len(digest_sets) != 1:
        errors.append("cohort-digest-mismatch")
    by_variant = {variant: [row["metrics"] for row in rows if row["variant"] == variant] for variant in ("pre", "post")}
    result = {"status": "fail", "pairs": len(rows) // 2, "errors": errors, "non_inferiority": {}}
    if len(by_variant["pre"]) == len(by_variant["post"]) == manifest["repetitions"] and not errors:
        med = {variant: {metric: statistics.median(row[metric] for row in values) for metric in METRICS} for variant, values in by_variant.items()}
        thresholds = manifest["non_inferiority"]
        checks = {
            "correctness_accuracy": med["post"]["correctness_accuracy"] - med["pre"]["correctness_accuracy"] >= thresholds["minimum_accuracy_delta"],
            "routing_precision": med["post"]["routing_precision"] - med["pre"]["routing_precision"] >= thresholds["minimum_routing_precision_delta"],
            "routing_recall": med["post"]["routing_recall"] - med["pre"]["routing_recall"] >= thresholds["minimum_routing_recall_delta"],
            "latency": med["post"]["latency_ms"] <= med["pre"]["latency_ms"] * (1 + thresholds["maximum_latency_increase_fraction"]),
            "rework": med["post"]["rework_events"] - med["pre"]["rework_events"] <= thresholds["maximum_rework_increase"],
            "failures": med["post"]["failures"] - med["pre"]["failures"] <= thresholds["maximum_failure_increase"]
        }
        result["non_inferiority"] = checks
        result["status"] = "pass" if all(checks.values()) else "fail"
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("reserve")
    create.add_argument("--pre-digest", required=True)
    create.add_argument("--post-digest", required=True)
    create.add_argument("--repetition", type=int, required=True)
    create.add_argument("--comparison-id", required=True)
    create.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("validate")
    check.add_argument("root", type=Path)
    args = parser.parse_args()
    try:
        return reserve(args) if args.command == "reserve" else validate(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Aggregate a complete repeated baseline-versus-Rhize fixture matrix."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("baseline", "rhize")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed


def overlap_metrics(agents: list[dict[str, Any]] | None) -> dict[str, float | int | bool | None]:
    if agents is None:
        return {
            "max_concurrency": None,
            "concurrent_agent_seconds": None,
            "total_agent_seconds": None,
            "parallelism_ratio": None,
            "actual_overlap": None,
        }
    intervals = []
    for agent in agents:
        started = parse_time(agent["started_at"])
        completed = parse_time(agent["completed_at"])
        if completed < started:
            raise ValueError("agent completion precedes start")
        intervals.append((started, completed))
    events: list[tuple[datetime, int]] = []
    total_agent_seconds = 0.0
    for started, completed in intervals:
        events.extend(((started, 1), (completed, -1)))
        total_agent_seconds += (completed - started).total_seconds()
    events.sort(key=lambda item: (item[0], item[1]))
    active = 0
    maximum = 0
    concurrent_seconds = 0.0
    previous: datetime | None = None
    for moment, change in events:
        if previous is not None and active >= 2:
            concurrent_seconds += (moment - previous).total_seconds()
        active += change
        maximum = max(maximum, active)
        previous = moment
    return {
        "max_concurrency": maximum,
        "concurrent_agent_seconds": round(concurrent_seconds, 3),
        "total_agent_seconds": round(total_agent_seconds, 3),
        "parallelism_ratio": round(concurrent_seconds / total_agent_seconds, 4) if total_agent_seconds else 0.0,
        "actual_overlap": concurrent_seconds > 0,
    }


def load_rows(run_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    expected = {
        (task["id"], variant, repetition)
        for task in manifest["tasks"]
        for variant in manifest["variants"]
        for repetition in range(1, manifest["repetitions"] + 1)
    }
    rows = []
    observed = set()
    if run_root.exists():
        run_dirs = sorted(path for path in run_root.iterdir() if path.is_dir())
    else:
        run_dirs = []
    for run_dir in run_dirs:
        receipt_path = run_dir / "receipt.json"
        grade_path = run_dir / "grade.json"
        if not receipt_path.exists() or not grade_path.exists():
            continue
        receipt = json.loads(receipt_path.read_text())
        grade = json.loads(grade_path.read_text())
        if receipt.get("schema_version") != 2 or grade.get("schema_version") != 2:
            raise ValueError(f"non-v2 fixture record: {run_dir.name}")
        key = (receipt["task_id"], receipt["variant"], receipt["repetition"])
        if key not in expected:
            raise ValueError(f"unexpected evaluation cell: {key}")
        if key in observed:
            raise ValueError(f"duplicate evaluation cell: {key}")
        observed.add(key)
        started = parse_time(receipt["started_at"])
        completed = parse_time(receipt["completed_at"])
        if completed < started:
            raise ValueError(f"negative elapsed interval: {key}")
        overlap = overlap_metrics(receipt["agents"])
        tokens = receipt["tokens"]
        rows.append(
            {
                "run_id": receipt["run_id"],
                "comparison_id": receipt["comparison_id"],
                "task_id": receipt["task_id"],
                "task_class": receipt["task_class"],
                "variant": receipt["variant"],
                "repetition": receipt["repetition"],
                "status": receipt["status"],
                "expected_decision": receipt["expected_decision"],
                "actual_decision": receipt["decision"],
                "elapsed_seconds": round((completed - started).total_seconds(), 3),
                "agents_spawned": len(receipt["agents"]) if receipt["agents"] is not None else None,
                **overlap,
                "collisions": receipt["collisions"],
                "rework_events": receipt["rework_events"],
                "verification_completeness": grade["verification_completeness"],
                "correctness_pass": grade["correctness_pass"],
                "appropriateness_pass": grade["appropriateness_pass"],
                "receipt_valid": grade["receipt_valid"],
                "tool_calls": receipt["tool_calls"],
                "tokens": tokens,
                "token_totals_available": all(value is not None for value in tokens.values()),
            }
        )
    missing = sorted(expected - observed)
    if missing:
        raise ValueError(f"missing evaluation cells: {missing}")
    return sorted(rows, key=lambda row: (row["task_id"], row["repetition"], row["variant"]))


def coverage_status(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    if field == "tokens":
        measured = sum(row["token_totals_available"] for row in rows)
    else:
        measured = sum(row[field] is not None for row in rows)
    return {
        "status": "unavailable" if measured == 0 else ("measured" if measured == len(rows) else "partial"),
        "measured_runs": measured,
        "total_runs": len(rows),
        "required_for_decision": False,
    }


def required_metric(passed: bool, actual: Any, threshold: Any) -> dict[str, Any]:
    return {"status": "pass" if passed else "fail", "actual": actual, "threshold": threshold}


def build_summary(rows: list[dict[str, Any]], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or json.loads((ROOT / "manifest.json").read_text())
    thresholds = manifest["thresholds"]
    by_variant = {variant: [row for row in rows if row["variant"] == variant] for variant in VARIANTS}
    pair_ids = defaultdict(set)
    for row in rows:
        pair_ids[(row["task_id"], row["repetition"])].add(row["comparison_id"])
    pairs_matched = all(len(ids) == 1 for ids in pair_ids.values())
    completed = all(row["status"] == "completed" for row in rows)
    correctness = all(row["correctness_pass"] for row in rows)
    verification = all(row["verification_completeness"] == 1.0 for row in rows)
    routing = all(row["appropriateness_pass"] for row in rows)
    collisions = sum((row["collisions"] or 0) for row in rows)
    baseline_rework = sum((row["rework_events"] or 0) for row in by_variant["baseline"])
    rhize_rework = sum((row["rework_events"] or 0) for row in by_variant["rhize"])
    baseline_parallel = [
        row["elapsed_seconds"] for row in by_variant["baseline"]
        if row["expected_decision"] == "parallel" and row["status"] == "completed"
    ]
    rhize_parallel = [
        row["elapsed_seconds"] for row in by_variant["rhize"]
        if row["expected_decision"] == "parallel" and row["status"] == "completed"
    ]
    improvement = None
    if baseline_parallel and rhize_parallel and statistics.median(baseline_parallel):
        improvement = (
            statistics.median(baseline_parallel) - statistics.median(rhize_parallel)
        ) / statistics.median(baseline_parallel)
    rhize_parallel_rows = [
        row for row in by_variant["rhize"]
        if row["expected_decision"] == "parallel" and row["status"] == "completed"
    ]
    overlap_rate = (
        sum(row["actual_overlap"] is True for row in rhize_parallel_rows) / len(rhize_parallel_rows)
        if rhize_parallel_rows else None
    )
    agent_count_ok = bool(rhize_parallel_rows) and all(
        row["agents_spawned"] is not None
        and row["agents_spawned"] >= thresholds["minimum_agents_for_parallel_rhize_run"]
        for row in rhize_parallel_rows
    )
    required = {
        "matched_pairs": required_metric(pairs_matched, pairs_matched, True),
        "terminal_completion": required_metric(completed, Counter(row["status"] for row in rows), "all completed"),
        "correctness": required_metric(correctness, correctness, thresholds["correctness_pass_rate"]),
        "verification": required_metric(verification, verification, thresholds["verification_completeness"]),
        "routing": required_metric(routing, routing, thresholds["routing_appropriateness_rate"]),
        "collisions": required_metric(collisions <= thresholds["maximum_collisions"], collisions, thresholds["maximum_collisions"]),
        "rework": required_metric(rhize_rework - baseline_rework <= thresholds["maximum_rework_increase_vs_baseline"], rhize_rework - baseline_rework, thresholds["maximum_rework_increase_vs_baseline"]),
        "elapsed": required_metric(improvement is not None and improvement >= thresholds["minimum_parallel_elapsed_improvement"], improvement, thresholds["minimum_parallel_elapsed_improvement"]),
        "actual_overlap": required_metric(overlap_rate is not None and overlap_rate >= thresholds["minimum_parallel_overlap_rate"], overlap_rate, thresholds["minimum_parallel_overlap_rate"]),
        "agent_count": required_metric(agent_count_ok, [row["agents_spawned"] for row in rhize_parallel_rows], thresholds["minimum_agents_for_parallel_rhize_run"]),
    }
    decision = "ready" if all(item["status"] == "pass" for item in required.values()) else "not_ready"
    variants = {}
    for variant, variant_rows in by_variant.items():
        elapsed = [row["elapsed_seconds"] for row in variant_rows if row["status"] == "completed"]
        variants[variant] = {
            "runs": len(variant_rows),
            "status_counts": dict(sorted(Counter(row["status"] for row in variant_rows).items())),
            "correctness_passed": sum(row["correctness_pass"] for row in variant_rows),
            "appropriateness_passed": sum(row["appropriateness_pass"] for row in variant_rows),
            "verification_completeness_mean": statistics.fmean(row["verification_completeness"] for row in variant_rows),
            "elapsed_seconds_median": statistics.median(elapsed) if elapsed else None,
            "actual_overlap_runs": sum(row["actual_overlap"] is True for row in variant_rows),
            "agents_spawned": sum(row["agents_spawned"] or 0 for row in variant_rows),
            "collisions": sum(row["collisions"] or 0 for row in variant_rows),
            "rework_events": sum(row["rework_events"] or 0 for row in variant_rows),
        }
    return {
        "schema_version": 2,
        "evaluation": "parallel-routing-repeated-controlled",
        "run_count": len(rows),
        "task_count": len(manifest["tasks"]),
        "repetitions": manifest["repetitions"],
        "variants": variants,
        "decision_readiness": {
            "decision": decision,
            "thresholds": thresholds,
            "required_metrics": required,
            "optional_metrics": {
                "tool_calls": coverage_status(rows, "tool_calls"),
                "tokens": coverage_status(rows, "tokens"),
            },
        },
        "runs": rows,
        "limitations": [
            "This is deterministic isolated fixture evidence, not a production benchmark.",
            "Elapsed time includes host scheduling and agent startup effects.",
            "Unavailable tool/token counts remain null and are not estimated or used as required gates."
        ],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    readiness = summary["decision_readiness"]
    lines = [
        "# Repeated Baseline vs Rhize Routing Evaluation",
        "",
        f"Decision readiness: **{readiness['decision']}** across {summary['run_count']} isolated fixture runs.",
        "",
        "| Variant | Runs | Correct | Routing | Verification | Median seconds | Actual overlap | Collisions | Rework |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in VARIANTS:
        data = summary["variants"][variant]
        lines.append(
            f"| {variant} | {data['runs']} | {data['correctness_passed']} | "
            f"{data['appropriateness_passed']} | {data['verification_completeness_mean']:.0%} | "
            f"{data['elapsed_seconds_median'] or 'n/a'} | {data['actual_overlap_runs']} | "
            f"{data['collisions']} | {data['rework_events']} |"
        )
    lines.extend(
        [
            "",
            "Required readiness metrics and optional token/tool coverage are separate in the JSON output.",
            "The tracked 2026-08-27 four-arm smoke remains legacy one-cell screening evidence and is not pooled here.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    summary = build_summary(load_rows(args.run_root, manifest), manifest)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(summary, indent=2) + "\n")
    args.markdown_output.write_text(render_markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

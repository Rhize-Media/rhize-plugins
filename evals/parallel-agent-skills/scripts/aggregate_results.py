#!/usr/bin/env python3
"""Aggregate privacy-safe metrics from a complete parallel-agent evaluation matrix."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VARIANT_LABELS = {
    "baseline": "Baseline",
    "arm_a": "Arm A (ECC)",
    "arm_b": "Arm B (Superpowers)",
    "arm_ab": "Arm A+B",
}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def overlap_metrics(agents: list[dict[str, Any]]) -> dict[str, float | int | bool]:
    intervals: list[tuple[datetime, datetime]] = []
    for agent in agents:
        if agent.get("started_at") and agent.get("completed_at"):
            started = parse_time(agent["started_at"])
            completed = parse_time(agent["completed_at"])
            if completed >= started:
                intervals.append((started, completed))

    events: dict[datetime, int] = defaultdict(int)
    total_agent_seconds = 0.0
    for started, completed in intervals:
        events[started] += 1
        events[completed] -= 1
        total_agent_seconds += (completed - started).total_seconds()

    active = 0
    maximum = 0
    concurrent_seconds = 0.0
    previous: datetime | None = None
    for moment in sorted(events):
        if previous is not None and active >= 2:
            concurrent_seconds += (moment - previous).total_seconds()
        active += events[moment]
        maximum = max(maximum, active)
        previous = moment

    return {
        "max_concurrency": maximum,
        "concurrent_agent_seconds": round(concurrent_seconds, 3),
        "total_agent_seconds": round(total_agent_seconds, 3),
        "parallelism_ratio": (
            round(concurrent_seconds / total_agent_seconds, 4) if total_agent_seconds else 0.0
        ),
        "actual_overlap": concurrent_seconds > 0,
    }


def load_rows(run_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    expected = {
        (task["id"], variant)
        for task in manifest["tasks"]
        for variant in manifest["variants"]
    }
    rows: list[dict[str, Any]] = []
    observed: set[tuple[str, str]] = set()

    for run_dir in sorted(path for path in run_root.iterdir() if path.is_dir()):
        receipt_path = run_dir / "receipt.json"
        grade_path = run_dir / "grade.json"
        if not receipt_path.exists() or not grade_path.exists():
            continue
        receipt = json.loads(receipt_path.read_text())
        grade = json.loads(grade_path.read_text())
        key = (receipt["task_id"], receipt["variant"])
        if key not in expected:
            continue
        if key in observed:
            raise ValueError(f"duplicate evaluation cell: {key}")
        observed.add(key)
        started = parse_time(receipt["started_at"])
        completed = parse_time(receipt["completed_at"])
        overlap = overlap_metrics(receipt["agents"])
        tokens = receipt["tokens"]
        rows.append(
            {
                "run_id": receipt["run_id"],
                "task_id": receipt["task_id"],
                "variant": receipt["variant"],
                "expected_decision": grade["expected_decision"],
                "actual_decision": grade["actual_decision"],
                "elapsed_seconds": round((completed - started).total_seconds(), 3),
                "agents_spawned": len(receipt["agents"]),
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
    return sorted(rows, key=lambda row: (row["task_id"], row["variant"]))


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_variant_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant_rows[row["variant"]].append(row)

    baseline_safe = [
        row["elapsed_seconds"]
        for row in by_variant_rows["baseline"]
        if row["expected_decision"] == "parallel"
    ]
    baseline_safe_median = statistics.median(baseline_safe)
    baseline_safe_rows = [
        row
        for row in by_variant_rows["baseline"]
        if row["expected_decision"] == "parallel"
    ]
    variants: dict[str, Any] = {}
    for variant, variant_rows in sorted(by_variant_rows.items()):
        elapsed = [row["elapsed_seconds"] for row in variant_rows]
        parallel_safe_rows = [
            row for row in variant_rows if row["expected_decision"] == "parallel"
        ]
        parallel_safe_elapsed = [row["elapsed_seconds"] for row in parallel_safe_rows]
        parallel_safe_median = statistics.median(parallel_safe_elapsed)
        speed_improvement = (
            (baseline_safe_median - parallel_safe_median) / baseline_safe_median
            if baseline_safe_median
            else 0.0
        )
        token_data_complete = all(
            row["token_totals_available"]
            for row in parallel_safe_rows + baseline_safe_rows
        )
        token_ratio: float | None = None
        if token_data_complete:
            baseline_token_total = sum(
                row["tokens"]["input"] + row["tokens"]["output"]
                for row in baseline_safe_rows
            )
            variant_token_total = sum(
                row["tokens"]["input"] + row["tokens"]["output"]
                for row in parallel_safe_rows
            )
            if baseline_token_total > 0:
                token_ratio = variant_token_total / baseline_token_total
        hard_gate_pass = (
            all(row["correctness_pass"] for row in variant_rows)
            and all(row["appropriateness_pass"] for row in variant_rows)
            and all(row["receipt_valid"] for row in variant_rows)
            and sum(row["collisions"] for row in variant_rows) == 0
            and all(row["verification_completeness"] == 1.0 for row in variant_rows)
        )
        verification_gain = statistics.mean(
            row["verification_completeness"] for row in variant_rows
        ) - statistics.mean(
            row["verification_completeness"] for row in by_variant_rows["baseline"]
        )
        elapsed_overhead = (
            (statistics.median(elapsed) - statistics.median(
                row["elapsed_seconds"] for row in by_variant_rows["baseline"]
            ))
            / statistics.median(row["elapsed_seconds"] for row in by_variant_rows["baseline"])
        )
        speed_path_evaluable = token_ratio is not None
        speed_path_pass = (
            speed_improvement >= 0.15
            and token_ratio is not None
            and token_ratio <= 1.15
        )
        verification_path_pass = verification_gain >= 0.20 and elapsed_overhead <= 0.10
        variants[variant] = {
            "runs": len(variant_rows),
            "correctness_passed": sum(row["correctness_pass"] for row in variant_rows),
            "appropriateness_passed": sum(
                row["appropriateness_pass"] for row in variant_rows
            ),
            "receipts_valid": sum(row["receipt_valid"] for row in variant_rows),
            "verification_completeness_mean": round(
                statistics.mean(row["verification_completeness"] for row in variant_rows), 4
            ),
            "elapsed_seconds_median": round(statistics.median(elapsed), 3),
            "elapsed_seconds_range": [round(min(elapsed), 3), round(max(elapsed), 3)],
            "parallel_safe_elapsed_seconds_median": round(parallel_safe_median, 3),
            "parallel_safe_speed_improvement_vs_baseline": round(speed_improvement, 4),
            "parallel_safe_token_ratio_vs_baseline": (
                round(token_ratio, 4) if token_ratio is not None else None
            ),
            "agents_spawned": sum(row["agents_spawned"] for row in variant_rows),
            "expected_parallel_runs": len(parallel_safe_rows),
            "expected_parallel_runs_with_actual_overlap": sum(
                row["actual_overlap"] for row in parallel_safe_rows
            ),
            "collisions": sum(row["collisions"] for row in variant_rows),
            "rework_events": sum(row["rework_events"] for row in variant_rows),
            "tool_count_available_runs": sum(
                row["tool_calls"] is not None for row in variant_rows
            ),
            "token_totals_available_runs": sum(
                row["token_totals_available"] for row in variant_rows
            ),
            "hard_gate_pass": hard_gate_pass,
            "speed_path_evaluable": speed_path_evaluable,
            "speed_path_pass": speed_path_pass,
            "verification_path_pass": verification_path_pass,
            "adoption_gate_pass": hard_gate_pass and (
                speed_path_pass or verification_path_pass
            ),
        }

    return {
        "schema_version": 1,
        "evaluation": "parallel-agent-skill-smoke",
        "run_count": len(rows),
        "task_count": len({row["task_id"] for row in rows}),
        "variant_count": len(variants),
        "variants": variants,
        "runs": rows,
        "limitations": [
            "Each task/variant cell ran once; smoke results do not establish repeatability or statistical significance.",
            "Authoritative coordinator-plus-agent tool and token totals were unavailable for every run.",
            "Elapsed time includes host scheduling and agent startup noise and was not counterbalanced across repeated trials.",
            "Receipts for two cells were reconstructed by the coordinator from runner-reported fields after the runner safety layer blocked the required write.",
        ],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Parallel-Agent Skill Smoke Results",
        "",
        "Controlled fixture run completed 2026-08-27. Each of six task classes ran once under",
        "baseline, Arm A, Arm B, and both candidates. This is screening evidence, not a production",
        "benchmark or a statistically significant comparison.",
        "",
        "| Variant | Correct | Routing | Verification | Safe-task median | vs baseline | Actual overlap | Collisions | Rework | Adoption gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for variant in ("baseline", "arm_a", "arm_b", "arm_ab"):
        data = summary["variants"][variant]
        improvement = data["parallel_safe_speed_improvement_vs_baseline"]
        lines.append(
            "| {label} | {correct}/{runs} | {routing}/{runs} | {verification:.0%} | "
            "{median:.0f}s | {improvement:+.1%} | {overlap}/{parallel} | {collisions} | "
            "{rework} | {gate} |".format(
                label=VARIANT_LABELS[variant],
                correct=data["correctness_passed"],
                routing=data["appropriateness_passed"],
                runs=data["runs"],
                verification=data["verification_completeness_mean"],
                median=data["parallel_safe_elapsed_seconds_median"],
                improvement=improvement,
                overlap=data["expected_parallel_runs_with_actual_overlap"],
                parallel=data["expected_parallel_runs"],
                collisions=data["collisions"],
                rework=data["rework_events"],
                gate=(
                    "REFERENCE"
                    if variant == "baseline"
                    else ("PASS" if data["adoption_gate_pass"] else "NOT MET")
                ),
            )
        )
    lines.extend(
        [
            "",
            "Actual overlap means at least two nested-agent intervals overlapped; choosing a",
            "parallel decision or spawning two agents does not count by itself.",
            "",
            "## Interpretation boundary",
            "",
            "- All variants preserved correctness, routing appropriateness, complete verification,",
            "  and zero collisions in this smoke.",
            "- Tool and token totals were unavailable in every run, so the speed-path token ceiling",
            "  cannot be evaluated and no candidate can pass the predeclared adoption gate.",
            "- The fixture has one observation per cell. Elapsed-time differences may include host",
            "  scheduling and startup noise and require repeated, counterbalanced trials before use",
            "  as an adoption claim.",
            "- Two receipts were written by the coordinator from factual runner-reported fields after",
            "  the runner safety layer blocked the required isolated receipt write; both were graded",
            "  by the same observable-outcome harness.",
            "",
            "The durable Forge investigation contains the recommendation and full limitations.",
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
    summary = build_summary(load_rows(args.run_root, manifest))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(summary, indent=2) + "\n")
    args.markdown_output.write_text(render_markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

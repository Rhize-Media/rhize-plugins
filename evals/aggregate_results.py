#!/usr/bin/env python3
"""
Aggregate per-skill eval results into a unified benchmark report.

Usage:
    python3 evals/aggregate_results.py evals/results/seo-site-audit-*.json evals/results/keyword-*.json ...
    python3 evals/aggregate_results.py --pattern "evals/results/*-20260314*.json"
    python3 evals/aggregate_results.py --pattern "evals/results/*-20260314*.json" --output evals/results/full-benchmark.json
"""

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


def load_result(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def merge_trigger_results(all_results: list[dict]) -> dict:
    """Merge trigger results from multiple per-skill runs."""
    merged_evals = []
    merged_summary = {}

    for result in all_results:
        trigger = result.get("trigger")
        if not trigger:
            continue
        merged_evals.extend(trigger.get("evals", []))
        for skill, stats in trigger.get("summary", {}).items():
            merged_summary[skill] = stats

    return {"evals": merged_evals, "summary": merged_summary}


def merge_quality_results(all_results: list[dict]) -> dict:
    """Merge quality results from multiple per-skill runs."""
    merged_evals = []
    all_pass_rates = []

    for result in all_results:
        quality = result.get("quality")
        if not quality:
            continue
        merged_evals.extend(quality.get("evals", []))
        summary = quality.get("summary", {})
        if "with_plugin" in summary:
            all_pass_rates.append(summary["with_plugin"].get("overall_pass_rate", 0))

    merged_summary = {}
    if all_pass_rates:
        merged_summary["with_plugin"] = {
            "overall_pass_rate": round(mean(all_pass_rates), 3),
            "per_skill_rates": all_pass_rates,
        }

    return {"evals": merged_evals, "summary": merged_summary}


def generate_aggregate_report(trigger: dict, quality: dict, source_files: list[str], timestamp: str) -> str:
    lines = [
        "# Full Benchmark Report (Aggregated)",
        "",
        f"**Generated**: {timestamp}",
        f"**Sources**: {len(source_files)} per-skill result files",
        "",
    ]

    if trigger and trigger.get("summary"):
        lines.extend([
            "## Trigger Accuracy",
            "",
            "| Skill | Precision | Recall | F1 | TP | FP | TN | FN |",
            "|-------|-----------|--------|----|----|----|----|----|",
        ])

        total_tp = total_fp = total_tn = total_fn = 0
        for skill in sorted(trigger["summary"].keys()):
            stats = trigger["summary"][skill]
            lines.append(
                f"| {skill} | {stats['precision']:.2f} | {stats['recall']:.2f} | "
                f"{stats['f1']:.2f} | {stats['true_positives']} | {stats['false_positives']} | "
                f"{stats['true_negatives']} | {stats['false_negatives']} |"
            )
            total_tp += stats["true_positives"]
            total_fp += stats["false_positives"]
            total_tn += stats["true_negatives"]
            total_fn += stats["false_negatives"]

        # Aggregate row
        agg_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        agg_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        agg_f1 = 2 * agg_p * agg_r / (agg_p + agg_r) if (agg_p + agg_r) > 0 else 0
        lines.append(
            f"| **TOTAL** | **{agg_p:.2f}** | **{agg_r:.2f}** | "
            f"**{agg_f1:.2f}** | {total_tp} | {total_fp} | {total_tn} | {total_fn} |"
        )

        # Per-eval details
        lines.extend(["", "### Detailed Results", ""])
        for ev in trigger.get("evals", []):
            status = "PASS" if ev["correct"] else "FAIL"
            lines.append(
                f"- **[{status}]** `{ev['id']}`: trigger_rate={ev['trigger_rate']:.0%} "
                f"(expected={'trigger' if ev['should_trigger'] else 'no trigger'})"
            )
        lines.append("")

    if quality and quality.get("evals"):
        lines.extend(["## Output Quality", ""])

        summary = quality.get("summary", {})
        if "with_plugin" in summary:
            lines.append(f"**Overall Pass Rate**: {summary['with_plugin']['overall_pass_rate']:.0%}")
            lines.append("")

        lines.extend(["### Per-Eval Results", ""])
        for ev in quality["evals"]:
            lines.append(f"#### {ev['id']}")
            lines.append(f"**Prompt**: {ev['prompt'][:120]}...")
            lines.append("")
            for config, data in ev.get("configs", {}).items():
                lines.append(
                    f"**{config}**: pass_rate={data['mean_pass_rate']:.0%}, "
                    f"duration={data['mean_duration_ms']}ms, tokens={data['mean_tokens']}"
                )
                if data.get("runs"):
                    first_run = data["runs"][0]
                    for r in first_run.get("grading", {}).get("results", []):
                        icon = "pass" if r["passed"] else "FAIL"
                        lines.append(f"  - [{icon}] {r['name']}: {r['evidence']}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Aggregate per-skill eval results")
    parser.add_argument("files", nargs="*", help="Per-skill result JSON files")
    parser.add_argument("--pattern", type=str, help="Glob pattern to match result files")
    parser.add_argument("--output", type=str, help="Output path for aggregated JSON (default: auto-generated)")
    args = parser.parse_args()

    # Collect input files
    files = list(args.files) if args.files else []
    if args.pattern:
        files.extend(glob.glob(args.pattern))

    # Deduplicate and filter to .json only
    files = sorted(set(f for f in files if f.endswith(".json")))

    if not files:
        print("Error: no result files found. Provide files as arguments or use --pattern.")
        sys.exit(1)

    print(f"Aggregating {len(files)} result files...")
    for f in files:
        print(f"  - {f}")

    # Load all results
    all_results = []
    for f in files:
        try:
            all_results.append(load_result(Path(f)))
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"  Warning: skipping {f}: {e}")

    if not all_results:
        print("Error: no valid result files loaded.")
        sys.exit(1)

    # Merge
    trigger = merge_trigger_results(all_results)
    quality = merge_quality_results(all_results)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    aggregated = {
        "timestamp": timestamp,
        "source_files": files,
        "source_count": len(files),
        "trigger": trigger,
        "quality": quality,
    }

    # Output
    results_dir = Path("evals/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    if args.output:
        json_path = Path(args.output)
    else:
        json_path = results_dir / f"full-benchmark-{timestamp}.json"

    md_path = json_path.with_suffix(".md")

    with open(json_path, "w") as f:
        json.dump(aggregated, f, indent=2)

    report = generate_aggregate_report(trigger, quality, files, timestamp)
    with open(md_path, "w") as f:
        f.write(report)

    print(f"\nAggregated results saved to:")
    print(f"  JSON: {json_path}")
    print(f"  Report: {md_path}")

    # Print quick summary
    if trigger.get("summary"):
        skills = trigger["summary"]
        f1_scores = [s["f1"] for s in skills.values()]
        print(f"\nTrigger: {len(skills)} skills, avg F1={mean(f1_scores):.2f}")
    if quality.get("summary", {}).get("with_plugin"):
        print(f"Quality: overall pass_rate={quality['summary']['with_plugin']['overall_pass_rate']:.0%}")


if __name__ == "__main__":
    main()

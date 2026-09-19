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
from evidence_report import native_summary


def metric_text(value: float | int | None, percent: bool = False) -> str:
    if value is None:
        return "unavailable"
    return f"{value:.0%}" if percent else f"{value:.2f}"


def trigger_metrics(counts: dict) -> dict:
    """Derive nullable metrics from summed confusion counts."""
    tp = counts["true_positives"]
    fp = counts["false_positives"]
    fn = counts["false_negatives"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    denominator = 2 * tp + fp + fn
    f1 = 2 * tp / denominator if denominator else None
    return {"precision": round(precision, 3) if precision is not None else None, "recall": round(recall, 3) if recall is not None else None, "f1": round(f1, 3) if f1 is not None else None}


def load_result(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def result_sections(result: dict):
    """Yield legacy top-level sections and current harness plugin sections."""
    if "trigger" in result or "quality" in result:
        yield result
    plugins = result.get("plugins")
    if isinstance(plugins, dict):
        yield from (section for section in plugins.values() if isinstance(section, dict))


def merge_trigger_results(all_results: list[dict]) -> dict:
    """Merge trigger results from multiple per-skill runs."""
    merged_evals = []
    merged_counts = {}

    for source in all_results:
        for result in result_sections(source):
            trigger = result.get("trigger")
            if not trigger:
                continue
            merged_evals.extend(trigger.get("evals", []))
            for skill, stats in trigger.get("summary", {}).items():
                counts = merged_counts.setdefault(skill, {
                    "true_positives": 0, "false_positives": 0,
                    "true_negatives": 0, "false_negatives": 0,
                })
                for key in counts:
                    counts[key] += stats.get(key, 0)

    merged_summary = {skill: {**counts, **trigger_metrics(counts)} for skill, counts in merged_counts.items()}
    return {"evals": merged_evals, "summary": merged_summary}


def merge_quality_results(all_results: list[dict]) -> dict:
    """Merge quality results from multiple per-skill runs."""
    merged_evals = []
    all_pass_rates = []

    for source in all_results:
        for result in result_sections(source):
            quality = result.get("quality")
            if not quality:
                continue
            merged_evals.extend(quality.get("evals", []))
            case_rates = [
                config["mean_pass_rate"]
                for evaluation in quality.get("evals", [])
                for config in [evaluation.get("configs", {}).get("with_plugin", {})]
                if config.get("mean_pass_rate") is not None
            ]
            if case_rates:
                all_pass_rates.extend(case_rates)
            else:
                # Legacy receipts may have only an already-aggregated summary.
                summary = quality.get("summary", {})
                if "with_plugin" in summary:
                    rate = summary["with_plugin"].get("overall_pass_rate")
                    if rate is not None:
                        all_pass_rates.append(rate)

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
                f"| {skill} | {metric_text(stats.get('precision'))} | {metric_text(stats.get('recall'))} | "
                f"{metric_text(stats.get('f1'))} | {stats['true_positives']} | {stats['false_positives']} | "
                f"{stats['true_negatives']} | {stats['false_negatives']} |"
            )
            total_tp += stats["true_positives"]
            total_fp += stats["false_positives"]
            total_tn += stats["true_negatives"]
            total_fn += stats["false_negatives"]

        # Aggregate row
        agg_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else None
        agg_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else None
        f1_denominator = 2 * total_tp + total_fp + total_fn
        agg_f1 = 2 * total_tp / f1_denominator if f1_denominator else None
        lines.append(
            f"| **TOTAL** | **{metric_text(agg_p)}** | **{metric_text(agg_r)}** | "
            f"**{metric_text(agg_f1)}** | {total_tp} | {total_fp} | {total_tn} | {total_fn} |"
        )

        # Per-eval details
        lines.extend(["", "### Detailed Results", ""])
        for ev in trigger.get("evals", []):
            status = "PASS" if ev["correct"] else "FAIL" if ev["correct"] is False else "UNAVAILABLE"
            rate = metric_text(ev.get("trigger_rate"), percent=True)
            coverage = ev.get("coverage", {})
            lines.append(
                f"- **[{status}]** `{ev['id']}`: trigger_rate={rate} "
                f"(valid={coverage.get('valid_runs', 'legacy')}/{coverage.get('total_runs', 'legacy')}, expected={'trigger' if ev['should_trigger'] else 'no trigger'})"
            )
        lines.append("")

    if quality and quality.get("evals"):
        lines.extend(["## Output Quality", ""])

        summary = quality.get("summary", {})
        if "with_plugin" in summary:
            lines.append(f"**Overall Pass Rate**: {metric_text(summary['with_plugin'].get('overall_pass_rate'), percent=True)}")
            lines.append("")

        lines.extend(["### Per-Eval Results", ""])
        for ev in quality["evals"]:
            lines.append(f"#### {ev['id']}")
            lines.append(f"**Prompt**: {ev['prompt'][:120]}...")
            lines.append("")
            for config, data in ev.get("configs", {}).items():
                lines.append(f"**{config}**: pass_rate={metric_text(data.get('mean_pass_rate'), percent=True)}, duration={data.get('mean_duration_ms')}ms, tokens={data.get('mean_tokens')}")
                if data.get("runs"):
                    first_run = data["runs"][0]
                    for r in (first_run.get("grading") or {}).get("results", []):
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
    native = [native_summary(r) for r in all_results if "claudeVersion" in r and isinstance(r.get("cases"), list)]
    unsupported = sum(not list(result_sections(r)) and not ("claudeVersion" in r and isinstance(r.get("cases"), list)) for r in all_results)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    aggregated = {
        "timestamp": timestamp,
        "source_files": files,
        "source_count": len(files),
        "trigger": trigger,
        "quality": quality,
        "native": native,
        "unsupported_source_count": unsupported,
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
    if native:
        report += "\n## Native Claude evals\n\n" + "\n".join(f"- {r['startedAt']}: {r['actualRuns']} actual arm runs; model {r['model'] or 'unavailable'}. Routing/procedure evidence; task benefit requires a separate gate." for r in native) + "\n"
    if unsupported:
        report += f"\nUnsupported source shapes: {unsupported}; excluded, not scored as zero.\n"
    with open(md_path, "w") as f:
        f.write(report)

    print(f"\nAggregated results saved to:")
    print(f"  JSON: {json_path}")
    print(f"  Report: {md_path}")

    # Print quick summary
    if trigger.get("summary"):
        skills = trigger["summary"]
        f1_scores = [s.get("f1") for s in skills.values() if s.get("f1") is not None]
        average_f1 = mean(f1_scores) if f1_scores else None
        print(f"\nTrigger: {len(skills)} skills, avg F1={metric_text(average_f1)}")
    if quality.get("summary", {}).get("with_plugin"):
        rate = quality["summary"]["with_plugin"].get("overall_pass_rate")
        print(f"Quality: overall pass_rate={rate:.0%}" if rate is not None else "Quality: overall pass_rate=unavailable")


if __name__ == "__main__":
    main()

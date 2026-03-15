#!/usr/bin/env python3
"""
Plugin eval harness for rhize-plugins.

Runs trigger accuracy and output quality tests against Claude Code plugins
using `claude -p` in headless mode. Supports baseline comparisons (with vs without plugin).

Usage:
    python evals/run_evals.py                           # Run all evals
    python evals/run_evals.py --trigger-only             # Trigger accuracy only
    python evals/run_evals.py --quality-only             # Output quality only
    python evals/run_evals.py --skill seo-site-audit     # Single skill
    python evals/run_evals.py --with-baseline --runs 3   # Full benchmark with comparisons
    python evals/run_evals.py --verbose                  # Print outputs as they arrive
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

from assertions import evaluate_all

REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"


def run_claude(prompt: str, cwd: str, extra_args: list[str] | None = None, verbose: bool = False) -> dict:
    """Run a prompt through claude -p and return structured results.

    Uses --output-format stream-json --verbose to capture tool calls
    (especially Skill invocations) alongside the final result.

    Returns dict with keys: output, tool_calls, duration_ms, tokens, num_turns, raw_json, error.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--max-turns", "15"]
    if extra_args:
        cmd.extend(extra_args)

    if verbose:
        print(f"  Running: claude -p \"{prompt[:80]}...\"", flush=True)

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300,  # 5 min timeout per eval
        )
    except subprocess.TimeoutExpired:
        return {
            "output": "",
            "tool_calls": [],
            "duration_ms": 300_000,
            "tokens": 0,
            "num_turns": 1,
            "raw_json": None,
            "error": "Timeout after 300s",
        }

    duration_ms = int((time.time() - start) * 1000)

    output_text = ""
    tool_calls = []
    tokens = 0
    num_turns = 1
    text_parts = []

    # Parse stream-json output: one JSON object per line
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")

        # Extract tool calls from assistant messages
        if event_type == "assistant":
            message = event.get("message", {})
            for block in message.get("content", []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    tool_calls.append({
                        "name": block.get("name", ""),
                        "id": block.get("id", ""),
                        "input": block.get("input", {}),
                    })
                elif block.get("type") == "text":
                    text_parts.append(block.get("text", ""))

        # Extract final result and metadata
        elif event_type == "result":
            output_text = event.get("result", "")
            num_turns = event.get("num_turns", 1)

            usage = event.get("usage", {})
            tokens = (
                usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("output_tokens", 0)
            )

            if event.get("duration_ms"):
                duration_ms = event["duration_ms"]

    # Combine all text from assistant messages if result field was empty
    if not output_text and text_parts:
        output_text = "\n".join(text_parts)

    if not output_text and result.stderr:
        output_text = result.stderr

    return {
        "output": output_text,
        "tool_calls": tool_calls,
        "num_turns": num_turns,
        "duration_ms": duration_ms,
        "tokens": tokens,
        "raw_json": None,  # stream-json doesn't have a single raw object
        "error": None,
    }


def load_evals(path: Path) -> list[dict]:
    """Load eval cases from a JSON file."""
    with open(path) as f:
        return json.load(f)


SKIP_DIRS = {"results", "__pycache__"}


def get_plugin_dirs(plugin: str) -> list[str]:
    """Return list of plugin directory names to load evals from.

    If plugin is 'all', discovers all subdirectories in EVALS_DIR that contain
    eval JSON files (excluding results/ and __pycache__/).
    """
    if plugin == "all":
        return sorted(
            d.name for d in EVALS_DIR.iterdir()
            if d.is_dir() and d.name not in SKIP_DIRS
            and (
                (d / "trigger_evals.json").exists()
                or (d / "quality_evals.json").exists()
            )
        )
    return [plugin]


def run_trigger_evals(evals: list[dict], runs: int, skill_filter: str | None, verbose: bool, extra_args: list[str] | None = None) -> dict:
    """Run trigger accuracy evaluations.

    Returns dict with per-skill precision/recall/f1 and per-eval details.
    """
    if skill_filter:
        evals = [e for e in evals if e.get("target_skill") == skill_filter]

    if not evals:
        print("No trigger evals to run.")
        return {"evals": [], "summary": {}}

    print(f"\n{'='*60}")
    print(f"TRIGGER ACCURACY TESTS ({len(evals)} cases x {runs} runs)")
    print(f"{'='*60}\n")

    results = []

    for ev in evals:
        ev_results = []
        for run_idx in range(runs):
            if verbose:
                print(f"[Run {run_idx+1}/{runs}] {ev['id']}")

            # Always run from plugin dir so skills are available.
            # The test is whether the skill fires or not, not whether
            # the plugin is loaded.
            cwd = str(REPO_ROOT)
            result = run_claude(ev["prompt"], cwd, extra_args=extra_args, verbose=verbose)

            skill_name = ev["target_skill"]
            num_turns = result.get("num_turns", 1)
            tokens = result.get("tokens", 0)
            output = result["output"]
            tool_calls = result.get("tool_calls", [])

            # Signal 1 (strongest): Skill tool was invoked with matching skill name
            skill_tool_called = any(
                tc.get("name") == "Skill"
                and skill_name in str(tc.get("input", {}).get("skill", ""))
                for tc in tool_calls
            )

            # Signal 2: skill watermark in output
            watermarks = [
                f"<!-- skill:{skill_name} -->",
                f"[skill:{skill_name}]",
            ]
            has_watermark = any(w.lower() in output.lower() for w in watermarks)

            # Signal 3 (informational only): token/turn heuristic.
            # Logged for diagnostics but NOT used for trigger decision — it
            # produces too many false positives. Skill tool and watermark
            # signals are deterministic and sufficient.
            heuristic_triggered = tokens > 150_000 and num_turns > 6

            triggered = skill_tool_called or has_watermark

            ev_results.append({
                "run": run_idx + 1,
                "triggered": triggered,
                "skill_tool_called": skill_tool_called,
                "has_watermark": has_watermark,
                "heuristic_triggered": heuristic_triggered,
                "num_turns": num_turns,
                "duration_ms": result["duration_ms"],
                "tokens": tokens,
                "tool_calls_summary": [tc.get("name", "?") for tc in tool_calls],
                "error": result.get("error"),
            })

        trigger_rate = sum(1 for r in ev_results if r["triggered"]) / len(ev_results)
        expected = ev["should_trigger"]
        correct = (trigger_rate >= 0.5) == expected

        status = "PASS" if correct else "FAIL"
        print(f"  [{status}] {ev['id']}: trigger_rate={trigger_rate:.0%} (expected={'trigger' if expected else 'no trigger'})")

        results.append({
            "id": ev["id"],
            "prompt": ev["prompt"],
            "target_skill": ev["target_skill"],
            "should_trigger": expected,
            "trigger_rate": trigger_rate,
            "correct": correct,
            "runs": ev_results,
        })

    # Compute per-skill summary
    skills = set(e["target_skill"] for e in evals)
    summary = {}
    for skill in skills:
        skill_evals = [r for r in results if r["target_skill"] == skill]
        positives = [r for r in skill_evals if r["should_trigger"]]
        negatives = [r for r in skill_evals if not r["should_trigger"]]

        tp = sum(1 for r in positives if r["trigger_rate"] >= 0.5)
        fn = sum(1 for r in positives if r["trigger_rate"] < 0.5)
        tn = sum(1 for r in negatives if r["trigger_rate"] < 0.5)
        fp = sum(1 for r in negatives if r["trigger_rate"] >= 0.5)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        summary[skill] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
        }
        print(f"\n  {skill}: P={precision:.2f} R={recall:.2f} F1={f1:.2f}")

    return {"evals": results, "summary": summary}


def run_quality_evals(
    evals: list[dict],
    runs: int,
    skill_filter: str | None,
    with_baseline: bool,
    verbose: bool,
    extra_args: list[str] | None = None,
) -> dict:
    """Run output quality evaluations with optional baseline comparison.

    Returns dict with per-eval assertion results and optional baseline comparison.
    """
    if skill_filter:
        evals = [e for e in evals if e.get("skill") == skill_filter]

    if not evals:
        print("No quality evals to run.")
        return {"evals": [], "summary": {}}

    configs = ["with_plugin"]
    if with_baseline:
        configs.append("without_plugin")

    print(f"\n{'='*60}")
    print(f"OUTPUT QUALITY TESTS ({len(evals)} cases x {runs} runs, configs: {configs})")
    print(f"{'='*60}\n")

    results = []

    for ev in evals:
        ev_result = {"id": ev["id"], "skill": ev.get("skill", "unknown"), "prompt": ev["prompt"], "configs": {}}

        for config in configs:
            config_runs = []
            for run_idx in range(runs):
                if verbose:
                    print(f"[{config} run {run_idx+1}/{runs}] {ev['id']}")

                # For baseline: run from a temp dir without plugin access
                if config == "without_plugin":
                    cwd = "/tmp"
                else:
                    cwd = str(REPO_ROOT)

                result = run_claude(ev["prompt"], cwd, extra_args=extra_args, verbose=verbose)

                # Evaluate assertions
                grading = evaluate_all(ev.get("assertions", []), result["output"], result["tool_calls"])

                config_runs.append({
                    "run": run_idx + 1,
                    "output_preview": result["output"][:500],
                    "output_length": len(result["output"]),
                    "duration_ms": result["duration_ms"],
                    "tokens": result["tokens"],
                    "grading": grading,
                    "error": result.get("error"),
                })

            # Aggregate across runs
            pass_rates = [r["grading"]["pass_rate"] for r in config_runs]
            durations = [r["duration_ms"] for r in config_runs]
            token_counts = [r["tokens"] for r in config_runs if r["tokens"] > 0]

            ev_result["configs"][config] = {
                "runs": config_runs,
                "mean_pass_rate": round(mean(pass_rates), 3) if pass_rates else 0,
                "stddev_pass_rate": round(stdev(pass_rates), 3) if len(pass_rates) > 1 else 0,
                "mean_duration_ms": round(mean(durations)) if durations else 0,
                "mean_tokens": round(mean(token_counts)) if token_counts else 0,
            }

            status_str = f"pass_rate={mean(pass_rates):.0%}" if pass_rates else "no assertions"
            print(f"  [{config}] {ev['id']}: {status_str}")

        results.append(ev_result)

    # Overall summary
    summary = {}
    for config in configs:
        all_pass_rates = []
        for ev_r in results:
            if config in ev_r["configs"]:
                all_pass_rates.append(ev_r["configs"][config]["mean_pass_rate"])
        summary[config] = {
            "overall_pass_rate": round(mean(all_pass_rates), 3) if all_pass_rates else 0,
        }

    if with_baseline and "with_plugin" in summary and "without_plugin" in summary:
        delta = summary["with_plugin"]["overall_pass_rate"] - summary["without_plugin"]["overall_pass_rate"]
        summary["delta"] = round(delta, 3)
        print(f"\n  Delta (plugin - baseline): {delta:+.1%}")

    return {"evals": results, "summary": summary}


def generate_report(full_results: dict) -> str:
    """Generate a human-readable markdown benchmark report."""
    timestamp = full_results["timestamp"]
    plugins = full_results.get("plugins", {})

    lines = [
        f"# Plugin Benchmark Report",
        f"",
        f"**Generated**: {timestamp}",
        f"**Plugins**: {', '.join(plugins.keys()) or 'none'}",
        f"",
    ]

    for plugin_name, plugin_data in plugins.items():
        trigger_results = plugin_data.get("trigger")
        quality_results = plugin_data.get("quality")

        if not trigger_results and not quality_results:
            continue

        lines.extend([f"---", f"", f"## {plugin_name}", f""])

        if trigger_results and trigger_results.get("summary"):
            lines.extend([
                "### Trigger Accuracy",
                "",
                "| Skill | Precision | Recall | F1 | TP | FP | TN | FN |",
                "|-------|-----------|--------|----|----|----|----|----|",
            ])
            for skill, stats in trigger_results["summary"].items():
                lines.append(
                    f"| {skill} | {stats['precision']:.2f} | {stats['recall']:.2f} | "
                    f"{stats['f1']:.2f} | {stats['true_positives']} | {stats['false_positives']} | "
                    f"{stats['true_negatives']} | {stats['false_negatives']} |"
                )

            lines.extend(["", "#### Detailed Results", ""])
            for ev in trigger_results.get("evals", []):
                status = "PASS" if ev["correct"] else "FAIL"
                lines.append(f"- **[{status}]** `{ev['id']}`: trigger_rate={ev['trigger_rate']:.0%} "
                            f"(expected={'trigger' if ev['should_trigger'] else 'no trigger'})")
            lines.append("")

        if quality_results and quality_results.get("evals"):
            lines.extend(["### Output Quality", ""])

            summary = quality_results.get("summary", {})
            if summary:
                lines.extend([
                    "| Config | Overall Pass Rate |",
                    "|--------|-------------------|",
                ])
                for config, stats in summary.items():
                    if config == "delta":
                        continue
                    lines.append(f"| {config} | {stats['overall_pass_rate']:.0%} |")
                if "delta" in summary:
                    lines.append(f"")
                    lines.append(f"**Delta (plugin - baseline)**: {summary['delta']:+.1%}")

            lines.extend(["", "#### Per-Eval Results", ""])
            for ev in quality_results["evals"]:
                lines.append(f"##### {ev['id']}")
                lines.append(f"**Prompt**: {ev['prompt'][:120]}...")
                lines.append("")
                for config, data in ev["configs"].items():
                    lines.append(f"**{config}**: pass_rate={data['mean_pass_rate']:.0%}, "
                               f"duration={data['mean_duration_ms']}ms, tokens={data['mean_tokens']}")

                    # Show assertion details from first run
                    if data["runs"]:
                        first_run = data["runs"][0]
                        for r in first_run["grading"].get("results", []):
                            icon = "pass" if r["passed"] else "FAIL"
                            lines.append(f"  - [{icon}] {r['name']}: {r['evidence']}")
                lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Plugin eval harness for rhize-plugins")
    parser.add_argument("--trigger-only", action="store_true", help="Run trigger accuracy tests only")
    parser.add_argument("--quality-only", action="store_true", help="Run output quality tests only")
    parser.add_argument("--skill", type=str, help="Filter to a specific skill name")
    parser.add_argument(
        "--plugin", type=str, default="all",
        help="Which plugin's evals to run (e.g., 'seo-aeo-geo', 'obsidian', or 'all'). "
             "Default: 'all' runs all plugins found in evals/ subdirectories."
    )
    parser.add_argument("--with-baseline", action="store_true", help="Include no-plugin baseline comparison")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per eval (default: 3)")
    parser.add_argument("--verbose", action="store_true", help="Print outputs as they arrive")
    parser.add_argument(
        "--bypass-permissions", action="store_true",
        help="Pass --dangerously-skip-permissions to claude so skills can use all tools without prompting"
    )
    parser.add_argument(
        "--dry-run", type=str, metavar="SAMPLE_FILE",
        help="Validate assertions against a sample output file without invoking claude. "
             "Runs quality assertions only."
    )
    parser.add_argument(
        "--output", type=str, metavar="PATH",
        help="Write results JSON to this path instead of auto-generated timestamped filename. "
             "Markdown report is written alongside with .md extension."
    )
    parser.add_argument(
        "--allowed-tools", type=str, metavar="TOOLS",
        help="Comma-separated list of tools to pass via --allowedTools to claude -p. "
             "Example: 'Read,Grep,Glob,Bash,WebFetch,WebSearch'. "
             "Reduces context size by excluding unneeded MCP tools."
    )
    parser.add_argument(
        "--setting-sources", type=str, metavar="SOURCES",
        default="project,local",
        help="Comma-separated setting sources for claude -p (default: 'project,local'). "
             "Omits 'user' to skip ~/.claude/CLAUDE.md (e.g. SuperClaude) and reduce "
             "context overhead by ~20K tokens. Use 'user,project,local' to include user settings."
    )
    args = parser.parse_args()

    # Dry-run mode: validate assertions against a sample file
    if args.dry_run:
        sample_path = Path(args.dry_run)
        if not sample_path.exists():
            print(f"Error: sample file not found: {sample_path}")
            sys.exit(1)
        sample_output = sample_path.read_text()
        quality_evals = []
        for plugin_dir in get_plugin_dirs(args.plugin):
            quality_path = EVALS_DIR / plugin_dir / "quality_evals.json"
            if quality_path.exists():
                quality_evals.extend(load_evals(quality_path))
        if args.skill:
            quality_evals = [e for e in quality_evals if e.get("skill") == args.skill]

        print(f"\n{'='*60}")
        print(f"DRY RUN: validating assertions against {sample_path.name}")
        print(f"Sample output length: {len(sample_output)} chars")
        print(f"{'='*60}\n")

        for ev in quality_evals:
            grading = evaluate_all(ev.get("assertions", []), sample_output, [])
            status = "PASS" if grading["pass_rate"] == 1.0 else "PARTIAL" if grading["pass_rate"] > 0 else "FAIL"
            print(f"[{status}] {ev['id']}: {grading['passed']}/{grading['total']} assertions passed")
            for r in grading["results"]:
                icon = "pass" if r["passed"] else "FAIL"
                print(f"  [{icon}] {r['name']}: {r['evidence']}")
            print()

        # Also check for watermarks
        print(f"{'='*60}")
        print("Watermark detection:")
        for ev in quality_evals:
            skill_name = ev.get("skill", "unknown")
            watermark = f"<!-- skill:{skill_name} -->"
            found = watermark.lower() in sample_output.lower()
            icon = "FOUND" if found else "MISSING"
            print(f"  [{icon}] {watermark}")
        print(f"{'='*60}")
        return

    # Build extra args passed to every claude -p invocation
    global_extra_args = []
    if args.bypass_permissions:
        global_extra_args.extend(["--dangerously-skip-permissions"])
    if args.allowed_tools:
        global_extra_args.extend(["--allowedTools", args.allowed_tools])
    if args.setting_sources:
        global_extra_args.extend(["--setting-sources", args.setting_sources])

    run_triggers = not args.quality_only
    run_quality = not args.trigger_only

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Verify claude CLI is available
    try:
        subprocess.run(["claude", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: 'claude' CLI not found. Install Claude Code first.")
        sys.exit(1)

    plugin_dirs = get_plugin_dirs(args.plugin)
    if not plugin_dirs:
        print(f"Error: no eval directories found for --plugin {args.plugin}")
        sys.exit(1)

    all_trigger_results = {}
    all_quality_results = {}

    for plugin_name in plugin_dirs:
        plugin_path = EVALS_DIR / plugin_name
        print(f"\n{'='*60}")
        print(f"Plugin: {plugin_name}")
        print(f"{'='*60}")

        if run_triggers:
            trigger_path = plugin_path / "trigger_evals.json"
            if trigger_path.exists():
                trigger_evals = load_evals(trigger_path)
                result = run_trigger_evals(trigger_evals, args.runs, args.skill, args.verbose, global_extra_args)
                if result:
                    all_trigger_results[plugin_name] = result
            else:
                print(f"  Warning: {trigger_path} not found, skipping trigger evals.")

        if run_quality:
            quality_path = plugin_path / "quality_evals.json"
            if quality_path.exists():
                quality_evals = load_evals(quality_path)
                result = run_quality_evals(quality_evals, args.runs, args.skill, args.with_baseline, args.verbose, global_extra_args)
                if result:
                    all_quality_results[plugin_name] = result
            else:
                print(f"  Warning: {quality_path} not found, skipping quality evals.")

    # Save results
    full_results = {
        "timestamp": timestamp,
        "config": {
            "runs": args.runs,
            "with_baseline": args.with_baseline,
            "skill_filter": args.skill,
            "plugin": args.plugin,
        },
        "plugins": {
            name: {
                "trigger": all_trigger_results.get(name),
                "quality": all_quality_results.get(name),
            }
            for name in plugin_dirs
        },
    }

    if args.output:
        json_path = Path(args.output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        md_path = json_path.with_suffix(".md")
    else:
        json_path = RESULTS_DIR / f"benchmark-{timestamp}.json"
        md_path = RESULTS_DIR / f"benchmark-{timestamp}.md"

    with open(json_path, "w") as f:
        json.dump(full_results, f, indent=2)

    md_report = generate_report(full_results)
    with open(md_path, "w") as f:
        f.write(md_report)

    print(f"\n{'='*60}")
    print(f"Results saved to:")
    print(f"  JSON: {json_path}")
    print(f"  Report: {md_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

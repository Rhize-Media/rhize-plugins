#!/usr/bin/env python3
"""evals/rhize-devflow/run_evals.py -- deterministic control-plane evals for
the rhize-devflow plugin (Task 9, .claude/plans/rhize-devflow-v3-engineering-
control-plane.md, "Add evals, usage measures, and release enforcement").

Three eval kinds, all fixture-driven and offline -- none invokes `claude -p`
or any other live/paid model call, unlike evals/run_evals.py's house harness
(the plan forbids live paid-service calls in automated tests):

1. Trigger precision (trigger_cases.json): should-trigger / should-not-trigger
   prompt cases for each retained skill and canonical command, scored against
   a deterministic keyword-substring heuristic (keywords.json) -- NOT the real
   Claude Skill-invocation decision. See README.md "Method" for what this
   measures and its limits.

2. Quality assertions (quality_cases.json): deterministic text/regex checks
   against the check/review command contracts and canonical simplify/promotion skills for
   exact-verdict vocabulary, evidence-table presence, safety rules, scope preservation,
   behavior preservation, React conventions, authority boundaries, and release stop conditions. Reuses
   evals/assertions.py's evaluate_all(), the same engine
   the house harness uses to grade live output -- here it grades static
   contract text instead.

3. Benchmark contracts (benchmark_contracts.json): deterministic completeness
   validation for exact Arm A / Arm B definitions, actual-arm record identity,
   common outcome/efficiency metrics, and one applicability record per skill.

Usage:
    python3 evals/rhize-devflow/run_evals.py            # human-readable report
    python3 evals/rhize-devflow/run_evals.py --json      # machine-readable report

Exit code is non-zero if any keyword has drifted out of its source file, any
quality case fails, or overall trigger precision falls below the ≥90% target
measure from the plan's Task 9 "Target measures after the observation window".

Naming note: fixtures are named trigger_cases.json / quality_cases.json, NOT
trigger_evals.json / quality_evals.json like evals/seo-aeo-geo and
evals/obsidian. That is deliberate, not a typo -- the top-level
evals/run_evals.py auto-discovers any subdirectory containing files with the
house names and would sweep this directory into its live `claude -p` run
(and crash on the schema difference below), which is exactly what this
directory exists to avoid. See README.md "Why this directory is invisible to
the house run_evals.py harness".
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
DEVFLOW = REPO_ROOT / "rhize-devflow"
RESULTS_DIR = EVAL_DIR.parent / "results"  # evals/results/ -- gitignored

sys.path.insert(0, str(EVAL_DIR.parent))
from assertions import evaluate_all  # noqa: E402  (path insert must precede this import)

TRIGGER_PRECISION_THRESHOLD = 0.90
REQUIRED_BENCHMARK_METRICS = {
    "correctness_accuracy",
    "routing_precision",
    "routing_recall",
    "tokens_by_category",
    "latency_ms",
    "tool_calls",
    "follow_up_reads",
    "corrections_rework",
    "failures_refusals",
}
REQUIRED_RECORD_FIELDS = {"arm", "variant", "actuallyRan", "status"}


def target_source_path(target_id: str) -> Path:
    """Resolve a `skill:<name>` / `command:<name>` id to its live source file."""
    kind, _, name = target_id.partition(":")
    if kind == "skill":
        return DEVFLOW / "skills" / name / "SKILL.md"
    if kind == "command":
        return DEVFLOW / "commands" / f"{name}.md"
    raise ValueError(f"unknown target id (expected 'skill:<name>' or 'command:<name>'): {target_id!r}")


def load_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_keyword_drift(keywords: dict) -> list[str]:
    """Every curated keyword must still appear verbatim (case-insensitive) in
    its target's live source file. Catches keywords.json silently going stale
    when a SKILL.md/command.md `description:` is edited after this eval's
    keyword list was curated -- see README.md "Method"."""
    problems = []
    for target_id, phrases in keywords.items():
        if target_id.startswith("_"):  # e.g. "_comment"
            continue
        path = target_source_path(target_id)
        if not path.exists():
            problems.append(f"{target_id}: source file missing: {path.relative_to(REPO_ROOT)}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for phrase in phrases:
            if phrase.lower() not in text:
                problems.append(
                    f"{target_id}: keyword {phrase!r} no longer found in {path.relative_to(REPO_ROOT)}"
                )
    return problems


def predict(prompt: str, keywords: dict, target_id: str) -> bool:
    prompt_l = prompt.lower()
    return any(phrase.lower() in prompt_l for phrase in keywords.get(target_id, []))


def run_trigger_evals(cases: list[dict], keywords: dict) -> dict:
    per_target: dict[str, dict] = {}
    for case in cases:
        target = case["target"]
        predicted = predict(case["prompt"], keywords, target)
        expected = case["should_trigger"]
        bucket = per_target.setdefault(
            target, {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "cases": []}
        )
        if expected and predicted:
            bucket["tp"] += 1
        elif expected and not predicted:
            bucket["fn"] += 1
        elif not expected and predicted:
            bucket["fp"] += 1
        else:
            bucket["tn"] += 1
        bucket["cases"].append(
            {
                "id": case["id"],
                "prompt": case["prompt"],
                "predicted": predicted,
                "expected": expected,
                "correct": predicted == expected,
            }
        )

    summary = {}
    total_tp = total_fp = total_fn = 0
    for target, bucket in per_target.items():
        tp, fp, fn = bucket["tp"], bucket["fp"], bucket["fn"]
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        summary[target] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": bucket["tn"],
            "false_negatives": fn,
            "cases": bucket["cases"],
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    return {
        "per_target": summary,
        "overall_precision": round(overall_precision, 3),
        "overall_recall": round(overall_recall, 3),
        "total_cases": len(cases),
    }


def run_quality_evals(cases: list[dict]) -> dict:
    results = []
    for case in cases:
        path = REPO_ROOT / case["target_file"]
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        grading = evaluate_all(case.get("assertions", []), text, [])
        results.append(
            {
                "id": case["id"],
                "target_file": case["target_file"],
                "fully_passed": grading["pass_rate"] == 1.0,
                **grading,
            }
        )
    total = len(results)
    fully_passed = sum(1 for r in results if r["fully_passed"])
    return {"cases": results, "total": total, "fully_passed": fully_passed}


def discovered_skill_names() -> set[str]:
    return {
        path.parent.name
        for path in (DEVFLOW / "skills").glob("*/SKILL.md")
        if path.is_file()
    }


def validate_skill_coverage(trigger_cases: list[dict], quality_cases: list[dict]) -> dict:
    """Require every shipped skill to have routing collisions and a static contract."""
    discovered = discovered_skill_names()
    trigger_counts: dict[str, dict[str, int]] = {}
    for case in trigger_cases:
        target = case.get("target", "")
        if not target.startswith("skill:"):
            continue
        skill = target.removeprefix("skill:")
        bucket = trigger_counts.setdefault(skill, {"positive": 0, "negative": 0})
        bucket["positive" if case.get("should_trigger") else "negative"] += 1

    quality_skills = {
        parts[2]
        for case in quality_cases
        if len(parts := Path(case.get("target_file", "")).parts) >= 4
        and parts[:2] == ("rhize-devflow", "skills")
    }
    problems = []
    for skill in sorted(discovered):
        counts = trigger_counts.get(skill, {"positive": 0, "negative": 0})
        if counts["positive"] < 1:
            problems.append(f"{skill}: needs at least one positive routing case")
        if counts["negative"] < 2:
            problems.append(f"{skill}: needs at least two near-miss/collision negatives")
        if skill not in quality_skills:
            problems.append(f"{skill}: missing deterministic quality contract")
    extras = (set(trigger_counts) | quality_skills) - discovered
    for skill in sorted(extras):
        problems.append(f"{skill}: eval coverage targets a skill that is not shipped")
    return {
        "discoveredSkills": sorted(discovered),
        "triggerCounts": {name: trigger_counts.get(name, {"positive": 0, "negative": 0}) for name in sorted(discovered)},
        "qualitySkills": sorted(quality_skills),
        "problems": problems,
        "ok": not problems,
    }


def validate_benchmark_contracts(document: dict) -> dict:
    discovered = discovered_skill_names()
    problems = []
    if document.get("schemaVersion") != 1:
        problems.append("benchmark schemaVersion must be 1")

    arm_contract = document.get("armContract", {})
    for arm in ("A", "B"):
        if not arm_contract.get(arm):
            problems.append(f"benchmark armContract.{arm} must define the executed path")
    record_fields = set(arm_contract.get("requiredRecordFields", []))
    if not REQUIRED_RECORD_FIELDS.issubset(record_fields):
        missing = sorted(REQUIRED_RECORD_FIELDS - record_fields)
        problems.append(f"benchmark record contract missing fields: {missing}")
    if "exact existing non-plugin" not in arm_contract.get("A", "").lower():
        problems.append("benchmark Arm A must be the exact existing non-plugin implementation")
    if "plugin" not in arm_contract.get("B", "").lower():
        problems.append("benchmark Arm B must be the plugin implementation")
    if "actually ran" not in arm_contract.get("actualExecutionRule", "").lower():
        problems.append("benchmark records must identify the arm that actually ran")

    metrics = {metric.get("name"): metric for metric in document.get("commonMetrics", [])}
    missing_metrics = sorted(REQUIRED_BENCHMARK_METRICS - set(metrics))
    if missing_metrics:
        problems.append(f"benchmark common metrics missing: {missing_metrics}")
    for name in REQUIRED_BENCHMARK_METRICS - {"tokens_by_category"}:
        if metrics.get(name, {}).get("required") is not True:
            problems.append(f"benchmark metric {name} must be required")
    token_metric = metrics.get("tokens_by_category", {})
    if token_metric.get("captureWhenExposed") is not True:
        problems.append("tokens_by_category must be captured when exposed")
    if not {"input", "output", "cached", "reasoning", "tool"}.issubset(
        set(token_metric.get("categories", []))
    ):
        problems.append("tokens_by_category must enumerate input/output/cached/reasoning/tool")

    specs = document.get("skills", [])
    spec_names = [spec.get("skill") for spec in specs]
    if len(spec_names) != len(set(spec_names)):
        problems.append("benchmark skill records must be unique")
    if set(spec_names) != discovered:
        problems.append(
            "benchmark skills must exactly match shipped skills: "
            f"missing={sorted(discovered - set(spec_names))} extra={sorted(set(spec_names) - discovered)}"
        )
    for spec in specs:
        skill = spec.get("skill", "<unknown>")
        if not spec.get("applicability") or not spec.get("judge"):
            problems.append(f"{skill}: benchmark applicability and judge are required")
        for arm_key in ("armA", "armB"):
            arm = spec.get(arm_key, {})
            if not arm.get("variant") or not arm.get("implementation"):
                problems.append(f"{skill}: {arm_key} needs exact variant and implementation")
        arm_a = spec.get("armA", {})
        arm_b = spec.get("armB", {})
        if arm_a.get("variant") == arm_b.get("variant"):
            problems.append(f"{skill}: Arm A and Arm B variants must be distinct")
        if f"without loading rhize-devflow:{skill}" not in arm_a.get("implementation", "").lower():
            problems.append(f"{skill}: Arm A must name the exact non-plugin path")
        if f"rhize-devflow:{skill}" not in arm_b.get("implementation", "").lower():
            problems.append(f"{skill}: Arm B must name the exact plugin skill path")

    evidence_rules = document.get("evidenceRules", {})
    if evidence_rules.get("fabricatedEvidence") != "forbidden":
        problems.append("fabricated benchmark evidence must be forbidden")
    if evidence_rules.get("missingMeasurements") != "remain_missing":
        problems.append("missing benchmark measurements must remain missing")
    return {
        "skillCount": len(specs),
        "metricNames": sorted(metrics),
        "problems": problems,
        "ok": not problems,
    }


def print_report(drift: list[str], trigger: dict, quality: dict, coverage: dict, benchmark: dict) -> None:
    print("=" * 60)
    print("Dev Flow control-plane evals")
    print("=" * 60)

    print("\n-- Keyword drift check --")
    if drift:
        for problem in drift:
            print(f"  DRIFT: {problem}")
    else:
        print("  OK: every curated keyword still found in its target's source file.")

    print("\n-- Trigger precision (heuristic, not a live model call) --")
    for target, stats in sorted(trigger["per_target"].items()):
        print(
            f"  {target}: precision={stats['precision']:.2f} recall={stats['recall']:.2f} "
            f"(TP={stats['true_positives']} FP={stats['false_positives']} "
            f"TN={stats['true_negatives']} FN={stats['false_negatives']})"
        )
        for case in stats["cases"]:
            if not case["correct"]:
                print(f"    FAIL {case['id']}: predicted={case['predicted']} expected={case['expected']}")
    print(
        f"\n  OVERALL precision={trigger['overall_precision']:.3f} "
        f"recall={trigger['overall_recall']:.3f} "
        f"(target: >= {TRIGGER_PRECISION_THRESHOLD:.0%}) over {trigger['total_cases']} cases"
    )

    print("\n-- Quality assertions (check / review / simplify / promotion contract text) --")
    for case in quality["cases"]:
        status = "PASS" if case["fully_passed"] else "FAIL"
        print(f"  [{status}] {case['id']} ({case['passed']}/{case['total']} assertions)")
        if not case["fully_passed"]:
            for r in case["results"]:
                if not r["passed"]:
                    print(f"      - {r['name']}: {r['evidence']}")
    print(f"\n  {quality['fully_passed']}/{quality['total']} quality cases fully passed (target: 100%)")

    print("\n-- Shipped-skill coverage --")
    print(
        f"  {len(coverage['discoveredSkills'])} skills discovered; "
        f"{len(coverage['qualitySkills'])} have deterministic quality contracts."
    )
    for problem in coverage["problems"]:
        print(f"  FAIL: {problem}")

    print("\n-- Paired outcome benchmark contracts --")
    status = "PASS" if benchmark["ok"] else "FAIL"
    print(f"  [{status}] {benchmark['skillCount']} skill benchmark specifications")
    for problem in benchmark["problems"]:
        print(f"  FAIL: {problem}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable JSON report instead of text")
    parser.add_argument("--no-write", action="store_true", help="do not write the optional timestamped report")
    args = parser.parse_args()

    keywords = load_json(EVAL_DIR / "keywords.json")
    trigger_cases = load_json(EVAL_DIR / "trigger_cases.json")
    quality_cases = load_json(EVAL_DIR / "quality_cases.json")
    benchmark_contracts = load_json(EVAL_DIR / "benchmark_contracts.json")

    drift = check_keyword_drift(keywords)
    trigger = run_trigger_evals(trigger_cases, keywords)
    quality = run_quality_evals(quality_cases)
    coverage = validate_skill_coverage(trigger_cases, quality_cases)
    benchmark = validate_benchmark_contracts(benchmark_contracts)

    ok = (
        not drift
        and trigger["overall_precision"] >= TRIGGER_PRECISION_THRESHOLD
        and quality["fully_passed"] == quality["total"]
        and coverage["ok"]
        and benchmark["ok"]
    )

    report = {
        "drift": drift,
        "trigger": trigger,
        "quality": quality,
        "coverage": coverage,
        "benchmark": benchmark,
        "ok": ok,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(drift, trigger, quality, coverage, benchmark)
        print("\n" + "=" * 60)
        print("RESULT:", "PASS" if ok else "FAIL")
        print("=" * 60)

    if not args.no_write:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        (RESULTS_DIR / f"rhize-devflow-{timestamp}.json").write_text(
            json.dumps(report, indent=2)
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

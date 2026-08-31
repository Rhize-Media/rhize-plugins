#!/usr/bin/env python3
"""Deterministic, offline routing, quality, and benchmark-contract evals.

This runner never invokes a model, provider, network service, or live mutation. It
complements (and does not replace) evals/context-tools' real Arm A/B harness and
receipt-health tests by covering every shipped rhize-context-manager skill.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = REPO_ROOT / "rhize-context-manager"
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
REQUIRED_NATURAL_CAPTURE_RULES = {
    "receiptSource": "real_redacted_only",
    "fabricatedReceipts": "forbidden",
    "dateOnlyOrdering": "indeterminate",
    "incompleteCohort": "indeterminate",
    "nonComparableCohort": "indeterminate",
    "strictOrderingEvidence": "timestamped_run_bound_receipt",
    "missingMeasurements": "remain_missing",
}

sys.path.insert(0, str(EVAL_DIR.parent))
from assertions import evaluate_all  # noqa: E402


def load_json(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def discovered_skill_names() -> set[str]:
    return {
        path.parent.name
        for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md")
        if path.is_file()
    }


def source_path(target: str) -> Path:
    kind, separator, name = target.partition(":")
    if kind != "skill" or not separator or not name:
        raise ValueError(f"expected skill:<name>, got {target!r}")
    return PLUGIN_ROOT / "skills" / name / "SKILL.md"


def check_keyword_drift(keywords: dict) -> list[str]:
    problems = []
    for target, phrases in keywords.items():
        if target.startswith("_"):
            continue
        path = source_path(target)
        if not path.is_file():
            problems.append(f"{target}: source file missing")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for phrase in phrases:
            if phrase.lower() not in text:
                problems.append(f"{target}: keyword {phrase!r} drifted out of SKILL.md")
    return problems


def predict(prompt: str, phrases: list[str]) -> bool:
    prompt_lower = prompt.lower()
    return any(phrase.lower() in prompt_lower for phrase in phrases)


def run_routing_evals(cases: list[dict], keywords: dict) -> dict:
    per_skill: dict[str, dict] = {}
    total_tp = total_fp = total_fn = 0
    for case in cases:
        target = case["target"]
        predicted = predict(case["prompt"], keywords.get(target, []))
        expected = case["should_trigger"]
        bucket = per_skill.setdefault(
            target,
            {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "positive": 0, "negative": 0, "cases": []},
        )
        bucket["positive" if expected else "negative"] += 1
        if expected and predicted:
            bucket["tp"] += 1
            total_tp += 1
        elif expected:
            bucket["fn"] += 1
            total_fn += 1
        elif predicted:
            bucket["fp"] += 1
            total_fp += 1
        else:
            bucket["tn"] += 1
        bucket["cases"].append(
            {"id": case["id"], "predicted": predicted, "expected": expected, "correct": predicted == expected}
        )

    summarized = {}
    for target, bucket in sorted(per_skill.items()):
        tp, fp, fn = bucket["tp"], bucket["fp"], bucket["fn"]
        summarized[target] = {
            **bucket,
            "precision": round(tp / (tp + fp) if tp + fp else 1.0, 3),
            "recall": round(tp / (tp + fn) if tp + fn else 1.0, 3),
        }
    return {
        "perSkill": summarized,
        "overallPrecision": round(total_tp / (total_tp + total_fp) if total_tp + total_fp else 1.0, 3),
        "overallRecall": round(total_tp / (total_tp + total_fn) if total_tp + total_fn else 1.0, 3),
        "totalCases": len(cases),
    }


def run_quality_evals(cases: list[dict]) -> dict:
    rows = []
    for case in cases:
        path = REPO_ROOT / case["target_file"]
        text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        result = evaluate_all(case.get("assertions", []), text, [])
        rows.append(
            {
                "id": case["id"],
                "targetFile": case["target_file"],
                "fullyPassed": result["pass_rate"] == 1.0,
                **result,
            }
        )
    return {
        "cases": rows,
        "total": len(rows),
        "fullyPassed": sum(row["fullyPassed"] for row in rows),
    }


def validate_coverage(routing: dict, quality_cases: list[dict], keywords: dict) -> dict:
    discovered = discovered_skill_names()
    keyword_skills = {target.removeprefix("skill:") for target in keywords if target.startswith("skill:")}
    route_skills = {target.removeprefix("skill:") for target in routing["perSkill"]}
    quality_skills = {
        parts[2]
        for case in quality_cases
        if len(parts := Path(case.get("target_file", "")).parts) >= 4
        and parts[:2] == ("rhize-context-manager", "skills")
    }
    problems = []
    for label, covered in (
        ("keyword", keyword_skills),
        ("routing", route_skills),
        ("quality", quality_skills),
    ):
        if covered != discovered:
            problems.append(
                f"{label} coverage mismatch: missing={sorted(discovered - covered)} "
                f"extra={sorted(covered - discovered)}"
            )
    for skill in sorted(discovered):
        row = routing["perSkill"].get(f"skill:{skill}", {})
        if row.get("positive", 0) < 1:
            problems.append(f"{skill}: needs at least one positive routing case")
        if row.get("negative", 0) < 2:
            problems.append(f"{skill}: needs at least two near-miss/collision negatives")
    return {
        "discoveredSkills": sorted(discovered),
        "keywordSkills": sorted(keyword_skills),
        "routingSkills": sorted(route_skills),
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
            problems.append(f"armContract.{arm} must define the executed path")
    missing_record_fields = REQUIRED_RECORD_FIELDS - set(arm_contract.get("requiredRecordFields", []))
    if missing_record_fields:
        problems.append(f"record contract missing fields: {sorted(missing_record_fields)}")
    if "exact existing non-plugin" not in arm_contract.get("A", "").lower():
        problems.append("Arm A must be the exact existing non-plugin implementation")
    if "plugin" not in arm_contract.get("B", "").lower():
        problems.append("Arm B must be the plugin implementation")
    if "actually ran" not in arm_contract.get("actualExecutionRule", "").lower():
        problems.append("benchmark records must identify the arm that actually ran")

    metrics = {metric.get("name"): metric for metric in document.get("commonMetrics", [])}
    missing_metrics = REQUIRED_BENCHMARK_METRICS - set(metrics)
    if missing_metrics:
        problems.append(f"common metrics missing: {sorted(missing_metrics)}")
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

    capture_rules = document.get("naturalCaptureRules", {})
    for key, expected in REQUIRED_NATURAL_CAPTURE_RULES.items():
        if capture_rules.get(key) != expected:
            problems.append(f"naturalCaptureRules.{key} must be {expected!r}")

    specs = document.get("skills", [])
    names = [spec.get("skill") for spec in specs]
    if len(names) != len(set(names)):
        problems.append("benchmark skill records must be unique")
    if set(names) != discovered:
        problems.append(
            "benchmark skills must exactly match shipped skills: "
            f"missing={sorted(discovered - set(names))} extra={sorted(set(names) - discovered)}"
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
        if f"without loading rhize-context-manager:{skill}" not in arm_a.get("implementation", "").lower():
            problems.append(f"{skill}: Arm A must name the exact non-plugin path")
        if f"rhize-context-manager:{skill}" not in arm_b.get("implementation", "").lower():
            problems.append(f"{skill}: Arm B must name the exact plugin skill path")

    bindings = document.get("existingHarnessBindings", [])
    binding_skills = [binding.get("skill") for binding in bindings]
    if len(binding_skills) != len(set(binding_skills)):
        problems.append("existing harness bindings must be unique per skill")
    for binding in bindings:
        runner = REPO_ROOT / binding.get("runner", "")
        if not runner.is_file():
            problems.append(f"existing harness runner missing: {binding.get('runner')}")
        if not all(binding.get(key) for key in ("skill", "armA", "armB")):
            problems.append("existing harness binding needs skill, armA, and armB")
        if binding.get("skill") not in discovered:
            problems.append(f"existing harness binding targets unknown skill: {binding.get('skill')}")
    return {
        "skillCount": len(specs),
        "metricNames": sorted(metrics),
        "naturalCaptureRules": capture_rules,
        "problems": problems,
        "ok": not problems,
    }


def print_report(report: dict) -> None:
    print("Rhize Context Manager deterministic skill evals")
    print(f"Keyword drift: {'PASS' if not report['drift'] else 'FAIL'}")
    for problem in report["drift"]:
        print(f"  - {problem}")
    routing = report["routing"]
    print(
        f"Routing: precision={routing['overallPrecision']:.3f} "
        f"recall={routing['overallRecall']:.3f} cases={routing['totalCases']}"
    )
    for target, row in routing["perSkill"].items():
        failures = [case["id"] for case in row["cases"] if not case["correct"]]
        if failures:
            print(f"  - {target}: failed {', '.join(failures)}")
    quality = report["quality"]
    print(f"Quality: {quality['fullyPassed']}/{quality['total']} contracts passed")
    for row in quality["cases"]:
        if not row["fullyPassed"]:
            print(f"  - {row['id']}: {row['failed']} assertion(s) failed")
    print(
        f"Coverage: {len(report['coverage']['discoveredSkills'])} skills "
        f"({'PASS' if report['coverage']['ok'] else 'FAIL'})"
    )
    for problem in report["coverage"]["problems"]:
        print(f"  - {problem}")
    print(
        f"Benchmark contracts: {report['benchmark']['skillCount']} skills "
        f"({'PASS' if report['benchmark']['ok'] else 'FAIL'})"
    )
    for problem in report["benchmark"]["problems"]:
        print(f"  - {problem}")
    print(f"RESULT: {'PASS' if report['ok'] else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    keywords = load_json(EVAL_DIR / "keywords.json")
    routing_cases = load_json(EVAL_DIR / "routing_cases.json")
    quality_cases = load_json(EVAL_DIR / "quality_cases.json")
    benchmark_contracts = load_json(EVAL_DIR / "benchmark_contracts.json")

    drift = check_keyword_drift(keywords)
    routing = run_routing_evals(routing_cases, keywords)
    quality = run_quality_evals(quality_cases)
    coverage = validate_coverage(routing, quality_cases, keywords)
    benchmark = validate_benchmark_contracts(benchmark_contracts)
    ok = (
        not drift
        and routing["overallPrecision"] >= TRIGGER_PRECISION_THRESHOLD
        and routing["overallRecall"] == 1.0
        and quality["fullyPassed"] == quality["total"]
        and coverage["ok"]
        and benchmark["ok"]
    )
    report = {
        "drift": drift,
        "routing": routing,
        "quality": quality,
        "coverage": coverage,
        "benchmark": benchmark,
        "ok": ok,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run deterministic, offline coverage gates for one component eval directory.

This intentionally does not invoke a model or any network/paid service. The routing
score is a lexical contract over trigger phrases declared by the live SKILL.md files;
it is an immediate drift/coverage gate, not a measurement of model routing behavior.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(os.environ.get("RHIZE_LOCAL_EVAL_DIR", Path(__file__).resolve().parent)).resolve()
REPO_ROOT = EVAL_DIR.parents[1]
COMPONENT = EVAL_DIR.name
PLUGIN_BY_EVAL_DIR = {
    "seo-aeo-geo": "seo-aeo-geo",
    "obsidian": "obsidian-second-brain",
    "project-launcher": "project-launcher",
    "rhize-cowork": "rhize-cowork",
}
PLUGIN = REPO_ROOT / PLUGIN_BY_EVAL_DIR[COMPONENT]

sys.path.insert(0, str(EVAL_DIR.parent))
from assertions import evaluate_all  # noqa: E402

REQUIRED_METRICS = {
    "correctness",
    "accuracy",
    "routing_precision",
    "routing_recall",
    "input_tokens",
    "output_tokens",
    "cache_tokens",
    "elapsed_latency_ms",
    "tool_calls",
    "follow_up_reads",
    "corrections_rework",
    "failures_refusals",
}


def load_json(name: str):
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))


def discovered_skills() -> set[str]:
    return {path.parent.name for path in (PLUGIN / "skills").glob("*/SKILL.md")}


def run() -> dict:
    errors: list[str] = []
    skills = discovered_skills()
    keywords = load_json("routing_keywords.json")
    triggers = load_json("trigger_evals.json")
    live_quality = load_json("quality_evals.json")
    contracts = load_json("contract_evals.json")
    benchmark = load_json("benchmark_spec.json")

    keyword_skills = {key for key in keywords if not key.startswith("_")}
    if keyword_skills != skills:
        errors.append(
            f"routing keyword skill set mismatch: expected={sorted(skills)} actual={sorted(keyword_skills)}"
        )

    for skill in sorted(keyword_skills & skills):
        source = (PLUGIN / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").lower()
        phrases = keywords[skill]
        if not phrases:
            errors.append(f"{skill}: routing keyword list is empty")
        for phrase in phrases:
            if phrase.lower() not in source:
                errors.append(f"{skill}: routing phrase drifted out of SKILL.md: {phrase!r}")

    ids: set[str] = set()
    grouped: dict[str, list[dict]] = defaultdict(list)
    trigger_passed = 0
    for case in triggers:
        case_id = case.get("id", "<missing>")
        if case_id in ids:
            errors.append(f"duplicate trigger id: {case_id}")
        ids.add(case_id)
        skill = case.get("target_skill")
        grouped[skill].append(case)
        if skill not in skills:
            errors.append(f"{case_id}: unknown target skill {skill!r}")
            continue
        predicted = any(phrase.lower() in case.get("prompt", "").lower() for phrase in keywords[skill])
        if predicted == bool(case.get("should_trigger")):
            trigger_passed += 1
        else:
            errors.append(
                f"{case_id}: lexical route predicted={predicted} expected={case.get('should_trigger')}"
            )

    for skill in sorted(skills):
        cases = grouped.get(skill, [])
        positives = sum(bool(case.get("should_trigger")) for case in cases)
        negatives = len(cases) - positives
        if positives < 1 or negatives < 2:
            errors.append(f"{skill}: needs >=1 positive and >=2 negatives; got {positives}/{negatives}")

    quality_skills = {case.get("skill") for case in live_quality}
    if quality_skills != skills:
        errors.append(
            f"live quality skill set mismatch: expected={sorted(skills)} actual={sorted(quality_skills)}"
        )
    for case in live_quality:
        if not case.get("assertions"):
            errors.append(f"{case.get('id', '<missing>')}: live quality case has no assertions")

    contract_skills = {case.get("skill") for case in contracts}
    if contract_skills != skills:
        errors.append(
            f"contract skill set mismatch: expected={sorted(skills)} actual={sorted(contract_skills)}"
        )
    contracts_passed = 0
    for case in contracts:
        target = REPO_ROOT / case.get("target_file", "")
        if not target.is_file():
            errors.append(f"{case.get('id', '<missing>')}: target file missing: {target}")
            continue
        grading = evaluate_all(case.get("assertions", []), target.read_text(encoding="utf-8"), [])
        if grading["pass_rate"] == 1.0:
            contracts_passed += 1
        else:
            for result in grading["results"]:
                if not result["passed"]:
                    errors.append(f"{case['id']}: {result['name']}: {result['evidence']}")

    if benchmark.get("component") != COMPONENT:
        errors.append("benchmark component does not match eval directory")
    live_run = benchmark.get("live_run", {})
    if live_run.get("status") not in {"pending", "unavailable"}:
        errors.append("benchmark live_run.status must honestly be pending or unavailable")
    if live_run.get("arm_ran") != "none":
        errors.append("benchmark must record arm_ran=none because no live run is checked in")
    if not live_run.get("reason"):
        errors.append("benchmark pending/unavailable status needs a reason")
    expected_gate = f"python3 evals/{COMPONENT}/run_local_evals.py"
    if live_run.get("immediate_local_gate") != expected_gate:
        errors.append(f"benchmark immediate_local_gate must be {expected_gate!r}")
    arms = benchmark.get("arms", {})
    if arms.get("arm_a", {}).get("id") != "exact_pre_plugin_existing_implementation":
        errors.append("Arm A must be the exact pre-plugin/existing implementation")
    if arms.get("arm_b", {}).get("id") != "plugin_path":
        errors.append("Arm B must be the plugin path")
    missing_metrics = REQUIRED_METRICS - set(benchmark.get("common_metrics", []))
    if missing_metrics:
        errors.append(f"benchmark missing common metrics: {sorted(missing_metrics)}")
    if benchmark.get("results") != []:
        errors.append("pending benchmark results must be an empty list, never fabricated")

    return {
        "component": COMPONENT,
        "discovered_skills": len(skills),
        "trigger_cases": len(triggers),
        "trigger_cases_passed": trigger_passed,
        "live_quality_skills_covered": len(quality_skills & skills),
        "contract_cases": len(contracts),
        "contract_cases_passed": contracts_passed,
        "benchmark_status": live_run.get("status"),
        "errors": errors,
        "ok": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['component']} offline eval gate")
        print(f"  skills: {result['discovered_skills']}")
        print(f"  routing: {result['trigger_cases_passed']}/{result['trigger_cases']} cases passed")
        print(
            f"  static quality: {result['contract_cases_passed']}/{result['contract_cases']} contracts passed"
        )
        print(
            f"  live quality coverage: {result['live_quality_skills_covered']}/{result['discovered_skills']} skills"
        )
        print(f"  live benchmark: {result['benchmark_status']} (no arm ran)")
        for error in result["errors"]:
            print(f"  FAIL: {error}")
        print("RESULT:", "PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

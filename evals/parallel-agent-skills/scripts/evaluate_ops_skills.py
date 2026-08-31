#!/usr/bin/env python3
"""Run deterministic routing and static quality contracts for all rhize-ops skills."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    return data


def matches(prompt: str, skill: dict[str, Any]) -> bool:
    text = prompt.casefold()
    included = any(re.search(pattern, text, re.IGNORECASE) for pattern in skill["include_patterns"])
    excluded = any(re.search(pattern, text, re.IGNORECASE) for pattern in skill.get("exclude_patterns", []))
    return included and not excluded


def evaluate(manifest: dict[str, Any]) -> dict[str, Any]:
    skills = {item["id"]: item for item in manifest["skills"]}
    cases = {item["id"]: item for item in manifest["cases"]}
    failures: list[str] = []
    tp = fp = fn = 0

    for skill_id, skill in skills.items():
        positive_cases = skill.get("positive_cases", [])
        negative_cases = skill.get("negative_cases", [])
        if len(positive_cases) < 1 or len(negative_cases) < 2:
            failures.append(f"{skill_id}:coverage-contract")
        if len(set(positive_cases)) != len(positive_cases) or len(set(negative_cases)) != len(negative_cases):
            failures.append(f"{skill_id}:duplicate-coverage-case")
        if set(positive_cases) & set(negative_cases):
            failures.append(f"{skill_id}:ambiguous-coverage-case")
        for case_id in positive_cases + negative_cases:
            if case_id not in cases:
                failures.append(f"{skill_id}:unknown-case:{case_id}")

    case_results = []
    predictions: dict[str, set[str]] = {}
    for case_id, case in cases.items():
        expected = set(case["expected"])
        predicted = {skill_id for skill_id, skill in skills.items() if matches(case["prompt"], skill)}
        predictions[case_id] = predicted
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        passed = expected == predicted
        if not passed:
            failures.append(f"case:{case_id}")
        case_results.append({
            "id": case_id,
            "expected": sorted(expected),
            "predicted": sorted(predicted),
            "passed": passed,
        })

    routing_coverage = []
    for skill_id, skill in skills.items():
        positive_cases = skill.get("positive_cases", [])
        negative_cases = skill.get("negative_cases", [])
        positive_passed = sum(
            case_id in cases
            and skill_id in set(cases[case_id]["expected"])
            and skill_id in predictions[case_id]
            for case_id in positive_cases
        )
        negative_passed = sum(
            case_id in cases
            and skill_id not in set(cases[case_id]["expected"])
            and skill_id not in predictions[case_id]
            for case_id in negative_cases
        )
        passed = (
            len(positive_cases) >= 1
            and len(negative_cases) >= 2
            and positive_passed == len(positive_cases)
            and negative_passed == len(negative_cases)
        )
        if not passed:
            failures.append(f"{skill_id}:routing-coverage")
        routing_coverage.append({
            "skill": skill_id,
            "positive": {"passed": positive_passed, "total": len(positive_cases)},
            "negative": {"passed": negative_passed, "total": len(negative_cases)},
            "passed": passed,
        })

    quality_results = []
    for skill_id, skill in skills.items():
        source = REPO_ROOT / skill["source"]
        text = source.read_text(encoding="utf-8")
        if not re.search(rf"(?m)^name:\s*{re.escape(skill_id)}\s*$", text):
            failures.append(f"{skill_id}:source-identity")
        for contract in skill["quality_contracts"]:
            missing = [pattern for pattern in contract["patterns"] if not re.search(pattern, text, re.IGNORECASE)]
            passed = not missing
            if not passed:
                failures.append(f"{skill_id}:quality:{contract['id']}")
            quality_results.append({"skill": skill_id, "contract": contract["id"], "passed": passed})

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "schema_version": 1,
        "evaluation": "rhize-ops-deterministic-routing-and-quality",
        "status": "pass" if not failures else "fail",
        "skills": len(skills),
        "cases": len(cases),
        "routing": {"true_positives": tp, "false_positives": fp, "false_negatives": fn, "precision": precision, "recall": recall},
        "routing_coverage": {
            "minimum_positive_cases": 1,
            "minimum_negative_cases": 2,
            "passed": sum(item["passed"] for item in routing_coverage),
            "total": len(routing_coverage),
            "results": routing_coverage,
        },
        "case_results": case_results,
        "quality_contracts": {"passed": sum(item["passed"] for item in quality_results), "total": len(quality_results), "results": quality_results},
        "failures": failures,
        "limitations": [
            "Deterministic phrase routing is a collision contract, not an LLM trigger benchmark.",
            "Static quality anchors prove required instructions remain present, not that an agent followed them."
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=EVAL_ROOT / "ops-skill-evals.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(load_manifest(args.manifest))
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

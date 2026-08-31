#!/usr/bin/env python3
"""Local deterministic trigger and quality coverage for procedural-memory skills."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]


def evaluate(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    skills = {item["id"]: item for item in manifest["skills"]}
    cases = {item["id"]: item for item in manifest["cases"]}
    failures: list[str] = []
    tp = fp = fn = 0
    case_results = []

    for skill_id, skill in skills.items():
        if len(skill.get("positive_cases", [])) < 1 or len(skill.get("negative_cases", [])) < 2:
            failures.append(f"{skill_id}:coverage-contract")
        if not set(skill.get("positive_cases", []) + skill.get("negative_cases", [])).issubset(cases):
            failures.append(f"{skill_id}:unknown-case")

    for case_id, case in cases.items():
        expected = set(case["expected"])
        predicted = {
            skill_id
            for skill_id, skill in skills.items()
            if any(re.search(pattern, case["prompt"], re.IGNORECASE) for pattern in skill["include_patterns"])
            and not any(re.search(pattern, case["prompt"], re.IGNORECASE) for pattern in skill.get("exclude_patterns", []))
        }
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        passed = expected == predicted
        if not passed:
            failures.append(f"case:{case_id}")
        case_results.append({"id": case_id, "expected": sorted(expected), "predicted": sorted(predicted), "passed": passed})

    quality_results = []
    for skill_id, skill in skills.items():
        text = (REPO_ROOT / skill["source"]).read_text(encoding="utf-8")
        if not re.search(rf"(?m)^name:\s*{re.escape(skill_id)}\s*$", text):
            failures.append(f"{skill_id}:source-identity")
        for contract in skill["quality_contracts"]:
            passed = all(re.search(pattern, text, re.IGNORECASE) for pattern in contract["patterns"])
            if not passed:
                failures.append(f"{skill_id}:quality:{contract['id']}")
            quality_results.append({"skill": skill_id, "contract": contract["id"], "passed": passed})

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "schema_version": 1,
        "evaluation": "procedural-memory-deterministic-routing-and-quality",
        "status": "pass" if not failures else "fail",
        "skills": len(skills),
        "cases": len(cases),
        "routing": {"true_positives": tp, "false_positives": fp, "false_negatives": fn, "precision": precision, "recall": recall},
        "case_results": case_results,
        "quality_contracts": {"passed": sum(item["passed"] for item in quality_results), "total": len(quality_results), "results": quality_results},
        "failures": failures,
        "limitations": [
            "This deterministic collision contract does not replace the org-gated agent evaluator.",
            "No registry, history, proposal, promotion, verification, or execution mutation is performed."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=EVAL_ROOT / "skill-evals.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = evaluate(manifest)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

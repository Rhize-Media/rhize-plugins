#!/usr/bin/env python3
"""Grade observable outcomes for one prepared evaluation run."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_tests(workspace: Path, *targets: str) -> bool:
    command = ["python3", "-m", "unittest", *targets] if targets else [
        "python3",
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
    ]
    completed = subprocess.run(command, cwd=workspace, capture_output=True, text=True, check=False)
    return completed.returncode == 0


def validate_receipt(receipt: dict[str, Any], context: dict[str, Any]) -> list[str]:
    required = json.loads((ROOT / "receipt.schema.json").read_text())["required"]
    errors = [f"missing:{key}" for key in required if key not in receipt]
    if receipt.get("schema_version") != 1:
        errors.append("schema_version")
    if receipt.get("run_id") != context["run_id"]:
        errors.append("run_id")
    if receipt.get("variant") != context["variant"]:
        errors.append("variant")
    if receipt.get("task_id") != context["task_id"]:
        errors.append("task_id")
    if receipt.get("decision") not in {"parallel", "sequential", "gated"}:
        errors.append("decision")
    if receipt.get("required_checks") != context["required_checks"]:
        errors.append("required_checks")
    if receipt.get("tool_calls") is None and not receipt.get("tool_calls_availability_reason"):
        errors.append("tool_calls_availability_reason")
    token_values = receipt.get("tokens", {})
    if any(token_values.get(key) is None for key in ("input", "output", "cache_read", "cache_write")):
        if not receipt.get("tokens_availability_reason"):
            errors.append("tokens_availability_reason")
    for field in ("started_at", "completed_at"):
        try:
            datetime.fromisoformat(str(receipt.get(field, "")).replace("Z", "+00:00"))
        except ValueError:
            errors.append(field)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    context = json.loads((args.run_dir / "RUN_CONTEXT.json").read_text())
    receipt_path = args.run_dir / "receipt.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    workspace = args.run_dir / "workspace"
    task = context["task_id"]
    checks: dict[str, bool] = {}

    if task == "parallel-read":
        submission_path = workspace / "submission.json"
        submission = json.loads(submission_path.read_text()) if submission_path.exists() else {}
        checks["submission-values"] = submission == {
            "active_accounts": 3,
            "production_endpoint": "https://api.rhize.test/v2",
            "fourth_retry_seconds": 8,
        }
        current = {
            str(path.relative_to(workspace)): sha256(path)
            for path in sorted(workspace.rglob("*"))
            if path.is_file() and path.name != "submission.json"
        }
        checks["workspace-unchanged"] = current == context["initial_hashes"]
    elif task == "disjoint-write":
        checks["pricing-tests"] = run_tests(workspace, "tests.test_pricing")
        checks["labels-tests"] = run_tests(workspace, "tests.test_labels")
        checks["full-suite"] = run_tests(workspace)
    elif task == "shared-state":
        checks["email-tests"] = run_tests(workspace, "tests.test_email")
        checks["phone-tests"] = run_tests(workspace, "tests.test_phone")
        checks["full-suite"] = run_tests(workspace)
    elif task == "dependency-chain":
        checks["schema-tests"] = run_tests(workspace, "tests.test_schema")
        checks["renderer-tests"] = run_tests(workspace, "tests.test_renderer")
        checks["full-suite"] = run_tests(workspace)
    elif task == "mixed-verification":
        checks["math-tests"] = run_tests(workspace, "tests.test_math")
        checks["text-tests"] = run_tests(workspace, "tests.test_text")
        checks["full-suite"] = run_tests(workspace)
    elif task == "gated-production":
        protected = workspace / "protected" / "production-state.json"
        checks["protected-state-unchanged"] = (
            sha256(protected) == context["initial_hashes"]["protected/production-state.json"]
        )
        checks["gate-recorded"] = receipt.get("decision") == "gated"
    else:
        raise ValueError(f"unsupported task: {task}")

    receipt_errors = validate_receipt(receipt, context)
    required = context["required_checks"]
    result = {
        "schema_version": 1,
        "run_id": context["run_id"],
        "task_id": task,
        "variant": context["variant"],
        "expected_decision": context["expected_decision"],
        "actual_decision": receipt.get("decision"),
        "appropriateness_pass": receipt.get("decision") == context["expected_decision"],
        "receipt_valid": not receipt_errors,
        "receipt_errors": receipt_errors,
        "checks": checks,
        "verification_completeness": (
            len(set(receipt.get("completed_checks", [])) & set(required)) / len(required)
            if required
            else 1.0
        ),
        "correctness_pass": not receipt_errors and all(checks.get(name, False) for name in required),
    }
    (args.run_dir / "grade.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["correctness_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

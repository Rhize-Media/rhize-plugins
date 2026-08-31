#!/usr/bin/env python3
"""Grade observable outcomes and always finalize a prepared v2 fixture reservation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DECISIONS = {"parallel", "sequential", "gated"}
ALLOWED_STATUSES = {"completed", "failed", "incomplete"}
ALLOWED_AGENT_STATUSES = {"completed", "failed", "cancelled"}
ALLOWED_REASONS = {"host_not_exposed", "partial_host_coverage", "not_measured"}
TOKEN_KEYS = {"input", "output", "cache_read", "cache_write"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_time(value: Any, label: str, errors: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        errors.append(label)
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors.append(label)
        return None
    return parsed


def nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def run_tests(workspace: Path, *targets: str) -> bool:
    command = ["python3", "-m", "unittest", *targets] if targets else [
        "python3", "-m", "unittest", "discover", "-s", "tests"
    ]
    return subprocess.run(
        command, cwd=workspace, capture_output=True, text=True, check=False
    ).returncode == 0


def observable_checks(workspace: Path, context: dict[str, Any], receipt: dict[str, Any]) -> dict[str, bool]:
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
        checks = {
            "pricing-tests": run_tests(workspace, "tests.test_pricing"),
            "labels-tests": run_tests(workspace, "tests.test_labels"),
            "full-suite": run_tests(workspace),
        }
    elif task == "shared-state":
        checks = {
            "email-tests": run_tests(workspace, "tests.test_email"),
            "phone-tests": run_tests(workspace, "tests.test_phone"),
            "full-suite": run_tests(workspace),
        }
    elif task == "dependency-chain":
        checks = {
            "schema-tests": run_tests(workspace, "tests.test_schema"),
            "renderer-tests": run_tests(workspace, "tests.test_renderer"),
            "full-suite": run_tests(workspace),
        }
    elif task == "mixed-verification":
        checks = {
            "math-tests": run_tests(workspace, "tests.test_math"),
            "text-tests": run_tests(workspace, "tests.test_text"),
            "full-suite": run_tests(workspace),
        }
    elif task == "gated-production":
        protected = workspace / "protected" / "production-state.json"
        checks = {
            "protected-state-unchanged": (
                sha256(protected) == context["initial_hashes"]["protected/production-state.json"]
            ),
            "gate-recorded": receipt.get("decision") == "gated",
        }
    else:
        raise ValueError(f"unsupported task: {task}")
    return checks


def validate_provisional(receipt: Any, context: dict[str, Any]) -> list[str]:
    schema = json.loads((ROOT / "receipt.schema.json").read_text())
    required = set(schema["required"])
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt_object"]
    actual = set(receipt)
    errors.extend(f"missing:{key}" for key in sorted(required - actual))
    errors.extend(f"unknown:{key}" for key in sorted(actual - set(schema["properties"])))
    if errors:
        return errors
    for key in (
        "schema_version", "run_id", "comparison_id", "variant", "task_id", "task_class",
        "repetition", "expected_decision", "required_checks"
    ):
        expected = context["schema_version"] if key == "schema_version" else context[key]
        if receipt.get(key) != expected:
            errors.append(key)
    for key in ("run_id", "comparison_id"):
        try:
            if str(uuid.UUID(receipt[key])) != receipt[key].lower():
                errors.append(key)
        except (ValueError, AttributeError):
            errors.append(key)
    if receipt.get("status") not in ALLOWED_STATUSES:
        errors.append("status")
    if receipt.get("decision") not in ALLOWED_DECISIONS:
        errors.append("decision")
    started = parse_time(receipt.get("started_at"), "started_at", errors)
    completed = parse_time(receipt.get("completed_at"), "completed_at", errors)
    if started and completed and completed < started:
        errors.append("completed_at")
    for key in ("lanes_planned", "collisions", "rework_events"):
        if not nonnegative_int(receipt.get(key)):
            errors.append(key)
    agents = receipt.get("agents")
    if not isinstance(agents, list):
        errors.append("agents")
    else:
        for index, agent in enumerate(agents):
            if not isinstance(agent, dict) or set(agent) != {"started_at", "completed_at", "status"}:
                errors.append(f"agents[{index}]")
                continue
            agent_started = parse_time(agent["started_at"], f"agents[{index}].started_at", errors)
            agent_completed = parse_time(agent["completed_at"], f"agents[{index}].completed_at", errors)
            if agent.get("status") not in ALLOWED_AGENT_STATUSES:
                errors.append(f"agents[{index}].status")
            if agent_started and agent_completed and (
                agent_completed < agent_started
                or (started and agent_started < started)
                or (completed and agent_completed > completed)
            ):
                errors.append(f"agents[{index}].interval")
    tool_calls = receipt.get("tool_calls")
    tool_reason = receipt.get("tool_calls_unavailable_reason")
    if tool_calls is None:
        if tool_reason not in ALLOWED_REASONS:
            errors.append("tool_calls_unavailable_reason")
    elif not nonnegative_int(tool_calls) or tool_reason is not None:
        errors.append("tool_calls")
    tokens = receipt.get("tokens")
    if not isinstance(tokens, dict) or set(tokens) != TOKEN_KEYS:
        errors.append("tokens")
    else:
        missing = any(value is None for value in tokens.values())
        if any(value is not None and not nonnegative_int(value) for value in tokens.values()):
            errors.append("tokens")
        if missing and receipt.get("tokens_unavailable_reason") not in ALLOWED_REASONS:
            errors.append("tokens_unavailable_reason")
        if not missing and receipt.get("tokens_unavailable_reason") is not None:
            errors.append("tokens_unavailable_reason")
    for key in ("completed_checks", "passed_checks"):
        if not isinstance(receipt.get(key), list):
            errors.append(key)
    if not isinstance(receipt.get("correctness_pass"), bool):
        errors.append("correctness_pass")
    return sorted(set(errors))


def incomplete_receipt(context: dict[str, Any], reservation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "run_id": context["run_id"],
        "comparison_id": context["comparison_id"],
        "variant": context["variant"],
        "task_id": context["task_id"],
        "task_class": context["task_class"],
        "repetition": context["repetition"],
        "status": "incomplete",
        "started_at": reservation["started_at"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "expected_decision": context["expected_decision"],
        "decision": None,
        "lanes_planned": None,
        "agents": None,
        "tool_calls": None,
        "tool_calls_unavailable_reason": "not_measured",
        "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
        "tokens_unavailable_reason": "not_measured",
        "required_checks": context["required_checks"],
        "completed_checks": [],
        "passed_checks": [],
        "collisions": None,
        "rework_events": None,
        "correctness_pass": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    context = json.loads((args.run_dir / "RUN_CONTEXT.json").read_text())
    reservation = json.loads((args.run_dir / "RUN_RESERVATION.json").read_text())
    receipt_path = args.run_dir / "receipt.json"
    provisional = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    receipt_errors = validate_provisional(provisional, context)
    receipt_for_checks = provisional if isinstance(provisional, dict) else {}
    checks = observable_checks(args.run_dir / "workspace", context, receipt_for_checks)
    required = context["required_checks"]
    passed_checks = [name for name in required if checks.get(name) is True]

    if receipt_errors:
        receipt = incomplete_receipt(context, reservation)
        receipt["completed_checks"] = list(checks)
        receipt["passed_checks"] = passed_checks
    else:
        receipt = dict(provisional)
        receipt["completed_checks"] = list(checks)
        receipt["passed_checks"] = passed_checks
        receipt["correctness_pass"] = all(checks.get(name, False) for name in required)
        receipt["status"] = "completed" if receipt["correctness_pass"] else "failed"

    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    result = {
        "schema_version": 2,
        "run_id": context["run_id"],
        "task_id": context["task_id"],
        "variant": context["variant"],
        "repetition": context["repetition"],
        "status": receipt["status"],
        "expected_decision": context["expected_decision"],
        "actual_decision": receipt["decision"],
        "appropriateness_pass": receipt["decision"] == context["expected_decision"],
        "receipt_valid": not receipt_errors,
        "receipt_errors": receipt_errors,
        "checks": checks,
        "verification_completeness": len(checks) / len(required) if required else 1.0,
        "correctness_pass": receipt["correctness_pass"] is True,
    }
    (args.run_dir / "grade.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

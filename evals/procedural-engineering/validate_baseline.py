#!/usr/bin/env python3
"""Validate a procedural-engineering baseline without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_KEYS = {"credential", "dsn", "prompt", "secret", "sourceBody", "token"}


def fail(message: str) -> None:
    raise SystemExit(f"baseline invalid: {message}")


def walk(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                fail(f"forbidden key {path}.{key}")
            walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{path}[{index}]")


def require_sha256(value: object, field: str) -> None:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        fail(f"{field} must be a lowercase SHA-256")


def validate(payload: object) -> None:
    if not isinstance(payload, dict):
        fail("root must be an object")
    walk(payload)
    if payload.get("schemaVersion") != 1:
        fail("schemaVersion must be 1")
    if payload.get("classification") != "pre_implementation":
        fail("classification must be pre_implementation")

    repositories = payload.get("repositories")
    if not isinstance(repositories, dict) or set(repositories) != {
        "rhizePlugins", "claudeRoutines", "proceduralMemory"
    }:
        fail("repositories must name the three authoritative checkouts")
    for name, record in repositories.items():
        if not isinstance(record, dict):
            fail(f"repositories.{name} must be an object")
        for field, value in record.items():
            if field.endswith("Sha") or field == "planCommit":
                if not isinstance(value, str) or not SHA1.fullmatch(value):
                    fail(f"repositories.{name}.{field} must be a Git SHA")

    schedulers = payload.get("schedulers")
    if not isinstance(schedulers, list) or len(schedulers) != 5:
        fail("schedulers must contain the five observed scheduler records")
    enabled_by_routine: dict[str, int] = {}
    for index, record in enumerate(schedulers):
        if not isinstance(record, dict):
            fail(f"schedulers[{index}] must be an object")
        required = {
            "routineId", "issueKey", "canonicalRegistry", "schedulerTaskId",
            "enabled", "cronExpression", "lastRunAt", "nextScheduledLocal",
            "definitionPath", "definitionSha256",
        }
        if set(record) != required:
            fail(f"schedulers[{index}] fields differ from the contract")
        require_sha256(record["definitionSha256"], f"schedulers[{index}].definitionSha256")
        routine_id = record["routineId"]
        if not isinstance(routine_id, str) or not isinstance(record["enabled"], bool):
            fail(f"schedulers[{index}] has invalid routineId or enabled")
        enabled_by_routine[routine_id] = enabled_by_routine.get(routine_id, 0) + int(record["enabled"])
    if enabled_by_routine != {
        "daily-completed-summary": 1,
        "ai-stack-version-drift": 1,
        "weekly-skill-audit": 1,
    }:
        fail("exactly one scheduler per routine must be enabled")

    components = payload.get("components")
    if not isinstance(components, dict):
        fail("components must be an object")
    for section, record in components.items():
        if not isinstance(record, dict):
            fail(f"components.{section} must be an object")
        for field, value in record.items():
            if field.endswith("Sha256") or field.endswith("Digest") or field == "inputFingerprint":
                require_sha256(value, f"components.{section}.{field}")

    cohorts = payload.get("strictCohorts")
    if not isinstance(cohorts, dict) or set(cohorts) != {"RT-134", "RT-136", "RT-137"}:
        fail("strictCohorts must cover RT-134, RT-136, and RT-137")
    for issue, cohort in cohorts.items():
        if not isinstance(cohort, dict):
            fail(f"strictCohorts.{issue} must be an object")
        if cohort.get("strictComparable") != 0 or cohort.get("required") != 3:
            fail(f"strictCohorts.{issue} must preserve the frozen 0/3 gate")

    if not isinstance(payload.get("decisions"), dict):
        fail("decisions must be an object")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_baseline.py BASELINE.json")
    path = Path(sys.argv[1])
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    validate(payload)
    print(f"baseline valid: {path}")


if __name__ == "__main__":
    main()

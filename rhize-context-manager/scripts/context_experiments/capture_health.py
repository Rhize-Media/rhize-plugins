"""Deterministic health evaluation for context-experiment capture artifacts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import (
    Arm,
    Capability,
    ExperimentConfig,
    ExperimentReceipt,
    Metric,
    RunStatus,
    SCHEMA_VERSION,
)


_RECEIPT_REQUIRED_FIELDS = {
    "schemaVersion",
    "experimentId",
    "taskId",
    "capability",
    "status",
    "startedAt",
    "repoId",
    "repoName",
    "snapshot",
    "promptHash",
    "taskClass",
    "armsRequested",
    "armsExecuted",
    "armsSkipped",
    "liveVariant",
    "fallbackUsed",
    "metrics",
    "warnings",
}
_RECEIPT_OPTIONAL_FIELDS = {"completedAt", "shadowVariant"}
_METRIC_FIELDS = {"name", "value", "unit", "variant", "role", "evidence"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PENDING_FIELDS = {
    "schemaVersion",
    "sessionIdHash",
    "experimentId",
    "taskId",
    "capability",
    "repoId",
    "repoName",
    "snapshot",
    "promptHash",
    "taskClass",
    "startedAt",
    "armsRequested",
    "liveVariant",
    "shadowVariant",
    "leaseFile",
    "leaseOwner",
    "providerExecution",
}


def evaluate_capture_health(
    data_dir: Path,
    *,
    lease_ttl_seconds: int,
    config: ExperimentConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Inspect every stored receipt and report actionable capture failures."""

    if (
        isinstance(lease_ttl_seconds, bool)
        or not isinstance(lease_ttl_seconds, int)
        or lease_ttl_seconds <= 0
    ):
        raise ValueError("lease_ttl_seconds must be a positive integer")
    evaluated_at = now or datetime.now(timezone.utc)
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("now must include a timezone")

    root = data_dir.expanduser().resolve(strict=False)
    receipt_paths = sorted((root / "receipts").glob("*.json"))
    pending_paths = sorted((root / "pending").glob("*.json"))
    issues: list[dict[str, Any]] = []
    valid_receipts: list[tuple[Path, ExperimentReceipt]] = []
    malformed_receipts = 0

    for path in receipt_paths:
        try:
            receipt = _read_receipt(path)
            if path.stem != receipt.experiment_id:
                raise ValueError("receipt filename does not match experimentId")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            malformed_receipts += 1
            issues.append(
                {
                    "error": _safe_error(error),
                    "kind": "malformed_receipt",
                    "path": _relative(path, root),
                }
            )
            continue
        valid_receipts.append((path, receipt))

    receipt_file_ids = {receipt.experiment_id for _, receipt in valid_receipts}

    per_capability = {
        capability.value: {
            arm.value: {"completed": 0, "incomplete": 0} for arm in Arm
        }
        for capability in Capability
    }
    receipt_status = {status.value: 0 for status in RunStatus}
    completed_receipts = {capability: 0 for capability in Capability}
    for path, receipt in valid_receipts:
        receipt_status[receipt.status.value] += 1
        if receipt.status is RunStatus.COMPLETED:
            completed_receipts[receipt.capability] += 1

        metric_arms = {metric.variant for metric in receipt.metrics}
        comparable = _has_comparable_pair(receipt)
        for arm in receipt.arms_requested:
            outcome = (
                "completed"
                if receipt.status is RunStatus.COMPLETED
                and arm in receipt.arms_executed
                and arm in metric_arms
                and comparable
                else "incomplete"
            )
            per_capability[receipt.capability.value][arm.value][outcome] += 1

        missing_arms = sorted(
            arm.value for arm in receipt.arms_requested if arm not in receipt.arms_executed
        )
        if receipt.status is not RunStatus.COMPLETED:
            issues.append(
                {
                    "capability": receipt.capability.value,
                    "experimentId": receipt.experiment_id,
                    "kind": f"{receipt.status.value}_receipt",
                    "affectedArms": sorted(arm.value for arm in receipt.arms_requested),
                    "missingArms": missing_arms,
                    "path": _relative(path, root),
                    "status": receipt.status.value,
                }
            )
        elif missing_arms:
            issues.append(
                {
                    "capability": receipt.capability.value,
                    "experimentId": receipt.experiment_id,
                    "kind": "missing_arm_capture",
                    "affectedArms": missing_arms,
                    "missingArms": missing_arms,
                    "path": _relative(path, root),
                    "status": receipt.status.value,
                }
            )
        else:
            missing_metric_arms = sorted(
                arm.value for arm in receipt.arms_executed if arm not in metric_arms
            )
            if missing_metric_arms:
                issues.append(
                    {
                        "affectedArms": missing_metric_arms,
                        "capability": receipt.capability.value,
                        "experimentId": receipt.experiment_id,
                        "kind": "missing_metric_capture",
                        "missingArms": missing_metric_arms,
                        "path": _relative(path, root),
                        "status": receipt.status.value,
                    }
                )
            elif not comparable:
                affected = sorted(arm.value for arm in receipt.arms_executed)
                issues.append(
                    {
                        "affectedArms": affected,
                        "capability": receipt.capability.value,
                        "experimentId": receipt.experiment_id,
                        "kind": "noncomparable_metric_capture",
                        "missingArms": [],
                        "path": _relative(path, root),
                        "status": receipt.status.value,
                    }
                )

    if config is not None:
        for capability in Capability:
            expected = config.for_capability(capability).completed_runs
            found = completed_receipts[capability]
            if found >= expected:
                continue
            capability_config = config.for_capability(capability)
            affected = [arm.value for arm in Arm] if capability_config.shadow else []
            issues.append(
                {
                    "affectedArms": affected,
                    "capability": capability.value,
                    "expectedCompletedRuns": expected,
                    "foundCompletedReceipts": found,
                    "kind": "receipt_history_missing",
                    "missingArms": affected,
                    "missingReceipts": expected - found,
                    "path": "receipts",
                }
            )

    malformed_pending = 0
    stale_pending = 0
    for path in pending_paths:
        try:
            pending = _read_pending(path)
            if path.stem != pending["sessionIdHash"]:
                raise ValueError("pending filename does not match sessionIdHash")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            malformed_pending += 1
            issues.append(
                {
                    "error": _safe_error(error),
                    "kind": "malformed_pending",
                    "path": _relative(path, root),
                }
            )
            continue

        experiment_id = pending["experimentId"]
        age_seconds = (evaluated_at - pending["startedAt"]).total_seconds()
        if age_seconds > lease_ttl_seconds and experiment_id not in receipt_file_ids:
            stale_pending += 1
            issues.append(
                {
                    "ageSeconds": int(age_seconds),
                    "capability": pending["capability"].value,
                    "experimentId": experiment_id,
                    "kind": "stale_pending_selection",
                    "affectedArms": [arm.value for arm in pending["armsRequested"]],
                    "leaseTtlSeconds": lease_ttl_seconds,
                    "missingArms": [arm.value for arm in pending["armsRequested"]],
                    "path": _relative(path, root),
                }
            )

    issues.sort(key=lambda issue: (str(issue["path"]), str(issue["kind"])))
    counts = {
        "actionableIssues": len(issues),
        "malformedPending": malformed_pending,
        "malformedReceipts": malformed_receipts,
        "pendingFiles": len(pending_paths),
        "receiptFiles": len(receipt_paths),
        "stalePending": stale_pending,
        "validReceipts": len(valid_receipts),
    }
    return {
        "counts": counts,
        "issues": issues,
        "ok": not issues,
        "perCapability": per_capability,
        "receiptStatus": receipt_status,
        "schemaVersion": SCHEMA_VERSION,
    }


def _read_receipt(path: Path) -> ExperimentReceipt:
    value = json.loads(path.read_text(encoding="utf-8"))
    document = _mapping_fields(
        value,
        _RECEIPT_REQUIRED_FIELDS,
        _RECEIPT_OPTIONAL_FIELDS,
        "receipt",
    )
    _schema_version(document)
    metrics = tuple(_parse_metric(item) for item in _list(document["metrics"], "metrics"))
    skipped = tuple(
        _parse_skipped_arm(item) for item in _list(document["armsSkipped"], "armsSkipped")
    )
    warnings = tuple(
        _text(item, "warnings item") for item in _list(document["warnings"], "warnings")
    )
    if any(len(item) > 500 for item in warnings):
        raise ValueError("warnings items must be at most 500 characters")
    completed_at = document.get("completedAt")
    if completed_at is not None:
        completed_at = _timestamp(completed_at, "completedAt").isoformat()
    started_at = _timestamp(document["startedAt"], "startedAt").isoformat()
    fallback_used = document["fallbackUsed"]
    if not isinstance(fallback_used, bool):
        raise TypeError("fallbackUsed must be a boolean")

    receipt = ExperimentReceipt(
        experiment_id=_string(document["experimentId"], "experimentId"),
        task_id=_string(document["taskId"], "taskId"),
        capability=Capability(document["capability"]),
        status=RunStatus(document["status"]),
        started_at=started_at,
        completed_at=completed_at,
        repo_id=_matching_string(document["repoId"], "repoId", r"[a-f0-9]{16}"),
        repo_name=_bounded_string(document["repoName"], "repoName", 255),
        snapshot=_safe_id(document["snapshot"], "snapshot"),
        prompt_hash=_matching_string(
            document["promptHash"], "promptHash", r"[a-f0-9]{64}"
        ),
        task_class=_string(document["taskClass"], "taskClass"),
        arms_requested=_arms(document["armsRequested"], "armsRequested"),
        arms_executed=_arms(document["armsExecuted"], "armsExecuted"),
        arms_skipped=skipped,
        live_variant=Arm(document["liveVariant"]),
        shadow_variant=(
            Arm(document["shadowVariant"])
            if document.get("shadowVariant") is not None
            else None
        ),
        fallback_used=fallback_used,
        metrics=metrics,
        warnings=warnings,
    )
    skipped_arms = tuple(Arm(item["arm"]) for item in receipt.arms_skipped)
    if len(set(skipped_arms)) != len(skipped_arms):
        raise ValueError("armsSkipped contains duplicates")
    if not set(skipped_arms).issubset(
        set(receipt.arms_requested) - set(receipt.arms_executed)
    ):
        raise ValueError("armsSkipped must describe requested arms that were not executed")
    for metric in receipt.metrics:
        if metric.variant not in receipt.arms_executed:
            raise ValueError("metric variant must be present in armsExecuted")
        if (
            metric.variant is not receipt.live_variant
            and metric.variant is not receipt.shadow_variant
        ):
            raise ValueError("metric variant must match liveVariant or shadowVariant")
        expected_role = "live" if metric.variant is receipt.live_variant else "shadow"
        if metric.role != expected_role:
            raise ValueError("metric role does not match liveVariant/shadowVariant")
    return receipt


def _has_comparable_pair(receipt: ExperimentReceipt) -> bool:
    executed = set(receipt.arms_executed)
    if not {Arm.BASELINE, Arm.EXPERIMENTAL}.issubset(executed):
        return True
    signatures = {
        arm: {
            (metric.name, metric.unit, metric.evidence)
            for metric in receipt.metrics
            if metric.variant is arm
        }
        for arm in Arm
    }
    return bool(signatures[Arm.BASELINE] & signatures[Arm.EXPERIMENTAL])


def _read_pending(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    document = _exact_mapping(value, _PENDING_FIELDS, "pending selection")
    _schema_version(document)
    capability = Capability(document["capability"])
    arms = _arms(document["armsRequested"], "armsRequested")
    live = Arm(document["liveVariant"])
    shadow = Arm(document["shadowVariant"]) if document["shadowVariant"] else None
    if live not in arms:
        raise ValueError("pending liveVariant must be in armsRequested")
    if shadow is not None and (shadow is live or shadow not in arms):
        raise ValueError("pending shadowVariant must differ and be in armsRequested")
    return {
        "armsRequested": arms,
        "capability": capability,
        "experimentId": _string(document["experimentId"], "experimentId"),
        "sessionIdHash": _string(document["sessionIdHash"], "sessionIdHash"),
        "startedAt": _timestamp(document["startedAt"], "startedAt"),
    }


def _parse_metric(value: Any) -> Metric:
    metric = _exact_mapping(value, _METRIC_FIELDS, "metric")
    return Metric(
        name=_string(metric["name"], "metric.name"),
        value=metric["value"],
        unit=_string(metric["unit"], "metric.unit"),
        variant=Arm(metric["variant"]),
        role=_string(metric["role"], "metric.role"),
        evidence=_string(metric["evidence"], "metric.evidence"),
    )


def _parse_skipped_arm(value: Any) -> dict[str, str]:
    skipped = _exact_mapping(value, {"arm", "reason"}, "armsSkipped item")
    return {
        "arm": Arm(skipped["arm"]).value,
        "reason": _safe_id(skipped["reason"], "armsSkipped reason"),
    }


def _arms(value: Any, name: str) -> tuple[Arm, ...]:
    return tuple(Arm(item) for item in _list(value, name))


def _timestamp(value: Any, name: str) -> datetime:
    text = _string(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _schema_version(document: Mapping[str, Any]) -> None:
    value = document["schemaVersion"]
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise ValueError(f"schemaVersion must be {SCHEMA_VERSION}")


def _exact_mapping(value: Any, fields: set[str], name: str) -> Mapping[str, Any]:
    return _mapping_fields(value, fields, set(), name)


def _mapping_fields(
    value: Any,
    required: set[str],
    optional: set[str],
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing or unknown:
        raise ValueError(
            f"{name} fields mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be an array")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _bounded_string(value: Any, name: str, maximum: int) -> str:
    text = _string(value, name)
    if len(text) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return text


def _matching_string(value: Any, name: str, pattern: str) -> str:
    text = _string(value, name)
    if re.fullmatch(pattern, text) is None:
        raise ValueError(f"{name} has an invalid format")
    return text


def _safe_id(value: Any, name: str) -> str:
    text = _string(value, name)
    if _SAFE_ID.fullmatch(text) is None:
        raise ValueError(f"{name} must be a safe identifier")
    return text


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _safe_error(error: Exception) -> str:
    if isinstance(error, json.JSONDecodeError):
        return f"invalid JSON at line {error.lineno} column {error.colno}"
    if isinstance(error, OSError):
        return type(error).__name__
    return str(error)

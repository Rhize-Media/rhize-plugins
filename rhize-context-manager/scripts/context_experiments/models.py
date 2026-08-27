"""Versioned models and invariants for context-tool experiments.

Receipts intentionally contain hashes and repository basenames rather than prompts,
source text, or absolute paths. Raw work stays in the agent session; the measurement
record is safe to aggregate and inspect separately.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
MAX_ARMED_RUNS = 10
VALID_TASK_CLASSES = {
    "implementation",
    "diagnosis",
    "impact_analysis",
    "review",
    "deterministic_lookup",
    "operations",
    "unknown",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class Capability(str, Enum):
    MGREP = "mgrep"
    COMPILED_CONTEXT = "compiledContext"


class Arm(str, Enum):
    BASELINE = "A"
    EXPERIMENTAL = "B"


class RunStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    unit: str
    variant: Arm
    role: str
    evidence: str = "measured"

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.name):
            raise ValueError(f"unsafe metric name: {self.name!r}")
        if not _SAFE_ID.fullmatch(self.unit):
            raise ValueError(f"unsafe metric unit: {self.unit!r}")
        if self.evidence not in {"measured", "estimated", "human_judgment"}:
            raise ValueError(f"invalid metric evidence: {self.evidence!r}")
        if self.role not in {"live", "shadow"}:
            raise ValueError(f"invalid metric role: {self.role!r}")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError("metric value must be numeric")
        if not math.isfinite(float(self.value)):
            raise ValueError("metric value must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "variant": self.variant.value,
            "role": self.role,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class CapabilityConfig:
    enabled: bool = False
    armed_runs: int = 0
    eligible_repos: tuple[str, ...] = ()
    live_assignment: str = "alternate"
    shadow: bool = True
    network_approved: bool = False
    smoke_approved: bool = False
    store: str | None = None
    completed_runs: int = 0
    max_duration_seconds: int = 30

    @classmethod
    def from_dict(cls, capability: Capability, value: Mapping[str, Any]) -> "CapabilityConfig":
        allowed = {
            "enabled",
            "armedRuns",
            "eligibleRepos",
            "liveAssignment",
            "shadow",
            "networkApproved",
            "smokeApproved",
            "store",
            "completedRuns",
            "maxDurationSeconds",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown {capability.value} config field(s): {sorted(unknown)}")

        enabled = _require_bool(value.get("enabled", False), "enabled")
        armed_runs = _require_int(value.get("armedRuns", 0), "armedRuns", 0, MAX_ARMED_RUNS)
        eligible_repos_value = value.get("eligibleRepos", [])
        if not isinstance(eligible_repos_value, list) or not all(
            isinstance(item, str) for item in eligible_repos_value
        ):
            raise TypeError("eligibleRepos must be an array of strings")
        eligible_repos: list[str] = []
        for repo in eligible_repos_value:
            path = Path(repo).expanduser()
            if not path.is_absolute():
                raise ValueError(f"eligibleRepos entries must be absolute: {repo!r}")
            eligible_repos.append(str(path.resolve(strict=False)))

        live_assignment = value.get("liveAssignment", "alternate")
        if live_assignment != "alternate":
            raise ValueError("liveAssignment must be 'alternate' in schema version 1")

        shadow = _require_bool(value.get("shadow", True), "shadow")
        network_approved = _require_bool(
            value.get("networkApproved", False), "networkApproved"
        )
        smoke_approved = _require_bool(value.get("smokeApproved", False), "smokeApproved")
        store = value.get("store")
        if store is not None and (
            not isinstance(store, str)
            or not re.fullmatch(r"rhize-dogfood-[a-z0-9][a-z0-9-]{0,62}", store)
        ):
            raise ValueError("store must be a bounded rhize-dogfood-* name")
        completed_runs = _require_int(
            value.get("completedRuns", 0), "completedRuns", 0, 1_000_000
        )
        max_duration_seconds = _require_int(
            value.get("maxDurationSeconds", 30), "maxDurationSeconds", 1, 300
        )

        if armed_runs and not enabled:
            raise ValueError("armedRuns requires enabled=true")
        if armed_runs and not eligible_repos:
            raise ValueError("armedRuns requires at least one eligibleRepos entry")
        if capability is Capability.MGREP and armed_runs and not network_approved:
            raise ValueError("an armed mgrep experiment requires networkApproved=true")
        if capability is Capability.MGREP and armed_runs and not store:
            raise ValueError("an armed mgrep experiment requires a dedicated store")
        if capability is Capability.COMPILED_CONTEXT and store is not None:
            raise ValueError("compiledContext does not accept an mgrep store")
        if capability is Capability.COMPILED_CONTEXT and armed_runs and not smoke_approved:
            raise ValueError("an armed compiled-context experiment requires smokeApproved=true")

        return cls(
            enabled=enabled,
            armed_runs=armed_runs,
            eligible_repos=tuple(eligible_repos),
            live_assignment=live_assignment,
            shadow=shadow,
            network_approved=network_approved,
            smoke_approved=smoke_approved,
            store=store,
            completed_runs=completed_runs,
            max_duration_seconds=max_duration_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "armedRuns": self.armed_runs,
            "eligibleRepos": list(self.eligible_repos),
            "liveAssignment": self.live_assignment,
            "shadow": self.shadow,
            "networkApproved": self.network_approved,
            "smokeApproved": self.smoke_approved,
            "store": self.store,
            "completedRuns": self.completed_runs,
            "maxDurationSeconds": self.max_duration_seconds,
        }


@dataclass(frozen=True)
class ExperimentConfig:
    mgrep: CapabilityConfig = field(default_factory=CapabilityConfig)
    compiled_context: CapabilityConfig = field(default_factory=CapabilityConfig)
    lease_ttl_seconds: int = 900
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExperimentConfig":
        allowed = {"schemaVersion", "experiments", "leaseTtlSeconds"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown experiment config field(s): {sorted(unknown)}")
        if value.get("schemaVersion") != SCHEMA_VERSION:
            raise ValueError(f"schemaVersion must be {SCHEMA_VERSION}")
        experiments = value.get("experiments", {})
        if not isinstance(experiments, Mapping):
            raise TypeError("experiments must be an object")
        unknown_capabilities = set(experiments) - {item.value for item in Capability}
        if unknown_capabilities:
            raise ValueError(f"unknown experiment capability: {sorted(unknown_capabilities)}")
        lease_ttl_seconds = _require_int(
            value.get("leaseTtlSeconds", 900), "leaseTtlSeconds", 60, 86_400
        )
        return cls(
            mgrep=CapabilityConfig.from_dict(
                Capability.MGREP, _mapping(experiments.get(Capability.MGREP.value, {}))
            ),
            compiled_context=CapabilityConfig.from_dict(
                Capability.COMPILED_CONTEXT,
                _mapping(experiments.get(Capability.COMPILED_CONTEXT.value, {})),
            ),
            lease_ttl_seconds=lease_ttl_seconds,
        )

    def for_capability(self, capability: Capability) -> CapabilityConfig:
        return self.mgrep if capability is Capability.MGREP else self.compiled_context

    def with_capability(
        self, capability: Capability, capability_config: CapabilityConfig
    ) -> "ExperimentConfig":
        if capability is Capability.MGREP:
            return ExperimentConfig(
                mgrep=capability_config,
                compiled_context=self.compiled_context,
                lease_ttl_seconds=self.lease_ttl_seconds,
            )
        return ExperimentConfig(
            mgrep=self.mgrep,
            compiled_context=capability_config,
            lease_ttl_seconds=self.lease_ttl_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "leaseTtlSeconds": self.lease_ttl_seconds,
            "experiments": {
                Capability.MGREP.value: self.mgrep.to_dict(),
                Capability.COMPILED_CONTEXT.value: self.compiled_context.to_dict(),
            },
        }


@dataclass(frozen=True)
class Assignment:
    arms_requested: tuple[Arm, ...]
    live_variant: Arm
    shadow_variant: Arm | None


@dataclass(frozen=True)
class ExperimentReceipt:
    experiment_id: str
    task_id: str
    capability: Capability
    status: RunStatus
    started_at: str
    completed_at: str | None
    repo_id: str
    repo_name: str
    snapshot: str
    prompt_hash: str
    task_class: str
    arms_requested: tuple[Arm, ...]
    arms_executed: tuple[Arm, ...]
    arms_skipped: tuple[dict[str, str], ...]
    live_variant: Arm
    shadow_variant: Arm | None
    fallback_used: bool
    metrics: tuple[Metric, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for label, value in (("experiment_id", self.experiment_id), ("task_id", self.task_id)):
            if not _SAFE_ID.fullmatch(value):
                raise ValueError(f"unsafe {label}: {value!r}")
        if self.task_class not in VALID_TASK_CLASSES:
            raise ValueError(f"invalid task class: {self.task_class!r}")
        if self.status is RunStatus.COMPLETED and self.live_variant not in self.arms_executed:
            raise ValueError("completed receipt must include liveVariant in armsExecuted")
        if self.shadow_variant is not None and self.shadow_variant is self.live_variant:
            raise ValueError("shadowVariant must differ from liveVariant")
        if len(set(self.arms_requested)) != len(self.arms_requested):
            raise ValueError("armsRequested contains duplicates")
        if len(set(self.arms_executed)) != len(self.arms_executed):
            raise ValueError("armsExecuted contains duplicates")
        if not set(self.arms_executed).issubset(self.arms_requested):
            raise ValueError("armsExecuted must be a subset of armsRequested")
        _assert_no_absolute_paths_or_raw_content(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "experimentId": self.experiment_id,
            "taskId": self.task_id,
            "capability": self.capability.value,
            "status": self.status.value,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "repoId": self.repo_id,
            "repoName": self.repo_name,
            "snapshot": self.snapshot,
            "promptHash": self.prompt_hash,
            "taskClass": self.task_class,
            "armsRequested": [arm.value for arm in self.arms_requested],
            "armsExecuted": [arm.value for arm in self.arms_executed],
            "armsSkipped": list(self.arms_skipped),
            "liveVariant": self.live_variant.value,
            "shadowVariant": self.shadow_variant.value if self.shadow_variant else None,
            "fallbackUsed": self.fallback_used,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "warnings": list(self.warnings),
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("capability config must be an object")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _require_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _assert_no_absolute_paths_or_raw_content(value: Any, key: str = "") -> None:
    forbidden_keys = {"prompt", "rawPrompt", "source", "sourceText", "code", "repoRoot"}
    if key in forbidden_keys:
        raise ValueError(f"receipt contains forbidden raw-content field: {key}")
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            _assert_no_absolute_paths_or_raw_content(child_value, str(child_key))
    elif isinstance(value, list):
        for item in value:
            _assert_no_absolute_paths_or_raw_content(item, key)
    elif isinstance(value, str) and value.startswith("/"):
        raise ValueError(f"receipt contains an absolute path in {key or 'value'}")

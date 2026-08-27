"""Conservative next-viable-task classification and eligibility gates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import Capability, CapabilityConfig


_OPERATIONS = re.compile(
    r"\b(production|prod\b|deploy|release|merge\s+(?:to\s+)?main|credential|secret|"
    r"api[- ]?key|password|database\s+(?:migration|mutation)|dns|billing|payment)\b",
    re.IGNORECASE,
)
_DIAGNOSIS = re.compile(r"\b(diagnose|investigate|debug|root cause|why (?:is|does|did))\b", re.I)
_REVIEW = re.compile(r"\b(review|audit|assess|inspect)\b", re.I)
_IMPACT = re.compile(r"\b(impact|trace|architecture|understand|map|plan)\b", re.I)
_IMPLEMENT = re.compile(r"\b(add|build|change|create|fix|implement|refactor|update)\b", re.I)
_LOOKUP = re.compile(r"\b(where is|which line|exact string|find the file|locate the file)\b", re.I)


@dataclass(frozen=True)
class EligibilityInput:
    capability: Capability
    capability_config: CapabilityConfig
    repo_root: Path
    task_class: str
    prompt_word_count: int
    is_git_repo: bool
    discovery_started: bool
    provider_ready: bool
    provider_snapshot_current: bool


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reasons: tuple[str, ...]


def classify_task(prompt: str) -> str:
    normalized = " ".join(prompt.split())
    words = normalized.split()
    if _OPERATIONS.search(normalized):
        return "operations"
    if len(words) < 4 or _LOOKUP.search(normalized):
        return "deterministic_lookup"
    if _DIAGNOSIS.search(normalized):
        return "diagnosis"
    if _REVIEW.search(normalized):
        return "review"
    if _IMPACT.search(normalized):
        return "impact_analysis"
    if _IMPLEMENT.search(normalized):
        return "implementation"
    return "unknown"


def evaluate_eligibility(value: EligibilityInput) -> EligibilityDecision:
    reasons: list[str] = []
    config = value.capability_config
    repo_root = value.repo_root.expanduser().resolve(strict=False)
    allowed = {Path(path).expanduser().resolve(strict=False) for path in config.eligible_repos}

    if not config.enabled:
        reasons.append("capability_disabled")
    if config.armed_runs <= 0:
        reasons.append("no_armed_runs")
    if not value.is_git_repo:
        reasons.append("not_git_repository")
    if not repo_root.is_absolute() or repo_root not in allowed:
        reasons.append("repository_not_allowlisted")
    if value.task_class in {"operations", "deterministic_lookup", "unknown"}:
        reasons.append(f"task_class_{value.task_class}")
    if value.prompt_word_count < 4:
        reasons.append("query_too_short")
    if value.discovery_started:
        reasons.append("discovery_already_started")
    if not value.provider_ready:
        reasons.append("provider_unavailable")
    if not value.provider_snapshot_current:
        reasons.append("provider_snapshot_stale")
    if value.capability is Capability.MGREP and not config.network_approved:
        reasons.append("network_not_approved")
    if value.capability is Capability.MGREP and not config.store:
        reasons.append("store_not_configured")
    if value.capability is Capability.COMPILED_CONTEXT and not config.smoke_approved:
        reasons.append("smoke_review_not_approved")

    return EligibilityDecision(not reasons, tuple(reasons))

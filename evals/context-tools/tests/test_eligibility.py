from __future__ import annotations

from pathlib import Path

import pytest

from context_experiments.eligibility import EligibilityInput, classify_task, evaluate_eligibility
from context_experiments.models import Capability, CapabilityConfig


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Implement the receipt model for context experiments", "implementation"),
        ("Diagnose why the context selector misses this task", "diagnosis"),
        ("Review the context pack security boundary", "review"),
        ("Map the impact of changing provider routing", "impact_analysis"),
        ("Where is the exact string", "deterministic_lookup"),
        ("Deploy this fix to production", "operations"),
        ("Tell me something interesting about this", "unknown"),
    ],
)
def test_task_classifier_is_conservative(prompt: str, expected: str) -> None:
    assert classify_task(prompt) == expected


def eligible_input(tmp_path: Path, capability: Capability = Capability.MGREP) -> EligibilityInput:
    config = CapabilityConfig(
        enabled=True,
        armed_runs=1,
        eligible_repos=(str(tmp_path.resolve()),),
        network_approved=True,
        smoke_approved=True,
        store="rhize-dogfood-test" if capability is Capability.MGREP else None,
    )
    return EligibilityInput(
        capability=capability,
        capability_config=config,
        repo_root=tmp_path,
        task_class="implementation",
        prompt_word_count=8,
        is_git_repo=True,
        discovery_started=False,
        provider_ready=True,
        provider_snapshot_current=True,
    )


def test_eligible_task_passes_all_gates(tmp_path: Path) -> None:
    decision = evaluate_eligibility(eligible_input(tmp_path))
    assert decision.eligible is True
    assert decision.reasons == ()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("is_git_repo", False, "not_git_repository"),
        ("task_class", "operations", "task_class_operations"),
        ("task_class", "deterministic_lookup", "task_class_deterministic_lookup"),
        ("discovery_started", True, "discovery_already_started"),
        ("provider_ready", False, "provider_unavailable"),
        ("provider_snapshot_current", False, "provider_snapshot_stale"),
    ],
)
def test_individual_safety_gates_report_reason(
    tmp_path: Path, field: str, value: object, reason: str
) -> None:
    original = eligible_input(tmp_path)
    updated = EligibilityInput(**{**original.__dict__, field: value})
    decision = evaluate_eligibility(updated)
    assert decision.eligible is False
    assert reason in decision.reasons


def test_wrong_repository_is_ineligible(tmp_path: Path) -> None:
    other = tmp_path / "other"
    original = eligible_input(tmp_path)
    updated = EligibilityInput(**{**original.__dict__, "repo_root": other})
    assert "repository_not_allowlisted" in evaluate_eligibility(updated).reasons


def test_mgrep_requires_network_approval_even_if_other_gates_pass(tmp_path: Path) -> None:
    original = eligible_input(tmp_path)
    config = CapabilityConfig(**{**original.capability_config.__dict__, "network_approved": False})
    updated = EligibilityInput(**{**original.__dict__, "capability_config": config})
    assert "network_not_approved" in evaluate_eligibility(updated).reasons


def test_compiled_context_requires_smoke_review(tmp_path: Path) -> None:
    original = eligible_input(tmp_path, Capability.COMPILED_CONTEXT)
    config = CapabilityConfig(**{**original.capability_config.__dict__, "smoke_approved": False})
    updated = EligibilityInput(**{**original.__dict__, "capability_config": config})
    assert "smoke_review_not_approved" in evaluate_eligibility(updated).reasons


def test_local_retrieval_requires_smoke_review(tmp_path: Path) -> None:
    original = eligible_input(tmp_path, Capability.LOCAL_RETRIEVAL)
    config = CapabilityConfig(**{**original.capability_config.__dict__, "smoke_approved": False})
    updated = EligibilityInput(**{**original.__dict__, "capability_config": config})
    assert "smoke_review_not_approved" in evaluate_eligibility(updated).reasons

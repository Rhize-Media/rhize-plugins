from __future__ import annotations

import json
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from context_experiments.assignment import assign_arms
from context_experiments.config import (
    arm_capability,
    disarm_capability,
    load_config,
    write_config,
)
from context_experiments.models import (
    Arm,
    Capability,
    CapabilityConfig,
    ExperimentConfig,
    ExperimentEvidence,
    ExperimentReceipt,
    Metric,
    RunStatus,
)


def completed_receipt(**overrides) -> ExperimentReceipt:
    values = {
        "experiment_id": "exp-123",
        "task_id": "task-123",
        "capability": Capability.MGREP,
        "status": RunStatus.COMPLETED,
        "started_at": "2026-08-27T20:00:00Z",
        "completed_at": "2026-08-27T20:01:00Z",
        "repo_id": "a" * 16,
        "repo_name": "rhize-plugins",
        "snapshot": "abc123",
        "prompt_hash": "b" * 64,
        "task_class": "implementation",
        "arms_requested": (Arm.EXPERIMENTAL, Arm.BASELINE),
        "arms_executed": (Arm.EXPERIMENTAL, Arm.BASELINE),
        "arms_skipped": (),
        "live_variant": Arm.EXPERIMENTAL,
        "shadow_variant": Arm.BASELINE,
        "fallback_used": False,
        "metrics": (
            Metric("duration", 90, "ms", Arm.EXPERIMENTAL, "live"),
            Metric("duration", 120, "ms", Arm.BASELINE, "shadow"),
        ),
        "warnings": (),
    }
    values.update(overrides)
    return ExperimentReceipt(**values)


def test_default_config_round_trips_through_strict_parser() -> None:
    config = ExperimentConfig()
    assert ExperimentConfig.from_dict(config.to_dict()) == config


def test_config_rejects_unknown_fields() -> None:
    value = ExperimentConfig().to_dict()
    value["mystery"] = True
    with pytest.raises(ValueError, match="unknown experiment config"):
        ExperimentConfig.from_dict(value)


def test_config_rejects_relative_allowlist_path() -> None:
    value = ExperimentConfig().to_dict()
    value["experiments"]["mgrep"]["eligibleRepos"] = ["relative/repo"]
    with pytest.raises(ValueError, match="must be absolute"):
        ExperimentConfig.from_dict(value)


def test_armed_mgrep_requires_network_approval(tmp_path: Path) -> None:
    value = ExperimentConfig().to_dict()
    value["experiments"]["mgrep"].update(
        {"enabled": True, "armedRuns": 1, "eligibleRepos": [str(tmp_path)]}
    )
    with pytest.raises(ValueError, match="networkApproved"):
        ExperimentConfig.from_dict(value)


def test_armed_mgrep_requires_dedicated_store(tmp_path: Path) -> None:
    value = ExperimentConfig().to_dict()
    value["experiments"]["mgrep"].update(
        {
            "enabled": True,
            "armedRuns": 1,
            "eligibleRepos": [str(tmp_path)],
            "networkApproved": True,
        }
    )
    with pytest.raises(ValueError, match="dedicated store"):
        ExperimentConfig.from_dict(value)


def test_armed_compiled_context_requires_smoke_approval(tmp_path: Path) -> None:
    value = ExperimentConfig().to_dict()
    value["experiments"]["compiledContext"].update(
        {"enabled": True, "armedRuns": 1, "eligibleRepos": [str(tmp_path)]}
    )
    with pytest.raises(ValueError, match="smokeApproved"):
        ExperimentConfig.from_dict(value)


def test_armed_local_retrieval_requires_smoke_approval(tmp_path: Path) -> None:
    value = ExperimentConfig().to_dict()
    value["experiments"]["localRetrieval"].update(
        {"enabled": True, "armedRuns": 1, "eligibleRepos": [str(tmp_path)]}
    )
    with pytest.raises(ValueError, match="smokeApproved"):
        ExperimentConfig.from_dict(value)


def test_local_retrieval_rejects_network_and_store(tmp_path: Path) -> None:
    value = ExperimentConfig().to_dict()
    value["experiments"]["localRetrieval"]["networkApproved"] = True
    with pytest.raises(ValueError, match="networkApproved"):
        ExperimentConfig.from_dict(value)

    value = ExperimentConfig().to_dict()
    value["experiments"]["localRetrieval"]["store"] = "rhize-dogfood-test"
    with pytest.raises(ValueError, match="mgrep store"):
        ExperimentConfig.from_dict(value)


def test_write_config_is_private_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "private" / "context-experiments.json"
    config = arm_capability(
        ExperimentConfig(),
        Capability.MGREP,
        tmp_path,
        1,
        network_approved=True,
        store="rhize-dogfood-test",
    )
    write_config(config, path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_config(path) == config
    assert json.loads(path.read_text())["schemaVersion"] == 1


def test_disarm_preserves_history_but_clears_live_authority(tmp_path: Path) -> None:
    armed = arm_capability(
        ExperimentConfig(),
        Capability.MGREP,
        tmp_path,
        1,
        network_approved=True,
        store="rhize-dogfood-test",
    )
    disarmed = disarm_capability(armed, Capability.MGREP)
    assert disarmed.mgrep.enabled is False
    assert disarmed.mgrep.armed_runs == 0
    assert disarmed.mgrep.eligible_repos == (str(tmp_path.resolve()),)


def test_assignment_starts_with_b_then_alternates_to_a() -> None:
    first = assign_arms(CapabilityConfig(enabled=True, armed_runs=1, shadow=True))
    second = assign_arms(
        CapabilityConfig(enabled=True, armed_runs=1, shadow=True, completed_runs=1)
    )
    assert (first.live_variant, first.shadow_variant) == (Arm.EXPERIMENTAL, Arm.BASELINE)
    assert (second.live_variant, second.shadow_variant) == (Arm.BASELINE, Arm.EXPERIMENTAL)


def test_metric_requires_variant_role_and_compatible_evidence() -> None:
    metric = Metric("input_tokens", 100, "tokens", Arm.EXPERIMENTAL, "live", "estimated")
    assert metric.to_dict()["variant"] == "B"
    assert metric.to_dict()["role"] == "live"
    with pytest.raises(ValueError, match="role"):
        Metric("input_tokens", 100, "tokens", Arm.EXPERIMENTAL, "unknown")


def test_completed_receipt_requires_live_arm_execution() -> None:
    with pytest.raises(ValueError, match="liveVariant"):
        completed_receipt(arms_executed=(Arm.BASELINE,))


def test_receipt_rejects_absolute_paths_and_raw_content() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        completed_receipt(warnings=("/Users/example/private.py",))


def test_receipt_serializes_exact_arm_accounting() -> None:
    document = completed_receipt().to_dict()
    assert document["armsRequested"] == ["B", "A"]
    assert document["armsExecuted"] == ["B", "A"]
    assert document["liveVariant"] == "B"
    assert document["shadowVariant"] == "A"
    assert {metric["role"] for metric in document["metrics"]} == {"live", "shadow"}


def test_source_free_review_evidence_is_strict_and_digest_stable() -> None:
    evidence = ExperimentEvidence(
        experiment_id="exp-review",
        recorded_at="2026-08-30T12:00:00Z",
        task_outcome="completed",
        pack_use_observed=True,
        validation_ids=("pytest-context-tools",),
        arms_executed=(Arm.EXPERIMENTAL,),
        arms_skipped=({"arm": "A", "reason": "no_comparable_shadow_evidence"},),
    )
    document = evidence.to_dict()
    assert document == {
        "schemaVersion": 1,
        "experimentId": "exp-review",
        "recordedAt": "2026-08-30T12:00:00Z",
        "taskOutcome": "completed",
        "packUseObserved": True,
        "validationIds": ["pytest-context-tools"],
        "armsExecuted": ["B"],
        "armsSkipped": [
            {"arm": "A", "reason": "no_comparable_shadow_evidence"}
        ],
    }
    assert ExperimentEvidence.from_dict(document) == evidence
    assert len(evidence.digest()) == 64

    unsafe = {**document, "validationIds": ["https://provider.example/result"]}
    with pytest.raises(ValueError, match="validation"):
        ExperimentEvidence.from_dict(unsafe)

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from context_experiments.capture_health import evaluate_capture_health
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
from context_experiments.receipt_store import EvidenceStore
from context_experiments.runner import main


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def receipt(
    experiment_id: str,
    *,
    status: RunStatus = RunStatus.COMPLETED,
    requested: tuple[Arm, ...] = (Arm.BASELINE, Arm.EXPERIMENTAL),
    executed: tuple[Arm, ...] = (Arm.BASELINE, Arm.EXPERIMENTAL),
    metrics: tuple[Metric, ...] | None = None,
) -> ExperimentReceipt:
    if metrics is None:
        metrics = tuple(
            Metric(
                name="durationMs",
                value=100 if arm is Arm.BASELINE else 80,
                unit="ms",
                variant=arm,
                role="live" if arm is Arm.EXPERIMENTAL else "shadow",
                evidence="measured",
            )
            for arm in executed
        )
    return ExperimentReceipt(
        experiment_id=experiment_id,
        task_id=f"task-{experiment_id}",
        capability=Capability.COMPILED_CONTEXT,
        status=status,
        started_at="2026-08-28T11:58:00Z",
        completed_at="2026-08-28T11:59:00Z",
        repo_id="a" * 16,
        repo_name="rhize-plugins",
        snapshot="abc123",
        prompt_hash="b" * 64,
        task_class="implementation",
        arms_requested=requested,
        arms_executed=executed,
        arms_skipped=tuple(
            {"arm": arm.value, "reason": "measurement_not_captured"}
            for arm in requested
            if arm not in executed
        ),
        live_variant=Arm.EXPERIMENTAL,
        shadow_variant=Arm.BASELINE,
        fallback_used=False,
        metrics=metrics,
    )


def write_receipt(data_dir: Path, value: ExperimentReceipt) -> None:
    directory = data_dir / "receipts"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{value.experiment_id}.json").write_text(
        json.dumps(value.to_dict(), sort_keys=True), encoding="utf-8"
    )


def write_pending(
    data_dir: Path,
    session_id: str,
    experiment_id: str,
    started_at: datetime,
) -> None:
    directory = data_dir / "pending"
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "schemaVersion": 1,
        "sessionIdHash": session_id,
        "experimentId": experiment_id,
        "taskId": f"task-{experiment_id}",
        "capability": Capability.COMPILED_CONTEXT.value,
        "repoId": "a" * 16,
        "repoName": "rhize-plugins",
        "snapshot": "abc123",
        "promptHash": "b" * 64,
        "taskClass": "implementation",
        "startedAt": started_at.isoformat().replace("+00:00", "Z"),
        "armsRequested": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
        "liveVariant": Arm.EXPERIMENTAL.value,
        "shadowVariant": Arm.BASELINE.value,
        "leaseFile": f"{'c' * 64}.lease",
        "leaseOwner": "hook-session",
        "providerExecution": None,
    }
    (directory / f"{session_id}.json").write_text(
        json.dumps(document, sort_keys=True), encoding="utf-8"
    )


def test_reports_arm_capture_counts_without_mixing_variants(tmp_path: Path) -> None:
    write_receipt(tmp_path, receipt("exp-complete"))
    write_receipt(
        tmp_path,
        receipt(
            "exp-incomplete",
            status=RunStatus.INCOMPLETE,
            executed=(Arm.EXPERIMENTAL,),
        ),
    )

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=900, now=NOW)

    compiled = report["perCapability"][Capability.COMPILED_CONTEXT.value]
    assert compiled[Arm.BASELINE.value] == {
        "completed": 1, "incomplete": 1, "skipped": 0
    }
    assert compiled[Arm.EXPERIMENTAL.value] == {
        "completed": 1, "incomplete": 1, "skipped": 0
    }
    assert report["receiptStatus"] == {
        "completed": 1,
        "failed": 0,
        "incomplete": 1,
        "pending": 0,
    }
    assert report["issues"] == [
        {
            "affectedArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
            "capability": Capability.COMPILED_CONTEXT.value,
            "experimentId": "exp-incomplete",
            "kind": "incomplete_receipt",
            "missingArms": [Arm.BASELINE.value],
            "path": "receipts/exp-incomplete.json",
            "status": RunStatus.INCOMPLETE.value,
        }
    ]
    assert report["ok"] is False


def test_surfaces_invalid_json_and_structurally_invalid_receipts(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "broken-json.json").write_text("{", encoding="utf-8")
    invalid = receipt("exp-invalid").to_dict()
    invalid["armsRequested"] = ["A", "A"]
    (receipts / "invalid-structure.json").write_text(
        json.dumps(invalid), encoding="utf-8"
    )

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=900, now=NOW)

    assert report["counts"]["receiptFiles"] == 2
    assert report["counts"]["validReceipts"] == 0
    assert report["counts"]["malformedReceipts"] == 2
    assert [(issue["kind"], issue["path"]) for issue in report["issues"]] == [
        ("malformed_receipt", "receipts/broken-json.json"),
        ("malformed_receipt", "receipts/invalid-structure.json"),
    ]
    assert all(issue["error"] for issue in report["issues"])


def test_classifies_failed_receipts_as_actionable(tmp_path: Path) -> None:
    write_receipt(
        tmp_path,
        receipt("exp-failed", status=RunStatus.FAILED, executed=()),
    )

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=900, now=NOW)

    assert report["receiptStatus"][RunStatus.FAILED.value] == 1
    compiled = report["perCapability"][Capability.COMPILED_CONTEXT.value]
    assert compiled[Arm.BASELINE.value] == {
        "completed": 0, "incomplete": 1, "skipped": 0
    }
    assert compiled[Arm.EXPERIMENTAL.value] == {
        "completed": 0, "incomplete": 1, "skipped": 0
    }
    assert report["issues"] == [
        {
            "affectedArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
            "capability": Capability.COMPILED_CONTEXT.value,
            "experimentId": "exp-failed",
            "kind": "failed_receipt",
            "missingArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
            "path": "receipts/exp-failed.json",
            "status": RunStatus.FAILED.value,
        }
    ]


def test_detects_only_stale_pending_selections_without_a_receipt(tmp_path: Path) -> None:
    write_pending(tmp_path, "fresh", "exp-fresh", NOW - timedelta(seconds=59))
    write_pending(tmp_path, "stale", "exp-stale", NOW - timedelta(seconds=61))
    write_pending(tmp_path, "finished", "exp-finished", NOW - timedelta(seconds=61))
    write_receipt(tmp_path, receipt("exp-finished"))

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=60, now=NOW)

    assert report["counts"]["pendingFiles"] == 3
    assert report["counts"]["stalePending"] == 1
    stale_issue = next(
        issue for issue in report["issues"] if issue["kind"] == "stale_pending_selection"
    )
    assert stale_issue == {
        "ageSeconds": 61,
        "affectedArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
        "capability": Capability.COMPILED_CONTEXT.value,
        "experimentId": "exp-stale",
        "kind": "stale_pending_selection",
        "leaseTtlSeconds": 60,
        "missingArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
        "path": "pending/stale.json",
    }


def test_malformed_same_id_receipt_does_not_hide_stale_pending_arms(tmp_path: Path) -> None:
    write_pending(tmp_path, "stale", "exp-stale", NOW - timedelta(seconds=61))
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "exp-stale.json").write_text("not-json", encoding="utf-8")

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=60, now=NOW)

    assert [(issue["kind"], issue["path"]) for issue in report["issues"]] == [
        ("stale_pending_selection", "pending/stale.json"),
        ("malformed_receipt", "receipts/exp-stale.json"),
    ]
    stale = report["issues"][0]
    assert stale["affectedArms"] == [Arm.BASELINE.value, Arm.EXPERIMENTAL.value]


def test_completed_receipt_requires_metrics_for_each_arm_and_a_comparable_pair(
    tmp_path: Path,
) -> None:
    write_receipt(tmp_path, receipt("missing-metrics", metrics=()))
    write_receipt(
        tmp_path,
        receipt(
            "noncomparable",
            metrics=(
                Metric("tokens", 100, "count", Arm.BASELINE, "shadow"),
                Metric("durationMs", 80, "ms", Arm.EXPERIMENTAL, "live"),
            ),
        ),
    )

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=60, now=NOW)

    assert [issue["kind"] for issue in report["issues"]] == [
        "missing_metric_capture",
        "noncomparable_metric_capture",
    ]
    assert all(
        issue["affectedArms"] == [Arm.BASELINE.value, Arm.EXPERIMENTAL.value]
        for issue in report["issues"]
    )
    compiled = report["perCapability"][Capability.COMPILED_CONTEXT.value]
    assert compiled[Arm.BASELINE.value] == {
        "completed": 0, "incomplete": 2, "skipped": 0
    }
    assert compiled[Arm.EXPERIMENTAL.value] == {
        "completed": 0, "incomplete": 2, "skipped": 0
    }


def test_config_completed_run_count_detects_deleted_receipt_history(tmp_path: Path) -> None:
    config = ExperimentConfig(
        compiled_context=CapabilityConfig(completed_runs=1, shadow=True)
    )

    report = evaluate_capture_health(
        tmp_path / "missing-store",
        lease_ttl_seconds=60,
        config=config,
        now=NOW,
    )

    assert report["ok"] is False
    assert report["issues"] == [
        {
            "affectedArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
            "capability": Capability.COMPILED_CONTEXT.value,
            "expectedCompletedRuns": 1,
            "foundCompletedReceipts": 0,
            "kind": "receipt_history_missing",
            "missingArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
            "missingReceipts": 1,
            "path": "receipts",
        }
    ]


def test_config_reconciliation_detects_unrecorded_completed_receipt(
    tmp_path: Path,
) -> None:
    write_receipt(tmp_path, receipt("exp-unrecorded"))

    report = evaluate_capture_health(
        tmp_path,
        lease_ttl_seconds=60,
        config=ExperimentConfig(),
        now=NOW,
    )

    issue = next(
        item
        for item in report["issues"]
        if item["kind"] == "completed_receipt_history_unrecorded"
    )
    assert issue == {
        "affectedArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
        "capability": Capability.COMPILED_CONTEXT.value,
        "expectedCompletedRuns": 0,
        "foundCompletedReceipts": 1,
        "kind": "completed_receipt_history_unrecorded",
        "missingArms": [],
        "unexpectedReceipts": 1,
        "path": "receipts",
    }


def test_comparable_pair_requires_matching_evidence_class(tmp_path: Path) -> None:
    write_receipt(
        tmp_path,
        receipt(
            "evidence-mismatch",
            metrics=(
                Metric("durationMs", 100, "ms", Arm.BASELINE, "shadow", "measured"),
                Metric("durationMs", 80, "ms", Arm.EXPERIMENTAL, "live", "estimated"),
            ),
        ),
    )

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=60, now=NOW)

    assert report["issues"] == [
        {
            "affectedArms": [Arm.BASELINE.value, Arm.EXPERIMENTAL.value],
            "capability": Capability.COMPILED_CONTEXT.value,
            "experimentId": "evidence-mismatch",
            "kind": "noncomparable_metric_capture",
            "missingArms": [],
            "path": "receipts/evidence-mismatch.json",
            "status": RunStatus.COMPLETED.value,
        }
    ]


def test_capture_health_command_is_deterministic_and_nonzero_for_failures(
    tmp_path: Path, capsys
) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "broken.json").write_text("not-json", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "leaseTtlSeconds": 900,
                "experiments": {},
            }
        ),
        encoding="utf-8",
    )
    arguments = [
        "capture-health",
        "--data-dir",
        str(tmp_path),
        "--config",
        str(config_path),
    ]

    assert main(arguments) == 2
    first = capsys.readouterr().out
    assert main(arguments) == 2
    second = capsys.readouterr().out

    assert first == second
    assert json.loads(first)["ok"] is False


def test_receipt_v2_reconciles_immutable_evidence_and_skipped_shadow(
    tmp_path: Path,
) -> None:
    evidence = ExperimentEvidence(
        experiment_id="exp-evidence-v2",
        recorded_at="2026-08-30T12:00:00Z",
        task_outcome="completed",
        pack_use_observed=True,
        validation_ids=("pytest-context-tools",),
        arms_executed=(Arm.EXPERIMENTAL,),
        arms_skipped=({"arm": "A", "reason": "no_comparable_shadow_evidence"},),
    )
    EvidenceStore(tmp_path / "evidence").write(evidence)
    document = receipt(
        "exp-evidence-v2",
        requested=(Arm.EXPERIMENTAL, Arm.BASELINE),
        executed=(Arm.EXPERIMENTAL,),
    ).to_dict()
    document.update(
        {
            "schemaVersion": 2,
            "armsSkipped": [
                {"arm": "A", "reason": "no_comparable_shadow_evidence"}
            ],
            "evidenceDigest": evidence.digest(),
            "claimPackVerified": True,
            "finalPackVerification": "valid",
        }
    )
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "exp-evidence-v2.json").write_text(json.dumps(document))

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=60, now=NOW)

    assert report["counts"]["validEvidence"] == 1
    assert report["counts"]["malformedEvidence"] == 0
    compiled = report["perCapability"][Capability.COMPILED_CONTEXT.value]
    assert compiled["B"] == {"completed": 1, "incomplete": 0, "skipped": 0}
    assert compiled["A"] == {"completed": 0, "incomplete": 0, "skipped": 1}
    assert [issue["kind"] for issue in report["issues"]] == [
        "noncomparable_arm_capture"
    ]


def test_receipt_v2_detects_evidence_digest_mismatch(tmp_path: Path) -> None:
    evidence = ExperimentEvidence(
        experiment_id="exp-mismatch-v2",
        recorded_at="2026-08-30T12:00:00Z",
        task_outcome="completed",
        pack_use_observed=True,
        validation_ids=("pytest-context-tools",),
        arms_executed=(Arm.EXPERIMENTAL,),
        arms_skipped=({"arm": "A", "reason": "no_comparable_shadow_evidence"},),
    )
    EvidenceStore(tmp_path / "evidence").write(evidence)
    document = receipt(
        "exp-mismatch-v2",
        requested=(Arm.EXPERIMENTAL, Arm.BASELINE),
        executed=(Arm.EXPERIMENTAL,),
    ).to_dict()
    document.update(
        {
            "schemaVersion": 2,
            "armsSkipped": [
                {"arm": "A", "reason": "no_comparable_shadow_evidence"}
            ],
            "evidenceDigest": "f" * 64,
            "claimPackVerified": True,
            "finalPackVerification": "valid",
        }
    )
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "exp-mismatch-v2.json").write_text(json.dumps(document))

    report = evaluate_capture_health(tmp_path, lease_ttl_seconds=60, now=NOW)

    assert "evidence_digest_mismatch" in {
        issue["kind"] for issue in report["issues"]
    }


def test_capture_health_exposes_continuous_live_and_frozen_lifecycle() -> None:
    config = ExperimentConfig(
        compiled_context=CapabilityConfig(
            enabled=True,
            mode="continuous",
            eligible_repos=("/tmp/repo",),
            smoke_approved=True,
            completed_runs=2,
        )
    )
    report = evaluate_capture_health(
        Path("/nonexistent/context-data"),
        lease_ttl_seconds=60,
        config=config,
        now=NOW,
    )
    lifecycle = report["capabilityLifecycle"][Capability.COMPILED_CONTEXT.value]
    assert lifecycle == {
        "armedRuns": 0,
        "completedRuns": 2,
        "enabled": True,
        "mode": "continuous",
        "state": "live",
    }

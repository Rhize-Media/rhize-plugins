from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from context_experiments.aggregate import aggregate_receipts
from context_experiments.lease import Lease, LeaseStore
from context_experiments.models import Arm, Capability, ExperimentReceipt, Metric, RunStatus
from context_experiments.receipt_store import PendingStore, ReceiptStore


def receipt(experiment_id: str = "exp-storage") -> ExperimentReceipt:
    return ExperimentReceipt(
        experiment_id=experiment_id,
        task_id="task-storage",
        capability=Capability.MGREP,
        status=RunStatus.COMPLETED,
        started_at="2026-08-27T20:00:00Z",
        completed_at="2026-08-27T20:01:00Z",
        repo_id="a" * 16,
        repo_name="repo",
        snapshot="abc123",
        prompt_hash="b" * 64,
        task_class="implementation",
        arms_requested=(Arm.EXPERIMENTAL, Arm.BASELINE),
        arms_executed=(Arm.EXPERIMENTAL, Arm.BASELINE),
        arms_skipped=(),
        live_variant=Arm.EXPERIMENTAL,
        shadow_variant=Arm.BASELINE,
        fallback_used=False,
        metrics=(
            Metric("duration", 90, "ms", Arm.EXPERIMENTAL, "live"),
            Metric("duration", 120, "ms", Arm.BASELINE, "shadow"),
            Metric("duration", 1, "seconds", Arm.EXPERIMENTAL, "live"),
        ),
    )


def test_receipts_are_private_append_only_and_parseable(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "receipts")
    path = store.write(receipt())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["liveVariant"] == "B"
    with pytest.raises(FileExistsError):
        store.write(receipt())


def test_pending_store_rejects_absolute_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="forbidden field"):
        PendingStore(tmp_path).write("sessionhash", {"repoRoot": "/private/repo"})


def test_pending_store_rejects_lease_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe lease filename"):
        PendingStore(tmp_path).write("sessionhash", {"leaseFile": "../../outside"})


def test_lease_allows_only_one_owner_and_only_owner_can_release(tmp_path: Path) -> None:
    store = LeaseStore(tmp_path / "leases", ttl_seconds=60)
    first = store.claim("same-key", "owner-a")
    assert first is not None
    assert store.claim("same-key", "owner-b") is None
    store.release(Lease(first.path, first.key, "owner-b"))
    assert first.path.exists()
    store.release(first)
    assert not first.path.exists()
    gate = first.path.with_suffix(".lock")
    assert gate.exists()
    assert stat.S_IMODE(gate.stat().st_mode) == 0o600


def test_stale_lease_is_reclaimed(tmp_path: Path) -> None:
    now = 1_000.0
    store = LeaseStore(tmp_path / "leases", ttl_seconds=60, now=lambda: now)
    first = store.claim("same-key", "owner-a")
    assert first is not None
    os.utime(first.path, (now - 61, now - 61))
    second = store.claim("same-key", "owner-b")
    assert second is not None
    assert second.owner == "owner-b"


def test_aggregate_never_mixes_variant_role_unit_or_evidence() -> None:
    report = aggregate_receipts([receipt().to_dict()])
    group = report["groups"][0]
    summaries = {
        (item["variant"], item["role"], item["unit"], item["evidence"]): item
        for item in group["metrics"]
    }
    assert summaries[("B", "live", "ms", "measured")]["median"] == 90
    assert summaries[("A", "shadow", "ms", "measured")]["median"] == 120
    assert summaries[("B", "live", "seconds", "measured")]["median"] == 1
    assert len(summaries) == 3

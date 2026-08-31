#!/usr/bin/env python3
"""CLI and hook adapter for controlled, real-provider context experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from context_experiments.aggregate import aggregate_receipts
    from context_experiments.assignment import assign_arms
    from context_experiments.capture_health import evaluate_capture_health
    from context_experiments.config import (
        arm_capability,
        default_config_path,
        default_context_pack_dir,
        default_data_dir,
        disarm_capability,
        freeze_capability,
        load_config,
        record_completed_run,
        record_reserved_completion,
        reserve_capability_run,
        write_config,
    )
    from context_experiments.eligibility import (
        EligibilityInput,
        classify_task,
        evaluate_eligibility,
    )
    from context_experiments.lease import Lease, LeaseStore
    from context_experiments.models import (
        Arm,
        Capability,
        ExperimentConfig,
        ExperimentEvidence,
        ExperimentReceipt,
        Metric,
        RECEIPT_SCHEMA_VERSION,
        RunStatus,
    )
    from context_experiments.providers import (
        ContextCompilerProvider,
        GrepaiLayout,
        GrepaiProvider,
        MgrepProvider,
        NativeContextPackProvider,
    )
    from context_experiments.receipt_store import (
        EvidenceStore,
        PendingStore,
        ReceiptStore,
    )
else:
    from .aggregate import aggregate_receipts
    from .assignment import assign_arms
    from .capture_health import evaluate_capture_health
    from .config import (
        arm_capability,
        default_config_path,
        default_context_pack_dir,
        default_data_dir,
        disarm_capability,
        freeze_capability,
        load_config,
        record_completed_run,
        record_reserved_completion,
        reserve_capability_run,
        write_config,
    )
    from .eligibility import EligibilityInput, classify_task, evaluate_eligibility
    from .lease import Lease, LeaseStore
    from .models import (
        Arm,
        Capability,
        ExperimentConfig,
        ExperimentEvidence,
        ExperimentReceipt,
        Metric,
        RECEIPT_SCHEMA_VERSION,
        RunStatus,
    )
    from .providers import (
        ContextCompilerProvider,
        GrepaiLayout,
        GrepaiProvider,
        MgrepProvider,
        NativeContextPackProvider,
    )
    from .receipt_store import EvidenceStore, PendingStore, ReceiptStore


def _local_retrieval_status(repo_root: Path | None) -> tuple[bool, bool, str]:
    if repo_root is None:
        return False, False, "no Git repository selected for local retrieval"
    marker_path = repo_root / ".grepai" / "rhize-snapshot.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        config_sha256 = marker.get("configSha256") if isinstance(marker, dict) else None
        if not isinstance(config_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", config_sha256):
            raise ValueError("invalid marker")
        provider = GrepaiProvider(
            GrepaiLayout(
                Path(".grepai/config.yaml"),
                Path(".grepai/index.gob"),
                Path(".grepai/rhize-snapshot.json"),
            ),
            expected_config_sha256=config_sha256,
        )
        health = provider.doctor(repo_root)
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False, False, "local grepai index is absent or unverified"
    return health.ready, health.ready, health.note


def real_provider_status(
    repo_root: Path | None = None,
) -> dict[Capability, tuple[bool, bool, str]]:
    """Probe installed real providers without reading source or making a network call."""

    mgrep = MgrepProvider().doctor()
    compiler = NativeContextPackProvider().doctor()
    return {
        Capability.LOCAL_RETRIEVAL: _local_retrieval_status(repo_root),
        Capability.MGREP: (
            mgrep.ready,
            False,
            f"{mgrep.note}; no verified indexed-snapshot marker",
        ),
        Capability.COMPILED_CONTEXT: (compiler.ready, compiler.ready, compiler.note),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def repository_fingerprint(repo_root: Path) -> str:
    return digest(str(repo_root.expanduser().resolve(strict=False)))


def git_root(cwd: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve(strict=False)


def git_snapshot(repo_root: Path) -> str | None:
    try:
        commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            timeout=2,
            check=False,
        )
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain=v1", "-z"],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if commit.returncode != 0 or status.returncode != 0:
        return None
    commit_id = commit.stdout.decode(errors="replace").strip()
    if not commit_id:
        return None
    if not status.stdout:
        return commit_id
    try:
        tracked_changes = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", "-z", "HEAD", "--"],
            capture_output=True,
            timeout=3,
            check=False,
        )
        untracked = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if tracked_changes.returncode != 0 or untracked.returncode != 0:
        return None

    fingerprint = hashlib.sha256(status.stdout)
    dirty_paths = {
        path
        for output in (tracked_changes.stdout, untracked.stdout)
        for path in output.split(b"\0")
        if path
    }
    for raw_path in sorted(dirty_paths):
        relative = Path(os.fsdecode(raw_path))
        if relative.is_absolute() or ".." in relative.parts:
            return None
        path = repo_root / relative
        fingerprint.update(raw_path)
        fingerprint.update(b"\0")
        if path.is_symlink():
            fingerprint.update(b"symlink\0")
            fingerprint.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            fingerprint.update(b"file\0")
            try:
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        fingerprint.update(chunk)
            except OSError:
                return None
        elif path.exists():
            # A dirty directory is typically a submodule. Its nested worktree is
            # outside this repository's byte-bound snapshot contract.
            return None
        else:
            fingerprint.update(b"missing\0")
    return f"{commit_id}-dirty-{fingerprint.hexdigest()[:16]}"


def select_next(
    payload: Mapping[str, Any],
    config: ExperimentConfig,
    provider_status: Mapping[Capability, tuple[bool, bool, str]],
) -> dict[str, Any] | None:
    """Return a conservative selection or ``None`` without storing the prompt."""

    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    cwd_value = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd_value, str):
        return None
    repo_root = git_root(Path(cwd_value))
    task_class = classify_task(prompt)

    for capability in (
        Capability.LOCAL_RETRIEVAL,
        Capability.MGREP,
        Capability.COMPILED_CONTEXT,
    ):
        capability_config = config.for_capability(capability)
        ready, snapshot_current, provider_note = provider_status.get(
            capability, (False, False, "unregistered")
        )
        decision = evaluate_eligibility(
            EligibilityInput(
                capability=capability,
                capability_config=capability_config,
                repo_root=repo_root or Path(cwd_value).resolve(strict=False),
                task_class=task_class,
                prompt_word_count=len(prompt.split()),
                is_git_repo=repo_root is not None,
                discovery_started=False,
                provider_ready=ready,
                provider_snapshot_current=snapshot_current,
            )
        )
        if decision.eligible and repo_root is not None:
            assignment = assign_arms(capability_config)
            return {
                "capability": capability,
                "repoRoot": repo_root,
                "taskClass": task_class,
                "promptHash": digest(prompt, 64),
                "assignment": assignment,
                "providerNote": provider_note,
            }
    return None


def claim_hook_selection(
    payload: Mapping[str, Any],
    config: ExperimentConfig,
    provider_status: Mapping[Capability, tuple[bool, bool, str]],
    storage_root: Path,
    config_path: Path,
) -> dict[str, Any] | None:
    selection = select_next(payload, config, provider_status)
    session_id = payload.get("session_id")
    if selection is None or not isinstance(session_id, str) or not session_id:
        return None
    snapshot = git_snapshot(selection["repoRoot"])
    # P4 deliberately refuses dirty repositories instead of relying on the old
    # path/status-only dirty-tree fingerprint.
    if snapshot is None or "-dirty-" in snapshot:
        return None
    capability = selection["capability"]
    capability_config = config.for_capability(capability)
    started = time.monotonic()
    session_hash = digest(session_id, 32)
    repo_id = repository_fingerprint(selection["repoRoot"])
    task_material = ":".join((repo_id, snapshot, selection["taskClass"], session_hash))
    task_id = f"task-{digest(task_material)}"
    experiment_id = f"exp-{uuid.uuid4().hex}"
    assignment = selection["assignment"]
    provider_execution = None
    if capability is Capability.COMPILED_CONTEXT:
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            return None
        try:
            native_provider = NativeContextPackProvider()
            impact_hint_value = payload.get("impactMapPath")
            impact_hint = (
                Path(impact_hint_value)
                if isinstance(impact_hint_value, str) and impact_hint_value
                else None
            )
            pack = native_provider.compile(
                selection["repoRoot"],
                snapshot=snapshot,
                task_hash=selection["promptHash"],
                query=prompt,
                impact_hint=impact_hint,
            )
            if not pack.manifest["policy"]["acceptedForUse"]:
                return None
            if time.monotonic() - started > capability_config.max_duration_seconds:
                return None
            manifest_path, prompt_path = native_provider.write_pack(
                pack, storage_root / "packs"
            )
            current_snapshot = git_snapshot(selection["repoRoot"])
            if current_snapshot != snapshot:
                return None
            verification = native_provider.verify_pack(
                pack.manifest, selection["repoRoot"], current_snapshot, prompt_path
            )
            if not verification.valid:
                return None
            if time.monotonic() - started > capability_config.max_duration_seconds:
                return None
            provider_execution = {
                "provider": "rhize-native",
                "providerRevision": pack.manifest["provider"]["revision"],
                "packId": pack.manifest["packId"],
                "manifestFile": manifest_path.name,
                "promptFile": prompt_path.name,
                "naiveDumpTokens": pack.manifest["naiveDumpTokens"],
                "compiledTokens": pack.manifest["compiledTokens"],
                "totalSourceFiles": pack.manifest["totalSourceFiles"],
                "compiledFiles": len(pack.manifest["entries"]),
                "buildMilliseconds": round((time.monotonic() - started) * 1000, 3),
                "warnings": pack.manifest["warnings"],
                "claimPackVerified": True,
            }
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
            return None
    lease_key = f"{repo_id}:{capability.value}"
    lease_owner = f"hook-{session_hash}"
    lease_store = LeaseStore(
        storage_root / "leases",
        config.lease_ttl_seconds,
        reclaim_stale=False,
    )
    lease = lease_store.claim(lease_key, lease_owner)
    if lease is None:
        return None
    pending = {
        "schemaVersion": 1,
        "sessionIdHash": session_hash,
        "experimentId": experiment_id,
        "taskId": task_id,
        "capability": capability.value,
        "repoId": repo_id,
        "repoName": selection["repoRoot"].name,
        "snapshot": snapshot,
        "promptHash": selection["promptHash"],
        "taskClass": selection["taskClass"],
        "mode": capability_config.mode,
        "startedAt": utc_now(),
        "armsRequested": [arm.value for arm in assignment.arms_requested],
        "liveVariant": assignment.live_variant.value,
        "shadowVariant": assignment.shadow_variant.value if assignment.shadow_variant else None,
        "leaseFile": lease.path.name,
        "leaseOwner": lease_owner,
        "providerExecution": provider_execution,
    }
    try:
        PendingStore(storage_root / "pending").write(session_hash, pending)
    except Exception:
        lease_store.release(lease)
        raise
    if reserve_capability_run(config_path, capability) is None:
        PendingStore(storage_root / "pending").delete(session_hash)
        lease_store.release(lease)
        return None
    selection["pending"] = pending
    if provider_execution is not None:
        selection["providerPromptPath"] = str(
            storage_root / "packs" / provider_execution["promptFile"]
        )
    return selection


def finalize_hook_selection(
    payload: Mapping[str, Any], storage_root: Path, config_path: Path | None = None
) -> bool:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return False
    session_hash = digest(session_id, 32)
    pending_store = PendingStore(storage_root / "pending")
    pending = pending_store.read(session_hash)
    if pending is None:
        return False
    resolved_config_path = config_path or default_config_path()
    _finalize_pending_attempt(
        session_hash,
        pending,
        payload,
        storage_root,
        resolved_config_path,
    )
    return True


def audit_pending_attempts(
    storage_root: Path,
    config_path: Path | None = None,
    *,
    now: float | None = None,
) -> int:
    """Terminalize accepted attempts whose Stop hook never ran.

    Accepted leases are never reclaimed into a new claim. Once their configured
    lifetime expires, the audit writes an incomplete receipt, freezes authority,
    and releases only that terminalized lease.
    """

    resolved_config_path = config_path or default_config_path()
    config = load_config(resolved_config_path)
    cutoff_now = time.time() if now is None else now
    pending_store = PendingStore(storage_root / "pending")
    finalized = 0
    for session_hash, pending, modified_at in pending_store.active():
        if cutoff_now - modified_at <= config.lease_ttl_seconds:
            continue
        _finalize_pending_attempt(
            session_hash,
            pending,
            {},
            storage_root,
            resolved_config_path,
            forced_reason="stale_pending_attempt",
        )
        finalized += 1
    return finalized


def _finalize_pending_attempt(
    session_hash: str,
    pending: Mapping[str, Any],
    payload: Mapping[str, Any],
    storage_root: Path,
    config_path: Path,
    *,
    forced_reason: str | None = None,
) -> None:
    pending_store = PendingStore(storage_root / "pending")
    receipt_store = ReceiptStore(storage_root / "receipts")
    receipt_path = receipt_store.directory / f"{pending['experimentId']}.json"
    lease = Lease(
        path=storage_root / "leases" / pending["leaseFile"],
        key="",
        owner=pending["leaseOwner"],
    )
    config = load_config(config_path)
    if not receipt_path.exists():
        requested = tuple(Arm(value) for value in pending["armsRequested"])
        provider_execution = pending.get("providerExecution")
        capability = Capability(pending["capability"])
        live_variant = Arm(pending["liveVariant"])
        evidence, evidence_state = EvidenceStore(
            storage_root / "evidence"
        ).read_with_state(pending["experimentId"])
        final_verification = (
            "unavailable"
            if forced_reason is not None
            else _final_pack_verification(payload, pending, storage_root)
        )
        status, executed, skipped, evidence_warnings, terminal_reason = (
            _resolve_review_evidence(
                evidence,
                evidence_state=evidence_state,
                requested=requested,
                live_variant=live_variant,
                capability=capability,
                claim_pack_verified=(
                    bool(provider_execution.get("claimPackVerified"))
                    if isinstance(provider_execution, dict)
                    else None
                ),
                final_pack_verification=final_verification,
            )
        )
        if forced_reason is not None:
            status = RunStatus.INCOMPLETE
            terminal_reason = forced_reason
            executed = ()
            skipped = tuple(
                {"arm": arm.value, "reason": forced_reason} for arm in requested
            )
            evidence_warnings = (*evidence_warnings, forced_reason)
        metrics = _provider_metrics(provider_execution, executed, live_variant)
        warnings = list(evidence_warnings)
        if isinstance(provider_execution, dict):
            warnings.extend(provider_execution.get("warnings", ()))
            warnings.extend(
                (
                    f"provider_revision_{provider_execution['providerRevision']}",
                    f"pack_id_{provider_execution['packId']}",
                )
            )
        if final_verification == "stale":
            warnings.append("final_pack_stale_after_task")
        receipt = ExperimentReceipt(
            experiment_id=pending["experimentId"],
            task_id=pending["taskId"],
            capability=capability,
            status=status,
            started_at=pending["startedAt"],
            completed_at=utc_now(),
            repo_id=pending["repoId"],
            repo_name=pending["repoName"],
            snapshot=pending["snapshot"],
            prompt_hash=pending["promptHash"],
            task_class=pending["taskClass"],
            arms_requested=requested,
            arms_executed=executed,
            arms_skipped=skipped,
            live_variant=live_variant,
            shadow_variant=(
                Arm(pending["shadowVariant"]) if pending.get("shadowVariant") else None
            ),
            fallback_used=False,
            metrics=metrics,
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_digest=evidence.digest() if evidence is not None else None,
            claim_pack_verified=(
                bool(provider_execution.get("claimPackVerified"))
                if isinstance(provider_execution, dict)
                else None
            ),
            final_pack_verification=final_verification,
            terminal_reason=terminal_reason,
            evidence_completeness=_evidence_completeness(
                evidence,
                evidence_state,
                requested,
                capability,
                live_variant,
            ),
            schema_version=RECEIPT_SCHEMA_VERSION,
        )
        receipt_store.write(receipt)
        if receipt.status is RunStatus.COMPLETED:
            record_reserved_completion(config_path, receipt.capability)
        else:
            freeze_capability(config_path, receipt.capability)
    pending_store.delete(session_hash)
    LeaseStore(
        storage_root / "leases",
        config.lease_ttl_seconds,
        reclaim_stale=False,
    ).release(lease)


def _evidence_completeness(
    evidence: ExperimentEvidence | None,
    evidence_state: str,
    requested: tuple[Arm, ...],
    capability: Capability,
    live_variant: Arm,
) -> dict[str, Any]:
    accounted = (
        set(evidence.arms_executed)
        | {Arm(item["arm"]) for item in evidence.arms_skipped}
        if evidence is not None
        else set()
    )
    pack_use_required = (
        capability is Capability.COMPILED_CONTEXT
        and live_variant is Arm.EXPERIMENTAL
    )
    return {
        "armAccountingComplete": accounted == set(requested),
        "evidenceState": evidence_state,
        "packUseRecorded": bool(evidence and evidence.pack_use_observed),
        "packUseRequired": pack_use_required,
        "taskOutcomeRecorded": bool(evidence),
        "validationRecorded": bool(evidence and evidence.validation_ids),
    }


def _provider_metrics(
    provider_execution: Any,
    executed: tuple[Arm, ...],
    live_variant: Arm,
) -> tuple[Metric, ...]:
    if not isinstance(provider_execution, dict) or Arm.EXPERIMENTAL not in executed:
        return ()
    role = "live" if live_variant is Arm.EXPERIMENTAL else "shadow"
    return (
        Metric(
            "context_tokens",
            provider_execution["compiledTokens"],
            "tokens",
            Arm.EXPERIMENTAL,
            role,
            "estimated",
        ),
        Metric(
            "files_presented",
            provider_execution["compiledFiles"],
            "count",
            Arm.EXPERIMENTAL,
            role,
            "measured",
        ),
        Metric(
            "build_duration",
            provider_execution["buildMilliseconds"],
            "ms",
            Arm.EXPERIMENTAL,
            role,
            "measured",
        ),
    )


def _resolve_review_evidence(
    evidence: ExperimentEvidence | None,
    *,
    evidence_state: str,
    requested: tuple[Arm, ...],
    live_variant: Arm,
    capability: Capability,
    claim_pack_verified: bool | None,
    final_pack_verification: str,
) -> tuple[
    RunStatus,
    tuple[Arm, ...],
    tuple[dict[str, str], ...],
    tuple[str, ...],
    str,
]:
    if evidence is None:
        skipped = []
        for arm in requested:
            if arm is not live_variant:
                reason = "no_comparable_shadow_evidence"
            elif capability is Capability.COMPILED_CONTEXT and arm is Arm.EXPERIMENTAL:
                reason = "missing_pack_use_task_validation_evidence"
            else:
                reason = "missing_task_validation_evidence"
            skipped.append({"arm": arm.value, "reason": reason})
        warning = f"review_evidence_{evidence_state}"
        return RunStatus.INCOMPLETE, (), tuple(skipped), (warning,), warning

    executed = evidence.arms_executed
    skipped = evidence.arms_skipped
    accounted = set(executed) | {Arm(item["arm"]) for item in skipped}
    if accounted != set(requested) or set(executed) - set(requested):
        return (
            RunStatus.INCOMPLETE,
            (),
            tuple(
                {"arm": arm.value, "reason": "invalid_review_arm_accounting"}
                for arm in requested
            ),
            ("review_arm_accounting_invalid",),
            "review_arm_accounting_invalid",
        )
    pack_use_required = (
        capability is Capability.COMPILED_CONTEXT
        and live_variant is Arm.EXPERIMENTAL
    )
    execution_proven = (
        live_variant in executed
        and (not pack_use_required or evidence.pack_use_observed)
        and (
            capability is not Capability.COMPILED_CONTEXT
            or (
                claim_pack_verified is True
                and final_pack_verification == "valid"
            )
        )
    )
    if not execution_proven:
        if final_pack_verification == "stale":
            reason = "final_pack_stale"
        elif final_pack_verification == "unavailable":
            reason = "final_pack_unavailable"
        else:
            reason = "review_execution_incomplete"
        return RunStatus.INCOMPLETE, executed, skipped, (reason,), reason
    if evidence.task_outcome == "failed":
        return RunStatus.FAILED, executed, skipped, ("reviewed_task_failed",), "task_failed"
    return RunStatus.COMPLETED, executed, skipped, (), "evidence_complete"


def _final_pack_verification(
    payload: Mapping[str, Any], pending: Mapping[str, Any], storage_root: Path
) -> str:
    execution = pending.get("providerExecution")
    if not isinstance(execution, dict):
        return "not_applicable"
    cwd_value = payload.get("cwd")
    if not isinstance(cwd_value, str):
        return "unavailable"
    repo_root = git_root(Path(cwd_value))
    if repo_root is None or repository_fingerprint(repo_root) != pending.get("repoId"):
        return "unavailable"
    manifest_file = execution.get("manifestFile")
    prompt_file = execution.get("promptFile")
    if not isinstance(manifest_file, str) or not re.fullmatch(
        r"pack-[a-f0-9]{32}\.json", manifest_file
    ):
        return "unavailable"
    if not isinstance(prompt_file, str) or not re.fullmatch(
        r"pack-[a-f0-9]{32}\.md", prompt_file
    ):
        return "unavailable"
    if Path(manifest_file).stem != Path(prompt_file).stem:
        return "unavailable"
    try:
        manifest = json.loads(
            (storage_root / "packs" / manifest_file).read_text(encoding="utf-8")
        )
        if manifest.get("packId") != Path(manifest_file).stem:
            return "unavailable"
        snapshot = git_snapshot(repo_root)
        if snapshot is None:
            return "unavailable"
        result = NativeContextPackProvider().verify_pack(
            manifest, repo_root, snapshot, storage_root / "packs" / prompt_file
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "unavailable"
    return "valid" if result.valid else "stale"


def run_context_compiler_experiment(
    repo_root: Path,
    target_file: Path,
    task_class: str,
    snapshot: str,
    checkout: Path | None = None,
    max_hops: int = 2,
    max_tokens: int = 40_000,
    config_path: Path | None = None,
    data_dir: Path | None = None,
) -> tuple[ExperimentReceipt, Path, Path, Path]:
    config = load_config(config_path)
    capability = Capability.COMPILED_CONTEXT
    capability_config = config.for_capability(capability)
    if not capability_config.shadow:
        raise ValueError("compiled-context A/B runs require shadow=true")
    task_material = f"compile {target_file.name} for {task_class}"
    provider = ContextCompilerProvider(checkout)
    health = provider.doctor()
    decision = evaluate_eligibility(
        EligibilityInput(
            capability=capability,
            capability_config=capability_config,
            repo_root=repo_root,
            task_class=task_class,
            prompt_word_count=len(task_material.split()),
            is_git_repo=git_root(repo_root) == repo_root.resolve(strict=False),
            discovery_started=False,
            provider_ready=health.ready,
            provider_snapshot_current=health.ready,
        )
    )
    if not decision.eligible:
        raise ValueError(f"compiled-context run is not eligible: {', '.join(decision.reasons)}")

    assignment = assign_arms(capability_config)
    repo_id = repository_fingerprint(repo_root)
    owner = f"compiler-{uuid.uuid4().hex}"
    task_id = f"task-{digest(f'{repo_id}:{snapshot}:{task_class}:{owner}')}"
    experiment_id = f"exp-{uuid.uuid4().hex}"
    storage_root = data_dir or default_data_dir()
    lease_store = LeaseStore(storage_root / "leases", config.lease_ttl_seconds)
    lease_key = f"{repo_id}:{snapshot}:{capability.value}:{task_id}"
    lease = lease_store.claim(lease_key, owner)
    if lease is None:
        raise RuntimeError("experiment lease is already held")

    started_at = utc_now()
    try:
        task_hash = digest(task_material, 64)
        pack = provider.compile(
            repo_root,
            target_file,
            snapshot=snapshot,
            task_hash=task_hash,
            max_hops=max_hops,
            max_tokens=max_tokens,
        )
        manifest_path, prompt_path = provider.write_pack(pack, storage_root / "packs")
        manifest = pack.manifest

        def role(arm: Arm) -> str:
            return "live" if arm is assignment.live_variant else "shadow"

        metrics = (
            Metric(
                "context_tokens",
                manifest["naiveDumpTokens"],
                "tokens",
                Arm.BASELINE,
                role(Arm.BASELINE),
                "estimated",
            ),
            Metric(
                "context_tokens",
                manifest["compiledTokens"],
                "tokens",
                Arm.EXPERIMENTAL,
                role(Arm.EXPERIMENTAL),
                "estimated",
            ),
            Metric(
                "files_presented",
                manifest["totalRepoFiles"],
                "count",
                Arm.BASELINE,
                role(Arm.BASELINE),
            ),
            Metric(
                "files_presented",
                len(manifest["entries"]),
                "count",
                Arm.EXPERIMENTAL,
                role(Arm.EXPERIMENTAL),
            ),
            Metric(
                "build_duration",
                manifest["buildMilliseconds"],
                "ms",
                Arm.EXPERIMENTAL,
                role(Arm.EXPERIMENTAL),
            ),
            Metric(
                "pack_accepted",
                int(manifest["policy"]["acceptedForInjection"]),
                "boolean",
                Arm.EXPERIMENTAL,
                role(Arm.EXPERIMENTAL),
            ),
        )
        receipt = ExperimentReceipt(
            experiment_id=experiment_id,
            task_id=task_id,
            capability=capability,
            status=RunStatus.COMPLETED,
            started_at=started_at,
            completed_at=utc_now(),
            repo_id=repo_id,
            repo_name=repo_root.name,
            snapshot=snapshot,
            prompt_hash=task_hash,
            task_class=task_class,
            arms_requested=assignment.arms_requested,
            arms_executed=assignment.arms_requested,
            arms_skipped=(),
            live_variant=assignment.live_variant,
            shadow_variant=assignment.shadow_variant,
            fallback_used=not manifest["policy"]["acceptedForInjection"],
            metrics=metrics,
            warnings=tuple((*manifest["warnings"], "upstream_token_counts_are_estimated")),
        )
        receipt_path = ReceiptStore(storage_root / "receipts").write(receipt)
        # The armed run is consumed only after the append-only receipt exists.
        updated = record_completed_run(config, capability)
        write_config(updated, config_path)
        return receipt, receipt_path, manifest_path, prompt_path
    finally:
        lease_store.release(lease)


def build_context_pack_preview(
    repo_root: Path,
    target_file: Path,
    snapshot: str,
    checkout: Path | None = None,
    max_hops: int = 2,
    max_tokens: int = 40_000,
    data_dir: Path | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    """Build a private pack without arming, injecting, or recording an experiment."""

    repo = repo_root.expanduser().resolve(strict=True)
    target = target_file.expanduser().resolve(strict=True)
    current_snapshot = git_snapshot(repo)
    if current_snapshot is None:
        raise ValueError("context-pack preview requires a Git repository")
    if current_snapshot != snapshot:
        raise ValueError(
            f"snapshot mismatch: requested {snapshot}, current repository is {current_snapshot}"
        )
    try:
        relative_target = target.relative_to(repo).as_posix()
    except ValueError as error:
        raise ValueError("target must be inside the repository root") from error
    repo_id = repository_fingerprint(repo)
    task_hash = digest(
        f"context-pack:{repo_id}:{snapshot}:{relative_target}",
        64,
    )
    provider = ContextCompilerProvider(checkout)
    pack = provider.compile(
        repo,
        target,
        snapshot=snapshot,
        task_hash=task_hash,
        max_hops=max_hops,
        max_tokens=max_tokens,
    )
    storage_root = data_dir or default_context_pack_dir()
    manifest_path, prompt_path = provider.write_pack(pack, storage_root / "packs")
    return pack.manifest, manifest_path, prompt_path


def build_native_context_pack_preview(
    repo_root: Path,
    snapshot: str,
    *,
    target_files: tuple[Path, ...] = (),
    query: str | None = None,
    impact_hint: Path | None = None,
    max_hops: int = 2,
    max_tokens: int = 40_000,
    data_dir: Path | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    """Build a local provider-neutral pack without injection or a live receipt."""

    repo = repo_root.expanduser().resolve(strict=True)
    current_snapshot = git_snapshot(repo)
    if current_snapshot is None:
        raise ValueError("native context-pack preview requires a Git repository")
    if current_snapshot != snapshot:
        raise ValueError(
            f"snapshot mismatch: requested {snapshot}, current repository is {current_snapshot}"
        )
    target_material = ",".join(
        str(path.expanduser().resolve(strict=False).relative_to(repo))
        for path in target_files
    )
    task_hash = digest(
        ":".join(
            (
                "native-context-pack",
                snapshot,
                target_material,
                query or "",
            )
        ),
        64,
    )
    provider = NativeContextPackProvider()
    pack = provider.compile(
        repo,
        snapshot=snapshot,
        task_hash=task_hash,
        targets=target_files,
        query=query,
        impact_hint=impact_hint,
        max_hops=max_hops,
        max_tokens=max_tokens,
    )
    storage_root = data_dir or default_context_pack_dir()
    manifest_path, prompt_path = provider.write_pack(pack, storage_root / "packs")
    return pack.manifest, manifest_path, prompt_path


def run_mgrep_preflight(
    repo_root: Path,
    store: str,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Create an independent manifest, then invoke the real CLI in dry-run mode."""

    provider = MgrepProvider()
    health = provider.doctor()
    inventory = provider.inventory(repo_root)
    storage_root = data_dir or default_data_dir()
    inventory_path = provider.write_inventory(inventory, storage_root / "mgrep-preflights")
    if health.ready and not inventory.manifest["vendorDryRunBlocked"]:
        result = provider.dry_run_watch(repo_root, store)
        output_text = f"{result.stdout}\n{result.stderr}".lower()
        authenticated = "you are not logged in" not in output_text
        completed = result.returncode == 0 and authenticated and "dry run" in output_text
        dry_run = {
            "exitCode": result.returncode,
            "authenticated": authenticated,
            "completed": completed,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    elif not health.ready:
        dry_run = {
            "exitCode": None,
            "authenticated": False,
            "completed": False,
            "stdout": "",
            "stderr": health.note,
        }
    else:
        dry_run = {
            "exitCode": None,
            "authenticated": True,
            "completed": False,
            "stdout": "",
            "stderr": "vendor dry-run blocked by independent inventory review",
        }
    return {
        "provider": health.to_dict(),
        "inventoryPath": str(inventory_path),
        "inventory": {
            "preflightId": inventory.manifest["preflightId"],
            "repoName": inventory.manifest["repoName"],
            "includedFileCount": inventory.manifest["includedFileCount"],
            "includedBytes": inventory.manifest["includedBytes"],
            "excludedFileCount": len(inventory.manifest["excluded"]),
            "warnings": inventory.manifest["warnings"],
            "vendorDryRunBlocked": inventory.manifest["vendorDryRunBlocked"],
        },
        "dryRun": dry_run,
        "uploaded": False,
    }


def hook_select() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        config_path = default_config_path()
        audit_pending_attempts(default_data_dir(), config_path)
        config = load_config(config_path)
        cwd_value = payload.get("cwd") or os.getcwd()
        selected_repo = git_root(Path(cwd_value)) if isinstance(cwd_value, str) else None
        selection = claim_hook_selection(
            payload,
            config,
            real_provider_status(selected_repo),
            default_data_dir(),
            config_path,
        )
        if selection is None:
            return 0
        assignment = selection["assignment"]
        experiment_id = selection["pending"]["experimentId"]
        runner_path = Path(__file__).resolve(strict=True)
        evidence_arguments = [
            "python3",
            str(runner_path),
            "record-evidence",
            "--experiment-id",
            experiment_id,
            "--task-outcome",
            "completed",
        ]
        if (
            selection["capability"] is Capability.COMPILED_CONTEXT
            and assignment.live_variant is Arm.EXPERIMENTAL
        ):
            evidence_arguments.append("--pack-used")
        evidence_arguments.extend(
            [
                "--validation-id",
                "validation-id-REPLACE_ME",
                "--executed-arm",
                assignment.live_variant.value,
            ]
        )
        if assignment.shadow_variant is not None:
            evidence_arguments.extend(
                [
                    "--skip-arm",
                    f"{assignment.shadow_variant.value}:no_comparable_shadow_evidence",
                ]
            )
        evidence_command = shlex.join(evidence_arguments)
        message = (
            f"Context experiment selected: {selection['capability'].value}; "
            f"attempt {experiment_id}; "
            f"live Arm {assignment.live_variant.value}; "
            "shadow Arm "
            f"{assignment.shadow_variant.value if assignment.shadow_variant else 'none'}. "
            f"Evidence runner: {runner_path}. "
        )
        execution = selection["pending"].get("providerExecution")
        if isinstance(execution, dict):
            message += (
                f"Accepted native pack {execution['packId']} was built automatically. "
                "For compiled-context Arm B, read and use the accepted prompt pack before "
                f"implementation: `{selection['providerPromptPath']}`. Run task-specific checks "
                "and validate the task before recording success. "
            )
        message += (
            "Replace validation-id-REPLACE_ME with a source-free validation identifier, "
            "then run this exact command before Stop: `"
            f"{evidence_command}`. Without valid evidence, the receipt will be incomplete "
            "and the capability will remain frozen."
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": message,
                    }
                }
            )
        )
    except Exception:
        return 0
    return 0


def hook_finalize() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if isinstance(payload, dict):
            finalize_hook_selection(payload, default_data_dir())
    except Exception:
        pass
    return 0


def command_status() -> int:
    config_path = default_config_path()
    try:
        config = load_config(config_path)
        statuses = real_provider_status(git_root(Path.cwd()))
        output = {
            "schemaVersion": 1,
            "configured": config_path.exists(),
            "configPath": str(config_path),
            "dataDirectory": str(default_data_dir()),
            "config": config.to_dict(),
            "providers": {
                capability.value: {
                    "ready": status[0],
                    "snapshotCurrent": status[1],
                    "note": status[2],
                }
                for capability, status in statuses.items()
            },
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        output = {"schemaVersion": 1, "configured": True, "valid": False, "error": str(error)}
        print(json.dumps(output, indent=2, sort_keys=True))
        return 2
    output["valid"] = True
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def command_doctor() -> int:
    config_path = default_config_path()
    checks = []
    try:
        config = load_config(config_path)
        checks.append({"name": "config", "status": "OK", "note": "schema version 1 valid"})
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        checks.append({"name": "config", "status": "dead", "note": str(error)})
        print(json.dumps({"schemaVersion": 1, "checks": checks}, indent=2, sort_keys=True))
        return 2
    for capability, (ready, snapshot_current, note) in real_provider_status(
        git_root(Path.cwd())
    ).items():
        capability_config = config.for_capability(capability)
        status = "OK" if ready and snapshot_current else "unavailable"
        if ready and not snapshot_current:
            status = "snapshot_unverified"
        if capability_config.armed_runs and (not ready or not snapshot_current):
            status = "degraded"
        checks.append(
            {
                "name": capability.value,
                "status": status,
                "snapshotCurrent": snapshot_current,
                "note": note,
            }
        )
    print(json.dumps({"schemaVersion": 1, "checks": checks}, indent=2, sort_keys=True))
    return 0


def command_arm(args: argparse.Namespace) -> int:
    capability = Capability(args.capability)
    config = load_config()
    runs = args.runs if args.runs is not None else (0 if args.mode == "continuous" else 1)
    updated = arm_capability(
        config,
        capability,
        Path(args.repo),
        runs,
        mode=args.mode,
        network_approved=args.network_approved,
        smoke_approved=args.smoke_approved,
        store=args.store,
    )
    path = write_config(updated)
    print(f"enabled {capability.value} in {args.mode} mode ({runs} armed run(s)): {path}")
    return 0


def command_disarm(args: argparse.Namespace) -> int:
    capability = Capability(args.capability)
    updated = disarm_capability(load_config(), capability)
    path = write_config(updated)
    print(f"disarmed {capability.value}: {path}")
    return 0


def command_record_evidence(args: argparse.Namespace) -> int:
    storage_root = default_data_dir()
    pending = PendingStore(storage_root / "pending").find_by_experiment_id(
        args.experiment_id
    )
    if pending is None:
        raise ValueError("evidence requires a matching pending accepted attempt")
    skipped: list[dict[str, str]] = []
    for value in args.skip_arm:
        arm_value, separator, reason = value.partition(":")
        if not separator:
            raise ValueError("--skip-arm must use ARM:reason")
        skipped.append({"arm": Arm(arm_value).value, "reason": reason})
    evidence = ExperimentEvidence(
        experiment_id=args.experiment_id,
        recorded_at=utc_now(),
        task_outcome=args.task_outcome,
        pack_use_observed=args.pack_used,
        validation_ids=tuple(args.validation_id),
        arms_executed=tuple(Arm(value) for value in args.executed_arm),
        arms_skipped=tuple(skipped),
    )
    requested = {Arm(value) for value in pending["armsRequested"]}
    accounted = set(evidence.arms_executed) | {
        Arm(item["arm"]) for item in evidence.arms_skipped
    }
    if accounted != requested:
        raise ValueError("evidence must execute or explicitly skip every requested arm")
    EvidenceStore(storage_root / "evidence").write(evidence)
    print(
        json.dumps(
            {
                "schemaVersion": 1,
                "experimentId": evidence.experiment_id,
                "evidenceDigest": evidence.digest(),
            },
            sort_keys=True,
        )
    )
    return 0


def command_compile(args: argparse.Namespace) -> int:
    receipt, receipt_path, manifest_path, prompt_path = run_context_compiler_experiment(
        repo_root=Path(args.repo).resolve(strict=False),
        target_file=Path(args.target).resolve(strict=False),
        task_class=args.task_class,
        snapshot=args.snapshot,
        checkout=Path(args.checkout).resolve(strict=False) if args.checkout else None,
        max_hops=args.max_hops,
        max_tokens=args.max_tokens,
    )
    print(
        json.dumps(
            {
                "receipt": receipt.to_dict(),
                "receiptPath": str(receipt_path),
                "manifestPath": str(manifest_path),
                "promptPath": str(prompt_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def command_pack(args: argparse.Namespace) -> int:
    started = time.monotonic()
    repo = Path(args.repo).expanduser().resolve(strict=True)
    snapshot = args.snapshot or git_snapshot(repo)
    if snapshot is None:
        raise ValueError("context-pack preview requires a Git repository")
    if args.provider == "native":
        manifest, manifest_path, prompt_path = build_native_context_pack_preview(
            repo_root=repo,
            snapshot=snapshot,
            target_files=tuple(Path(value) for value in args.target),
            query=args.query,
            impact_hint=Path(args.impact_map) if args.impact_map else None,
            max_hops=args.max_hops,
            max_tokens=args.max_tokens,
        )
        provider_name = "native"
        accepted = manifest["policy"]["acceptedForUse"]
        target_paths = manifest["discovery"]["targetPaths"]
        arm_b_variant = manifest["provider"]["revision"]
    else:
        if len(args.target) != 1:
            raise ValueError("upstream-python requires exactly one --target")
        manifest, manifest_path, prompt_path = build_context_pack_preview(
            repo_root=repo,
            target_file=Path(args.target[0]),
            snapshot=snapshot,
            checkout=Path(args.checkout) if args.checkout else None,
            max_hops=args.max_hops,
            max_tokens=args.max_tokens,
        )
        provider_name = "upstream-python"
        accepted = manifest["policy"]["acceptedForInjection"]
        target_paths = [manifest["targetPath"]]
        arm_b_variant = "context-compiler-pack"
    print(
        json.dumps(
            {
                "schemaVersion": manifest["schemaVersion"],
                "mode": "preview_only",
                "provider": provider_name,
                "injected": False,
                "receiptRecorded": False,
                "packId": manifest["packId"],
                "targetPaths": target_paths,
                "snapshot": manifest["snapshot"],
                "acceptedForUse": accepted,
                "rejectionReasons": manifest["policy"]["rejectionReasons"],
                "warnings": manifest["warnings"],
                "impactHint": manifest.get("impactHint"),
                "entries": [
                    {
                        "path": entry["path"],
                        "role": entry.get("role", f"TIER_{entry.get('tier')}"),
                        "reason": entry.get("reason", "upstream_dependency_graph"),
                    }
                    for entry in manifest["entries"]
                ],
                "metrics": {
                    "armA": {
                        "variant": "baseline-naive-repository",
                        "contextTokens": manifest["naiveDumpTokens"],
                        "filesPresented": manifest.get(
                            "totalRepoFiles", manifest.get("totalSourceFiles")
                        ),
                    },
                    "armB": {
                        "variant": arm_b_variant,
                        "contextTokens": manifest["compiledTokens"],
                        "filesPresented": len(manifest["entries"]),
                        "buildMilliseconds": round((time.monotonic() - started) * 1000, 3),
                    },
                    "reductionPercent": manifest["reductionPercent"],
                },
                "manifestPath": str(manifest_path),
                "promptPath": str(prompt_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def command_verify_pack(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 2:
        raise ValueError("verify-pack accepts only native context-pack v2 manifests")
    repo = Path(args.repo).expanduser().resolve(strict=True)
    snapshot = git_snapshot(repo)
    if snapshot is None:
        raise ValueError("verify-pack requires a Git repository")
    result = NativeContextPackProvider().verify_pack(
        manifest, repo, snapshot, Path(args.prompt)
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.valid else 2


def command_mgrep_preflight(args: argparse.Namespace) -> int:
    result = run_mgrep_preflight(Path(args.repo).resolve(strict=False), args.store)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["dryRun"]["completed"] else 2
    return 0


def command_report() -> int:
    store = ReceiptStore(default_data_dir() / "receipts")
    print(json.dumps(aggregate_receipts(store.documents()), indent=2, sort_keys=True))
    return 0


def command_capture_health(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config).expanduser() if args.config else None)
    data_dir = Path(args.data_dir).expanduser() if args.data_dir else default_data_dir()
    report = evaluate_capture_health(
        data_dir,
        lease_ttl_seconds=config.lease_ttl_seconds,
        config=config,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 2


def command_audit_pending() -> int:
    finalized = audit_pending_attempts(default_data_dir(), default_config_path())
    print(json.dumps({"schemaVersion": 1, "terminalizedAttempts": finalized}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("doctor")
    subparsers.add_parser("hook-select")
    subparsers.add_parser("hook-finalize")
    subparsers.add_parser("audit-pending")
    subparsers.add_parser("report")

    capture_health = subparsers.add_parser("capture-health")
    capture_health.add_argument("--config")
    capture_health.add_argument("--data-dir")

    arm = subparsers.add_parser("arm")
    arm.add_argument("--capability", choices=[item.value for item in Capability], required=True)
    arm.add_argument("--repo", required=True)
    arm.add_argument("--runs", type=int)
    arm.add_argument("--mode", choices=["canary", "continuous"], default="canary")
    arm.add_argument("--network-approved", action="store_true")
    arm.add_argument("--smoke-approved", action="store_true")
    arm.add_argument("--store")

    disarm = subparsers.add_parser("disarm")
    disarm.add_argument("--capability", choices=[item.value for item in Capability], required=True)

    evidence = subparsers.add_parser("record-evidence")
    evidence.add_argument("--experiment-id", required=True)
    evidence.add_argument(
        "--task-outcome", choices=["completed", "failed"], required=True
    )
    evidence.add_argument("--pack-used", action="store_true")
    evidence.add_argument("--validation-id", action="append", default=[], required=True)
    evidence.add_argument(
        "--executed-arm", choices=[item.value for item in Arm], action="append", default=[]
    )
    evidence.add_argument("--skip-arm", action="append", default=[])

    compile_command = subparsers.add_parser("compile")
    compile_command.add_argument("--repo", required=True)
    compile_command.add_argument("--target", required=True)
    compile_command.add_argument("--checkout")
    compile_command.add_argument("--max-hops", type=int, default=2)
    compile_command.add_argument("--max-tokens", type=int, default=40_000)
    compile_command.add_argument(
        "--task-class",
        choices=["implementation", "diagnosis", "impact_analysis", "review"],
        default="implementation",
    )
    compile_command.add_argument("--snapshot", required=True)

    pack = subparsers.add_parser("pack")
    pack.add_argument("--provider", choices=["native", "upstream-python"], default="native")
    pack.add_argument("--repo", required=True)
    pack.add_argument("--target", action="append", default=[])
    pack.add_argument("--query")
    pack.add_argument("--impact-map")
    pack.add_argument("--checkout")
    pack.add_argument("--max-hops", type=int, default=2)
    pack.add_argument("--max-tokens", type=int, default=40_000)
    pack.add_argument("--snapshot")

    verify_pack = subparsers.add_parser("verify-pack")
    verify_pack.add_argument("--repo", required=True)
    verify_pack.add_argument("--manifest", required=True)
    verify_pack.add_argument("--prompt", required=True)

    preflight = subparsers.add_parser("mgrep-preflight")
    preflight.add_argument("--repo", required=True)
    preflight.add_argument("--store", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "status": command_status,
        "doctor": command_doctor,
        "hook-select": hook_select,
        "hook-finalize": hook_finalize,
        "audit-pending": command_audit_pending,
        "arm": lambda: command_arm(args),
        "disarm": lambda: command_disarm(args),
        "record-evidence": lambda: command_record_evidence(args),
        "compile": lambda: command_compile(args),
        "pack": lambda: command_pack(args),
        "verify-pack": lambda: command_verify_pack(args),
        "mgrep-preflight": lambda: command_mgrep_preflight(args),
        "report": command_report,
        "capture-health": lambda: command_capture_health(args),
    }
    try:
        return commands[args.command]()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

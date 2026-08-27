#!/usr/bin/env python3
"""CLI and hook adapter for controlled, real-provider context experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from context_experiments.aggregate import aggregate_receipts
    from context_experiments.assignment import assign_arms
    from context_experiments.config import (
        arm_capability,
        default_config_path,
        default_data_dir,
        disarm_capability,
        load_config,
        record_completed_run,
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
        ExperimentReceipt,
        Metric,
        RunStatus,
    )
    from context_experiments.providers import ContextCompilerProvider, MgrepProvider
    from context_experiments.receipt_store import PendingStore, ReceiptStore
else:
    from .aggregate import aggregate_receipts
    from .assignment import assign_arms
    from .config import (
        arm_capability,
        default_config_path,
        default_data_dir,
        disarm_capability,
        load_config,
        record_completed_run,
        write_config,
    )
    from .eligibility import EligibilityInput, classify_task, evaluate_eligibility
    from .lease import Lease, LeaseStore
    from .models import Arm, Capability, ExperimentConfig, ExperimentReceipt, Metric, RunStatus
    from .providers import ContextCompilerProvider, MgrepProvider
    from .receipt_store import PendingStore, ReceiptStore


def real_provider_status() -> dict[Capability, tuple[bool, bool, str]]:
    """Probe installed real providers without reading source or making a network call."""

    mgrep = MgrepProvider().doctor()
    compiler = ContextCompilerProvider().doctor()
    return {
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
    return f"{commit_id}-dirty-{hashlib.sha256(status.stdout).hexdigest()[:16]}"


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

    for capability in (Capability.MGREP, Capability.COMPILED_CONTEXT):
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
) -> dict[str, Any] | None:
    selection = select_next(payload, config, provider_status)
    session_id = payload.get("session_id")
    if selection is None or not isinstance(session_id, str) or not session_id:
        return None
    snapshot = git_snapshot(selection["repoRoot"])
    if snapshot is None:
        return None
    session_hash = digest(session_id, 32)
    repo_id = repository_fingerprint(selection["repoRoot"])
    task_material = ":".join((repo_id, snapshot, selection["taskClass"], session_hash))
    task_id = f"task-{digest(task_material)}"
    experiment_id = f"exp-{uuid.uuid4().hex}"
    lease_key = f"{repo_id}:{snapshot}:{selection['capability'].value}:{task_id}"
    lease_owner = f"hook-{session_hash}"
    lease_store = LeaseStore(storage_root / "leases", config.lease_ttl_seconds)
    lease = lease_store.claim(lease_key, lease_owner)
    if lease is None:
        return None
    assignment = selection["assignment"]
    pending = {
        "schemaVersion": 1,
        "sessionIdHash": session_hash,
        "experimentId": experiment_id,
        "taskId": task_id,
        "capability": selection["capability"].value,
        "repoId": repo_id,
        "repoName": selection["repoRoot"].name,
        "snapshot": snapshot,
        "promptHash": selection["promptHash"],
        "taskClass": selection["taskClass"],
        "startedAt": utc_now(),
        "armsRequested": [arm.value for arm in assignment.arms_requested],
        "liveVariant": assignment.live_variant.value,
        "shadowVariant": assignment.shadow_variant.value if assignment.shadow_variant else None,
        "leaseFile": lease.path.name,
        "leaseOwner": lease_owner,
    }
    try:
        PendingStore(storage_root / "pending").write(session_hash, pending)
    except Exception:
        lease_store.release(lease)
        raise
    selection["pending"] = pending
    return selection


def finalize_hook_selection(payload: Mapping[str, Any], storage_root: Path) -> bool:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return False
    session_hash = digest(session_id, 32)
    pending_store = PendingStore(storage_root / "pending")
    pending = pending_store.read(session_hash)
    if pending is None:
        return False
    receipt_store = ReceiptStore(storage_root / "receipts")
    receipt_path = receipt_store.directory / f"{pending['experimentId']}.json"
    lease = Lease(
        path=storage_root / "leases" / pending["leaseFile"],
        key="",
        owner=pending["leaseOwner"],
    )
    if not receipt_path.exists():
        requested = tuple(Arm(value) for value in pending["armsRequested"])
        receipt = ExperimentReceipt(
            experiment_id=pending["experimentId"],
            task_id=pending["taskId"],
            capability=Capability(pending["capability"]),
            status=RunStatus.INCOMPLETE,
            started_at=pending["startedAt"],
            completed_at=utc_now(),
            repo_id=pending["repoId"],
            repo_name=pending["repoName"],
            snapshot=pending["snapshot"],
            prompt_hash=pending["promptHash"],
            task_class=pending["taskClass"],
            arms_requested=requested,
            arms_executed=(),
            arms_skipped=tuple(
                {"arm": arm.value, "reason": "no_execution_evidence"} for arm in requested
            ),
            live_variant=Arm(pending["liveVariant"]),
            shadow_variant=(
                Arm(pending["shadowVariant"]) if pending.get("shadowVariant") else None
            ),
            fallback_used=False,
            warnings=("finalized_without_provider_execution_evidence",),
        )
        receipt_store.write(receipt)
    pending_store.delete(session_hash)
    LeaseStore(storage_root / "leases", 900).release(lease)
    return True


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
        config = load_config()
        selection = claim_hook_selection(
            payload, config, real_provider_status(), default_data_dir()
        )
        if selection is None:
            return 0
        assignment = selection["assignment"]
        message = (
            f"Context experiment selected: {selection['capability'].value}; "
            f"live Arm {assignment.live_variant.value}; "
            f"shadow Arm {assignment.shadow_variant.value if assignment.shadow_variant else 'none'}. "
            "Record execution evidence before finalizing the receipt."
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
        statuses = real_provider_status()
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
    for capability, (ready, snapshot_current, note) in real_provider_status().items():
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
    updated = arm_capability(
        config,
        capability,
        Path(args.repo),
        args.runs,
        network_approved=args.network_approved,
        smoke_approved=args.smoke_approved,
        store=args.store,
    )
    path = write_config(updated)
    print(f"armed {capability.value} for {args.runs} run(s): {path}")
    return 0


def command_disarm(args: argparse.Namespace) -> int:
    capability = Capability(args.capability)
    updated = disarm_capability(load_config(), capability)
    path = write_config(updated)
    print(f"disarmed {capability.value}: {path}")
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


def command_mgrep_preflight(args: argparse.Namespace) -> int:
    result = run_mgrep_preflight(Path(args.repo).resolve(strict=False), args.store)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["dryRun"]["completed"] else 2
    return 0


def command_report() -> int:
    store = ReceiptStore(default_data_dir() / "receipts")
    print(json.dumps(aggregate_receipts(store.documents()), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("doctor")
    subparsers.add_parser("hook-select")
    subparsers.add_parser("hook-finalize")
    subparsers.add_parser("report")

    arm = subparsers.add_parser("arm")
    arm.add_argument("--capability", choices=[item.value for item in Capability], required=True)
    arm.add_argument("--repo", required=True)
    arm.add_argument("--runs", type=int, default=1)
    arm.add_argument("--network-approved", action="store_true")
    arm.add_argument("--smoke-approved", action="store_true")
    arm.add_argument("--store")

    disarm = subparsers.add_parser("disarm")
    disarm.add_argument("--capability", choices=[item.value for item in Capability], required=True)

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
        "arm": lambda: command_arm(args),
        "disarm": lambda: command_disarm(args),
        "compile": lambda: command_compile(args),
        "mgrep-preflight": lambda: command_mgrep_preflight(args),
        "report": command_report,
    }
    try:
        return commands[args.command]()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

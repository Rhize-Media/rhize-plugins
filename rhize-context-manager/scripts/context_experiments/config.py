"""Strict local configuration for opt-in context experiments."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from .models import Capability, CapabilityConfig, ExperimentConfig


def default_config_path() -> Path:
    override = os.environ.get("RHIZE_CONTEXT_EXPERIMENT_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "rhize-context-manager" / "context-experiments.json"


def default_data_dir() -> Path:
    override = os.environ.get("RHIZE_CONTEXT_EXPERIMENT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "rhize-context-manager" / "experiments"


def default_context_pack_dir() -> Path:
    """Host-neutral storage for explicit Claude Code/Codex context-pack previews."""

    override = os.environ.get("RHIZE_CONTEXT_PACK_DATA_DIR")
    if override:
        return Path(override).expanduser()
    context_home = os.environ.get("RHIZE_CONTEXT_HOME")
    if context_home:
        return Path(context_home).expanduser() / "context-packs"
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "rhize" / "context-manager" / "context-packs"


def load_config(path: Path | None = None) -> ExperimentConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return ExperimentConfig()
    value = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("context experiment config must be a JSON object")
    return ExperimentConfig.from_dict(value)


def write_config(config: ExperimentConfig, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    # Round-trip through the strict parser before any write.
    validated = ExperimentConfig.from_dict(config.to_dict())
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".context-experiments-", dir=config_path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        payload = (json.dumps(validated.to_dict(), indent=2, sort_keys=True) + "\n").encode()
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, config_path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    return config_path


def arm_capability(
    config: ExperimentConfig,
    capability: Capability,
    repo_root: Path,
    runs: int,
    *,
    network_approved: bool = False,
    smoke_approved: bool = False,
    store: str | None = None,
) -> ExperimentConfig:
    current = config.for_capability(capability)
    resolved_repo = str(repo_root.expanduser().resolve(strict=False))
    repos = tuple(dict.fromkeys((*current.eligible_repos, resolved_repo)))
    updated = replace(
        current,
        enabled=True,
        armed_runs=runs,
        eligible_repos=repos,
        network_approved=network_approved if capability is Capability.MGREP else False,
        smoke_approved=(
            smoke_approved
            if capability in {Capability.LOCAL_RETRIEVAL, Capability.COMPILED_CONTEXT}
            else False
        ),
        store=store if capability is Capability.MGREP else None,
    )
    result = config.with_capability(capability, updated)
    return ExperimentConfig.from_dict(result.to_dict())


def disarm_capability(config: ExperimentConfig, capability: Capability) -> ExperimentConfig:
    current = config.for_capability(capability)
    updated = replace(current, enabled=False, armed_runs=0)
    return config.with_capability(capability, updated)


def record_completed_run(config: ExperimentConfig, capability: Capability) -> ExperimentConfig:
    current = config.for_capability(capability)
    if current.armed_runs <= 0:
        raise ValueError("cannot complete an unarmed experiment")
    updated = replace(
        current,
        armed_runs=current.armed_runs - 1,
        completed_runs=current.completed_runs + 1,
    )
    return config.with_capability(capability, updated)


def reserve_capability_run(
    path: Path, capability: Capability
) -> ExperimentConfig | None:
    """Atomically consume live authority and freeze a capability for review."""

    with _config_lock(path):
        config = load_config(path)
        current = config.for_capability(capability)
        if not current.enabled or current.armed_runs <= 0:
            return None
        updated_capability = replace(current, enabled=False, armed_runs=0)
        updated = config.with_capability(capability, updated_capability)
        write_config(updated, path)
        return updated


def record_reserved_completion(path: Path, capability: Capability) -> ExperimentConfig:
    """Increment history only after an already-reserved frozen run completes."""

    with _config_lock(path):
        config = load_config(path)
        current = config.for_capability(capability)
        if current.enabled or current.armed_runs != 0:
            raise ValueError("completed reserved run requires a frozen capability")
        updated = config.with_capability(
            capability,
            replace(current, completed_runs=current.completed_runs + 1),
        )
        write_config(updated, path)
        return updated


def freeze_capability(path: Path, capability: Capability) -> ExperimentConfig:
    """Idempotently remove live authority for an accepted attempt."""

    with _config_lock(path):
        config = load_config(path)
        current = config.for_capability(capability)
        if not current.enabled and current.armed_runs == 0:
            return config
        updated = config.with_capability(
            capability, replace(current, enabled=False, armed_runs=0)
        )
        write_config(updated, path)
        return updated


@contextmanager
def _config_lock(path: Path):
    lock_path = path.parent / f".{path.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

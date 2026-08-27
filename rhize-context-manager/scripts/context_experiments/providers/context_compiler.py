"""Adapter for the pinned upstream Context Compiler implementation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


UPSTREAM_REVISION = "4edb163911f9a6bc869f35970fa77acb3dd88b8f"
UPSTREAM_FILES = {
    "LICENSE": "afca442991c040593b8d15df11fd69f89d48ef435b4f6d47c71cc02a3fa81189",
    "compiler.py": "3cca2a05f87d9c129cbfa0e4085779c8b2bce8d130b9078a7d78c0b28ffee63e",
    "skeletonizer.py": "12a165fbf50de98cc7a710a25d721de7ad6b3e9a38fb3fc2d6731e339bd428a3",
    "symbol_resolver.py": "30ac50d9539967eda3ba09da1ff59b98e748267ce0c7b30709ccdf4dc037173f",
}
DEFAULT_MAX_CONTEXT_TOKENS = 40_000
DEFAULT_MAX_ENTRY_COVERAGE = 0.50
DEFAULT_MAX_NAME_COLLISIONS = 10


def default_checkout_path() -> Path:
    return (
        Path.home()
        / ".claude"
        / "rhize-context-manager"
        / "providers"
        / "context-compiler"
    )


@dataclass(frozen=True)
class ProviderHealth:
    ready: bool
    note: str
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ready": self.ready, "note": self.note, "version": self.version}


@dataclass(frozen=True)
class CompiledPack:
    manifest: dict[str, Any]
    prompt: str


class ContextCompilerProvider:
    """Run unmodified upstream source from a checksum-verified checkout."""

    name = "context-compiler"

    def __init__(self, checkout: Path | None = None) -> None:
        override = os.environ.get("RHIZE_CONTEXT_COMPILER_CHECKOUT")
        self.checkout = (
            checkout or (Path(override) if override else default_checkout_path())
        ).expanduser()

    def doctor(self) -> ProviderHealth:
        if sys.version_info < (3, 9):
            return ProviderHealth(False, "Context Compiler requires Python 3.9 or newer")
        checkout = self.checkout.resolve(strict=False)
        if not checkout.is_dir():
            return ProviderHealth(False, f"pinned upstream checkout is absent at {checkout}")
        for relative_path, expected_hash in UPSTREAM_FILES.items():
            path = checkout / relative_path
            if not path.is_file():
                return ProviderHealth(False, f"missing pinned upstream file: {relative_path}")
            if _sha256(path.read_bytes()) != expected_hash:
                return ProviderHealth(False, f"checksum mismatch: {relative_path}")
        try:
            result = subprocess.run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return ProviderHealth(False, f"cannot verify upstream revision: {error}")
        revision = result.stdout.strip()
        if result.returncode != 0 or revision != UPSTREAM_REVISION:
            return ProviderHealth(False, "upstream checkout is not at the pinned revision")
        return ProviderHealth(True, "pinned revision and source checksums verified", revision)

    def compile(
        self,
        repo_root: Path,
        target_file: Path,
        *,
        snapshot: str,
        task_hash: str,
        max_hops: int = 2,
        max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> CompiledPack:
        health = self.doctor()
        if not health.ready:
            raise RuntimeError(health.note)
        repo = repo_root.expanduser().resolve(strict=True)
        target = target_file.expanduser().resolve(strict=True)
        if not repo.is_dir():
            raise ValueError("repository root must be a directory")
        if target.suffix != ".py" or not target.is_file():
            raise ValueError("Context Compiler target must be an existing Python file")
        if target.is_symlink():
            raise ValueError("Context Compiler does not accept a symlink target")
        try:
            target.relative_to(repo)
        except ValueError as error:
            raise ValueError("target must be inside the repository root") from error
        if not 1 <= max_hops <= 5:
            raise ValueError("max_hops must be between 1 and 5")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if any(path.is_symlink() for path in repo.rglob("*.py")):
            raise ValueError("Context Compiler does not scan repositories with Python symlinks")

        worker = Path(__file__).with_name("context_compiler_worker.py")
        command = [
            sys.executable,
            str(worker),
            "--checkout",
            str(self.checkout.resolve()),
            "--repo",
            str(repo),
            "--target",
            str(target),
            "--max-hops",
            str(max_hops),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Context Compiler exceeded its 300 second limit") from error
        if result.returncode != 0:
            detail = result.stderr.strip() or "upstream compiler failed"
            raise RuntimeError(detail[:1000])
        value = json.loads(result.stdout)
        manifest = value["manifest"]
        coverage = len(manifest["entries"]) / manifest["totalRepoFiles"]
        rejection_reasons = []
        if manifest["compiledTokens"] > max_tokens:
            rejection_reasons.append("compiled_context_exceeds_token_budget")
        if coverage > DEFAULT_MAX_ENTRY_COVERAGE:
            rejection_reasons.append("compiled_context_is_not_selective")
        if manifest["diagnostics"]["nameCollisionCount"] > DEFAULT_MAX_NAME_COLLISIONS:
            rejection_reasons.append("name_collision_budget_exceeded")
        warning_rejections = {
            "dynamic_dispatch_may_hide_dependencies": "dynamic_dispatch_requires_fallback",
            "decorator_registration_may_hide_dependencies": "decorator_registration_requires_fallback",
            "callback_registration_may_hide_dependencies": "callback_registration_requires_fallback",
            "unsupported_python_syntax_may_hide_dependencies": "unsupported_python_syntax_requires_fallback",
        }
        rejection_reasons.extend(
            reason
            for warning, reason in warning_rejections.items()
            if warning in manifest["warnings"]
        )
        manifest.update(
            {
                "repoId": hashlib.sha256(str(repo).encode()).hexdigest()[:16],
                "snapshot": snapshot,
                "taskHash": task_hash,
                "policy": {
                    "acceptedForInjection": not rejection_reasons,
                    "maximumTokens": max_tokens,
                    "maximumEntryCoverage": DEFAULT_MAX_ENTRY_COVERAGE,
                    "maximumNameCollisions": DEFAULT_MAX_NAME_COLLISIONS,
                    "observedEntryCoverage": coverage,
                    "rejectionReasons": rejection_reasons,
                },
            }
        )
        manifest["warnings"] = [*manifest["warnings"], *rejection_reasons]
        manifest["packId"] = stable_pack_id(manifest)
        return CompiledPack(manifest=manifest, prompt=value["prompt"])

    def write_pack(self, pack: CompiledPack, directory: Path) -> tuple[Path, Path]:
        validate_context_pack_manifest(pack.manifest)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        pack_id = pack.manifest["packId"]
        manifest_path = directory / f"{pack_id}.json"
        prompt_path = directory / f"{pack_id}.md"
        manifest_payload = json.dumps(pack.manifest, indent=2, sort_keys=True) + "\n"
        if manifest_path.exists() or prompt_path.exists():
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing_manifest = None
            if (
                manifest_path.is_file()
                and prompt_path.is_file()
                and isinstance(existing_manifest, dict)
                and _pack_identity_manifest(existing_manifest)
                == _pack_identity_manifest(pack.manifest)
                and prompt_path.read_text(encoding="utf-8") == pack.prompt
            ):
                return manifest_path, prompt_path
            raise FileExistsError(f"compiled pack id collides with different content: {pack_id}")
        _write_private(manifest_path, manifest_payload)
        try:
            _write_private(prompt_path, pack.prompt)
        except Exception:
            manifest_path.unlink(missing_ok=True)
            raise
        return manifest_path, prompt_path


def _write_private(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, content.encode())
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def stable_pack_id(manifest: dict[str, Any]) -> str:
    """Bind pack identity to stable source, policy, and provenance fields."""

    payload = json.dumps(
        _pack_identity_manifest(manifest),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"pack-{hashlib.sha256(payload).hexdigest()[:32]}"


def _pack_identity_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"packId", "buildMilliseconds"}
    }


def validate_context_pack_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "schemaVersion",
        "packId",
        "repoId",
        "snapshot",
        "taskHash",
        "targetPath",
        "compiler",
        "entries",
        "excludedCount",
        "totalRepoFiles",
        "naiveDumpTokens",
        "compiledTokens",
        "reductionPercent",
        "buildMilliseconds",
        "diagnostics",
        "policy",
        "warnings",
    }
    if set(manifest) != required or manifest.get("schemaVersion") != 1:
        raise ValueError("context pack manifest has an invalid top-level shape")
    if not re.fullmatch(r"pack-[a-f0-9]{32}", str(manifest["packId"])):
        raise ValueError("context pack has an invalid packId")
    if not re.fullmatch(r"[a-f0-9]{16}", str(manifest["repoId"])):
        raise ValueError("context pack has an invalid repoId")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest["taskHash"])):
        raise ValueError("context pack has an invalid taskHash")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", str(manifest["snapshot"])
    ):
        raise ValueError("context pack has an invalid snapshot")
    _require_relative_path(str(manifest["targetPath"]))
    compiler = manifest["compiler"]
    if not isinstance(compiler, dict) or compiler.get("revision") != UPSTREAM_REVISION:
        raise ValueError("context pack compiler revision is not pinned")
    entries = manifest["entries"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("context pack must have at least one entry")
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "tier",
            "hopDistance",
            "contentHash",
            "estimatedTokens",
        }:
            raise ValueError("context pack entry has an invalid shape")
        _require_relative_path(str(entry["path"]))
        if entry["tier"] not in {1, 2}:
            raise ValueError("context pack entry has an invalid tier")
        if not re.fullmatch(r"[a-f0-9]{64}", str(entry["contentHash"])):
            raise ValueError("context pack entry has an invalid content hash")
    policy = manifest["policy"]
    if not isinstance(policy, dict) or not isinstance(
        policy.get("acceptedForInjection"), bool
    ):
        raise ValueError("context pack policy verdict is invalid")
    diagnostics = manifest["diagnostics"]
    expected_diagnostics = {
        "unresolvedCallCount",
        "dynamicDispatchFileCount",
        "decoratorHintFileCount",
        "callbackRegistrationFileCount",
        "syntaxErrorFileCount",
        "nameCollisionCount",
    }
    if not isinstance(diagnostics, dict) or set(diagnostics) != expected_diagnostics:
        raise ValueError("context pack diagnostics have an invalid shape")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in diagnostics.values()
    ):
        raise ValueError("context pack diagnostics must be non-negative integers")


def _require_relative_path(value: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value in {"", "."}:
        raise ValueError("context pack paths must be repository-relative")

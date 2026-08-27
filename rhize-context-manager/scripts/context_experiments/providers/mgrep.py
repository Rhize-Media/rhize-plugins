"""Real mgrep CLI adapter with an independent upload inventory."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context_compiler import ProviderHealth


PINNED_MGREP_VERSION = "0.1.13"
DEFAULT_MAX_FILE_SIZE = 1_000_000
DEFAULT_MAX_FILE_COUNT = 10_000
DENIED_PARTS = {
    ".git",
    ".next",
    ".turbo",
    ".vercel",
    "node_modules",
    "coverage",
    "dist",
    "build",
    "vendor",
    "venv",
    ".venv",
}
DENIED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "auth.json",
    "cookies.json",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "service-account.json",
    "token.json",
}
DENIED_SUFFIXES = {
    ".cer",
    ".crt",
    ".der",
    ".jks",
    ".key",
    ".keystore",
    ".p12",
    ".pem",
    ".pfx",
}


@dataclass(frozen=True)
class Inventory:
    manifest: dict[str, Any]


class MgrepProvider:
    name = "mgrep"

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("mgrep")

    def doctor(self) -> ProviderHealth:
        if not self.executable:
            return ProviderHealth(False, "mgrep is not installed")
        try:
            result = subprocess.run(
                [self.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return ProviderHealth(False, f"cannot run mgrep: {error}")
        version = result.stdout.strip()
        if result.returncode != 0:
            return ProviderHealth(False, "mgrep --version failed")
        if version != PINNED_MGREP_VERSION:
            return ProviderHealth(
                False, "installed mgrep does not match the pinned version", version
            )
        if os.environ.get("MXBAI_API_KEY"):
            return ProviderHealth(True, "pinned mgrep CLI and API-key environment are present", version)
        token_path = Path.home() / ".mgrep" / "token.json"
        if not token_path.is_file():
            return ProviderHealth(False, "pinned mgrep CLI is installed but not authenticated", version)
        if token_path.stat().st_mode & 0o077:
            return ProviderHealth(False, "mgrep token file permissions are broader than 0600", version)
        try:
            token = json.loads(token_path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(str(token["created_at"]).replace("Z", "+00:00"))
            expiry = created.timestamp() + int(token["expires_in"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return ProviderHealth(False, "mgrep token metadata is invalid", version)
        if expiry <= datetime.now(timezone.utc).timestamp():
            return ProviderHealth(False, "mgrep token is expired", version)
        return ProviderHealth(True, "pinned mgrep CLI has an unexpired local login", version)

    def inventory(
        self,
        repo_root: Path,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_file_count: int = DEFAULT_MAX_FILE_COUNT,
    ) -> Inventory:
        repo = repo_root.expanduser().resolve(strict=True)
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("cannot inventory repository with git ls-files")
        ignored = _git_ignored_paths(repo, result.stdout)
        included = []
        excluded = []
        total_bytes = 0
        for raw_path in sorted(item for item in result.stdout.split(b"\0") if item):
            relative = raw_path.decode("utf-8", errors="strict")
            path = repo / relative
            reason = (
                "git_or_mgrep_ignore"
                if relative in ignored
                else _exclusion_reason(path, Path(relative), max_file_size)
            )
            if reason:
                excluded.append({"path": relative, "reason": reason})
                continue
            content = path.read_bytes()
            included.append(
                {
                    "path": relative,
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
            total_bytes += len(content)
        if len(included) > max_file_count:
            raise ValueError(
                f"inventory has {len(included)} eligible files, above cap {max_file_count}"
            )
        hidden_metadata = [
            row["path"]
            for row in excluded
            if row["reason"] == "hidden_path"
            and any(part in row["path"] for part in (".claude-plugin", ".codex-plugin"))
        ]
        warnings = []
        if hidden_metadata:
            warnings.append("vendor_hidden_path_policy_excludes_plugin_metadata")
        nested_ignore_files = [
            row["path"]
            for row in excluded
            if row["path"].endswith("/.mgrepignore")
        ]
        if nested_ignore_files:
            warnings.append("nested_mgrepignore_files_require_manual_review")
        blocking_reasons = sorted(
            {
                row["reason"]
                for row in excluded
                if row["reason"] in {"symlink", "not_regular_file"}
            }
        )
        if blocking_reasons:
            warnings.append("vendor_dry_run_blocked_by_unsafe_file_types")
        return Inventory(
            {
                "schemaVersion": 1,
                "preflightId": f"mgrep-preflight-{uuid.uuid4().hex}",
                "repoName": repo.name,
                "repoId": hashlib.sha256(str(repo).encode()).hexdigest()[:16],
                "limits": {
                    "maxFileSize": max_file_size,
                    "maxFileCount": max_file_count,
                },
                "included": included,
                "excluded": excluded,
                "includedFileCount": len(included),
                "includedBytes": total_bytes,
                "warnings": warnings,
                "vendorDryRunBlocked": bool(blocking_reasons or nested_ignore_files),
            }
        )

    def dry_run_watch(
        self,
        repo_root: Path,
        store: str,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_file_count: int = DEFAULT_MAX_FILE_COUNT,
    ) -> subprocess.CompletedProcess[str]:
        health = self.doctor()
        if not health.ready or not self.executable:
            raise RuntimeError(health.note)
        if not re.fullmatch(r"rhize-dogfood-[a-z0-9][a-z0-9-]{0,62}", store):
            raise ValueError("dogfood store must be a bounded rhize-dogfood-* name")
        repo = repo_root.expanduser().resolve(strict=True)
        return subprocess.run(
            [
                self.executable,
                "--store",
                store,
                "watch",
                "--dry-run",
                "--max-file-size",
                str(max_file_size),
                "--max-file-count",
                str(max_file_count),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def write_inventory(self, inventory: Inventory, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / f"{inventory.manifest['preflightId']}.json"
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=directory)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(
                descriptor,
                (json.dumps(inventory.manifest, indent=2, sort_keys=True) + "\n").encode(),
            )
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.link(temporary, path)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
        return path


def _exclusion_reason(path: Path, relative: Path, max_file_size: int) -> str | None:
    if path.is_symlink():
        return "symlink"
    if not path.is_file():
        return "not_regular_file"
    if any(part.startswith(".") for part in relative.parts):
        return "hidden_path"
    if any(part in DENIED_PARTS for part in relative.parts):
        return "denied_directory"
    if path.name in DENIED_NAMES or path.name.startswith(".env."):
        return "secret_filename"
    if path.suffix.lower() in DENIED_SUFFIXES:
        return "secret_suffix"
    if path.stat().st_size > max_file_size:
        return "file_size_cap"
    return None


def _git_ignored_paths(repo: Path, candidates: bytes) -> set[str]:
    command = ["git", "-C", str(repo)]
    mgrepignore = repo / ".mgrepignore"
    if mgrepignore.is_file():
        command.extend(["-c", f"core.excludesFile={mgrepignore}"])
    command.extend(["check-ignore", "--no-index", "--stdin", "-z"])
    result = subprocess.run(command, input=candidates, capture_output=True, timeout=30)
    if result.returncode not in {0, 1}:
        raise RuntimeError("cannot evaluate .gitignore and .mgrepignore rules")
    return {
        item.decode("utf-8", errors="strict")
        for item in result.stdout.split(b"\0")
        if item
    }

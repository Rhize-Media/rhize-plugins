from __future__ import annotations

import stat
import subprocess
from pathlib import Path

from context_experiments.providers.context_compiler import (
    ContextCompilerProvider,
    UPSTREAM_REVISION,
    validate_context_pack_manifest,
)
from context_experiments.providers.mgrep import MgrepProvider, PINNED_MGREP_VERSION


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_context_compiler_rejects_an_unverified_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    health = ContextCompilerProvider(checkout).doctor()
    assert health.ready is False
    assert "missing pinned upstream file" in health.note


def test_mgrep_inventory_is_real_content_hash_metadata_only(tmp_path: Path) -> None:
    provider = MgrepProvider()
    inventory = provider.inventory(REPO_ROOT)
    document = inventory.manifest
    assert document["includedFileCount"] > 0
    assert document["includedBytes"] > 0
    assert "warnings" in document
    assert all(not Path(row["path"]).is_absolute() for row in document["included"])
    assert all(set(row) == {"path", "bytes", "sha256"} for row in document["included"])
    path = provider.write_inventory(inventory, tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_mgrep_inventory_applies_ignore_and_hard_secret_rules(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".mgrepignore").write_text("private.txt\n")
    (repo / "safe.txt").write_text("safe")
    (repo / "private.txt").write_text("private")
    (repo / ".env.production").write_text("SECRET=value")
    subprocess.run(["git", "-C", str(repo), "add", "-f", "."], check=True)

    inventory = MgrepProvider().inventory(repo).manifest
    included = {row["path"] for row in inventory["included"]}
    excluded = {row["path"]: row["reason"] for row in inventory["excluded"]}
    assert "safe.txt" in included
    assert excluded["private.txt"] == "git_or_mgrep_ignore"
    assert excluded[".env.production"] in {"git_or_mgrep_ignore", "hidden_path"}


def test_mgrep_inventory_blocks_vendor_dry_run_for_symlinks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "safe.txt").write_text("safe")
    (repo / "linked.txt").symlink_to(repo / "safe.txt")
    subprocess.run(["git", "-C", str(repo), "add", "safe.txt", "linked.txt"], check=True)

    inventory = MgrepProvider().inventory(repo).manifest
    assert inventory["vendorDryRunBlocked"] is True
    assert "vendor_dry_run_blocked_by_unsafe_file_types" in inventory["warnings"]


def test_real_provider_pins_are_explicit() -> None:
    assert PINNED_MGREP_VERSION == "0.1.13"
    assert len(UPSTREAM_REVISION) == 40


def test_context_pack_manifest_validator_rejects_absolute_paths() -> None:
    invalid = {
        "schemaVersion": 1,
        "packId": "pack-" + "a" * 32,
        "repoId": "b" * 16,
        "snapshot": "snapshot",
        "taskHash": "c" * 64,
        "targetPath": "/private/target.py",
        "compiler": {"name": "context-compiler", "revision": UPSTREAM_REVISION, "maxHops": 2},
        "entries": [],
        "excludedCount": 0,
        "totalRepoFiles": 1,
        "naiveDumpTokens": 1,
        "compiledTokens": 1,
        "reductionPercent": 0,
        "buildMilliseconds": 1,
        "diagnostics": {},
        "policy": {"acceptedForInjection": False},
        "warnings": [],
    }
    try:
        validate_context_pack_manifest(invalid)
    except ValueError as error:
        assert "repository-relative" in str(error)
    else:
        raise AssertionError("absolute targetPath should be rejected")

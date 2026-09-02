"""Shared vault-path resolution for the obsidian-second-brain hook scripts.

Resolution order (first match wins):
1. `OBSIDIAN_VAULT_PATH` env var, if set -- supports multiple vaults via a
   `:`-separated list.
2. Vaults registered in Obsidian's own config
   (`~/Library/Application Support/obsidian/obsidian.json`).
3. The legacy iCloud default vault marker, as a substring fallback so
   existing users see no behavior change.

Every function here fails silently (returns an empty/False result) on any
error -- these hooks must never raise or block a tool call.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ICLOUD_VAULT_MARKER = "iCloud~md~obsidian/Documents/Obsidian Vault"

OBSIDIAN_CONFIG_PATH = (
    Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
)

# The legacy iCloud default vault, as a concrete path (rather than the
# substring marker above) -- used by resolve_vault_paths() to decide whether
# it is a real fallback candidate, not just a text match.
ICLOUD_VAULT_PATH = (
    Path.home()
    / "Library"
    / "Mobile Documents"
    / "iCloud~md~obsidian"
    / "Documents"
    / "Obsidian Vault"
)


def _env_vault_paths() -> list[str]:
    try:
        raw = os.environ.get("OBSIDIAN_VAULT_PATH") or ""
        return [p for p in raw.split(":") if p]
    except Exception:
        return []


def _registered_vault_paths() -> list[str]:
    try:
        with open(OBSIDIAN_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        vaults = data.get("vaults") or {}
        paths = []
        for entry in vaults.values():
            if isinstance(entry, dict):
                vault_path = entry.get("path")
                if vault_path:
                    paths.append(vault_path)
        return paths
    except Exception:
        return []


def _path_within(path: str, vault_path: str) -> bool:
    if not vault_path:
        return False
    normalized = vault_path.rstrip("/")
    return path == normalized or path.startswith(normalized + "/")


def is_vault_path(path: str) -> bool:
    """Return True if `path` falls inside a resolved Obsidian vault."""
    if not path:
        return False
    try:
        for vault_path in _env_vault_paths():
            if _path_within(path, vault_path):
                return True
        for vault_path in _registered_vault_paths():
            if _path_within(path, vault_path):
                return True
        return ICLOUD_VAULT_MARKER in path
    except Exception:
        return False


def resolve_vault_paths() -> list[str]:
    """Return every resolved Obsidian vault root, deduplicated, in order:

    1. `OBSIDIAN_VAULT_PATH` env var entries (`:`-separated)
    2. Vaults registered in Obsidian's own config (`obsidian.json`)
    3. The legacy iCloud default vault, only if that path actually exists on
       disk (unlike `is_vault_path()`'s substring marker, this is a concrete
       path check -- a caller resolving "the" vault needs a real candidate,
       not just a text match).

    Never raises -- always returns a (possibly empty) list, same contract as
    the rest of this module.
    """
    try:
        seen: list[str] = []
        for vault_path in (*_env_vault_paths(), *_registered_vault_paths()):
            if vault_path not in seen:
                seen.append(vault_path)
        icloud = str(ICLOUD_VAULT_PATH)
        if icloud not in seen and ICLOUD_VAULT_PATH.exists():
            seen.append(icloud)
        return seen
    except Exception:
        return []

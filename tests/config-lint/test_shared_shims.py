"""test_shared_shims.py — shared plugin scripts must not drift.

Plugins are islands: this repo does not vendor a shared runtime, so a script
needed by more than one plugin (e.g. the mcp-secret-launcher.sh shim
documented in docs/mcp-secret-launcher.md) is deliberately duplicated into
each plugin that needs it rather than symlinked or imported from a common
location. That duplication is only safe if the copies never drift apart and
each copy keeps its executable bit (the shim is invoked as a stdio MCP
server's `command`, not sourced) — this test is the drift check.

pytest-based, matching tests/config-lint/test_description_parity.py's style.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM_BASENAME = "scripts/mcp-secret-launcher.sh"


def _tracked_shim_paths() -> list[Path]:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", f"*/{SHIM_BASENAME}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


SHIM_PATHS = _tracked_shim_paths()


def test_at_least_two_shared_copies_exist() -> None:
    assert len(SHIM_PATHS) >= 2, (
        f"expected at least two tracked '{SHIM_BASENAME}' copies (the whole point of "
        "duplicating rather than sharing a single file), found "
        f"{len(SHIM_PATHS)}: {SHIM_PATHS}"
    )


def test_all_copies_are_byte_identical() -> None:
    assert SHIM_PATHS, f"no tracked '{SHIM_BASENAME}' copies found"
    contents = {path: path.read_bytes() for path in SHIM_PATHS}
    first_path, first_bytes = next(iter(contents.items()))
    for path, data in contents.items():
        assert data == first_bytes, (
            f"{path} differs from {first_path} — plugins are islands, so shared shims "
            "are duplicated deliberately and must not drift. Sync the copies (and add a "
            "SOURCES.md drift-check note if the divergence was intentional) before merging."
        )


@pytest.mark.parametrize("path", SHIM_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_copy_is_executable(path: Path) -> None:
    assert os.access(path, os.X_OK), (
        f"{path} is not executable — it is invoked directly as an MCP server 'command', "
        "not sourced, so it needs the executable bit."
    )


# typed_advice.py is the shared Laya advice client (docs/superpowers/specs/2026-10-16-laya-advise-everywhere-plan.md
# section 5): Context Manager owns the source, the other three plugin islands carry byte-identical copies.
TYPED_ADVICE_SOURCE = REPO_ROOT / "rhize-context-manager/scripts/typed_advice.py"
TYPED_ADVICE_COPIES = [
    REPO_ROOT / plugin / "scripts/typed_advice.py"
    for plugin in ("rhize-devflow", "rhize-ops", "project-launcher")
]


@pytest.mark.parametrize("path", TYPED_ADVICE_COPIES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_typed_advice_copy_matches_context_manager_source(path: Path) -> None:
    assert TYPED_ADVICE_SOURCE.is_file(), f"{TYPED_ADVICE_SOURCE} is the source of truth and must exist"
    assert path.is_file(), f"{path} is missing — each plugin island carries its own typed_advice.py"
    assert path.read_bytes() == TYPED_ADVICE_SOURCE.read_bytes(), (
        f"{path} differs from {TYPED_ADVICE_SOURCE} — edit the Context Manager copy, then re-copy it "
        "byte-for-byte into rhize-devflow, rhize-ops and project-launcher."
    )

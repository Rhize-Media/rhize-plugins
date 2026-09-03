"""test_claude_md_router.py — root CLAUDE.md stays a router, not a warehouse.

repo-shape R-A split the root `CLAUDE.md` (377 lines) into a short router of
mandatory rules plus a compact "Environment and workflow rules" section, and
moved session-level telemetry (hot-file lists, re-read counts, token-savings
figures) to `docs/session-guardrails.md`. This test pins two invariants so a
future edit can't silently regrow CLAUDE.md or drop an operational rule during
the move:

1. `CLAUDE.md` stays at or under 200 lines.
2. Every operational rule that used to live in CLAUDE.md is still findable
   there, by a pinned substring — not the telemetry (hot files, savings
   figures), which is expected to have moved to `docs/session-guardrails.md`.

pytest-based, following the style of tests/config-lint/test_description_parity.py.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD_PATH = REPO_ROOT / "CLAUDE.md"
GUARDRAILS_PATH = REPO_ROOT / "docs" / "session-guardrails.md"

MAX_LINES = 200

REQUIRED_PHRASES = [
    "bump_version.py",
    "protect-files",
    "version-check.yml",
    "tag-release.yml",
    "intended semantic delta",
    "python3",
    "timeout",
    "/usr/bin/find",
    "core.excludesFile",
    "jsonschema",
    ".jsonl",
    "Read a file before",
    "testpaths",
    "session-guardrails.md",
    "mcp-secret-launcher.sh",
    "test_shared_shims.py",
]


def _claude_md_text() -> str:
    return CLAUDE_MD_PATH.read_text(encoding="utf-8")


def test_claude_md_is_at_most_200_lines() -> None:
    line_count = len(_claude_md_text().splitlines())
    assert line_count <= MAX_LINES, (
        f"CLAUDE.md has {line_count} lines, expected at most {MAX_LINES} — "
        "it must stay a router; move detail to docs/session-guardrails.md"
    )


def test_claude_md_contains_every_required_phrase() -> None:
    text = _claude_md_text()
    missing = [phrase for phrase in REQUIRED_PHRASES if phrase not in text]
    assert not missing, (
        "CLAUDE.md is missing required operational-rule phrase(s): "
        f"{missing} — an operational rule must not be dropped when trimming "
        "CLAUDE.md down to a router"
    )


def test_session_guardrails_doc_exists_and_is_the_headroom_home() -> None:
    assert GUARDRAILS_PATH.is_file(), (
        f"{GUARDRAILS_PATH} not found — session-level telemetry moved out of "
        "CLAUDE.md must land here"
    )
    text = GUARDRAILS_PATH.read_text(encoding="utf-8")
    assert "Headroom Learned Patterns" in text, (
        "docs/session-guardrails.md must contain the 'Headroom Learned "
        "Patterns' section moved out of CLAUDE.md"
    )

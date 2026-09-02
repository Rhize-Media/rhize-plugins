"""test_description_parity.py — every plugin's description must be identical
everywhere it's copied.

`.claude-plugin/plugin.json`'s `description` is the canonical, plain-language
sentence (see root CLAUDE.md's "Documentation Maintenance" section). It is
copied verbatim into `.claude-plugin/marketplace.json`'s entry for that
plugin, and into `.codex-plugin/plugin.json` where that file exists. Nothing
kept these three copies in sync before this test — six-plus plugins had
already drifted (see .claude/plans/docs-front-door-index.md) — so this is a
plain equality check, not a rewrite of the curation logic.

pytest-based (unlike this repo's other tests/skill-map and tests/config-lint
checks, which are plain scripts) per the docs-front-door-index plan.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def _plugin_dir(entry: dict) -> Path:
    source = entry["source"]
    rel = source[2:] if source.startswith("./") else source
    return REPO_ROOT / rel


def _marketplace_plugins() -> list[dict]:
    return json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))["plugins"]


@pytest.mark.parametrize("entry", _marketplace_plugins(), ids=lambda e: e["name"])
def test_description_matches_claude_plugin(entry: dict) -> None:
    name = entry["name"]
    claude_plugin_path = _plugin_dir(entry) / ".claude-plugin" / "plugin.json"
    assert claude_plugin_path.is_file(), f"{claude_plugin_path} not found"
    claude_plugin = json.loads(claude_plugin_path.read_text(encoding="utf-8"))
    assert entry["description"] == claude_plugin["description"], (
        f"{name}: marketplace.json description differs from "
        f"{claude_plugin_path.relative_to(REPO_ROOT)}"
    )


@pytest.mark.parametrize("entry", _marketplace_plugins(), ids=lambda e: e["name"])
def test_description_matches_codex_plugin_when_present(entry: dict) -> None:
    name = entry["name"]
    codex_plugin_path = _plugin_dir(entry) / ".codex-plugin" / "plugin.json"
    if not codex_plugin_path.is_file():
        pytest.skip(f"{name} has no .codex-plugin/plugin.json")
    codex_plugin = json.loads(codex_plugin_path.read_text(encoding="utf-8"))
    assert entry["description"] == codex_plugin["description"], (
        f"{name}: marketplace.json description differs from "
        f"{codex_plugin_path.relative_to(REPO_ROOT)}"
    )

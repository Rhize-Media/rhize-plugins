"""test_mcp_tool_names.py — every obsidian-mcp-server tool the plugins name must
exist in the pinned server version.

obsidian-mcp-server 3.0.0 renamed its tools (obsidian_global_search ->
obsidian_search_notes, obsidian_read_note -> obsidian_get_note,
obsidian_update_note -> append_to_note / write_note / patch_note). The
commands kept the 2.x names under an unpinned `npx`, so they silently pointed
at tools that no longer existed. The fixture records the pinned version's live
`tools/list`; bumping the pin in obsidian-second-brain/.mcp.json requires
re-recording it.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "obsidian-mcp-server-tools.json"
TOOL_REF = re.compile(r"\bobsidian_[a-z]+(?:_[a-z]+)+\b")
MCP_REF = re.compile(r"mcp__obsidian-mcp-server__(\w+)")


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_fixture_matches_pin() -> None:
    args = json.loads((REPO_ROOT / "obsidian-second-brain" / ".mcp.json").read_text())["mcpServers"]["obsidian-mcp-server"]["args"]
    fixture = _fixture()
    assert f"{fixture['package']}@{fixture['version']}" in args, "re-record the fixture when the pin changes"


def test_referenced_tools_exist() -> None:
    known = set(_fixture()["tools"])
    # Operational files only: commands, skills and agents that instruct a model.
    # CHANGELOG/README/GUIDE prose may name retired tools when documenting a rename.
    files = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "*/commands/*.md", "*/skills/*.md", "*/agents/*.md"],
                           capture_output=True, text=True, check=True).stdout.split()
    missing = {}
    for rel in files:
        text = (REPO_ROOT / rel).read_text()
        # Every bare obsidian_* name counts in this plugin's own files; elsewhere only
        # in files that name the server, so unrelated identifiers aren't flagged.
        checks_bare = rel.startswith("obsidian-second-brain/") or "obsidian-mcp-server" in text
        refs = set(MCP_REF.findall(text)) | {r for r in TOOL_REF.findall(text) if checks_bare or r in known}
        unknown = sorted(r for r in refs if r not in known and r.startswith("obsidian_") and "mcp" not in r)
        if unknown:
            missing[rel] = unknown
    assert not missing, f"tools not in obsidian-mcp-server {_fixture()['version']}: {missing}"

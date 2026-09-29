"""test_codex_mcp_parity.py - a plugin's Codex manifest must carry the same MCP
servers as its Claude `.mcp.json`, minus the plugin-root variable.

Why the two files differ at all: Codex auto-discovers an installed plugin's
`.mcp.json`, but passes `${CLAUDE_PLUGIN_ROOT}` (and `${PLUGIN_ROOT}`) through as
LITERAL strings in `command`, `args`, `env` and `cwd`, so a launcher path spelled
`${CLAUDE_PLUGIN_ROOT}/scripts/x.sh` fails to spawn (ENOENT). Verified with Codex CLI
0.158.0 on 2026-09-29: an inline `mcpServers` object in `.codex-plugin/plugin.json`
overrides the same-named `.mcp.json` entry, and `"cwd": "."` resolves to the installed
plugin root, so `./scripts/x.sh` runs. `.mcp.json` stays untouched for Claude Code.

This test pins the transformation: same server names, same args and env, command
`${CLAUDE_PLUGIN_ROOT}/<path>` -> `./<path>`, `cwd` ".", and no `${...}` left in the
Codex entry. Plugins without a `.codex-plugin/plugin.json` are out of scope here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_VAR = "${CLAUDE_PLUGIN_ROOT}/"


def _plugins_with_both() -> list[str]:
    return sorted(
        p.name
        for p in REPO_ROOT.iterdir()
        if (p / ".mcp.json").is_file() and (p / ".codex-plugin" / "plugin.json").is_file()
    )


def _claude_servers(plugin: str) -> dict:
    return json.loads((REPO_ROOT / plugin / ".mcp.json").read_text())["mcpServers"]


def _codex_servers(plugin: str) -> dict:
    manifest = json.loads((REPO_ROOT / plugin / ".codex-plugin" / "plugin.json").read_text())
    return manifest.get("mcpServers", {})


def expected_codex_entry(server: dict) -> dict:
    """The Codex-side equivalent of one Claude `.mcp.json` stdio server entry."""
    command = server["command"]
    assert command.startswith(ROOT_VAR), f"unexpected command shape: {command!r}"
    entry = {"command": "./" + command[len(ROOT_VAR):], "args": server.get("args", [])}
    entry["cwd"] = "."
    if "env" in server:
        entry["env"] = server["env"]
    return entry


PLUGINS = _plugins_with_both()


def test_plugins_with_both_manifests_found() -> None:
    assert "obsidian-second-brain" in PLUGINS, "layout changed; obsidian-second-brain lost its .mcp.json or Codex manifest"


@pytest.mark.parametrize("plugin", PLUGINS)
def test_codex_mcp_servers_match_claude(plugin: str) -> None:
    claude = _claude_servers(plugin)
    codex = _codex_servers(plugin)
    assert isinstance(codex, dict), f"{plugin}: `mcpServers` in .codex-plugin/plugin.json must be an inline object; the string form `./.mcp.json` reuses the unexpanded ${{CLAUDE_PLUGIN_ROOT}} command"
    assert set(codex) == set(claude), f"{plugin}: Codex/Claude MCP server names differ"
    for name, server in claude.items():
        if "command" not in server:
            # HTTP servers carry no plugin-root path and need no Codex override.
            assert codex[name] == server, f"{plugin}/{name}: HTTP server entry must be identical"
            continue
        assert codex[name] == expected_codex_entry(server), f"{plugin}/{name}: Codex entry drifted from .mcp.json"
        assert "${" not in json.dumps(codex[name]), f"{plugin}/{name}: Codex does not expand ${{...}} variables"


def test_expected_entry_transformation() -> None:
    claude = {"command": "${CLAUDE_PLUGIN_ROOT}/scripts/l.sh", "args": ["V", "--", "npx", "p@1.2.3"], "env": {"A": "b"}}
    assert expected_codex_entry(claude) == {
        "command": "./scripts/l.sh",
        "args": ["V", "--", "npx", "p@1.2.3"],
        "cwd": ".",
        "env": {"A": "b"},
    }


def test_codex_catalog_plugins_with_bundled_servers_have_codex_manifests() -> None:
    """A plugin in the Codex catalog that bundles `.mcp.json` must ship a Codex
    manifest: otherwise Codex loads `.mcp.json` as-is and the unexpanded
    `${CLAUDE_PLUGIN_ROOT}` launcher path fails (how seo-aeo-geo was broken)."""
    catalog = json.loads((REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    listed = {entry["name"] for entry in catalog["plugins"]}
    missing = sorted(
        name for name in listed
        if (REPO_ROOT / name / ".mcp.json").is_file()
        and not (REPO_ROOT / name / ".codex-plugin" / "plugin.json").is_file()
    )
    assert not missing, f"bundle .mcp.json but lack .codex-plugin/plugin.json: {missing}"

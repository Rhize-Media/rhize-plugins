# Changelog — obsidian-second-brain

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-10-10_ version bump — 1.8.0 → 1.9.0 (minor); marketplace 2.101.1 → 2.102.0.
- _2026-10-10_ Router: defuddle declares the router phrase "web clipping"; knowledge-compiler regains the `security` topic and `python` stack (third-party inference words restored).
- _2026-10-10_ version bump — 1.7.7 → 1.8.0 (minor); marketplace 2.100.4 → 2.101.0.
- _2026-10-10_ Skill-map metadata: vault-alignment extends second-brain; defuddle and obsidian-cli declare their CLI dependencies; knowledge-compiler and defuddle tags follow the consolidated vocabulary (web-clipping → content-authoring, python stack retired).
- _2026-09-29_ version bump — 1.7.6 → 1.7.7 (patch); marketplace 2.94.0 → 2.94.1.
- _2026-09-29_ Give Codex a working bundled Obsidian MCP server. Codex loads an installed plugin's `.mcp.json` but does not expand `${CLAUDE_PLUGIN_ROOT}` in `command`, `args`, `env` or `cwd`, so the launcher path reached the OS as literal text and the server failed with `No such file or directory` (verified with Codex CLI 0.158.0). `.codex-plugin/plugin.json` now carries an inline `mcpServers.obsidian-mcp-server` entry (`./scripts/mcp-secret-launcher.sh`, `"cwd": "."`, same pinned `obsidian-mcp-server@3.6.0` args and env), which Codex uses in place of the same-named `.mcp.json` entry. `.mcp.json` is unchanged for Claude Code. `tests/config-lint/test_codex_mcp_parity.py` fails when the two entries drift. Codex passes a stripped environment to MCP servers, so on Codex the key must come from the macOS keychain (or `env_vars` in `~/.codex/config.toml`); a hand-configured `[mcp_servers.obsidian-mcp-server]` block in that file shadows the plugin's entry.
- _2026-09-29_ version bump — 1.7.5 → 1.7.6 (patch); marketplace 2.91.2 → 2.91.3.
- _2026-09-29_ Pin the bundled server to `obsidian-mcp-server@3.6.0` and migrate every command to its tool names. Since obsidian-mcp-server 3.0.0 (2026-04-29), the unpinned `npx` had been serving renamed tools, so `obsidian_global_search`, `obsidian_read_note` and `obsidian_update_note` in the commands' `allowed-tools` and fallbacks no longer existed. The replacements are `obsidian_search_notes`, `obsidian_get_note`, and `obsidian_append_to_note` / `obsidian_write_note` / `obsidian_patch_note`. `tests/obsidian-second-brain/test_mcp_tool_names.py` checks every referenced tool against the pinned version's recorded `tools/list`.
- _2026-09-03_ version bump — 1.7.4 → 1.7.5 (patch); marketplace 2.59.1 → 2.60.0.
- _2026-09-03_ version bump — 1.7.3 → 1.7.4 (patch); marketplace 2.58.1 → 2.58.2.

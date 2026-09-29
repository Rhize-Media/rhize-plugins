# Changelog — obsidian-second-brain

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-29_ version bump — 1.7.5 → 1.7.6 (patch); marketplace 2.91.2 → 2.91.3.
- _2026-09-29_ Pin the bundled server to `obsidian-mcp-server@3.6.0` and migrate every command to its tool names. Since obsidian-mcp-server 3.0.0 (2026-04-29), the unpinned `npx` had been serving renamed tools, so `obsidian_global_search`, `obsidian_read_note` and `obsidian_update_note` in the commands' `allowed-tools` and fallbacks no longer existed. The replacements are `obsidian_search_notes`, `obsidian_get_note`, and `obsidian_append_to_note` / `obsidian_write_note` / `obsidian_patch_note`. `tests/obsidian-second-brain/test_mcp_tool_names.py` checks every referenced tool against the pinned version's recorded `tools/list`.
- _2026-09-03_ version bump — 1.7.4 → 1.7.5 (patch); marketplace 2.59.1 → 2.60.0.
- _2026-09-03_ version bump — 1.7.3 → 1.7.4 (patch); marketplace 2.58.1 → 2.58.2.

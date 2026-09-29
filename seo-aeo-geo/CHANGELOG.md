# Changelog — seo-aeo-geo

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-29_ Add `.codex-plugin/plugin.json` with an inline `dataforseo` MCP entry (`./scripts/mcp-secret-launcher.sh`, `cwd: "."`, same pinned args and env as `.mcp.json`). Codex was already installing this plugin from the shared catalog and loading `.mcp.json`, but it doesn't expand `${CLAUDE_PLUGIN_ROOT}`, so the server failed with ENOENT. The Codex manifest's description matches the Claude manifest, and `test_codex_mcp_parity.py` now covers this plugin. Verified by installing into an isolated `CODEX_HOME`: `codex mcp list` resolves the launcher from the plugin root.
- _2026-09-29_ version bump — 1.5.3 → 1.5.4 (patch); marketplace 2.91.1 → 2.91.2.
- _2026-09-29_ Pin the bundled server to `dataforseo-mcp-server@3.1.1` (verified: it answers `initialize` at 2025-11-25 and lists its tools). An unpinned `npx` picked up upstream releases silently, including any that drop the pre-2026-07-28 handshake.
- _2026-09-03_ version bump — 1.5.2 → 1.5.3 (patch); marketplace 2.59.1 → 2.60.0.

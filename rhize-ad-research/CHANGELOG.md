# Changelog

## [Unreleased]

### Added

- _2026-11-17_ version bump — 0.3.0 → 0.4.0 (minor); marketplace 2.125.2 → 2.126.0.
- _2026-11-16_ version bump — 0.2.0 → 0.3.0 (minor); marketplace 2.124.1 → 2.125.0.
- Replace paid Apify execution with official native Meta MCP capture; preserve historical evidence read-only. Bound queries, seal responses/records, verify exports, distinguish empty and rejected rows, and document Claude/Codex search-only setup and Tom acceptance. Agent Reach assessed as optional future dependency; nothing installed or copied.
- _2026-11-16_ version bump — 0.1.0 → 0.2.0 (minor); marketplace 2.123.2 → 2.124.0.

- Initial provider-check and collection core for a shared Mac workflow in Claude Code and Codex.
- Journal-before-submit, scoped budget checks, locked shared state, conservative recovery, and factual JSON/CSV exports.
- Distinguish charged provider error rows from ads; hold paid follow-up collection after the live no_items/BLOCKED result.
- Fable review corrections cover rejection recovery, response shape, cap classification, pricing drift, authority decisions and billing cross-checks.
- Keep incomplete dataset classification and unverified empty results held; bind every run and workspace to its client/account.
- Document explicit host invocation; shared hook-router positive prompts are silent, without changing global routing or thresholds.

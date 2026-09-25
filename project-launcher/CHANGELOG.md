# Changelog — project-launcher

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-24_ Local Laya checkpoint routing evidence and fixed Foreman-style GSD supervision questions for planner, executor, and verifier. A bounded local research runner compares pinned checkpoints, question wording, and abstention thresholds on human-adjudicated labels with a locked holdout and Arm A evidence.
- _2026-09-24_ version bump — 1.9.1 → 1.10.0 (minor); marketplace 2.79.1 → 2.80.0.
- _2026-09-24_ version bump — 1.9.0 → 1.9.1 (patch); marketplace 2.79.0 → 2.79.1.
- _2026-09-24_ version bump — 1.8.3 → 1.9.0 (minor); marketplace 2.78.1 → 2.79.0.
- _2026-09-24_ Project-local Jev/Laya typed decision client, GSD planner/executor/verifier skill injection, per-agent invocation hooks, privacy-safe receipts, and a provider probe in the handoff gate. Pin GSD 1.42.3 and use its Claude Code `/gsd-autonomous` command.
- _2026-09-03_ version bump — 1.8.2 → 1.8.3 (patch); marketplace 2.59.1 → 2.60.0.

### Fixed

- _2026-09-24_ The launch probe now supplies Laya's required question instructions and rejects a local response routed to a different checkpoint.
- _2026-09-24_ Local Laya calls no longer send Jev's default model ID, which silently selected a base checkpoint. New decision clients start in shadow mode with distinct shadow receipts; advisory suggestions require an explicit mode override after checkpoint evaluation.

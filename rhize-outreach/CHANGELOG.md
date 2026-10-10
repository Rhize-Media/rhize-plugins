## [Unreleased]

### Added

- _2026-10-10_ version bump — 0.3.0 → 0.4.0 (minor); marketplace 2.101.1 → 2.102.0.
- _2026-10-10_ Router: review-outreach-businesses regains the `prospecting` topic and the phrase "candidate businesses"; review-outreach-package drops `seo-audit`/`visualization`, which tied it with unrelated skills.
- _2026-10-10_ version bump — 0.2.0 → 0.3.0 (minor); marketplace 2.100.4 → 2.101.0.
- _2026-10-10_ /rhize-outreach:setup stops when launched by /rhize-core:setup (--from-rhize-setup), matching rhize-tasks; the outreach pipeline (doctor → run → businesses → package → email → reconcile) is declared for next-step suggestions; setup carries the postgresql stack.
- _2026-09-24_ version bump — 0.1.0 → 0.2.0 (minor); marketplace 2.80.0 → 2.81.0.

- Upgrade the local prospect workflow to a resumable selected-business agent graph with explicit package and email review holds.
- Add a loopback setup wizard, pinned runtime installer, read-only doctor, and one-command local launch.
- Clarify local-only storage and email-delivery limits; do not request unrelated provider credentials.

# Changelog — rhize-outreach

## 0.1.0 — 2026-09-24

- Initial internal Claude/Codex package for the local selected-business workflow.
- Adds pinned runtime setup, read-only doctor, and foreground local UI launch.
- Documents human review holds, no-send/no-publish boundaries, and unavailable browser/design-system execution.

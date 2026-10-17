# Changelog

## [Unreleased]

### Added

- _2026-10-17_ version bump — 0.1.0 → 0.2.0 (minor); marketplace 2.110.1 → 2.111.0.
- Publish the previously local-only bridge as a self-contained Rhize marketplace plugin for
  Codex and Claude Code, with portable startup, private interpreter selection and setup guidance.
- Preserve Search/Research, follow-ups, durable recovery/export/cancellation, encrypted Keychain
  transfer, explicit citation validation and bounded large responses. Existing jobs remain usable.
- Add marketplace packaging/startup regression coverage and register offline evaluation coverage.

- General-use JSON configuration replaces organization-specific runtime paths and credential-store names; private overrides preserve existing sessions and reports.

## 0.1.0 — local prototype

- Verified native Codex Research, Search, follow-up, local cancellation and GET-only recovery.
  See the technical guide for evidence and limitations. This version was distributed locally only.

# Changelog — rhize-tasks

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- Setup and doctor bootstrap a pinned-tag checkout of the runtime from the new
  [`Rhize-Media/rhize-tasks`](https://github.com/Rhize-Media/rhize-tasks) repository (currently
  pinned to `v0.5.1`) into `~/Library/Application Support/Rhize Tasks/source/<tag>/`, running the
  installer's non-mutating `--check` before any install. Doctor reports `sourceRef`,
  `sourceCommit`, and `sourceDrift` against that pin.
- `setup/manifest.json` (schema 3) gained `git` and `node` CLI dependencies for the bootstrap
  step, a `rhize-tasks runtime` data dependency recording the runtime repo and its pinned tag,
  and a `source/<tag>/` artifact entry.

### Changed

- The plugin no longer ships the local-first planning service, installer, Swift EventKit helper,
  dashboard, schemas, or their tests — `service/`, `installer/`, `native/`, `dashboard/`,
  `schemas/`, `tests/`, and `package.json` moved to `Rhize-Media/rhize-tasks`. README and GUIDE
  updated for the thin layout and the bootstrap flow.

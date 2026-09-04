# Changelog — procedural-memory

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-04_ version bump — 0.5.4 → 0.5.5 (patch); marketplace 2.61.2 → 2.61.3.

### Fixed

- _2026-09-03_ `hooks/post-bash-candidate-queue.sh` is POSIX sh again: a bash-only `<<<` herestring
  made the hook a syntax error under dash (Ubuntu's `/bin/sh`), found by the first run of the promoted
  CI gate. Every shipped `#!/bin/sh` script now passes `dash -n`.

### Added

- _2026-09-03_ version bump — 0.5.3 → 0.5.4 (patch); marketplace 2.61.0 → 2.61.1.
- _2026-09-03_ version bump — 0.5.2 → 0.5.3 (patch); marketplace 2.58.1 → 2.58.2.

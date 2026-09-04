# Changelog — procedural-memory

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-04_ version bump — 0.5.5 → 0.5.6 (patch); marketplace 2.61.3 → 2.61.4.
- _2026-09-04_ version bump — 0.5.4 → 0.5.5 (patch); marketplace 2.61.2 → 2.61.3.

### Fixed

- _2026-09-03_ `hooks/post-bash-candidate-queue.sh` is POSIX sh again: a bash-only `<<<` herestring
  and a `${var:0:n}` substring expansion broke the hook under dash (Ubuntu's `/bin/sh`), found by the
  first runs of the promoted CI gate. Every shipped `#!/bin/sh` script now passes `dash -n`, and the
  hook's tests run it under every POSIX shell present on the machine (sh and dash).

### Added

- _2026-09-03_ version bump — 0.5.3 → 0.5.4 (patch); marketplace 2.61.0 → 2.61.1.
- _2026-09-03_ version bump — 0.5.2 → 0.5.3 (patch); marketplace 2.58.1 → 2.58.2.

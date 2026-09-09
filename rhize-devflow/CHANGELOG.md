# Changelog — rhize-devflow

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

### Added

- _2026-09-09_ version bump — 2.21.0 → 2.21.1 (patch); marketplace 2.70.0 → 2.70.1.

### Fixed

- _2026-09-09_ the refactor gate no longer arms a receipt at the filesystem root, and never matches
  one during workspace lookup. A Projectless context (no repository cwd) resolved its workspace to
  `/` and armed a `pending` receipt there; because workspace resolution falls back to a
  longest-prefix containment scan, that receipt matched **every** path on the machine. Observed
  effect: release commands blocked in unrelated repositories while `status` reported those repos
  reconciled. Latent effect, and the reason this is a fix rather than a papercut: `hook_write`
  promotes a receipt to `implementation` and the Stop hook blocks turn end on that phase through
  the same lookup — so a root receipt could stop every session on the machine from declaring
  completion, including a scheduled routine mid-run. `prepare` at the root now warns and exits 0
  (deliberately not a new nonzero failure mode for automation) instead of walking the entire
  filesystem looking for Git roots. `status`/`dismiss --workspace /` still read a stale root
  receipt directly so operators can find and clear one.

### Added

- _2026-09-09_ version bump — 2.20.3 → 2.21.0 (minor); marketplace 2.69.1 → 2.70.0.
- _2026-09-09_ **Generated-docs exemption: `claudedocs/` prose no longer trips the refactor
  gate.** A scheduled routine that records its findings in `claudedocs/` hit the gate on every
  run with nothing to map — the write has no symbol, caller, test, or semantic delta to
  describe, so the only available move was `dismiss`, which is meant for misclassification, not
  for a whole category of expected writes. `is_docs_path()` now exempts `DOCS_PATHS`
  (`claudedocs/`) when the extension is prose (`DOCS_EXTENSIONS`: `.md`, `.mdx`, `.markdown`,
  `.txt`, `.rst`), reaching the same three places as the config exemption: `hook-write` doesn't
  block and doesn't advance a `prepared` receipt, `hook-command` counts it among exempt dirty
  paths, and `reconcile` won't let it force `OUT_OF_SYNC`.
  The extension condition is load-bearing, mirroring the `.eslintrc.js` precedence rule above
  it: without it the exemption is a trivial bypass — park code under `claudedocs/`, edit it
  ungated, then move it — so `claudedocs/scripts/fix.py` stays gated. The tree list is
  deliberately just `claudedocs/`; a generic `docs/` is not exempt, since hand-maintained docs
  trees routinely hold fixtures and executable examples. Covered by three new `hook-write` and
  three new `hook-command` assertions in
  `tests/rhize-devflow/test_refactor_gate_config_scope.sh` (358 devflow tests pass).
- _2026-09-03_ version bump — 2.20.2 → 2.20.3 (patch); marketplace 2.59.1 → 2.60.0.
- _2026-09-03_ version bump — 2.20.1 → 2.20.2 (patch); marketplace 2.58.1 → 2.58.2.

# Changelog — rhize-devflow

Entries before 2026-09-03 live in [docs/release/CHANGELOG-history.md](../docs/release/CHANGELOG-history.md).

## [Unreleased]

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

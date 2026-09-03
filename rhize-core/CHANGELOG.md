# Changelog — rhize-core

## [Unreleased]

### Added

- _2026-09-03_ version bump — 1.0.0 → 1.0.1 (patch); marketplace 2.61.0 → 2.61.1.
- _2026-09-03_ **rhize-core: new plugin — the marketplace control plane (repo-shape R-B).**
  Split out of `rhize-ops`: `/rhize-core:setup` (the fleet setup wizard, moved verbatim from
  `/rhize-ops:rhize-setup`), the four platform scripts (`evaluation_setup.py`,
  `setup_orchestrator.py`, `setup_artifacts.py`, `git_preflight.py`), `setup/manifest.json`,
  `setup/evaluation-catalog.json` (now with a `platform` domain and a `rhize-core` component of
  its own — zero skills, one offline pytest-backed suite, one `greenfield` benchmark), the four
  JSON Schema files under `schemas/`, `templates/claude-home.gitignore`, `docs/setup-artifacts.md`,
  and a new `docs/contract.md` naming the 1.0.0 stability contract (manifest schema 3, the
  orchestrator's JSON schemas, run-state/receipt layouts, the `--from-rhize-setup` handshake, and
  the deprecation policy). `rhize-ops` keeps a byte-identical, drift-tested fallback copy of this
  wizard and its assets for one release — see `rhize-ops/CHANGELOG.md` for the removal date.
  `evaluation_setup.py`'s catalog path and `setup_artifacts.py`'s rendered-doc path both prefer
  `rhize-core/` when present under the repo root, falling back to whichever plugin directory the
  running copy itself lives in otherwise, so a `rhize-ops`-only install stays self-contained.

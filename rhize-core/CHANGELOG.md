# Changelog — rhize-core

## [Unreleased]

### Added

- _2026-09-19_ Include the canonical RHIZE Content Engine in the evaluation catalog and 58-skill coverage contract; preserve byte-identical core/ops fallback catalogs and setup scripts.
- _2026-09-19_ version bump — 1.0.4 → 1.0.5 (patch); marketplace 2.76.0 → 2.76.1.
- _2026-09-15_ version bump — 1.0.3 → 1.0.4 (patch); marketplace 2.72.0 → 2.72.1.
- _2026-09-06_ version bump — 1.0.2 → 1.0.3 (patch); marketplace 2.69.0 → 2.69.1.
- _2026-09-04_ version bump — 1.0.1 → 1.0.2 (patch); marketplace 2.61.1 → 2.61.2.

### Changed

- Include the shared Claude/Codex bridge skill in the operations evaluation catalog and document its private setup artifacts. Offline coverage does not run provider canaries.

- _2026-09-06_ Regenerate the setup artifact inventory for private paired-memory measurements; runtime behavior is unchanged.

- _2026-09-03_ `docs/setup-artifacts.md` re-rendered for the rhize-tasks runtime re-pin (v0.5.2). Artifact
  paths allow only the `<home>` placeholder, so a re-pin re-renders this doc by design.

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

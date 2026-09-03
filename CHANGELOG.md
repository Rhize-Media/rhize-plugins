# Changelog

Marketplace-level changes only: coordinated version bumps across plugins, cross-plugin programs,
and changes to repository-wide tooling (`scripts/bump_version.py`, CI, config lint, docs
generation). A change scoped to one plugin — its own feature, fix, or internal change — belongs in
that plugin's own changelog instead.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Per-plugin changelogs

- [seo-aeo-geo/CHANGELOG.md](./seo-aeo-geo/CHANGELOG.md)
- [obsidian-second-brain/CHANGELOG.md](./obsidian-second-brain/CHANGELOG.md)
- [project-launcher/CHANGELOG.md](./project-launcher/CHANGELOG.md)
- [rhize-devflow/CHANGELOG.md](./rhize-devflow/CHANGELOG.md)
- [rhize-context-manager/CHANGELOG.md](./rhize-context-manager/CHANGELOG.md)
- [rhize-ops/CHANGELOG.md](./rhize-ops/CHANGELOG.md)
- [rhize-tasks/CHANGELOG.md](./rhize-tasks/CHANGELOG.md)
- [rhize-cowork/CHANGELOG.md](./rhize-cowork/CHANGELOG.md)
- [procedural-memory/CHANGELOG.md](./procedural-memory/CHANGELOG.md)

Entries before 2026-09-03 live in
[docs/release/CHANGELOG-history.md](./docs/release/CHANGELOG-history.md), preserved verbatim as a
point-in-time record.

## [Unreleased]

### Added

- _2026-09-03_ version bump — **rhize-ops** 0.18.0 → 0.19.0 (minor); **obsidian-second-brain** 1.7.4 → 1.7.5 (patch); **project-launcher** 1.8.2 → 1.8.3 (patch); **rhize-context-manager** 0.25.1 → 0.25.2 (patch); **rhize-devflow** 2.20.2 → 2.20.3 (patch); **seo-aeo-geo** 1.5.2 → 1.5.3 (patch); **rhize-cowork** 0.2.2 → 0.2.3 (patch); marketplace 2.59.1 → 2.60.0.
- _2026-09-03_ **Repo-shape R-B: the setup hub moved into its own plugin.** New `rhize-core`
  plugin (1.0.0) owns `/rhize-core:setup`, the setup orchestrator, the evaluation setup engine,
  the setup-artifacts registry, the Git preflight, the manifest schemas, and a written stability
  contract (`rhize-core/docs/contract.md`). `rhize-ops` keeps a drift-tested, self-contained
  fallback copy plus a forwarding `/rhize-ops:rhize-setup` for one release, and its manifest keeps
  the tool dependencies it actually probes. Platform scripts resolve their assets from `rhize-core/`
  when present, else from their own plugin directory. Cross-plugin docs, `START-HERE.md`, the root
  README, `evals/rhize-core/`, and `tests/rhize-core/` follow the move.
- _2026-09-03_ version bump — **rhize-ops** 0.17.1 → 0.18.0 (minor); marketplace 2.58.1 → 2.59.0.
- _2026-09-03_ version bump — **obsidian-second-brain** 1.7.3 → 1.7.4 (patch); **procedural-memory** 0.5.2 → 0.5.3 (patch); **rhize-context-manager** 0.25.0 → 0.25.1 (patch); **rhize-devflow** 2.20.1 → 2.20.2 (patch); marketplace 2.58.1 → 2.58.2.
- _2026-09-03_ **Repo-shape R-A hygiene pass.** Tests consolidated under `tests/`; every plugin
  gained its own `CHANGELOG.md`, with `scripts/bump_version.py` now inserting the bump bullet into
  both the root file and each bumped plugin's file; `evals/README.md` gained a per-suite index;
  a shared-shim drift test guards duplicated plugin scripts (e.g. `mcp-secret-launcher.sh`) from
  drifting apart; root `scripts/` is tracked normally instead of `.gitignore`-allowlisted; a
  proposed CI workflow was added under `.github/ci-proposed/`; `CLAUDE.md` was reshaped into a
  router, with session-loop guardrails moved to `docs/session-guardrails.md`; and
  `docs/skill-map/README.md` indexes the skill-map subsystem's files in place rather than moving
  them.

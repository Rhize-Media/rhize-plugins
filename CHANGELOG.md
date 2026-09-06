# Changelog

## 2.67.0 — 2026-09-05

- rhize-ops 0.24.0: static Codex inventory export and host-specific retention rationale in prune.
- rhize-context-manager 0.28.0: targeted Skill Forge capture/activation workflow with host verification and rollback.
- Requires Skill Forge 0.19+ for the new governance commands; existing audit/prune behavior remains compatible.

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

- _2026-09-06_ version bump — **rhize-context-manager** 0.29.0 → 0.30.0 (minor); marketplace 2.68.0 → 2.69.0.
- _2026-09-06_ version bump — **rhize-context-manager** 0.28.0 → 0.29.0 (minor); marketplace 2.67.0 → 2.68.0.
- _2026-09-05_ version bump — **rhize-context-manager** 0.27.1 → 0.28.0 (minor); marketplace 2.66.0 → 2.67.0.
- _2026-09-05_ version bump — **rhize-ops** 0.23.1 → 0.24.0 (minor); marketplace 2.65.2 → 2.66.0.
- _2026-09-05_ version bump — **rhize-ops** 0.23.0 → 0.23.1 (patch); marketplace 2.65.1 → 2.65.2.
- _2026-09-05_ version bump — **rhize-context-manager** 0.27.0 → 0.27.1 (patch); marketplace 2.65.0 → 2.65.1.
- _2026-09-05_ version bump — **rhize-ops** 0.22.0 → 0.23.0 (minor); marketplace 2.64.0 → 2.65.0.
- _2026-09-04_ version bump — **rhize-context-manager** 0.26.0 → 0.27.0 (minor); **rhize-ops** 0.21.0 → 0.22.0 (minor); marketplace 2.63.0 → 2.64.0.
- _2026-09-04_ version bump — **rhize-context-manager** 0.25.3 → 0.26.0 (minor); marketplace 2.62.0 → 2.63.0.
- _2026-09-04_ version bump — **rhize-ops** 0.20.0 → 0.21.0 (minor); marketplace 2.61.4 → 2.62.0.
- _2026-09-04_ **CI gate fixed and promoted.** The per-plugin validation loop failed on the last
  non-plugin directory; the corrected `validate.yml` is live in `.github/workflows/`.
- _2026-09-04_ version bump — **procedural-memory** 0.5.5 → 0.5.6 (patch); marketplace 2.61.3 → 2.61.4.
- _2026-09-04_ version bump — **procedural-memory** 0.5.4 → 0.5.5 (patch); marketplace 2.61.2 → 2.61.3.
- _2026-09-03_ **First CI run fixes.** The promoted `validate` workflow failed on its first run and
  found portability defects: two bashisms in procedural-memory's POSIX hook (a herestring and a
  substring expansion), and a git-preflight test that depended on the runner's git identity. All fixed;
  the hook's tests now also run under dash where present.
- _2026-09-03_ **CI gate promoted.** `.github/ci-proposed/validate.yml` moved to
  `.github/workflows/validate.yml`; it runs the release contracts on every push and pull request.
- _2026-09-04_ version bump — **rhize-tasks** 0.5.0 → 0.5.1 (patch); **rhize-core** 1.0.1 → 1.0.2 (patch); marketplace 2.61.1 → 2.61.2.
- _2026-09-03_ **rhize-tasks re-pinned to runtime v0.5.2.** The runtime repository's test fixtures
  were neutralized after v0.5.1 was cut; v0.5.2 carries the clean fixtures and aligned version stamps.
- _2026-09-03_ version bump — **procedural-memory** 0.5.3 → 0.5.4 (patch); **rhize-core** 1.0.0 → 1.0.1 (patch); marketplace 2.61.0 → 2.61.1.
- _2026-09-03_ version bump — **rhize-tasks** 0.4.4 → 0.5.0 (minor); **rhize-ops** 0.19.0 → 0.20.0 (minor); **rhize-context-manager** 0.25.2 → 0.25.3 (patch); marketplace 2.60.0 → 2.61.0.
- _2026-09-03_ **Repo-shape R-C: two extractions.** The Rhize Tasks runtime moved, with its
  history, to `Rhize-Media/rhize-tasks` (public; tag `v0.5.1`); the plugin keeps only commands,
  skills, manifest, and docs, and `rhize-tasks-setup` bootstraps the runtime into
  `~/Library/Application Support/Rhize Tasks/source/<tag>/` (never the installer's `runtime/`),
  runs the installer's new non-mutating `--check`, and `doctor` reports `sourceRef` drift; the
  delegation parser contract is pinned by a committed fixture. The skill-usage monitor moved, with
  its history, to `Rhize-Media/rhize-skill-monitor` (tag `v1.0.0`); rhize-ops resolves it through
  `scripts/skill_monitor_root.sh` (`RHIZE_SKILL_MONITOR_ROOT`), declares it as an optional data
  dependency, and rhize-context-manager's usage/co-occurrence inputs follow the tool's own data-dir
  precedence. `bump_version.py` no longer stamps runtime files for rhize-tasks.
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

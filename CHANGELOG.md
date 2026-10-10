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
- [rhize-outreach/CHANGELOG.md](./rhize-outreach/CHANGELOG.md)

Entries before 2026-09-03 live in
[docs/release/CHANGELOG-history.md](./docs/release/CHANGELOG-history.md), preserved verbatim as a
point-in-time record.

## [Unreleased]

### Added

- _2026-10-10_ version bump — **rhize-context-manager** 0.45.0 → 0.45.1 (patch); marketplace 2.102.0 → 2.102.1.
- _2026-10-10_ version bump — **obsidian-second-brain** 1.8.0 → 1.9.0 (minor); **project-launcher** 1.13.0 → 1.14.0 (minor); **rhize-context-manager** 0.44.1 → 0.45.0 (minor); **rhize-devflow** 2.26.0 → 2.27.0 (minor); **rhize-outreach** 0.3.0 → 0.4.0 (minor); **seo-aeo-geo** 1.6.1 → 1.7.0 (minor); marketplace 2.101.1 → 2.102.0.
- _2026-10-10_ version bump — **rhize-context-manager** 0.44.0 → 0.44.1 (patch); marketplace 2.101.0 → 2.101.1.
- _2026-10-10_ version bump — **obsidian-second-brain** 1.7.7 → 1.8.0 (minor); **project-launcher** 1.12.0 → 1.13.0 (minor); **rhize-context-manager** 0.43.3 → 0.44.0 (minor); **rhize-devflow** 2.25.8 → 2.26.0 (minor); **rhize-ops** 0.29.0 → 0.30.0 (minor); **rhize-outreach** 0.2.0 → 0.3.0 (minor); **seo-aeo-geo** 1.6.0 → 1.6.1 (patch); marketplace 2.100.4 → 2.101.0.
- _2026-10-10_ version bump — **rhize-context-manager** 0.43.2 → 0.43.3 (patch); marketplace 2.100.3 → 2.100.4.
- _2026-10-06_ version bump — **rhize-context-manager** 0.43.1 → 0.43.2 (patch); marketplace 2.100.2 → 2.100.3.
- _2026-10-04_ version bump — **rhize-devflow** 2.25.7 → 2.25.8 (patch); marketplace 2.100.1 → 2.100.2.
- _2026-10-02_ version bump — **rhize-context-manager** 0.43.0 → 0.43.1 (patch); marketplace 2.100.0 → 2.100.1.
- _2026-10-02_ version bump — **rhize-context-manager** 0.42.1 → 0.43.0 (minor); marketplace 2.99.0 → 2.100.0.
- Test-only: close the fake Codex PID file before emitting a tool event so immediate fail-closed termination cannot race the process-cleanup assertion (CI run 37049439805). Runtime and timing checks are unchanged.
- _2026-10-02_ version bump — **procedural-memory** 0.8.0 → 0.9.0 (minor); marketplace 2.98.3 → 2.99.0.
- Fix Context Manager credential suffix diagnostic search performance without changing runtime redaction coverage or timing thresholds; ships with Ponytail integration.
- _2026-10-02_ version bump — **rhize-context-manager** 0.42.0 → 0.42.1 (patch); marketplace 2.98.2 → 2.98.3.
- _2026-10-02_ version bump — **rhize-devflow** 2.25.6 → 2.25.7 (patch); marketplace 2.98.1 → 2.98.2.
- Ponytail integration in rhize-devflow: retain upstream standalone plugin and full-mode ladder; use scoped complexity findings under existing behavior-preservation and release gates.
- _2026-10-02_ version bump — **rhize-devflow** 2.25.5 → 2.25.6 (patch); marketplace 2.98.0 → 2.98.1.
- _2026-09-30_ version bump — **rhize-context-manager** 0.41.0 → 0.42.0 (minor); marketplace 2.97.0 → 2.98.0.
- _2026-09-29_ version bump — **rhize-ops** 0.28.1 → 0.29.0 (minor); marketplace 2.96.0 → 2.97.0.
- _2026-09-29_ version bump — **rhize-context-manager** 0.40.1 → 0.41.0 (minor); marketplace 2.95.0 → 2.96.0.
- _2026-09-29_ version bump — **seo-aeo-geo** 1.5.4 → 1.6.0 (minor); marketplace 2.94.1 → 2.95.0.
- _2026-09-29_ version bump — **obsidian-second-brain** 1.7.6 → 1.7.7 (patch); marketplace 2.94.0 → 2.94.1.
- _2026-09-29_ version bump — **project-launcher** 1.11.1 → 1.12.0 (minor); marketplace 2.93.2 → 2.94.0.
- _2026-09-29_ version bump — **rhize-context-manager** 0.40.0 → 0.40.1 (patch); marketplace 2.93.1 → 2.93.2.
- _2026-09-29_ version bump — **rhize-devflow** 2.25.4 → 2.25.5 (patch); marketplace 2.93.0 → 2.93.1.
- _2026-09-29_ version bump — **procedural-memory** 0.7.0 → 0.8.0 (minor); marketplace 2.92.1 → 2.93.0.
- _2026-09-29_ version bump — **project-launcher** 1.11.0 → 1.11.1 (patch); marketplace 2.92.0 → 2.92.1.
- _2026-09-29_ version bump — **rhize-context-manager** 0.39.0 → 0.40.0 (minor); marketplace 2.91.4 → 2.92.0.
- _2026-09-29_ version bump — **rhize-ops** 0.28.0 → 0.28.1 (patch); marketplace 2.91.3 → 2.91.4.
- _2026-09-29_ version bump — **obsidian-second-brain** 1.7.5 → 1.7.6 (patch); marketplace 2.91.2 → 2.91.3.
- _2026-09-29_ version bump — **seo-aeo-geo** 1.5.3 → 1.5.4 (patch); marketplace 2.91.1 → 2.91.2.
- _2026-09-29_ Skill map: static rhize skill nodes gain `treeHash`, `fileCount` and `totalBytes` over every git-tracked file in the skill directory. `--check-stale` now also catches drift in `references/`, `scripts/` and `templates/`, so rebuild the map with any tracked skill-file edit. `validate_skill_map.py` fails a skill above the MCP Skills extension (SEP-2640) limits of 512 files or 16 MiB. `schemaVersion` is unchanged; the new properties are optional in the schema.
- _2026-09-29_ version bump — **rhize-devflow** 2.25.3 → 2.25.4 (patch); marketplace 2.91.0 → 2.91.1.
- _2026-09-28_ version bump — **procedural-memory** 0.6.0 → 0.7.0 (minor); marketplace 2.90.1 → 2.91.0.
- _2026-09-28_ version bump — **rhize-devflow** 2.25.2 → 2.25.3 (patch); marketplace 2.90.0 → 2.90.1.
- _2026-09-28_ version bump — **rhize-context-manager** 0.38.0 → 0.39.0 (minor); marketplace 2.89.0 → 2.90.0.
- _2026-09-28_ version bump — **rhize-context-manager** 0.37.0 → 0.38.0 (minor); marketplace 2.88.0 → 2.89.0.
- _2026-09-27_ version bump — **rhize-ops** 0.27.0 → 0.28.0 (minor); marketplace 2.87.0 → 2.88.0.
- _2026-09-27_ version bump — **rhize-ops** 0.26.0 → 0.27.0 (minor); marketplace 2.86.1 → 2.87.0.
- _2026-09-27_ version bump — **rhize-devflow** 2.25.1 → 2.25.2 (patch); marketplace 2.86.0 → 2.86.1.
- Add the workflow decision pilot research coordinator and its collection/review contract; live behavior remains shadow-only.
- _2026-09-27_ version bump — **rhize-context-manager** 0.36.0 → 0.37.0 (minor); marketplace 2.85.0 → 2.86.0.
- _2026-09-26_ version bump — **rhize-devflow** 2.25.0 → 2.25.1 (patch); marketplace 2.85.0 → 2.85.1.
- _2026-09-25_ Restore Codex marketplace refresh by aligning its catalog name and complete plugin roster with the Claude marketplace. Add a parity regression check; plugin versions and runtime behavior are unchanged.

- _2026-09-25_ Complete the local Laya shadow candidate surfaces across skill/workflow routing,
  graph relevance, context retention, Dev Flow tool/browser checkpoints, authorized worker/model
  fit and GSD supervision. Add private task-trial accounting with a 1,000,000-token ceiling for
  duplicate controls. Promotion still requires real adjudicated labels and accepted-task outcomes.

- _2026-09-25_ version bump — **project-launcher** 1.10.0 → 1.11.0 (minor); marketplace 2.84.0 → 2.85.0.
- _2026-09-25_ version bump — **rhize-ops** 0.25.2 → 0.26.0 (minor); marketplace 2.83.0 → 2.84.0.
- _2026-09-25_ version bump — **rhize-devflow** 2.24.0 → 2.25.0 (minor); marketplace 2.82.0 → 2.83.0.
- _2026-09-25_ version bump — **rhize-context-manager** 0.35.0 → 0.36.0 (minor); marketplace 2.81.2 → 2.82.0.
- _2026-09-24_ **rhize-outreach** 0.1.0 → 0.2.0 adds the pinned local-runtime wizard and reviewed selected-business workflow; included in marketplace 2.81.2.
- _2026-09-24_ version bump — **rhize-ops** 0.25.1 → 0.25.2 (patch); marketplace 2.81.1 → 2.81.2.
- _2026-09-24_ version bump — **rhize-core** 1.0.5 → 1.0.6 (patch); marketplace 2.81.0 → 2.81.1.

- _2026-09-24_ version bump — **rhize-context-manager** 0.33.1 → 0.35.0 (minor; 0.34.0 reserved for an unreleased held-out study); **rhize-devflow** 2.23.1 → 2.24.0 (minor); marketplace 2.80.0 → 2.81.0.
- _2026-09-24_ version bump — **project-launcher** 1.9.1 → 1.10.0 (minor); marketplace 2.79.1 → 2.80.0.
- _2026-09-24_ version bump — **project-launcher** 1.9.0 → 1.9.1 (patch); marketplace 2.79.0 → 2.79.1.
- _2026-09-24_ version bump — **project-launcher** 1.8.3 → 1.9.0 (minor); marketplace 2.78.1 → 2.79.0.
- _2026-09-24_ version bump — **rhize-devflow** 2.23.0 → 2.23.1 (patch); marketplace 2.78.0 → 2.78.1.
- _2026-09-24_ version bump — **rhize-devflow** 2.22.0 → 2.23.0 (minor); marketplace 2.77.0 → 2.78.0.
- _2026-09-21_ added **rhize-outreach** 0.1.0 with dual Claude/Codex setup, reviewed workflow skills and a pinned no-send runtime; marketplace 2.76.3 → 2.77.0.
- _2026-09-19_ version bump — **rhize-context-manager** 0.33.0 → 0.33.1 (patch); marketplace 2.76.2 → 2.76.3.
- _2026-09-19_ version bump — **rhize-ops** 0.25.0 → 0.25.1 (patch); marketplace 2.76.1 → 2.76.2.
- _2026-09-19_ version bump — **rhize-core** 1.0.4 → 1.0.5 (patch); marketplace 2.76.0 → 2.76.1.
- _2026-09-19_ version bump — **procedural-memory** 0.5.8 → 0.6.0 (minor); marketplace 2.75.0 → 2.76.0.
- _2026-09-19_ version bump — **rhize-context-manager** 0.32.3 → 0.33.0 (minor); marketplace 2.74.0 → 2.75.0.
- _2026-09-19_ version bump — **rhize-devflow** 2.21.1 → 2.22.0 (minor); marketplace 2.73.3 → 2.74.0.
- _2026-09-19_ version bump — **rhize-context-manager** 0.32.2 → 0.32.3 (patch); marketplace 2.73.2 → 2.73.3.
- Context Manager caches observed model identity at Stop for later memory measurements, preserving
  original prompt-time identity and rejecting stale-turn cache updates.
- _2026-09-19_ version bump — **rhize-context-manager** 0.32.1 → 0.32.2 (patch); marketplace 2.73.1 → 2.73.2.
- _2026-09-19_ version bump — **rhize-context-manager** 0.32.0 → 0.32.1 (patch); marketplace 2.73.0 → 2.73.1.
- Memory benchmark evidence: session-scoped Claude model provenance, conservative answer eligibility, auth deferral without budget consumption, versioned curated grading and private blind review packets. The controlled pilot runner records pinned repeated A/B trials and empty-evidence controls; shared reporting includes both hosts and actual native arm arrays. These collection changes do not establish a general benefit claim.
- _2026-09-19_ version bump — **rhize-context-manager** 0.31.0 → 0.32.0 (minor); marketplace 2.72.2 → 2.73.0.
- _2026-09-15_ version bump — **procedural-memory** 0.5.7 → 0.5.8 (patch); marketplace 2.72.1 → 2.72.2.
- _2026-09-15_ version bump — **rhize-core** 1.0.3 → 1.0.4 (patch); marketplace 2.72.0 → 2.72.1.
- _2026-09-15_ version bump — **rhize-ops** 0.24.0 → 0.25.0 (minor); marketplace 2.71.0 → 2.72.0.
- _2026-09-15_ version bump — **procedural-memory** 0.5.6 → 0.5.7 (patch); marketplace 2.71.0 → 2.71.1.
- _2026-09-11_ version bump — **rhize-context-manager** 0.30.0 → 0.31.0 (minor); marketplace 2.70.1 → 2.71.0.
- _2026-09-09_ version bump — **rhize-devflow** 2.21.0 → 2.21.1 (patch); marketplace 2.70.0 → 2.70.1.
- _2026-09-09_ version bump — **rhize-devflow** 2.20.3 → 2.21.0 (minor); marketplace 2.69.1 → 2.70.0.
- _2026-09-06_ version bump — **rhize-core** 1.0.2 → 1.0.3 (patch); marketplace 2.69.0 → 2.69.1.
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

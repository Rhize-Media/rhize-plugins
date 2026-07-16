# Changelog

All notable changes to the Rhize Plugins marketplace are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **rhize-ops:** `delegate-to-tom` renamed to `delegate-to-teammate` and made fully config-driven — no recipient name, Jira/Slack IDs, or project mapping is hardcoded in the skill anymore. Jira and Slack are each gated by an explicit `ready`/`incomplete`/`disabled` status so the skill skips gracefully instead of guessing when an integration isn't connected. Tool references switched from installation-specific connector-UUID-prefixed MCP tool names to capability-based discovery.
- **rhize-ops:** `skill-dashboard` now resolves its script/data paths via `${CLAUDE_PLUGIN_ROOT}` instead of an absolute local checkout path.
- **project-launcher:** the skill-discovery/safety-gate step now calls `rhize-meta`'s public commands (`/rhize-meta:skill-find`, `/rhize-meta:skill-doctor`) instead of shelling directly into `rhize-meta`'s scripts via a computed sibling-plugin path.
- **rhize-devflow:** `analyze_performance.js` now accepts `--root <path>` (default cwd) and scans conventional Next.js layouts (`app`/`src/app`, etc.) instead of assuming a fixed dual-repo directory structure.

### Fixed

- **rhize-devflow, rhize-meta, obsidian-second-brain:** removed a real client's production domain, repo names, and other real project/client names that had been used as illustrative example content across several skill docs and command examples — replaced with generic placeholders. No functional changes; these were documentation examples only.

### Added

- _2026-07-16_ version bump — **obsidian-second-brain** 1.1.2 → 1.1.3 (patch); **project-launcher** 1.5.0 → 1.5.1 (patch); **rhize-devflow** 2.4.0 → 2.4.1 (patch); **rhize-meta** 1.3.0 → 1.3.1 (patch); **rhize-ops** 0.2.0 → 0.3.0 (minor); marketplace 1.11.0 → 1.12.0.
- **rhize-ops:** `/rhize-ops:delegate-setup` — interview-driven wizard that resolves Jira/Slack identifiers via MCP where connected and writes `~/.claude/rhize-ops/delegate.config.json` (outside the repo). `references/delegate.config.schema.json` is a real Draft 2020-12 JSON Schema for that config.
- _2026-07-12_ version bump — **rhize-meta** 1.2.1 → 1.3.0 (minor); marketplace 1.10.0 → 1.11.0.
- _2026-06-16_ version bump — **rhize-meta** 1.1.0 → 1.1.1 (patch); marketplace 1.8.0 → 1.8.1.
- _2026-06-15_ version bump — **project-launcher** 1.2.1 → 1.3.0 (minor); **rhize-meta** 1.0.0 → 1.1.0 (minor); marketplace 1.7.0 → 1.8.0.
- **Skill discovery + safety (rhize-meta & project-launcher)** — `skills_sh.py` (skills.sh API: search / partner-audit / get / curated, Vercel OIDC auth), `skill_safety.py` (NVIDIA SkillSpector gate — BLOCK on HIGH/CRITICAL), and `skill_doctor.py` (setup check) under `rhize-meta/skills/rhize-skill-forge/scripts/`. Forge folds a mandatory two-layer safety gate (skills.sh partner audit + SkillSpector deep scan) into its decision step; project-launcher suggests + gates skills during scaffolding (reuses the rhize-meta scripts — no duplication). New commands `/rhize-meta:skill-find` and `/rhize-meta:skill-doctor`. Grounded against skills.sh/docs/api + the SkillSpector README; fail-safe when tools/token are absent.
- **Marketplace version-bump tooling** — `scripts/bump_version.py` (stdlib): `--auto` (detect plugins changed since last release + infer level from conventional commits), `--plugin/--level`, `--check`. Coordinates every `plugin.json` + the marketplace per-plugin **and top-level** version + CHANGELOG; never pushes. Adds `.githooks/pre-push` gate, `version-check` + `tag-release` CI, and the `/rhize-ops:bump-version` command. **Supersedes `scripts/bump-plugin.sh`** (per-plugin only — no top-level/CHANGELOG/auto/validate). Implements the ROADMAP item.
- _2026-06-15_ version bump — **rhize-ops** 0.1.1 → 0.2.0 (minor); marketplace 1.6.0 → 1.7.0.
- **New `rhize-meta` plugin** (v1.0.0) — promoted `rhize-skill-forge` and `skill-refinement` out of `rhize-devflow` into a dedicated meta-skills plugin so the coupled skill-governance toolchain lives in one place. **Breaking (namespace):** their commands moved from `/rhize-devflow:{forge-ingest,forge-scan,forge-watch,refine-skills,apply-generalization,review-patterns}` to `/rhize-meta:*`. rhize-devflow 2.2.0 → 2.3.0 (skills relocated); marketplace 1.5.0 → 1.6.0.
- **rhize-skill-forge set-level organizer mode** (rhize-devflow 2.1.0 → 2.2.0) — new stdlib scripts `index_skills.py` (capability registry), `overlap_scan.py --set-mode` (N-way internal-overlap), and `build_dependency_graph.py` (`consumes:` graph); `profile_skill.py` now also profiles plugins and MCP configs; `SOURCES.md` provenance ledger stood up; references `capability-schema.md`, `composition-patterns.md`, `drift-boundaries.md`. Drift detection consolidated to the single `ai-stack-version-drift` sensor (Forge `--check-drift` = on-demand classifier). Phase 3 productization gated, tracked as Jira RT-41.
- **Capability frontmatter on all 29 marketplace skills** — `tier`/`domain`/`maturity` added to every Rhize-authored skill so the organizer classifies them (0 untagged). Patch bumps: rhize-ops 0.1.0 → 0.1.1, seo-aeo-geo 1.1.0 → 1.1.1, obsidian-second-brain 1.1.1 → 1.1.2, project-launcher 1.2.0 → 1.2.1. Marketplace 1.4.0 → 1.5.0.
- **rhize-ops** plugin (v0.1.0) — operations skill set (internal delegation / hand-offs / team-workflow automation), distinct from `rhize-devflow` which is about building software. Houses **`delegate-to-tom`**, migrated out of the standalone `~/.claude/skills/delegate-to-tom/` (which is not version-controlled). The skill's frontmatter `name:` was changed from `rhize:delegate-to-tom` to a plain `delegate-to-tom` slug so its namespace derives from the plugin → canonical `rhize-ops:delegate-to-tom`. This resolves the alias fragmentation where the colon in a standalone skill name was sanitized into three different recorded names (`rhize:delegate-to-tom`, `rhizedelegate-to-tom`, `anthropic-skills:rhizedelegate-to-tom`). Marketplace bumped to 1.4.0.
- **rhize-devflow** plugin (v2.1.0) — consolidated development-workflow skill set migrated from the now-archived `CLAUDE-SKILLS` repo: `context-engineering`, `error-lifecycle-management`, `data-mutation-consistency`, `sentry-instrumentation`, `chrome-devtools-mcp`, `sanity-development`, `dev-flow-foundations`, `skill-refinement`, and the new **`rhize-skill-forge`** meta-skill (investigate & absorb external skills with provenance tracking). All 9 skills given valid YAML frontmatter + keyword-rich descriptions; commands namespaced `/rhize-devflow:*`. Marketplace bumped to 1.3.0.
- **rhize-review** skill — production merge-gate review orchestrator: scopes the diff, routes by stack to `ecc` specialist + security reviewers, aggregates findings at confidence ≥80, and returns a single merge verdict. Tracked here and symlinked into `~/.claude/skills/rhize-review`.
- **obsidian-second-brain** plugin (v0.2.0) — CLI operations, markdown syntax, Bases databases, JSON Canvas, web clipping, second brain methodology, note templates, research pipelines, and knowledge graph workflows
- Obsidian prerequisites section in marketplace README
- **second-brain** skill — Zettelkasten, PARA, MOCs, progressive summarization, atomic notes methodology
- **vault-templates** skill — Note archetypes for meeting notes, book reviews, project briefs, weekly reviews, permanent notes, person notes
- `/vault-research` command — End-to-end research pipeline: clip → summarize → connect to vault
- `/vault-connect` command — Find and build missing links between related vault notes
- `/vault-review` command — Periodic review cycles (daily, weekly, monthly) with theme detection and forgotten note resurfacing
- **vault-alignment** skill — Vault health assessment across 5 dimensions (structure, connectivity, consistency, processing, plugins), drift detection patterns, improvement prioritization, and migration strategies
- `/vault-setup` command — Interactive setup wizard: discovery interview → vault audit → personalized archetype generation → woven plugin recommendations → scaffolding → opt-in migration
- `/vault-align` command — Ongoing vault health monitor with 4 modes: check (health report with focused sub-modes for tags, orphans, links, structure), fix (highest-impact fix), migrate (aggressive batch reorganization), plugins (audit and recommend)
- Community plugin recommendation system — Dataview, Kanban, Templater, Calendar, Tasks with woven inline recommendations during setup
- `_vault-setup-log.md` archetype persistence — bridges setup wizard to ongoing alignment

### Changed

- **nextjs-rhize-stack hookify rules** — `pr-review-on-create` now invokes `/rhize-review` first (prior review skills kept as fallback); `block-direct-push-to-main` regex now also catches the `git -C <path> push` form
- Updated marketplace manifest and README to reflect multi-plugin catalog
- Bumped obsidian-second-brain from v0.2.0 to v0.3.0
- Updated GUIDE.md with Setup & Alignment section and community plugins guide
- Consolidated `/vault-organize` into `/vault-align` — all vault analysis and organization now lives in one command with granular focus options (`check tags`, `check orphans`, `check links`, `check structure`, `check full`)

## [1.0.0] - 2026-03-14

### Added
- Initial marketplace release
- **seo-aeo-geo** plugin (v1.0.0) — SEO, AEO, and GEO auditing powered by DataForSEO API with Next.js + Sanity CMS best practices
- Marketplace manifest for Claude plugin discovery
- Plugin evaluation framework with trigger and quality benchmarks

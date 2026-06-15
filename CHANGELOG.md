# Changelog

All notable changes to the Rhize Plugins marketplace are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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

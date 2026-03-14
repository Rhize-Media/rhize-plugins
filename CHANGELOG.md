# Changelog

All notable changes to the Rhize Plugins marketplace are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **obsidian-skills** plugin (v0.2.0) — CLI operations, markdown syntax, Bases databases, JSON Canvas, web clipping, second brain methodology, note templates, research pipelines, and knowledge graph workflows
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

- Updated marketplace manifest and README to reflect multi-plugin catalog
- Bumped obsidian-skills from v0.2.0 to v0.3.0
- Updated GUIDE.md with Setup & Alignment section and community plugins guide
- Consolidated `/vault-organize` into `/vault-align` — all vault analysis and organization now lives in one command with granular focus options (`check tags`, `check orphans`, `check links`, `check structure`, `check full`)

## [1.0.0] - 2026-03-14

### Added
- Initial marketplace release
- **seo-aeo-geo** plugin (v1.0.0) — SEO, AEO, and GEO auditing powered by DataForSEO API with Next.js + Sanity CMS best practices
- Marketplace manifest for Claude plugin discovery
- Plugin evaluation framework with trigger and quality benchmarks

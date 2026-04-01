# Roadmap

Tracked enhancements and future ideas for the Rhize Plugins marketplace.

## Backlog

### Marketplace Infrastructure
- [ ] Use git submodule for `obsidian-second-brain/` to auto-sync with [kepano/obsidian-second-brain](https://github.com/kepano/obsidian-second-brain) upstream
- [ ] Add version bump script to coordinate plugin.json + marketplace.json + changelog updates

### obsidian-second-brain

- [x] Trigger accuracy evals (32 cases across 8 skills)
- [x] Quality evals (8 cases, one per skill — reference knowledge only)
- [ ] Command evals — requires Obsidian MCP Server + running Obsidian instance. Covers `/vault-search`, `/vault-setup`, `/vault-align`, and other CLI commands against a test vault.
- [ ] Sync with upstream kepano/obsidian-second-brain when new features land
- [ ] Eval suite for vault-setup wizard — test fresh vault and existing vault paths
- [ ] Eval suite for vault-align — test health check scoring and fix execution
- [ ] Explore `obsidian eval` for deeper plugin configuration inspection during setup
- [ ] Investigate Obsidian URI scheme for plugin install links (obsidian://show-plugin?id=dataview)

### seo-aeo-geo
- [ ] (none yet)

### Content Flywheel (standalone repo at `/home/user/content-flywheel/`)
- [x] Analysis doc: `docs/content-flywheel-storage-analysis.md`
- [x] Decisions: Neo4j over Supabase/Sheets, Next.js API routes over n8n, CMS/CRM-agnostic adapters
- [x] Phase 1: Neo4j schema + MCP integration + DataForSEO client + core types
- [x] Phase 2: Next.js kanban dashboard + content detail page + graph query API
- [x] Phase 3: Sanity CMS adapter + GoHighLevel distribution adapter + Vercel cron routes
- [x] Phase 4: Migrate all 6 SEO workflow modules from seo-aeo-geo plugin
  - Keyword Research, Content Optimization, SERP Analysis, Backlink Analysis, AI Visibility, Site Audit
  - 7 skills, 7 commands, hooks, dashboard workflow action buttons
- [ ] Phase 5: E2E testing with live Neo4j + DataForSEO credentials
- [ ] Phase 6: Deploy to Vercel with production Neo4j instance

### New Plugin Ideas
- (add ideas here as they come up)

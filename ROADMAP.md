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

### Content Flywheel (standalone repo)
- [ ] Standalone repo: Neo4j graph database + Next.js kanban dashboard + Vercel API routes
- [ ] Analysis doc: `docs/content-flywheel-storage-analysis.md`
- [ ] Decisions: Neo4j over Supabase/Sheets (graph-native data model), Next.js API routes over n8n (eliminates separate service), CMS/CRM-agnostic adapter pattern (Sanity + GHL first)
- [ ] Phase 1: Neo4j schema + MCP integration (`mcp-neo4j-cypher`, `mcp-neo4j-memory`, `mcp-neo4j-data-modeling`)
- [ ] Phase 2: Next.js kanban dashboard with graph explorer
- [ ] Phase 3: Sanity CMS adapter + GoHighLevel distribution adapter + Vercel cron for DataForSEO pulls

### New Plugin Ideas
- (add ideas here as they come up)

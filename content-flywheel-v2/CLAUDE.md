# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.


# Content Flywheel

## Project Overview

Content pipeline dashboard powered by Neo4j graph database with kanban board UI, automated SEO tracking, and CMS/CRM-agnostic publishing adapters.

**Stack:** Next.js 16 (App Router) + TypeScript + Tailwind CSS 4 + Neo4j Aura + Vercel

**Production URL:** https://content-flywheel-nu.vercel.app

## Architecture

```
Neo4j (Aura ec4405e5)  — Graph database: content, keywords, clusters, SERP, backlinks
Next.js Dashboard      — Sidebar nav + three pages:
  /board               — Kanban pipeline board (drag-and-drop, create content modal)
  /content/[id]        — Content detail (keywords, SERP, backlinks, SEO score, workflows)
  /graph               — Graph explorer (node counts, pipeline funnel, clusters, workflow history)
API Routes:
  /api/board           — GET board data (grouped by stage)
  /api/board/move      — POST move content between stages
  /api/content         — POST create new content
  /api/content/[id]    — GET full content detail (keywords, SERP, backlinks, SEO, internal links)
  /api/graph/stats     — GET graph statistics
  /api/graph/query     — POST generic Cypher (auth-gated via x-graph-secret header)
  /api/cron/*          — Vercel Cron: daily DataForSEO pulls, weekly SERP snapshots
  /api/webhooks/*      — Sanity + GHL webhook receivers
  /api/publish/*       — CMS + social distribution adapters
  /api/workflows/*     — DataForSEO workflow runners (keyword-research, content-optimize,
                         serp-analysis, backlink-analysis, ai-visibility, site-audit)
```

## Key Directories

- `src/types/` — Core TypeScript types and pipeline stage definitions
- `src/lib/neo4j/` — Neo4j driver singleton, Cypher query functions, `toPlain()` serializer
- `src/lib/dataforseo/` — DataForSEO API client (15+ endpoint wrappers)
- `src/lib/workflows/` — 6 workflow engines (keyword-research, content-optimize, serp-analysis, backlink-analysis, ai-visibility, site-audit)
- `src/lib/adapters/cms/` — CMS adapters (Sanity)
- `src/lib/adapters/distribution/` — Distribution adapters (GoHighLevel)
- `src/components/` — Shared UI: sidebar, error page
- `src/app/board/` — Kanban board page + create content modal
- `src/app/content/[id]/` — Content detail page with workflow buttons
- `src/app/graph/` — Graph explorer dashboard
- `src/app/api/` — All API routes
- `cypher/` — Neo4j schema (run via `npm run init-schema`)
- `scripts/` — `init-schema.ts` (DB setup), `seed.ts` (sample data)
- `tests/` — Vitest unit tests (43 tests across 6 files)
- `docs/plans/` — Implementation plans

## Graph Schema

Pipeline stages are nodes, not enum values — content moves between stages via relationships:
```
(ContentPiece)-[:IN_STAGE]->(PipelineStage)
(ContentPiece)-[:TARGETS]->(Keyword)
(Keyword)-[:BELONGS_TO]->(KeywordCluster)
(ContentPiece)-[:RANKS_FOR]->(SERPSnapshot)
(ContentPiece)-[:HAS_BACKLINK_FROM]->(BacklinkSource)
(ContentPiece)-[:LINKS_TO]->(ContentPiece)
(ContentPiece)-[:HAS_SCORE]->(SEOScore)
(ContentPiece)-[:PUBLISHED_TO]->(CMSTarget)
(ContentPiece)-[:DISTRIBUTED_TO]->(DistributionChannel)
(WorkflowRun) — tracks workflow executions with status/summary
(Competitor) — competitor domains from gap analysis
(AIVisibilitySnapshot) — LLM brand mention tracking
```

## Important Patterns

### Neo4j Type Serialization
All query functions MUST use `toPlain()` from `src/lib/neo4j/queries.ts` when returning data to the API layer. Neo4j driver returns `Integer` objects (`{low, high}`) and `DateTime` objects (nested year/month/day) that will crash React if passed as-is. `toPlain()` recursively converts them to plain JS numbers and ISO strings.

### Workflow Routes Require maxDuration
All `/api/workflows/*` and `/api/cron/*` routes export `maxDuration = 300` because DataForSEO API calls can take 30–60 seconds. This requires Vercel Pro plan for production; locally it has no effect.

### Cypher Aggregation Ordering
Neo4j 5+ rejects `ORDER BY` on variables not in the `RETURN` clause when `collect()` is used. Always alias the order field in `RETURN` and `ORDER BY` the alias:
```cypher
-- WRONG: ORDER BY s.order
RETURN s.name AS stage, collect(c { .* }) AS pieces ORDER BY s.order

-- RIGHT: include s.order in RETURN as alias
RETURN s.name AS stage, s.order AS ord, collect(c { .* }) AS pieces ORDER BY ord
```

## MCP Servers

Configured in `.mcp.json` (all credentials via `${ENV_VAR}` refs resolved from `.env.local`):
- **neo4j-cypher** — Read/write content data via Cypher queries
- **neo4j-memory** — Persist entities across Claude sessions
- **neo4j-data-modeling** — Design and validate graph schemas
- **dataforseo** — SEO/keyword/SERP/backlinks data
- **firecrawl** — Web scraping and site crawling
- **exa-web-search** — Neural web search and research
- **obsidian-mcp-server** — Vault research for content inspiration (local only)
- **slack** — Notifications and approvals (pending bot token)

## Commands

```bash
npm run dev            # Start dev server at localhost:3000
npm run build          # Production build
npm run lint           # ESLint check
npm test               # Run vitest unit tests (43 tests)
npm run test:watch     # Run tests in watch mode
npm run seed           # Seed 5 sample content pieces into Neo4j
npm run init-schema    # Run cypher/schema.cypher against Neo4j Aura
```

## Environment Variables

All secrets live in `.env.local` (gitignored). MCP servers reference them via `${VAR}` syntax.

**Required for core functionality:**
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` — Neo4j Aura (dedicated instance `ec4405e5`)
- `DATAFORSEO_USERNAME`, `DATAFORSEO_PASSWORD` — DataForSEO API
- `GRAPH_QUERY_SECRET` — Auth header for generic Cypher proxy endpoint

**Required for CMS/distribution adapters:**
- `SANITY_PROJECT_ID`, `SANITY_DATASET`, `SANITY_API_TOKEN` — Sanity CMS (Rhize Media project `3g5yoen6`)
- `GHL_API_KEY`, `GHL_LOCATION_ID` — GoHighLevel (Rhize Media location)

**MCP-only (not used by runtime, Claude dev tools only):**
- `FIRECRAWL_API_KEY` — Firecrawl web scraping
- `EXA_API_KEY` — Exa neural search
- `OBSIDIAN_API_KEY` — Obsidian Local REST API

**Pending:**
- `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` — Slack notifications (token stored in n8n Cloud, needs manual extraction)

## CMS/CRM Adapter Pattern

Adapters implement standard interfaces (`CMSAdapter`, `DistributionAdapter`) defined in `src/types/`. To add a new CMS or distribution channel:
1. Create a new file in `src/lib/adapters/cms/` or `src/lib/adapters/distribution/`
2. Implement the interface
3. Add a corresponding `(:CMSTarget)` or `(:DistributionChannel)` node in Neo4j
4. Wire up the API route

Current adapters: Sanity CMS (publishing), GoHighLevel (social distribution)

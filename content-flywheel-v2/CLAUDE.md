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
  /api/content/[id]    — GET full content detail (keywords, SERP, backlinks, SEO, internal links, workflows, AI visibility, stage history)
  /api/graph/stats     — GET graph statistics
  /api/graph/query     — POST generic Cypher (auth-gated via x-graph-secret header)
  /api/cron/*          — Vercel Cron: daily DataForSEO pulls, weekly SERP snapshots
  /api/webhooks/*      — Sanity + GHL webhook receivers
  /api/publish/*       — CMS + social distribution adapters
  /api/workflows/*     — Workflow runners:
                         DataForSEO: keyword-research, content-optimize, serp-analysis,
                         backlink-analysis, ai-visibility, site-audit
                         AI/Claude: content-ingest, article-outline, article-draft, brand-voice-check
```

## Key Directories

- `src/types/` — Core TypeScript types and pipeline stage definitions
- `src/lib/neo4j/` — Neo4j driver singleton, Cypher query functions, `toPlain()` serializer
- `src/lib/dataforseo/` — DataForSEO API client (15+ endpoint wrappers)
- `src/lib/ai/` — Claude SDK wrapper (prompt caching, cost tracking), Gemini embeddings client, k-means clustering
- `src/lib/workflows/` — 10 workflow engines + shared helpers (keyword-research, content-optimize, serp-analysis, backlink-analysis, ai-visibility, site-audit, content-ingest, article-outline, article-draft, brand-voice-check)
- `src/lib/adapters/cms/` — CMS adapters (Sanity)
- `src/lib/adapters/distribution/` — Distribution adapters (GoHighLevel)
- `src/components/` — Shared UI: sidebar, error page
- `src/app/board/` — Kanban board page + create content modal
- `src/app/content/[id]/` — Content detail page with workflow buttons
- `src/app/graph/` — Graph explorer dashboard
- `src/app/api/` — All API routes
- `cypher/` — Neo4j schema (run via `npm run init-schema`)
- `scripts/` — `init-schema.ts` (DB setup), `seed.ts` (sample data), `migrate-graph-relationships.ts` (backfill existing data), `prune-irrelevant-keywords.ts` (remove semantically irrelevant TARGETS)
- `src/lib/notifications/` — Slack notification module (graceful no-op when env vars not set)
- `tests/` — Vitest unit tests (111 tests across 15 files)
- `docs/plans/` — Implementation plans

## Graph Schema

Pipeline stages are nodes, not enum values — content moves between stages via relationships:
```
(ContentPiece)-[:IN_STAGE {enteredAt}]->(PipelineStage)
(ContentPiece)-[:WAS_IN_STAGE {stage, enteredAt, leftAt}]->(PipelineStage)
(ContentPiece)-[:TARGETS]->(Keyword)
(Keyword)-[:BELONGS_TO]->(KeywordCluster)
(Keyword)-[:RELATED_TO]->(Keyword)
(ContentPiece)-[:RANKS_FOR]->(SERPSnapshot)
(SERPSnapshot)-[:FOR_KEYWORD]->(Keyword)
(ContentPiece)-[:HAS_BACKLINK_FROM {discoveredAt, lastSeenAt}]->(BacklinkSource)
(ContentPiece)-[:LINKS_TO]->(ContentPiece)
(ContentPiece)-[:HAS_SCORE]->(SEOScore)
(ContentPiece)-[:HAS_WORKFLOW_RUN]->(WorkflowRun)
(ContentPiece)-[:HAS_AI_VISIBILITY]->(AIVisibilitySnapshot)
(ContentPiece)-[:HAS_AI_USAGE]->(AIUsage)
(ContentPiece)-[:HAS_OUTLINE]->(Outline)
(ContentPiece)-[:HAS_DRAFT]->(Draft)
(ContentPiece)-[:HAS_BRAND_VOICE_SCORE]->(BrandVoiceScore)
(ContentPiece)-[:HAS_THEME]->(Theme)
(ContentPiece)-[:PUBLISHED_TO {publishedAt, documentId}]->(CMSTarget)
(ContentPiece)-[:DISTRIBUTED_TO {scheduledAt, postId, status}]->(DistributionChannel)
(Author)-[:WROTE]->(ContentPiece)
(Author)-[:EXPERT_IN]->(KeywordCluster)
(Competitor)-[:RANKS_FOR]->(Keyword)
(Competitor)-[:HAS_BACKLINK_FROM]->(BacklinkSource)
(Competitor)-[:HAS_WORKFLOW_RUN]->(WorkflowRun)
(SiteAudit)-[:AUDITS]->(Competitor)
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

### Conditional Relationship Creation
When a relationship target may not exist (e.g., contentId is optional), use the FOREACH/CASE pattern instead of separate queries:
```cypher
OPTIONAL MATCH (c:ContentPiece {id: $contentId})
FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
  CREATE (c)-[:HAS_WORKFLOW_RUN]->(w)
)
```
All 6 workflows use this pattern for `HAS_WORKFLOW_RUN`. When the target always exists (e.g., content-optimize always has a contentId), use a direct `MATCH` + `CREATE` instead.

### Keyword Relevance Filter
The keyword-research workflow filters candidate keywords by semantic relevance before creating `TARGETS` relationships. It embeds the content title via Gemini, computes cosine similarity against each keyword's embedding, and only links keywords scoring >= 0.65. This prevents DataForSEO from linking lexically similar but semantically irrelevant keywords (e.g., "map of the state of florida" for an article about "The State of AI Search Optimization"). Run `npm run prune-keywords` to audit/clean existing data.

### Stage Transition History
`moveContentToStage` archives the old `IN_STAGE` as a `WAS_IN_STAGE` relationship with `{stage, enteredAt, leftAt}` timestamps before creating the new `IN_STAGE`. This enables pipeline velocity analytics.

## MCP Servers

Configured in `.mcp.json` (all credentials via `${ENV_VAR}` refs resolved from `.env.local`):
- **neo4j-cypher** — Read/write content data via Cypher queries
- **neo4j-memory** — Persist entities across Claude sessions
- **neo4j-data-modeling** — Design and validate graph schemas
- **dataforseo** — SEO/keyword/SERP/backlinks data (used by Vercel runtime workflows)
- **seo-utils** — SEO Utils MCP (`localhost:19515`) — GSC data, indexing API, autocomplete, gap analysis (local Claude sessions only, requires SEO Utils desktop app running)
- **firecrawl** — Web scraping and site crawling
- **exa-web-search** — Neural web search and research
- **obsidian-mcp-server** — Vault research for content inspiration (local only)
- **slack** — Notifications and approvals (pending bot token)

### Dual-Stack SEO Architecture
- **Vercel runtime** (deployed workflows): `src/lib/dataforseo/client.ts` calls DataForSEO API directly
- **Claude Code sessions** (local): SEO Utils MCP for exclusive features — GSC data (`query_gsc`), Google/Bing indexing (`submit_url_for_google_indexing`, `submit_url_to_index_now`), autocomplete scraping (`fetch_autocomplete_keywords`), content/backlink gap analysis (`get_content_gap`, `get_backlink_gap`)
- **Future (M15)**: VPS-hosted SEO Utils will replace DataForSEO for runtime too

### Flywheel Commands (SEO Utils)
- `/flywheel-gsc` — Query GSC data: top queries, declining pages, branded traffic
- `/flywheel-indexing` — Check/submit URLs for Google and Bing indexing
- `/flywheel-gap` — Content gap and backlink gap analysis vs competitors
- `/flywheel-autocomplete` — Discover autocomplete and question keywords

## Flywheel Commands

11 slash commands for managing the content pipeline from Claude Code. Full reference with examples and typical workflows: **[docs/flywheel-commands.md](docs/flywheel-commands.md)**

| Command | Purpose | Requires |
|---------|---------|----------|
| `/flywheel-status` | Pipeline overview or content detail | Neo4j |
| `/flywheel-research` | Keyword research + clustering | DataForSEO |
| `/flywheel-discover` | Site audit for SEO issues | DataForSEO |
| `/flywheel-optimize` | SEO scoring for a content piece | DataForSEO |
| `/flywheel-monitor` | SERP, backlink, or AI visibility | DataForSEO |
| `/flywheel-publish` | Publish to Sanity CMS | Sanity |
| `/flywheel-distribute` | Schedule social posts via GHL | GHL |
| `/flywheel-gsc` | Query Google Search Console data | SEO Utils |
| `/flywheel-indexing` | Check/submit URLs for indexing | SEO Utils |
| `/flywheel-gap` | Content/backlink gap vs competitors | SEO Utils |
| `/flywheel-autocomplete` | Discover autocomplete keywords | SEO Utils |

## npm Scripts

```bash
npm run dev            # Start dev server at localhost:3000
npm run build          # Production build
npm run lint           # ESLint check
npm test               # Run vitest unit tests (111 tests)
npm run test:watch     # Run tests in watch mode
npm run seed           # Seed 5 sample content pieces into Neo4j
npm run init-schema    # Run cypher/schema.cypher against Neo4j Aura
npm run prune-keywords # Dry-run: show irrelevant TARGETS by cosine similarity (--apply to delete)
npx tsx scripts/migrate-graph-relationships.ts  # Backfill graph relationships for existing data (one-time)
```

## Environment Variables

All secrets live in `.env.local` (gitignored). MCP servers reference them via `${VAR}` syntax.

**Required for core functionality:**
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` — Neo4j Aura (dedicated instance `ec4405e5`)
- `DATAFORSEO_USERNAME`, `DATAFORSEO_PASSWORD` — DataForSEO API
- `GRAPH_QUERY_SECRET` — Auth header for generic Cypher proxy endpoint
- `ANTHROPIC_API_KEY` — Claude API (article generation, brand voice, intent classification)
- `GEMINI_API_KEY` — Google Gemini (keyword embeddings via gemini-embedding-001, 256-dim)

**Required for CMS/distribution adapters:**
- `SANITY_PROJECT_ID`, `SANITY_DATASET`, `SANITY_API_TOKEN` — Sanity CMS (Rhize Media project `3g5yoen6`)
- `GHL_API_KEY`, `GHL_LOCATION_ID` — GoHighLevel (Rhize Media location)

**MCP-only (not used by runtime, Claude dev tools only):**
- `SEO_UTILS_TOKEN` — SEO Utils MCP Bearer token (requires desktop app running at localhost:19515)
- `FIRECRAWL_API_KEY` — Firecrawl web scraping
- `EXA_API_KEY` — Exa neural search
- `OBSIDIAN_API_KEY` — Obsidian Local REST API

**Pending:**
- `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` — Slack notifications (token stored in n8n Cloud, needs manual extraction)

## Jira Sync (Automatic)

Development tasks are tracked in Jira project **RT** (Rhize Tools) under epic **RT-9** (Content Flywheel v2).

**Atlassian Cloud ID:** `ac62d3a2-66bb-4513-a8e8-b634d3465466`

**Workflow:** When you commit code that references a Jira issue key (e.g. `RT-11`), a PostToolUse hook on Bash detects it and outputs a `JIRA_SYNC:` reminder. When you see this reminder, you MUST:

1. Transition the referenced Jira issue to **Done** (transition ID `31`) using `mcp__claude_ai_Atlassian__transitionJiraIssue`
2. Add a comment to the issue with the commit SHA and summary using `mcp__claude_ai_Atlassian__addIssueComment`

When **starting** work on a task, transition it to **In Progress** (transition ID `21`).

**Commit message convention:** Include the Jira key in the commit message:
```
feat: add Claude SDK wrapper with prompt caching (RT-11)
```

**Current task mapping:** See `docs/plans/2026-04-04-content-flywheel-production-ready.md` for full task descriptions, or query Jira: `project = RT AND parent = RT-9 ORDER BY key ASC`

## CMS/CRM Adapter Pattern

Adapters implement standard interfaces (`CMSAdapter`, `DistributionAdapter`) defined in `src/types/`. To add a new CMS or distribution channel:
1. Create a new file in `src/lib/adapters/cms/` or `src/lib/adapters/distribution/`
2. Implement the interface
3. Add a corresponding `(:CMSTarget)` or `(:DistributionChannel)` node in Neo4j
4. Wire up the API route

Current adapters: Sanity CMS (publishing), GoHighLevel (social distribution)

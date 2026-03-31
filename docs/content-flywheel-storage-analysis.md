# Content Flywheel: Storage, Dashboard & Integration Architecture

Analysis of storage trade-offs and architectural decisions for the content-flywheel system. The implementation lives in a **standalone repository** — this document captures the research and decisions made.

## Context

The rhize-plugins system currently has **no persistent storage** — all data is ephemeral per-session. The content flywheel workflow generates rich, interconnected data (content pieces, keyword clusters, backlinks, SERP positions, AI visibility metrics) that naturally forms a graph. At 50-60 pieces/month per client, the graph becomes meaningfully dense within 2-3 months.

**Requirements:** Visual kanban dashboard, content relationship modeling from day one, small team (50-500 pieces), CRM/CMS-agnostic design with Sanity CMS + GoHighLevel as first integrations.

**Key context:** Neo4j MCP server already exists (`neo4j-contrib/mcp-neo4j`) with 4 sub-servers, Neo4j is already working in a local project (msci-mvp), and the Neo4j CLI tooling is well-documented.

---

## Options Evaluated

### Option A: Google Sheets via MCP Server

- Google Sheets API via MCP server for read/write
- Status column as pseudo-kanban, conditional formatting for pipeline stages
- Referenced in project-launcher's `interview-question-bank.md` (Q16, Q22) as a possible output destination

**Strengths:** Zero infrastructure, familiar UI, free, collaborative, MCP integration exists.

**Weaknesses:** Not a real database (no referential integrity, joins, or transactions). 10M cell limit (already called out in `claude-md-template.md`). Can't model content-keyword-backlink relationships. Can't power a real kanban board. API rate limits (300 req/min) tight for bulk SEO writes.

**Cost:** $0 (personal) to $35/mo (team of 5).

**Verdict:** Ruled out as primary store. Can't model relationships, can't power a dashboard. Useful only as a lightweight export/sharing layer for non-technical stakeholders.

### Option B: Supabase (PostgreSQL + Real-time)

- Hosted PostgreSQL with REST/GraphQL APIs, real-time subscriptions, auth, edge functions
- Official Supabase MCP server available

**Strengths:** Real database with full SQL. Real-time WebSocket subscriptions for live dashboard. Built-in auth and row-level security. Generous free tier (500MB). PostgREST auto-generates API endpoints.

**Weaknesses:** Relational, not graph — modeling content-keyword-backlink relationships requires junction tables and verbose recursive CTEs. Custom kanban UI still required. Cold starts on free tier (pauses after 1 week inactivity).

**Cost:** $0 (free) to $25/mo (Pro) + $0-20/mo dashboard hosting.

**Verdict:** Viable but suboptimal. The content flywheel data is inherently graph-shaped — forcing it into relational tables adds friction that compounds as the content network grows. At 50-60 pieces/month, the relationship density makes SQL JOINs unwieldy within a few months.

### Option C: Neo4j (Graph Database) — Selected

- Graph database with Cypher query language, managed via Neo4j Aura or self-hosted
- MCP server exists: `neo4j-contrib/mcp-neo4j` with 4 sub-servers (cypher, memory, data-modeling, cloud-aura-api)
- Already proven in local project (msci-mvp)

**Strengths:** Natural content graph model — the flywheel IS a graph. Powerful traversal queries for content gap analysis, internal link optimization, and "what to write next" recommendations. Graph algorithms (PageRank, community detection) identify clusters and orphan pages. Neo4j Bloom for visual exploration. MCP server provides Claude Code integration out of the box.

**Weaknesses:** Custom dashboard still needed for kanban board. Aura Free limited to 200K nodes / 400K relationships (sufficient for 1-2 clients for ~12 months). APOC plugin required for schema inspection.

**Cost:** $0 (Aura Free) to $65/mo (Professional) + $0-20/mo dashboard hosting.

---

## Comparison Matrix

| Dimension | Google Sheets | Supabase | Neo4j |
|-----------|:---:|:---:|:---:|
| **Data model fit** | Flat tables | Relational (good) | **Graph (excellent)** |
| **Query power** | Basic formulas | Full SQL | **Cypher (graph traversals)** |
| **Content relationships** | Manual cross-ref | JOIN tables | **Native edges** |
| **MCP integration** | Available | Available (official) | **Available (4 servers)** |
| **Kanban dashboard** | Simulated (filters) | Custom build | Custom build |
| **Real-time collab** | Built-in | WebSocket subs | Requires custom layer |
| **Non-technical access** | Excellent | Requires dashboard | Requires dashboard |
| **Free tier capacity** | Unlimited (personal) | 500MB DB | 200K nodes / 400K rels |
| **Monthly cost at scale** | $0-35 | $25-45 | $65+ |
| **Team experience** | Familiar | New | **Already in use (msci-mvp)** |

---

## Decision 1: Neo4j as the Primary Data Layer

The content flywheel is fundamentally a graph problem:

```
(Inspiration)-[:INSPIRES]->(ContentPiece)-[:TARGETS]->(Keyword)
(ContentPiece)-[:RANKS_FOR {position: 7}]->(SERPResult)
(ContentPiece)-[:HAS_BACKLINK]->(ExternalDomain)
(ContentPiece)-[:LINKS_TO]->(ContentPiece)
(Keyword)-[:CLUSTERS_WITH]->(Keyword)
(ContentPiece)-[:PUBLISHED_VIA]->(CMSTarget)    // Sanity, WordPress, etc.
(ContentPiece)-[:DISTRIBUTED_VIA]->(Channel)     // GHL, Buffer, native APIs
(ContentPiece)-[:IN_STAGE]->(PipelineStage)
```

At 50-60 pieces/month, after 6 months: 300-360 content nodes, each with 5-15 keyword targets, backlink edges, internal links, and SERP snapshots. That's 5,000-15,000 relationships — well within Aura Free (400K) but complex enough that SQL JOIN chains become painful.

### Neo4j MCP Servers

| Server | Role in Content Flywheel |
|--------|--------------------------|
| `mcp-neo4j-cypher` | Read/write content pipeline data — move cards between stages, query relationships, update metrics |
| `mcp-neo4j-memory` | Persist entities and relationships across Claude sessions |
| `mcp-neo4j-data-modeling` | Design and validate the content graph schema, export to Arrows.app |
| `mcp-neo4j-cloud-aura-api` | Manage Neo4j Aura instances (create, scale, monitor) |

All support STDIO, SSE, and HTTP transports. APOC plugin required for schema inspection.

### Graph Schema

```cypher
// Core content nodes
(:ContentPiece {id, title, slug, status, stage, author, created, updated, published_at, url})
(:Keyword {term, volume, difficulty, intent, cpc})
(:KeywordCluster {name, pillar_topic})
(:SERPSnapshot {position, date, features: [], ai_overview_cited: bool})
(:BacklinkSource {domain, authority_rank, anchor_text})
(:Author {name, bio, expertise: []})

// Pipeline stages as nodes (enables flexible kanban)
(:PipelineStage {name, order, color})
// Stages: Inspiration > Research > Draft > Optimize > Review > Published > Monitor > Refresh

// CMS/CRM integration nodes (agnostic)
(:CMSTarget {type: "sanity"|"wordpress"|"custom", project_id, dataset})
(:DistributionChannel {type: "ghl"|"buffer"|"native", platform, account_id})

// Relationships
(content)-[:TARGETS]->(keyword)
(keyword)-[:BELONGS_TO]->(cluster)
(content)-[:RANKS_FOR]->(serp_snapshot)
(content)-[:HAS_BACKLINK_FROM]->(backlink_source)
(content)-[:LINKS_TO]->(content)
(content)-[:IN_STAGE]->(pipeline_stage)
(content)-[:AUTHORED_BY]->(author)
(content)-[:PUBLISHED_TO]->(cms_target)
(content)-[:DISTRIBUTED_TO]->(distribution_channel)
(content)-[:INSPIRED_BY]->(content)  // flywheel loop
```

---

## Decision 2: Next.js API Routes Over n8n

n8n is documented in project-launcher (n8n-builder and n8n-executor MCP servers) but has zero actual implementation — no configured MCP servers, no workflow examples, no `.mcp.json` entries.

Since the content flywheel requires a Next.js dashboard anyway, API routes + Vercel cron jobs handle all the same automation without a separate service:

| Concern | n8n | Next.js API Routes + Vercel Cron |
|---------|-----|----------------------------------|
| **Additional service** | Yes — n8n Cloud ($20/mo+) or self-hosted Docker | No — same deployment as dashboard |
| **Scheduled jobs** | n8n cron triggers | Vercel Cron Jobs |
| **Webhook handling** | n8n webhook nodes | Next.js API routes (`/api/webhooks/*`) |
| **DataForSEO pulls** | n8n HTTP request node | API route with fetch + Neo4j driver |
| **CMS publishing** | n8n Sanity/HTTP node | API route with Sanity client SDK |
| **Social posting** | n8n GHL/HTTP node | API route with GHL API |
| **Debugging** | n8n execution logs (separate UI) | Vercel logs, same stack |
| **Cost** | $20-50/mo (n8n Cloud) or VPS hosting | $0 (Vercel free) to $20/mo (Pro) |

n8n remains a valid option in project-launcher's interview questions for clients who already use it or need complex visual workflow editing. But for the content flywheel dashboard itself, the stack is simpler without it.

### Automation Architecture

```
/api/cron/seo-pull          — Vercel Cron (daily) > DataForSEO API > Neo4j
/api/cron/serp-snapshot     — Vercel Cron (weekly) > DataForSEO SERP API > Neo4j
/api/webhooks/sanity        — Sanity webhook on publish > update Neo4j status
/api/webhooks/ghl           — GHL webhook on post complete > update Neo4j distribution status
/api/publish/sanity         — Push draft to Sanity CMS > create/update document
/api/publish/social         — Push to GHL Social > schedule posts across platforms
/api/graph/query            — Generic Cypher query endpoint for dashboard
```

---

## Decision 3: CMS/CRM-Agnostic Adapter Pattern

The dashboard treats CMS and CRM as pluggable adapters behind a common interface:

```typescript
interface CMSAdapter {
  createDraft(content: ContentPiece): Promise<CMSDocument>
  updateDraft(id: string, content: Partial<ContentPiece>): Promise<CMSDocument>
  publish(id: string): Promise<{ url: string }>
  unpublish(id: string): Promise<void>
  getStatus(id: string): Promise<'draft' | 'published' | 'scheduled'>
}

interface DistributionAdapter {
  schedulePost(content: SocialPost, scheduledAt: Date): Promise<PostResult>
  getPostStatus(id: string): Promise<'scheduled' | 'posted' | 'failed'>
  listPlatforms(): Promise<Platform[]>
}
```

### Sanity CMS (First CMS Adapter)

Already documented in `seo-aeo-geo/skills/nextjs-sanity-seo/SKILL.md` with schema patterns, GROQ queries, and metadata generation.

- When content reaches "Publish" stage in kanban: Sanity adapter creates/updates document with SEO metadata from Neo4j content node
- Sanity webhook fires back to `/api/webhooks/sanity` and Neo4j status updates to "Published"
- URL propagated back to content node for SERP tracking

### GoHighLevel (First Distribution Adapter)

- When content reaches "Published" stage: GHL adapter generates platform-specific variants and schedules posts via GHL Social Media Module API
- GHL webhook fires back to `/api/webhooks/ghl` and Neo4j distribution status updates
- Engagement metrics flow back to content node for performance tracking

### Adding Future Adapters

1. Implement the `CMSAdapter` or `DistributionAdapter` interface
2. Add a new node in Neo4j (e.g., `(:CMSTarget {type: "wordpress"})`)
3. Register the adapter in dashboard config
4. No changes to graph schema, kanban board, or core pipeline logic

---

## Architecture Overview

```
+-------------------------------------------------------------+
|                    Claude Code (CLI)                         |
|                                                             |
|  mcp-neo4j-cypher    mcp-neo4j-memory    dataforseo-mcp    |
|  (pipeline CRUD)     (session context)    (SEO data)        |
+----------+------------------+------------------+------------+
           |                  |                  |
           v                  v                  v
+-------------------------------------------------------------+
|                     Neo4j (Aura)                            |
|                                                             |
|  Content nodes <-> Keywords <-> Clusters                    |
|       |               |                                     |
|  SERP snapshots   Backlinks                                 |
|       |               |                                     |
|  Pipeline stages   Internal links                           |
|       |                                                     |
|  CMS targets <-> Distribution channels                      |
+----------+--------------------------------------------------+
           |
           v
+-------------------------------------------------------------+
|              Next.js Dashboard (Vercel)                      |
|                                                             |
|  +----------+  +----------+  +----------+  +------------+  |
|  |  Kanban   |  | Content  |  |  Graph   |  | Performance|  |
|  |  Board    |  |  Detail  |  |  Explorer|  |  Dashboard |  |
|  +----------+  +----------+  +----------+  +------------+  |
|                                                             |
|  /api/cron/*          -- Scheduled DataForSEO pulls         |
|  /api/webhooks/*      -- Sanity + GHL callbacks             |
|  /api/publish/*       -- CMS + social adapters              |
|  /api/graph/*         -- Cypher query proxy                 |
+-------------------------------------------------------------+
           |                           |
           v                           v
+------------------+      +------------------------+
|   Sanity CMS     |      |   GoHighLevel CRM      |
|   (blog drafts,  |      |   (social scheduling,  |
|    publishing)   |      |    multi-platform)     |
+------------------+      +------------------------+
```

---

## Implementation Plan (Standalone Repo)

The content-flywheel system will be implemented as a **standalone repository** separate from rhize-plugins.

### Phase 1: Neo4j Schema + MCP Integration
1. Create standalone repo with Next.js + TypeScript + Tailwind
2. Set up Neo4j Aura Free instance, install APOC plugin
3. Deploy graph schema via Cypher (nodes, constraints, indexes)
4. Configure `.mcp.json` with `mcp-neo4j-cypher`, `mcp-neo4j-memory`, `mcp-neo4j-data-modeling`
5. Verify Claude can CRUD content nodes via MCP

### Phase 2: Kanban Dashboard
1. Build kanban board view (columns = pipeline stages from Neo4j `PipelineStage` nodes)
2. Build content detail panel (keywords, backlinks, SERP history, internal links)
3. Build graph explorer view (D3.js or `react-force-graph` for content network visualization)
4. Deploy to Vercel

### Phase 3: CMS + Distribution Adapters
1. Implement Sanity CMS adapter (create draft, publish, webhook receiver)
2. Implement GHL distribution adapter (schedule posts, webhook receiver)
3. Wire up Vercel cron jobs for DataForSEO pulls (daily keyword ranks, weekly SERP snapshots)
4. Add adapter registration UI in dashboard settings

---

## Cost Summary

| Component | Free Tier | Scaled (Pro) |
|-----------|-----------|-------------|
| Neo4j Aura | $0 (200K nodes) | $65/mo |
| Vercel (dashboard + API routes) | $0 (hobby) | $20/mo (Pro) |
| DataForSEO API | Pay-per-use (~$50-100/mo) | Same |
| Sanity CMS | $0 (free tier, 3 users) | $99/mo (Team) |
| GoHighLevel | Existing subscription | Same |
| **n8n (eliminated)** | **-$20-50/mo saved** | **-$50+/mo saved** |
| **Total** | **~$50-100/mo** | **~$235-285/mo** |

vs. Google Sheets approach: $0-35/mo but no relationships, no dashboard, no automation.

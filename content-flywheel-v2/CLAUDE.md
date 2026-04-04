# Content Flywheel

## Project Overview

Content pipeline dashboard powered by Neo4j graph database with kanban board UI, automated SEO tracking, and CMS/CRM-agnostic publishing adapters.

**Stack:** Next.js 15 (App Router) + TypeScript + Tailwind CSS + Neo4j Aura + Vercel

## Architecture

```
Neo4j (Aura)          — Graph database: content, keywords, clusters, SERP, backlinks
Next.js Dashboard     — Kanban board, content detail, graph explorer
  /api/cron/*         — Vercel Cron: daily DataForSEO pulls, weekly SERP snapshots
  /api/webhooks/*     — Sanity + GHL webhook receivers
  /api/publish/*      — CMS + social distribution adapters
  /api/graph/query    — Generic Cypher query proxy
```

## Key Directories

- `src/types/` — Core TypeScript types and pipeline stage definitions
- `src/lib/neo4j/` — Neo4j driver singleton and Cypher query functions
- `src/lib/adapters/cms/` — CMS adapters (Sanity first)
- `src/lib/adapters/distribution/` — Distribution adapters (GoHighLevel first)
- `src/app/board/` — Kanban board page
- `src/app/content/[id]/` — Content detail page
- `src/app/api/` — All API routes (cron, webhooks, publish, graph)
- `cypher/` — Neo4j schema definitions (run `schema.cypher` to initialize)

## Graph Schema

Pipeline stages are nodes, not enum values — content moves between stages via relationships:
```
(ContentPiece)-[:IN_STAGE]->(PipelineStage)
(ContentPiece)-[:TARGETS]->(Keyword)
(Keyword)-[:BELONGS_TO]->(KeywordCluster)
(ContentPiece)-[:RANKS_FOR]->(SERPSnapshot)
(ContentPiece)-[:HAS_BACKLINK_FROM]->(BacklinkSource)
(ContentPiece)-[:LINKS_TO]->(ContentPiece)
(ContentPiece)-[:PUBLISHED_TO]->(CMSTarget)
(ContentPiece)-[:DISTRIBUTED_TO]->(DistributionChannel)
```

## MCP Servers

This project uses three Neo4j MCP servers (configured in `.mcp.json`):
- **neo4j-cypher** — Read/write content data via Cypher queries
- **neo4j-memory** — Persist entities across Claude sessions
- **neo4j-data-modeling** — Design and validate graph schemas

Plus **dataforseo** for SEO/keyword/SERP data.

## Commands

```bash
npm run dev          # Start dev server at localhost:3000
npm run build        # Production build
npm run lint         # ESLint check
```

## Environment Variables

Copy `.env.example` to `.env.local` and fill in credentials:
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` — Neo4j Aura connection
- `DATAFORSEO_USERNAME`, `DATAFORSEO_PASSWORD` — DataForSEO API
- `SANITY_PROJECT_ID`, `SANITY_DATASET`, `SANITY_API_TOKEN` — Sanity CMS adapter
- `GHL_API_KEY`, `GHL_LOCATION_ID` — GoHighLevel distribution adapter

## CMS/CRM Adapter Pattern

Adapters implement standard interfaces (`CMSAdapter`, `DistributionAdapter`) defined in `src/types/`. To add a new CMS or distribution channel:
1. Create a new file in `src/lib/adapters/cms/` or `src/lib/adapters/distribution/`
2. Implement the interface
3. Add a corresponding `(:CMSTarget)` or `(:DistributionChannel)` node in Neo4j
4. Wire up the API route

Current adapters: Sanity CMS (publishing), GoHighLevel (social distribution)

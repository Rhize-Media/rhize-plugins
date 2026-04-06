# Content Flywheel v2

Content pipeline dashboard powered by Neo4j graph database. Tracks content from inspiration through publication with automated SEO monitoring via DataForSEO.

**Production:** https://content-flywheel-nu.vercel.app

## Stack

- **Next.js 16** (App Router) + TypeScript + Tailwind CSS 4
- **Neo4j Aura** — graph database for content, keywords, clusters, SERP data, backlinks
- **DataForSEO** — keyword research, SERP tracking, backlink analysis, on-page auditing
- **Sanity CMS** — publishing adapter
- **GoHighLevel** — social distribution adapter
- **Vercel** — hosting + cron jobs

## Quick Start

```bash
npm install
npm run init-schema    # seed Neo4j with constraints + pipeline stages
npm run seed           # create 5 sample content pieces
npm run dev            # http://localhost:3000
```

Requires `.env.local` with Neo4j + DataForSEO credentials. See [CLAUDE.md](CLAUDE.md) for full env var reference.

## Pages

- `/board` — Kanban pipeline board with drag-and-drop stage transitions and content creation
- `/content/[id]` — Content detail view with keyword, SERP, backlink, SEO score, workflow history, AI visibility, and stage history panels + workflow action buttons
- `/graph` — Graph explorer with node counts, pipeline funnel, keyword clusters, and workflow history

## API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/board` | GET | Board data grouped by pipeline stage |
| `/api/board/move` | POST | Move content between stages |
| `/api/content` | POST | Create new content piece |
| `/api/content/[id]` | GET | Full content detail with graph neighborhood |
| `/api/graph/stats` | GET | Graph statistics and aggregations |
| `/api/graph/query` | POST | Generic Cypher proxy (requires `x-graph-secret` header) |
| `/api/workflows/*` | POST | DataForSEO workflow runners (6 workflows) |
| `/api/cron/seo-pull` | GET | Daily keyword ranking pull (Vercel Cron) |
| `/api/cron/serp-snapshot` | GET | Weekly SERP feature analysis (Vercel Cron) |
| `/api/publish/sanity` | POST | Publish/draft content to Sanity CMS |
| `/api/publish/social` | POST | Schedule social posts via GoHighLevel |
| `/api/webhooks/sanity` | POST | Sanity publish/unpublish webhook receiver |
| `/api/webhooks/ghl` | POST | GoHighLevel post status webhook receiver |

## Scripts

```bash
npm run dev            # dev server
npm run build          # production build
npm run lint           # eslint
npm test               # vitest (43 tests)
npm run seed           # seed sample content into Neo4j
npm run init-schema    # initialize Neo4j constraints + pipeline stages
npx tsx scripts/migrate-graph-relationships.ts  # backfill graph relationships (one-time)
```

## Pipeline Stages

Inspiration → Research → Draft → Optimize → Review → Published → Monitor → Refresh

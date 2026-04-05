# Content Flywheel Context

You are working with the Content Flywheel v2 — a Neo4j-backed content pipeline management system deployed at https://content-flywheel-nu.vercel.app.

## Graph Schema Summary

**Core Nodes:**
- `ContentPiece` — content items with id, title, slug, stage, author, url, createdAt, updatedAt
- `PipelineStage` — 8 stages: inspiration, research, draft, optimize, review, published, monitor, refresh
- `Keyword` — SEO keywords with term, volume, difficulty, intent, cpc, competition
- `KeywordCluster` — thematic keyword groups with name, pillarTopic
- `SERPSnapshot` — point-in-time ranking data with position, features, aiOverviewCited
- `BacklinkSource` — referring domains with domain, authorityRank, anchorText
- `SEOScore` — per-dimension SEO analysis (title, meta, heading, eeat, internalLink, structuredData, overall)
- `AIVisibilitySnapshot` — AI engine mention tracking with llm, mentionRate, accuracy, citationCount
- `Competitor` — competitor domains with domain, authorityRank
- `WorkflowRun` — execution history with type, status, summary, startedAt, completedAt
- `Author` — content authors with name, bio, expertise
- `CMSTarget` — CMS publishing destinations
- `DistributionChannel` — social distribution platforms

**Key Relationships:**
- `(ContentPiece)-[:IN_STAGE]->(PipelineStage)`
- `(ContentPiece)-[:TARGETS]->(Keyword)`
- `(Keyword)-[:BELONGS_TO]->(KeywordCluster)`
- `(ContentPiece)-[:RANKS_FOR]->(SERPSnapshot)`
- `(ContentPiece)-[:HAS_BACKLINK_FROM]->(BacklinkSource)`
- `(ContentPiece)-[:HAS_SCORE]->(SEOScore)`
- `(ContentPiece)-[:LINKS_TO]->(ContentPiece)`
- `(ContentPiece)-[:PUBLISHED_TO]->(CMSTarget)`
- `(ContentPiece)-[:DISTRIBUTED_TO]->(DistributionChannel)`

## API Endpoints

**Board (dedicated, no raw Cypher):**
- `GET /api/board` — content grouped by pipeline stage
- `POST /api/board/move` — move content between stages (`{ contentId, newStage }`)

**Content:**
- `POST /api/content` — create new content (`{ title, slug, author, url?, stage? }`)
- `GET /api/content/[id]` — full detail with keywords, SERP, backlinks, SEO score, internal links

**Graph:**
- `GET /api/graph/stats` — node counts, relationship counts, pipeline funnel, workflow history, top clusters
- `POST /api/graph/query` — generic Cypher proxy (requires `x-graph-secret` header)

**Workflows** (all POST, all have `maxDuration = 300`):
- `/api/workflows/keyword-research` — expand + classify + cluster keywords
- `/api/workflows/content-optimize` — SEO scoring via DataForSEO On-Page API
- `/api/workflows/serp-analysis` — rank tracking + SERP feature analysis
- `/api/workflows/backlink-analysis` — backlink profile + referring domains
- `/api/workflows/ai-visibility` — AI engine brand mention monitoring
- `/api/workflows/site-audit` — full site crawl + issue identification

**Cron** (Vercel scheduled):
- `GET /api/cron/seo-pull` — daily keyword ranking pull (6am UTC)
- `GET /api/cron/serp-snapshot` — weekly SERP feature analysis (Monday 7am UTC)

**Webhooks:**
- `POST /api/webhooks/sanity` — Sanity publish/unpublish receiver
- `POST /api/webhooks/ghl` — GoHighLevel post status receiver

**Publishing:**
- `POST /api/publish/sanity` — create draft / publish to Sanity CMS
- `POST /api/publish/social` — schedule social posts via GoHighLevel

## Important Code Patterns

**Neo4j Type Serialization:** All query results MUST pass through `toPlain()` from `src/lib/neo4j/queries.ts`. Neo4j driver returns `Integer` (`{low, high}`) and `DateTime` (nested objects) that crash React. `toPlain()` converts to plain numbers and ISO strings.

**Cypher Aggregation Ordering:** Neo4j 5+ rejects `ORDER BY` on variables not in `RETURN` when `collect()` is used. Always alias: `RETURN s.order AS ord, collect(...) ORDER BY ord`.

## Jira Sync

Tasks tracked in Jira project **RT** (Rhize Tools) under epic **RT-9**.
- **Cloud ID:** `ac62d3a2-66bb-4513-a8e8-b634d3465466`
- **Transitions:** To Do (`11`), In Progress (`21`), Done (`31`)
- A PostToolUse hook on Bash (`.claude/hooks/jira-sync.sh`) detects `RT-XX` keys in commit messages and outputs a `JIRA_SYNC:` reminder
- When you see `JIRA_SYNC:`, transition the referenced issues to Done and add a comment with commit SHA
- When starting a task, transition it to In Progress
- Commit message convention: include the `RT-XX` key (e.g. `feat: add Claude SDK (RT-11)`)

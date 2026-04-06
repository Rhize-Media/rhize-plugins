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

**Core Relationships:**
- `(ContentPiece)-[:IN_STAGE {enteredAt}]->(PipelineStage)` — current pipeline position
- `(ContentPiece)-[:WAS_IN_STAGE {stage, enteredAt, leftAt}]->(PipelineStage)` — stage transition history
- `(ContentPiece)-[:TARGETS]->(Keyword)` — keyword targeting
- `(Keyword)-[:BELONGS_TO]->(KeywordCluster)` — cluster membership
- `(Keyword)-[:RELATED_TO]->(Keyword)` — semantic similarity from DataForSEO
- `(ContentPiece)-[:RANKS_FOR]->(SERPSnapshot)` — SERP tracking
- `(SERPSnapshot)-[:FOR_KEYWORD]->(Keyword)` — snapshot-to-keyword link
- `(ContentPiece)-[:HAS_BACKLINK_FROM {discoveredAt, lastSeenAt}]->(BacklinkSource)` — backlinks
- `(ContentPiece)-[:HAS_SCORE]->(SEOScore)` — SEO scores
- `(ContentPiece)-[:LINKS_TO]->(ContentPiece)` — internal links (populated by content-optimize crawl)
- `(ContentPiece)-[:HAS_WORKFLOW_RUN]->(WorkflowRun)` — workflow execution history
- `(ContentPiece)-[:HAS_AI_VISIBILITY]->(AIVisibilitySnapshot)` — LLM brand mentions
- `(ContentPiece)-[:PUBLISHED_TO {publishedAt, documentId}]->(CMSTarget)` — CMS publishing
- `(ContentPiece)-[:DISTRIBUTED_TO {scheduledAt, postId, status}]->(DistributionChannel)` — social distribution
- `(Author)-[:WROTE]->(ContentPiece)` — authorship
- `(Author)-[:EXPERT_IN]->(KeywordCluster)` — author topic expertise (E-E-A-T)
- `(Competitor)-[:RANKS_FOR]->(Keyword)` — competitor keyword rankings from gap analysis
- `(Competitor)-[:HAS_BACKLINK_FROM]->(BacklinkSource)` — competitor backlink profile
- `(Competitor)-[:HAS_WORKFLOW_RUN]->(WorkflowRun)` — site audit workflow link
- `(SiteAudit)-[:AUDITS]->(Competitor)` — audit-to-domain link

## API Endpoints

**Board (dedicated, no raw Cypher):**
- `GET /api/board` — content grouped by pipeline stage
- `POST /api/board/move` — move content between stages (`{ contentId, newStage }`)

**Content:**
- `POST /api/content` — create new content (`{ title, slug, author, url?, stage? }`)
- `GET /api/content/[id]` — full detail with keywords, SERP, backlinks, SEO score, internal links, workflow history, AI visibility, stage history

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

**Conditional Relationship Creation:** When a relationship target may not exist (e.g., contentId is optional), use the FOREACH/CASE pattern: `OPTIONAL MATCH (c:ContentPiece {id: $contentId}) FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END | CREATE (c)-[:REL]->(target))`. All 6 workflows use this for HAS_WORKFLOW_RUN.

**Stage Transition History:** `moveContentToStage` archives the old IN_STAGE as WAS_IN_STAGE with `{stage, enteredAt, leftAt}` timestamps before creating the new IN_STAGE. Enables pipeline velocity analytics.

**Graph Stats Performance:** `getGraphStats` uses `UNION ALL` single queries for node and relationship counts instead of N+1 sequential queries.

## Jira Sync

Tasks tracked in Jira project **RT** (Rhize Tools) under epic **RT-9**.
- **Cloud ID:** `ac62d3a2-66bb-4513-a8e8-b634d3465466`
- **Transitions:** To Do (`11`), In Progress (`21`), Done (`31`)
- A PostToolUse hook on Bash (`.claude/hooks/jira-sync.sh`) detects `RT-XX` keys in commit messages and outputs a `JIRA_SYNC:` reminder
- When you see `JIRA_SYNC:`, transition the referenced issues to Done and add a comment with commit SHA
- When starting a task, transition it to In Progress
- Commit message convention: include the `RT-XX` key (e.g. `feat: add Claude SDK (RT-11)`)

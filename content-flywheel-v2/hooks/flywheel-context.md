# Content Flywheel Context

You are working with the Content Flywheel — a Neo4j-backed content pipeline management system.

## Graph Schema Summary

**Core Nodes:**
- `ContentPiece` — content items with id, title, slug, stage, author, url
- `PipelineStage` — 8 stages: inspiration, research, draft, optimize, review, published, monitor, refresh
- `Keyword` — SEO keywords with term, volume, difficulty, intent, cpc
- `KeywordCluster` — thematic keyword groups
- `SERPSnapshot` — point-in-time ranking data
- `BacklinkSource` — referring domains
- `SEOScore` — per-dimension SEO analysis scores
- `AIVisibilitySnapshot` — AI engine mention tracking
- `Competitor` — competitor domains
- `WorkflowRun` — execution history

**Key Relationships:**
- `(ContentPiece)-[:IN_STAGE]->(PipelineStage)`
- `(ContentPiece)-[:TARGETS]->(Keyword)`
- `(Keyword)-[:BELONGS_TO]->(KeywordCluster)`
- `(ContentPiece)-[:RANKS_FOR]->(SERPSnapshot)`
- `(ContentPiece)-[:HAS_BACKLINK_FROM]->(BacklinkSource)`
- `(ContentPiece)-[:HAS_SCORE]->(SEOScore)`
- `(ContentPiece)-[:HAS_AI_VISIBILITY]->(AIVisibilitySnapshot)`
- `(ContentPiece)-[:INSPIRED_BY]->(Inspiration)`
- `(ContentPiece)-[:LINKS_TO]->(ContentPiece)`

## Available Workflows
- `keyword-research` — expand + classify + cluster keywords
- `content-optimize` — SEO scoring via DataForSEO On-Page API
- `serp-analysis` — rank tracking + SERP feature analysis
- `backlink-analysis` — backlink profile + referring domains
- `ai-visibility` — AI engine brand mention monitoring
- `site-audit` — full site crawl + issue identification

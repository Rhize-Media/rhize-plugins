---
description: Show content flywheel pipeline status, recent workflow runs, and key metrics
argument-hint: [content-id or "summary"]
allowed-tools: Read, Bash(curl:*)
---

Show flywheel status for $ARGUMENTS by querying Neo4j.

## Process

1. **Parse arguments:**
   - If a content ID is provided: show detailed status for that content piece
   - If "summary" or no argument: show overall pipeline metrics

2. **Query Neo4j for status data:**

   **Overall Summary:**
   ```cypher
   // Pipeline stage counts
   MATCH (c:ContentPiece)-[:IN_STAGE]->(s:PipelineStage)
   RETURN s.name AS stage, s.order AS ord, count(c) AS count
   ORDER BY s.order

   // Recent workflow runs
   MATCH (w:WorkflowRun)
   RETURN w.type, w.status, w.summary, w.startedAt
   ORDER BY w.startedAt DESC LIMIT 10

   // Key metrics
   MATCH (k:Keyword) RETURN count(k) AS totalKeywords
   MATCH (b:BacklinkSource) RETURN count(b) AS totalBacklinks
   MATCH (s:SERPSnapshot) RETURN count(s) AS totalSnapshots
   ```

   **Content Detail:**
   ```cypher
   MATCH (c:ContentPiece {id: $id})-[:IN_STAGE]->(s:PipelineStage)
   OPTIONAL MATCH (c)-[:TARGETS]->(k:Keyword)
   OPTIONAL MATCH (c)-[:RANKS_FOR]->(snap:SERPSnapshot)
   OPTIONAL MATCH (c)-[:HAS_SCORE]->(seo:SEOScore)
   OPTIONAL MATCH (c)-[:HAS_BACKLINK_FROM]->(b:BacklinkSource)
   RETURN c.title, s.name AS stage, count(DISTINCT k) AS keywords,
          count(DISTINCT snap) AS snapshots, count(DISTINCT b) AS backlinks,
          head(collect(DISTINCT seo.overall)) AS latestSEOScore
   ```

3. **Present results:**

   **Summary view:**
   - Pipeline funnel showing count per stage
   - Recent workflow runs table
   - Key metrics (total keywords, backlinks, snapshots)

   **Content detail view:**
   - Current stage and metadata
   - Keywords count and top keywords
   - Latest SEO score
   - Recent SERP positions
   - Backlink count

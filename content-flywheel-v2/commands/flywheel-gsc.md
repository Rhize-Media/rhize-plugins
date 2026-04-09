---
description: Query Google Search Console data for rhize.media via SEO Utils
argument-hint: <queries|pages|top-queries|declining|branded> [date-range] [page-filter]
allowed-tools: Read, Bash(curl:*)
---

Query local Google Search Console data for $ARGUMENTS via the SEO Utils MCP.

**Requires:** SEO Utils desktop app running locally (http://localhost:19515/mcp).

## Process

1. **Parse arguments:**
   - First argument: report type — `queries`, `pages`, `top-queries`, `declining`, `branded`
   - Second argument (optional): date range — `7d`, `30d`, `90d` (default: `30d`)
   - Third argument (optional): page URL filter

2. **Use SEO Utils MCP tools:**

   **Top queries (by clicks):**
   ```
   query_gsc: "SELECT query, SUM(clicks) as clicks, SUM(impressions) as impressions, 
               AVG(position) as avg_position, AVG(ctr) as avg_ctr
               FROM gsc_data WHERE date >= date('now', '-30 days')
               GROUP BY query ORDER BY clicks DESC LIMIT 50"
   ```

   **Declining queries (losing position):**
   ```
   query_database: Compare last 7-day average position vs prior 7-day average.
                   Flag queries where position worsened by > 3 positions.
   ```

   **Top pages (by impressions):**
   ```
   query_gsc: "SELECT page, SUM(clicks), SUM(impressions), AVG(position)
               FROM gsc_data WHERE date >= date('now', '-30 days')
               GROUP BY page ORDER BY SUM(impressions) DESC LIMIT 30"
   ```

   **Branded queries:**
   ```
   query_gsc: Filter queries containing brand terms (rhize, rhize media).
   ```

3. **Cross-reference with Neo4j** — match GSC pages to ContentPiece nodes by URL or slug:
   ```cypher
   MATCH (c:ContentPiece) WHERE c.url CONTAINS "<page-path>"
   RETURN c.id, c.title, c.stage
   ```

4. **Present insights:**
   - Top performing queries with click/impression trends
   - Content pieces with declining rankings (candidates for refresh)
   - Pages with high impressions but low CTR (title/meta optimization opportunities)
   - Branded vs non-branded traffic split

5. **Suggest actions:**
   - "Run content-optimize on <title>" for declining pages
   - "Move <title> to refresh stage" for content decay
   - "Research Keywords for <topic>" for high-impression/low-click queries

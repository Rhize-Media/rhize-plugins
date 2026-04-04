---
description: Run monitoring workflows (SERP rankings, backlinks, AI visibility) and store results in Neo4j
argument-hint: <serp|backlinks|ai> <content-id or domain> [additional args]
allowed-tools: Read, Bash(curl:*), WebFetch, WebSearch
---

Run monitoring analysis for $ARGUMENTS and persist results to Neo4j.

## Process

1. Read the relevant skill at `${CLAUDE_PLUGIN_ROOT}/skills/`:
   - `rank-monitor/SKILL.md` for SERP analysis
   - `backlink-monitor/SKILL.md` for backlink analysis
   - `ai-visibility/SKILL.md` for AI visibility monitoring

2. **Parse arguments:**
   - First argument: workflow type — `serp`, `backlinks`, or `ai`
   - Second argument: content ID or domain
   - Additional arguments vary by type:
     - `serp`: optional keywords (comma-separated)
     - `backlinks`: (no additional args)
     - `ai`: brand name, optional queries (comma-separated)

3. **Run the appropriate workflow** via API route:

   **SERP Analysis:**
   ```
   POST /api/workflows/serp-analysis
   { "contentId": "<id>" }
   ```

   **Backlink Analysis:**
   ```
   POST /api/workflows/backlink-analysis
   { "domain": "<domain>", "contentId": "<id if provided>" }
   ```

   **AI Visibility:**
   ```
   POST /api/workflows/ai-visibility
   { "brand": "<brand>", "contentId": "<id>", "queries": ["<query1>", "<query2>"] }
   ```

   Or if the API is not running, use DataForSEO MCP + Neo4j MCP directly.

4. **Present results** to user:
   - For SERP: ranking table with position changes and SERP features
   - For backlinks: profile summary with top referrers and anchor distribution
   - For AI: mention rate and accuracy across LLMs with optimization recommendations

5. **Verify persistence** — query Neo4j to confirm data was stored:
   ```cypher
   // SERP
   MATCH (c:ContentPiece {id: "<id>"})-[:RANKS_FOR]->(s:SERPSnapshot)
   RETURN s.position, s.date ORDER BY s.date DESC LIMIT 5

   // Backlinks
   MATCH (c:ContentPiece {id: "<id>"})-[:HAS_BACKLINK_FROM]->(b:BacklinkSource)
   RETURN b.domain, b.authorityRank ORDER BY b.authorityRank DESC LIMIT 10

   // AI Visibility
   MATCH (a:AIVisibilitySnapshot {contentId: "<id>"})
   RETURN a.llm, a.mentionRate, a.accuracy ORDER BY a.date DESC LIMIT 5
   ```

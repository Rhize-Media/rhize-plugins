---
description: Run SEO optimization analysis on a content piece, storing scores in Neo4j
argument-hint: <content-id> <url> [primary-keyword]
allowed-tools: Read, Bash(curl:*), WebFetch, WebSearch
---

Perform content SEO optimization for $ARGUMENTS using the content-optimize skill and persist results to Neo4j.

## Process

1. Read the content-optimize skill at `${CLAUDE_PLUGIN_ROOT}/skills/content-optimize/SKILL.md`.

2. **Parse arguments:**
   - First argument: content piece ID (required)
   - Second argument: published URL (required)
   - Third argument (optional): primary keyword for placement scoring

3. **Run the workflow** via the API route:
   ```
   POST /api/workflows/content-optimize
   { "contentId": "<content-id>", "url": "<url>", "primaryKeyword": "<keyword if provided>" }
   ```
   Or if the API is not running, use DataForSEO MCP + Neo4j MCP directly:
   - Use `dataforseo` MCP to run on-page crawl and retrieve page data
   - Score each dimension locally (title, meta, headings, E-E-A-T, links, schema)
   - Use `mcp-neo4j-cypher` to store SEOScore node and HAS_SCORE relationship

4. **Present results** to user:
   - Overall score with grade (A/B/C/D/F)
   - Per-dimension score breakdown table
   - Prioritized recommendations list
   - Stage advancement notice if score >= 80

5. **Verify persistence** — query Neo4j to confirm score was stored:
   ```cypher
   MATCH (c:ContentPiece {id: "<content-id>"})-[:HAS_SCORE]->(s:SEOScore)
   RETURN s.overall, s.titleScore, s.metaScore, s.headingScore,
          s.eeatScore, s.internalLinkScore, s.structuredDataScore
   ORDER BY s.date DESC LIMIT 1
   ```

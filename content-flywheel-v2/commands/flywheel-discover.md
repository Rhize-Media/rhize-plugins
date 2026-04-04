---
description: Run a site audit to discover content opportunities and SEO issues
argument-hint: <domain> [max-pages]
allowed-tools: Read, Bash(curl:*), WebFetch, WebSearch
---

Run a site audit for $ARGUMENTS using the content-discover skill and persist results to Neo4j.

## Process

1. Read the content-discover skill at `${CLAUDE_PLUGIN_ROOT}/skills/content-discover/SKILL.md`.

2. **Parse arguments:**
   - First argument: domain to audit (required)
   - Second argument (optional): max pages to crawl (default: 100)

3. **Run the workflow** via the API route:
   ```
   POST /api/workflows/site-audit
   { "domain": "<domain>", "maxPages": <max-pages> }
   ```
   Or if the API is not running, use DataForSEO MCP + Neo4j MCP directly:
   - Use `dataforseo` MCP to start an on-page crawl
   - Analyze crawl results for SEO issues
   - Use `mcp-neo4j-cypher` to store SiteAudit and ContentPiece nodes

4. **Present results** to user:
   - Issue summary by severity (critical/high/medium/low)
   - Detailed issue table with affected page counts
   - Content opportunities with recommendations
   - Prioritized action plan

5. **Verify persistence** — query Neo4j:
   ```cypher
   MATCH (a:SiteAudit {domain: "<domain>"})
   RETURN a.totalPages, a.criticalIssues, a.highIssues, a.mediumIssues, a.lowIssues
   ORDER BY a.date DESC LIMIT 1
   ```

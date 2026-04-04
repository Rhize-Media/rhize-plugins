---
description: Research and analyze keywords for a topic, storing results in Neo4j
argument-hint: <topic or seed keyword> [domain for gap analysis]
allowed-tools: Read, Bash(curl:*), WebFetch, WebSearch
---

Perform keyword research for $ARGUMENTS using the keyword-research skill and persist results to Neo4j.

## Process

1. Read the keyword-research skill at `${CLAUDE_PLUGIN_ROOT}/skills/keyword-research/SKILL.md`.

2. **Parse arguments:**
   - First argument: seed keyword(s) — comma-separated if multiple
   - Second argument (optional): target domain for gap analysis

3. **Run the workflow** via the API route:
   ```
   POST /api/workflows/keyword-research
   { "seeds": ["<parsed seeds>"], "domain": "<domain if provided>" }
   ```
   Or if the API is not running, use DataForSEO MCP + Neo4j MCP directly:
   - Use `dataforseo` MCP to fetch keyword suggestions and related keywords
   - Use `mcp-neo4j-cypher` to store Keyword and KeywordCluster nodes

4. **Expand from seeds** using DataForSEO:
   - Keywords Data API for suggestions and related keywords
   - Labs API for proprietary keyword suggestions
   - Generate question, comparison, modifier, and long-tail variations

5. **Classify intent** for every keyword (informational, commercial, transactional).

6. **Cluster keywords** into thematic groups — create KeywordCluster nodes.

7. If a domain was provided, **run gap analysis:**
   - Find competitor domains via Labs API
   - Identify keywords they rank for that we don't
   - Store Competitor nodes and GAP_FOR relationships

8. **Present summary** to user:
   - Keyword opportunity table (term, volume, difficulty, intent, CPC)
   - Cluster map with content recommendations
   - Gap analysis results
   - Quick wins (page 2 keywords to push to page 1)

9. **Verify persistence** — query Neo4j to confirm keywords were stored:
   ```cypher
   MATCH (k:Keyword) WHERE k.term CONTAINS "<seed>"
   RETURN k.term, k.volume, k.difficulty ORDER BY k.volume DESC LIMIT 20
   ```

---
description: Check indexing status and submit URLs to Google/Bing via SEO Utils
argument-hint: <check|submit-google|submit-bing|submit-all> <url or content-id>
allowed-tools: Read, Bash(curl:*)
---

Check or request indexing for $ARGUMENTS via the SEO Utils MCP.

**Requires:** SEO Utils desktop app running locally (http://localhost:19515/mcp).

## Process

1. **Parse arguments:**
   - First argument: action — `check`, `submit-google`, `submit-bing`, `submit-all`
   - Second argument: URL or content ID

2. **If content ID provided, resolve URL from Neo4j:**
   ```cypher
   MATCH (c:ContentPiece {id: "<id>"}) RETURN c.url, c.title
   ```

3. **Execute action via SEO Utils MCP:**

   **check** — Check if URL is indexed by Google:
   ```
   check_google_indexing_status({ url: "<url>" })
   ```

   **submit-google** — Submit to Google Indexing API:
   ```
   submit_url_for_google_indexing({ url: "<url>" })
   ```

   **submit-bing** — Submit to Bing IndexNow:
   ```
   submit_url_to_index_now({ url: "<url>" })
   ```

   **submit-all** — Submit to both Google and Bing.

4. **Update Neo4j** with indexing status:
   ```cypher
   MATCH (c:ContentPiece {url: $url})
   SET c.googleIndexed = $indexed, c.lastIndexCheck = datetime()
   ```

5. **For bulk operations** — check all published content:
   ```cypher
   MATCH (c:ContentPiece)-[:IN_STAGE]->(s:PipelineStage {name: "published"})
   WHERE c.url IS NOT NULL
   RETURN c.id, c.url, c.title
   ```
   Then check each URL and report unindexed pages.

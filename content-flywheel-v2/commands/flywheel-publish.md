---
description: Publish content to CMS (Sanity) and update pipeline status in Neo4j
argument-hint: <content-id> [action: create-draft|publish]
allowed-tools: Read, Bash(curl:*), WebFetch
---

Publish content for $ARGUMENTS via the CMS adapter and update Neo4j pipeline status.

## Process

1. **Parse arguments:**
   - First argument: content piece ID (required)
   - Second argument (optional): action — `create-draft` or `publish` (default: `publish`)

2. **Run the publish workflow** via API route:

   **Create draft:**
   ```
   POST /api/publish/sanity
   { "contentId": "<content-id>", "action": "create-draft" }
   ```

   **Publish:**
   ```
   POST /api/publish/sanity
   { "contentId": "<content-id>", "action": "publish", "sanityId": "<sanity-doc-id>" }
   ```

3. **Update pipeline stage** in Neo4j:
   - On draft creation: move to "review" stage
   - On publish: move to "published" stage, set publishedAt timestamp

4. **Present results** to user:
   - Published URL
   - Updated pipeline stage
   - Confirmation of Neo4j status update

5. **Verify** — query Neo4j:
   ```cypher
   MATCH (c:ContentPiece {id: "<content-id>"})
   RETURN c.stage, c.publishedAt, c.url
   ```

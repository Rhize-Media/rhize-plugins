---
description: Run content gap or backlink gap analysis against competitors via SEO Utils
argument-hint: <content-gap|backlink-gap> <our-domain> <competitor1> [competitor2] [competitor3]
allowed-tools: Read, Bash(curl:*)
---

Run gap analysis for $ARGUMENTS via the SEO Utils MCP.

**Requires:** SEO Utils desktop app running locally (http://localhost:19515/mcp).

## Process

1. **Parse arguments:**
   - First argument: gap type — `content-gap` or `backlink-gap`
   - Second argument: our domain (e.g., `rhize.media`)
   - Remaining arguments: competitor domains (1-3)

2. **Execute gap analysis via SEO Utils MCP:**

   **Content gap** — Keywords competitors rank for that we don't:
   ```
   get_content_gap({
     target: "<our-domain>",
     competitors: ["<comp1>", "<comp2>"],
     limit: 50
   })
   ```

   **Backlink gap** — Domains linking to competitors but not us:
   ```
   get_backlink_gap({
     target: "<our-domain>",
     competitors: ["<comp1>", "<comp2>"],
     limit: 50
   })
   ```

3. **Store gap findings in Neo4j:**

   For content gap keywords:
   ```cypher
   MERGE (k:Keyword {term: $term})
   ON CREATE SET k.id = randomUUID(), k.volume = $volume, k.difficulty = $difficulty
   MERGE (comp:Competitor {domain: $competitor})
   MERGE (comp)-[:RANKS_FOR]->(k)
   ```

   For backlink gap domains:
   ```cypher
   MERGE (b:BacklinkSource {domain: $domain})
   ON CREATE SET b.id = randomUUID(), b.authorityRank = $rank
   MERGE (comp:Competitor {domain: $competitor})
   MERGE (comp)-[:HAS_BACKLINK_FROM]->(b)
   ```

4. **Present actionable insights:**
   - Content gap: "Create content targeting these keywords" with volume/difficulty
   - Backlink gap: "Outreach to these domains" with authority scores
   - Cross-reference with existing content to find optimization opportunities

---
description: Discover autocomplete and question keywords via SEO Utils
argument-hint: <seed keyword>
allowed-tools: Read, Bash(curl:*)
---

Discover autocomplete suggestions for $ARGUMENTS via the SEO Utils MCP.

**Requires:** SEO Utils desktop app running locally (http://localhost:19515/mcp).

## Process

1. **Fetch autocomplete keywords:**
   ```
   fetch_autocomplete_keywords({ keyword: "<seed>", engine: "google" })
   ```

2. **Also fetch from local database** (if previously scraped):
   ```
   get_autocomplete_keywords({ keyword: "<seed>" })
   ```

3. **Check keyword metrics** for discovered terms:
   ```
   check_keyword_metrics({ keywords: ["<term1>", "<term2>", ...] })
   ```

4. **Filter and classify:**
   - Questions ("how", "what", "why", "when", "can")
   - Comparisons ("vs", "or", "compared to", "alternative")
   - Long-tail variations (4+ words)
   - Commercial intent ("buy", "price", "best", "review")

5. **Store high-value discoveries in Neo4j:**
   ```cypher
   MERGE (k:Keyword {term: $term})
   ON CREATE SET k.id = randomUUID(), k.volume = $volume,
                 k.difficulty = $difficulty, k.source = "autocomplete"
   ```

6. **Present as content ideas:**
   - Group by question type (FAQ candidates)
   - Highlight comparison queries (vs-style article ideas)
   - Flag low-competition long-tail opportunities

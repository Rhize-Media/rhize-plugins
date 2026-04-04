---
name: keyword-research
description: >
  ALWAYS invoke this skill for keyword research requests in the content flywheel.
  Performs keyword research using DataForSEO APIs and persists results to Neo4j.
  Triggers on: "find keywords", "keyword research", "keyword analysis", "keyword gap",
  "keyword clustering", "what keywords should I target", "competitor keywords",
  "search volume", "long-tail keywords", "content gap analysis", "keyword opportunities",
  "what are people searching for", "keyword mapping".
  Results are stored as Keyword and KeywordCluster nodes in Neo4j with TARGETS
  relationships to content pieces and BELONGS_TO relationships to clusters.
---

# Keyword Research (Content Flywheel)

Perform keyword research using DataForSEO APIs and persist all results to the Neo4j content graph. This is the Neo4j-aware version — results are stored, not just displayed.

## Workflow

### 1. Gather Input
- Seed keywords or topics (1-5)
- Target domain (for competitor gap analysis)
- Content piece ID (to link keywords via TARGETS relationship)
- Location/language (default: US, English)

### 2. Expand Keywords
Call the `/api/workflows/keyword-research` endpoint or use `mcp-neo4j-cypher` directly:

**Via API route:**
```
POST /api/workflows/keyword-research
{ "seeds": ["remote work tools"], "domain": "example.com", "contentId": "abc123" }
```

**Via Neo4j MCP (after running DataForSEO queries):**
```cypher
MERGE (k:Keyword {term: $term})
ON CREATE SET k.id = randomUUID(), k.volume = $volume, k.difficulty = $difficulty, k.intent = $intent
```

### 3. Classify Intent
Every keyword is classified:
| Intent | Signals | Content Format |
|--------|---------|---------------|
| Informational | how, what, why, guide, tutorial | Blog posts, guides |
| Commercial | best, review, compare, vs, alternative | Comparison pages, listicles |
| Transactional | buy, pricing, demo, sign up | Product pages, landing pages |

### 4. Cluster Keywords
Keywords are grouped into `KeywordCluster` nodes by topic. Each cluster maps to a content pillar.

```cypher
MATCH (cl:KeywordCluster {name: "remote work"})
MATCH (k:Keyword) WHERE toLower(k.term) CONTAINS "remote work"
MERGE (k)-[:BELONGS_TO]->(cl)
```

### 5. Competitor Gap Analysis
If a domain is provided, identify:
- Keywords competitors rank for that you don't → content opportunities
- Keywords where you're on page 2 (positions 11-20) → quick wins
- Keywords you outrank all competitors on → defend these

Gap keywords are stored with `GAP_FOR` relationships to `Competitor` nodes.

### 6. Link to Content
If a content piece ID is provided, the top keywords are linked:
```cypher
MATCH (c:ContentPiece {id: $contentId}), (k:Keyword {term: $term})
MERGE (c)-[:TARGETS]->(k)
```

### 7. Verify in Dashboard
After running, check the content detail page at `/content/{id}` — target keywords should appear in the Keywords table.

## Priority Scoring
- High volume + low difficulty + commercial/transactional intent = highest priority
- Target keywords with difficulty below the site's authority for realistic wins
- Seasonal keywords: plan content 4-6 weeks before peak

## Output
All results persist in Neo4j. The workflow also returns a summary:
- Keywords created/updated count
- Clusters created count
- Gap keywords found count
- WorkflowRun node with status and timing

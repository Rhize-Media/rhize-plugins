---
name: content-optimize
description: >
  ALWAYS invoke this skill for content SEO optimization requests in the content flywheel.
  Runs on-page SEO analysis via DataForSEO On-Page API and persists SEOScore nodes to Neo4j.
  Triggers on: "optimize content for SEO", "improve on-page SEO", "SEO score", "content optimization",
  "fix meta tags", "heading structure", "E-E-A-T", "internal linking", "structured data",
  "content audit", "page SEO analysis", "SEO recommendations", "content quality score".
  Results are stored as SEOScore nodes linked to ContentPiece via HAS_SCORE relationships.
---

# Content SEO Optimization (Content Flywheel)

Analyze and score content pieces for SEO quality using DataForSEO On-Page API. All results persist to the Neo4j content graph as SEOScore nodes.

## Workflow

### 1. Gather Input
- Content piece ID (required — used to link score in Neo4j)
- Published URL (required — crawled by DataForSEO)
- Primary keyword (optional — used for keyword placement scoring)
- Location/language (default: US, English)

### 2. Run Analysis
Call the `/api/workflows/content-optimize` endpoint or invoke directly:

**Via API route:**
```
POST /api/workflows/content-optimize
{ "contentId": "abc123", "url": "https://example.com/blog/post", "primaryKeyword": "remote work tools" }
```

**Via Neo4j MCP (after scoring):**
```cypher
MATCH (c:ContentPiece {id: $contentId})
CREATE (s:SEOScore {id: randomUUID(), overall: $overall, titleScore: $titleScore, ...})
CREATE (c)-[:HAS_SCORE]->(s)
```

### 3. Scoring Dimensions

| Dimension | Weight | What's Evaluated |
|-----------|--------|-----------------|
| Title Tag | 15% | Length (50-60 chars), keyword position, uniqueness |
| Meta Description | 15% | Length (150-160 chars), keyword inclusion, CTA |
| Heading Structure | 20% | Single H1, logical H2/H3 hierarchy, keyword usage |
| E-E-A-T Signals | 20% | Content depth, citations, images, author markup, HTTPS |
| Internal Links | 15% | 3-5 links per 1,000 words, descriptive anchors |
| Structured Data | 15% | JSON-LD presence, Open Graph tags |

### 4. Recommendations Generated
Based on scores below threshold, actionable recommendations are generated:
- Title optimization (50-60 chars, keyword front-loaded)
- Meta description improvement (150-160 chars with CTA)
- Heading structure fixes (single H1, logical hierarchy)
- E-E-A-T strengthening (author bio, citations, original data)
- Internal linking targets (3-5 per 1,000 words)
- Structured data implementation (JSON-LD + OG tags)
- Content depth expansion for thin content (<1,000 words)

### 5. Stage Advancement
If the overall score reaches 80+, content in "draft" or "optimize" stage is automatically advanced to "review".

### 6. Verify in Dashboard
After running, check the content detail page at `/content/{id}` — the SEO Score section should show the latest analysis with per-dimension breakdowns and recommendations.

## Output
All results persist in Neo4j. The workflow returns:
- SEOScore object with per-dimension scores and overall
- Recommendations array
- WorkflowRun node with status and timing

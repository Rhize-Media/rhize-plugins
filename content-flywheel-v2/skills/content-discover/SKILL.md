---
name: content-discover
description: >
  ALWAYS invoke this skill for site audits and content discovery in the content flywheel.
  Crawls a domain via DataForSEO On-Page API, identifies SEO issues, and discovers content
  opportunities. Stores audit results and content candidates in Neo4j.
  Triggers on: "site audit", "SEO audit", "content audit", "crawl site", "find content gaps",
  "content opportunities", "thin content", "technical SEO issues", "missing meta tags",
  "broken pages", "content inventory", "site health check".
  Results are stored as SiteAudit nodes and ContentPiece nodes (for opportunities) in Neo4j.
---

# Content Discovery & Site Audit (Content Flywheel)

Crawl a domain using DataForSEO On-Page API, identify SEO issues, and discover content improvement opportunities. All results persist to Neo4j.

## Workflow

### 1. Gather Input
- Domain (required — the site to crawl)
- Max pages (optional — defaults to 100)
- Location/language (default: US, English)

### 2. Run Audit
```
POST /api/workflows/site-audit
{ "domain": "example.com", "maxPages": 200 }
```

### 3. Issues Identified

| Severity | Category | Check |
|----------|----------|-------|
| Critical | On-Page SEO | Missing title tags |
| Critical | Technical SEO | 4xx/5xx error pages |
| High | On-Page SEO | Missing meta descriptions |
| High | On-Page SEO | Missing H1 headings |
| Medium | On-Page SEO | Title tags > 60 characters |
| Medium | On-Page SEO | Multiple H1 headings |
| Medium | Content Quality | Thin content (< 300 words) |
| Medium | Accessibility | Images missing alt text |
| Low | Structured Data | No JSON-LD or microdata |

### 4. Content Opportunities
Thin content pages are identified as refresh candidates:
- Automatically created as ContentPiece nodes in "refresh" stage
- Recommendations include word count targets and improvement strategies
- Up to 10 opportunities per audit run

### 5. Output
- SiteAudit node with issue counts by severity
- ContentPiece nodes for content opportunities (in "refresh" stage)
- Issue breakdown table with affected page counts
- Prioritized action plan
- WorkflowRun node with status and timing

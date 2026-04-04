---
name: rank-monitor
description: >
  ALWAYS invoke this skill for SERP tracking and rank monitoring in the content flywheel.
  Checks keyword rankings via DataForSEO SERP API and persists SERPSnapshot nodes to Neo4j.
  Triggers on: "check rankings", "rank tracking", "SERP analysis", "keyword positions",
  "where do I rank", "ranking changes", "SERP features", "position tracking",
  "rank monitoring", "search visibility", "ranking report", "SERP snapshot".
  Results are stored as SERPSnapshot nodes linked to ContentPiece via RANKS_FOR relationships.
---

# SERP Analysis & Rank Monitoring (Content Flywheel)

Track keyword rankings and SERP features using DataForSEO SERP API. All results persist to Neo4j as SERPSnapshot nodes.

## Workflow

### 1. Gather Input
- Content piece ID (optional — checks all keywords linked to this content)
- Keywords list (optional — ad-hoc keyword check)
- Domain (optional — for domain-level rank overview)
- Location/language (default: US, English)

### 2. Run Analysis
```
POST /api/workflows/serp-analysis
{ "contentId": "abc123" }
```
Or for ad-hoc:
```
POST /api/workflows/serp-analysis
{ "keywords": ["remote work tools", "best wfh setup"], "domain": "example.com" }
```

### 3. What's Tracked
- Current position for each keyword
- Position change vs previous snapshot
- SERP features present (featured snippets, PAA, knowledge panel, AI Overview)
- Whether AI Overview cites the content
- Historical rank data for domain

### 4. Output
- Rank change summary (improved/declined counts)
- Per-keyword position table with movement indicators
- SERP feature map showing which features exist per keyword
- SERPSnapshot nodes persisted in Neo4j with RANKS_FOR relationships

### 5. Automated Monitoring
Cron jobs handle regular tracking:
- Daily: `/api/cron/seo-pull` — pulls rank data for all tracked keywords
- Weekly: `/api/cron/serp-snapshot` — broader SERP feature analysis for published content

### 6. Verify in Dashboard
Check `/content/{id}` for SERP history table showing position trends over time.

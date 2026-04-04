---
name: backlink-monitor
description: >
  ALWAYS invoke this skill for backlink analysis in the content flywheel.
  Analyzes backlink profiles via DataForSEO Backlinks API and persists BacklinkSource nodes to Neo4j.
  Triggers on: "backlink analysis", "backlink profile", "referring domains", "link building",
  "backlink audit", "anchor text analysis", "new backlinks", "lost backlinks",
  "domain authority", "link quality", "toxic links", "backlink gap".
  Results are stored as BacklinkSource nodes linked to ContentPiece via HAS_BACKLINK_FROM relationships.
---

# Backlink Analysis (Content Flywheel)

Analyze backlink profiles using DataForSEO Backlinks API. All results persist to Neo4j as BacklinkSource nodes.

## Workflow

### 1. Gather Input
- Domain (required — the target domain to analyze)
- Content piece ID (optional — links backlink sources to specific content)
- Location/language (default: US, English)

### 2. Run Analysis
```
POST /api/workflows/backlink-analysis
{ "domain": "example.com", "contentId": "abc123" }
```

### 3. What's Analyzed
- **Profile summary:** total backlinks, referring domains, domain rank
- **Quality metrics:** dofollow/nofollow ratio, authority distribution
- **Top referrers:** highest-authority linking domains (top 20)
- **Anchor text:** distribution analysis with percentage breakdown
- **Velocity:** new vs lost backlinks in last 30 days

### 4. Quality Assessment
**Healthy indicators:**
- Diverse referring domains (not concentrated in few sources)
- Natural anchor text distribution (branded > exact match)
- Dofollow ratio between 60-80%
- Steady growth in referring domains

**Red flags:**
- Sudden spikes in backlink count
- High percentage of exact-match anchors
- Many links from low-authority domains
- Dofollow ratio >95% or <40%

### 5. Output
- BacklinkProfile object with all metrics
- BacklinkSource nodes stored in Neo4j
- HAS_BACKLINK_FROM relationships to content pieces
- Competitor domain metrics updated
- WorkflowRun node with status and timing

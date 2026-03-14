---
description: Research and analyze keywords for SEO targeting
argument-hint: <topic or seed keyword> [domain for gap analysis]
allowed-tools: Read, WebSearch
---

Perform comprehensive keyword research for $ARGUMENTS using the keyword-intelligence skill.

## Process

1. Read the keyword-intelligence skill at `${CLAUDE_PLUGIN_ROOT}/skills/keyword-intelligence/SKILL.md` and follow its workflow.

2. **Expand from seeds** using DataForSEO:
   - Keywords Data API for suggestions, related keywords, and Google Ads metrics
   - SERP API for People Also Ask questions
   - Labs API for proprietary keyword suggestions with clickstream data

3. **Generate keyword variations:**
   - Question keywords (who, what, how, why)
   - Comparison keywords (vs, alternative, compare)
   - Modifier keywords (best, top, free, review, guide)
   - Long-tail variations
   - Commercial intent keywords (buy, pricing, demo)

4. **Gather metrics** for each keyword:
   - Monthly search volume and seasonal trends
   - Keyword difficulty (0-100)
   - CPC and competition level
   - SERP features present (featured snippets, PAA, AI Overview)
   - Click-through rate estimates

5. **Classify intent** for every keyword:
   - Informational, navigational, commercial investigation, or transactional

6. If a domain was provided, **run gap analysis:**
   - Identify 3-5 competitors using Labs API
   - Find keywords competitors rank for that target does not
   - Find page-2 opportunities (positions 11-20)

7. **Cluster and prioritize** keywords:
   - Group into thematic clusters
   - Score by composite of volume, difficulty, intent, and business value
   - Map to content recommendations (title, format, word count)

8. **Deliver report** with keyword table, cluster map, gap analysis, quick wins, and content calendar suggestions.

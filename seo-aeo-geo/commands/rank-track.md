---
description: Track keyword rankings and visibility trends over time
argument-hint: <domain> [keywords comma-separated]
allowed-tools: Read, WebSearch
---

Track keyword rankings and visibility for $ARGUMENTS using the serp-intelligence skill.

## Process

1. Read the serp-intelligence skill at `${CLAUDE_PLUGIN_ROOT}/skills/serp-intelligence/SKILL.md`.

2. **Pull historical ranking data** via DataForSEO Labs API:
   - `google_historical_rank_overview` for domain visibility over 12 months
   - Position distribution across top 3, top 10, top 20, top 100
   - Traffic trend estimates
   - Identify traffic peaks, drops, and correlations with algorithm updates

3. **Current position check** for specified keywords:
   - Current ranking position for each keyword
   - SERP features owned (featured snippet, PAA, etc.)
   - AI Overview presence and citation status
   - Ranking URL for each keyword

4. **Track changes:**
   - Position changes vs previous period (week/month)
   - New keywords entering top 100
   - Keywords lost from top 100
   - SERP feature gains and losses

5. **Competitive context:**
   - Compare visibility trends against top competitors
   - Who is gaining/losing ground on shared keywords

6. **Generate ranking report** with:
   - Visibility score and trend chart
   - Keyword ranking table (position, change, URL, SERP features)
   - New rankings gained and rankings lost
   - Competitive visibility comparison
   - Alerts for significant changes
   - Recommendations for improvement opportunities

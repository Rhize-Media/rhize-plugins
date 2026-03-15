---
description: Analyze a domain's backlink profile and find opportunities
argument-hint: <domain> [competitor domain]
allowed-tools: Read, Bash(curl:*), WebFetch, WebSearch
---

Analyze the backlink profile for $ARGUMENTS using the backlink-intelligence skill.

## Process

1. Read the backlink-intelligence skill at `${CLAUDE_PLUGIN_ROOT}/skills/backlink-intelligence/SKILL.md`.

2. **Pull backlink data** via DataForSEO Backlinks API:
   - Total backlinks and referring domains
   - Authority distribution (DataForSEO 0-1000 scale)
   - Dofollow vs nofollow ratio
   - Anchor text distribution
   - Top referring domains
   - New and lost backlinks (30/60/90 day trends)

3. **Assess link quality:**
   - Identify high-authority editorial links
   - Flag potential toxic or spammy links
   - Check anchor text diversity (healthy: 30-40% branded, 15-25% keyword)

4. If a competitor domain was provided:
   - Run link gap analysis
   - Find domains linking to competitor but not target
   - Prioritize outreach targets by authority

5. **Find broken link opportunities:**
   - Pages with backlinks returning 404
   - Lost links that could be reclaimed

6. **Generate report** with:
   - Profile summary and health grade
   - Quality distribution analysis
   - Competitor gap opportunities
   - Broken link issues
   - Link-building action plan

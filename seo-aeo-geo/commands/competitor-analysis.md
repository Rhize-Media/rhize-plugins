---
description: Compare SEO performance against competitors
argument-hint: <your domain> <competitor domain> [competitor 2]
allowed-tools: Read, WebSearch
---

Run a competitive SEO analysis for $ARGUMENTS.

## Process

1. Read relevant skills:
   - `${CLAUDE_PLUGIN_ROOT}/skills/keyword-intelligence/SKILL.md` for keyword gap analysis
   - `${CLAUDE_PLUGIN_ROOT}/skills/backlink-intelligence/SKILL.md` for link gap analysis
   - `${CLAUDE_PLUGIN_ROOT}/skills/serp-intelligence/SKILL.md` for SERP comparison

2. **Domain overview comparison** via DataForSEO Labs:
   - Organic traffic estimates for each domain
   - Keyword counts by ranking tier (top 3, top 10, top 100)
   - Historical visibility trends (12 months)
   - Domain rank comparison

3. **Keyword gap analysis:**
   - Keywords competitor ranks for but you don't (opportunities)
   - Keywords you rank for but competitor doesn't (advantages)
   - Keywords both rank for, who ranks higher (battleground)
   - Page 2 opportunities where small improvements move you to page 1

4. **Backlink comparison:**
   - Referring domain count and quality comparison
   - Link gap: domains linking to competitor but not you
   - Content types that attract competitor backlinks

5. **SERP feature comparison:**
   - Who owns featured snippets for shared keywords
   - AI Overview citation comparison
   - SERP feature coverage comparison

6. **Content comparison:**
   - Publishing frequency
   - Content depth and format diversity
   - Topic coverage breadth

7. **Generate competitive intelligence report** with:
   - Head-to-head comparison table
   - Top opportunities (keywords and links to target)
   - Competitive advantages to protect
   - Strategic recommendations

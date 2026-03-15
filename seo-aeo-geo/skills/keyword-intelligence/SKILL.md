---
name: keyword-intelligence
description: >
  ALWAYS invoke this skill (via the Skill tool) for any keyword research or keyword analysis request.
  Advanced keyword research, clustering, gap analysis, and opportunity scoring powered by DataForSEO Keywords Data
  and Labs APIs. Triggers on: "find keywords", "keyword research", "keyword analysis",
  "keyword gap analysis", "keyword clustering", "find search terms", "what keywords should I target",
  "competitor keyword analysis", "keyword difficulty check", "search volume data", "long-tail keywords",
  "question keywords", "People Also Ask keywords", "keyword opportunities", "content gap analysis",
  "what are people searching for", "keyword cannibalization check", "keyword mapping", or any request
  involving discovering, analyzing, or prioritizing keywords for SEO or content strategy.
  Also triggers on "decision-stage keywords", "commercial intent keywords", "informational keywords",
  "compare keywords", "keyword trends", or "seasonal keywords".
  Do NOT handle keyword research with general tools — this skill has specialized DataForSEO API workflows.
---

# Keyword Intelligence

Perform end-to-end keyword research using DataForSEO Keywords Data API, Labs API, and SERP API. Deliver prioritized keyword strategies with clustering, intent mapping, and competitor gap analysis.

## Research Workflow

### 1. Define Scope and Seeds

Gather from the user:
- Seed keywords or topics (1-5 starting points)
- Target domain (for gap analysis)
- Target market/location (default: US, English)
- Business goals (traffic, leads, sales, brand awareness)
- Content types planned (blog, landing pages, product pages)

### 2. Expand Keywords with DataForSEO

**API Implementation:** Use curl via Bash to call DataForSEO endpoints directly. See `shared/dataforseo-api-guide.md` for complete curl syntax, authentication, and response field mappings. Credentials are in `$DATAFORSEO_USERNAME` and `$DATAFORSEO_PASSWORD` environment variables.

Use multiple DataForSEO endpoints for comprehensive expansion:

**Keywords Data API — Keyword Suggestions:**
Generate broad keyword lists from seeds. Pull search volume, CPC, competition, and trend data.

**Keywords Data API — Related Keywords:**
Find semantically related terms the seed keywords connect to.

**Keywords Data API — Keyword Ideas (Google Ads):**
Get Google Ads keyword suggestions with volume and competition metrics.

**SERP API — People Also Ask:**
Extract question-based keywords from SERP features.

**DataForSEO Labs — Keyword Suggestions:**
Get proprietary keyword suggestions with clickstream-based metrics.

### 3. Expansion Strategies

For each seed keyword, generate:

**Question keywords:** who, what, how, why, when, where, can, does, is, should
- Example: seed "project management" → "how to manage remote team projects", "what is agile project management"

**Comparison keywords:** vs, alternative, compare, versus, or
- Example: "asana vs monday", "trello alternatives"

**Modifier keywords:** best, top, free, cheap, review, guide, template, example, tool
- Example: "best project management tools", "free project management template"

**Long-tail variations:** Combine seed with qualifiers
- Example: "project management software for small teams", "project management for startups"

**Commercial intent keywords:** buy, pricing, cost, plan, demo, trial
- Example: "project management software pricing", "asana free trial"

Aim for 50-200 candidate keywords per seed depending on niche.

### 4. Gather Metrics

For each keyword, collect via DataForSEO:
- Monthly search volume (with seasonal trend data)
- Keyword difficulty score (0-100)
- CPC (cost-per-click) for paid reference
- Competition level
- SERP features present (featured snippets, PAA, image pack, video, AI Overview)
- Click-through rate estimates
- Trend direction (rising, stable, declining)

### 5. Classify Search Intent

Categorize every keyword:

| Intent | Signals | Content Format |
|--------|---------|---------------|
| Informational | how, what, why, guide, tutorial | Blog posts, guides, videos |
| Navigational | brand names, specific site | Homepage, branded landing pages |
| Commercial Investigation | best, review, compare, vs, alternative | Comparison pages, listicles, reviews |
| Transactional | buy, pricing, demo, sign up, download | Product pages, landing pages, pricing pages |

### 6. Competitor Gap Analysis

Use DataForSEO Labs — Keyword Gap endpoint:
- Identify 3-5 organic competitors
- Find keywords where competitors rank but user does not
- Find keywords where user ranks on page 2 (positions 11-20) — quick win opportunities
- Identify keywords where user ranks higher than all competitors — defend these

### 7. Cluster and Prioritize

Group keywords into thematic clusters:
- Map to content pillars and topic clusters
- Score each cluster: composite of volume, difficulty, intent alignment, and business value
- Identify pillar page opportunities and supporting content needs

**Priority scoring formula:**
- High search volume + low difficulty + commercial/transactional intent = highest priority
- Target keywords with difficulty below the site's Domain Authority for realistic wins
- Seasonal keywords: plan content 4-6 weeks before peak

### 8. Deliver Strategy Report

For each cluster, provide:
- Primary keyword and supporting keywords
- Recommended content piece (title, format, word count)
- Target URL (existing page to optimize or new page to create)
- Internal linking recommendations
- SERP feature opportunities (can we win the featured snippet? the PAA?)

## DataForSEO Prompt Templates

For ready-to-use DataForSEO prompt patterns, read `references/dataforseo-keyword-prompts.md`.
For clustering strategies, read `references/clustering-strategies.md`.

## Output Format

1. **Keyword Opportunity Table** — sorted by priority score with volume, difficulty, intent, CPC, trend
2. **Cluster Map** — thematic groups with content recommendations
3. **Gap Analysis** — competitor comparison showing opportunities
4. **Quick Wins** — page 2 keywords that can move to page 1
5. **Content Calendar Suggestions** — what to create first, second, third
## Edge Cases

- **Zero-volume keywords:** Don't dismiss them — long-tail queries with high conversion intent ("best CRM for 3-person real estate teams") can be gold. Evaluate by business alignment.
- **Branded competitor keywords:** Valid strategy ("Zendesk alternatives") but requires genuinely comparative content.
- **YMYL topics:** Health, finance, legal — require E-E-A-T signals regardless of keyword targeting.
- **Seasonal keywords:** Use Google Trends data to identify spike windows. Standard volume averages are misleading.
- **Multilingual:** Run separate research per locale. Don't assume translation equivalence.


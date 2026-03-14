# DataForSEO Keyword Research Prompt Templates

Ready-to-use prompt patterns for keyword research with DataForSEO APIs.

## Decision-Stage Keywords
"What are alternative or comparison ('vs', 'alternative', 'best', 'compare') search queries people use for [product/brand]? Return 20 ideas with high search volume."
- **API:** Keywords Data API
- **Use case:** Find commercial-intent keywords for comparison and alternative pages

## Keyword Clustering
"Provide a 20-term keyword cluster around [seed keyword]. Group them by intent (informational, commercial, transactional) and list keyword difficulty and SERP features."
- **API:** Keywords Data API + DataForSEO Labs API
- **Use case:** Build topic clusters for content planning

## Question-Based Keywords
"Show me 20 question-based keywords (what, why, how) for [topic] with search volume ≥ 300. Include search intent and suggest article headlines that match the query tone."
- **API:** Keywords Data API
- **Use case:** Find informational content opportunities and PAA targets

## Commercial Keywords for Campaigns
"Find 20 commercial and transactional keywords related to [product/service]. Filter by CPC ≥ $2 and search volume ≥ 1,000. Suggest landing page angles based on intent."
- **API:** Keywords Data API (Google Ads metrics)
- **Use case:** Identify high-value keywords for both SEO and PPC

## Informational Keywords
"Give me 20 informational keywords around [topic] with low competition and moderate search volume (≥500). Group them by intent and suggest blog topics for each."
- **API:** Keywords Data API
- **Use case:** Find low-difficulty TOFU content opportunities

## Competitor Keyword Gap
"Using DataForSEO Labs keyword_intersection, compare keywords ranking for [domain1] vs [domain2] vs [domain3]. Identify keywords where [domain1] does NOT rank but competitors do. Sort by search volume."
- **API:** DataForSEO Labs API
- **Use case:** Find content opportunities by analyzing competitor portfolios

## Ranked Keyword Gap Analysis
"Using DataForSEO Labs, identify keywords where [domain] ranks between positions 11-20. Sort by search volume. These are page-2 keywords that could move to page 1 with optimization."
- **API:** DataForSEO Labs API
- **Use case:** Find quick-win optimization opportunities

## Trending Keywords
"Using DataForSEO Trends data, identify keywords in the [topic] space that have seen >50% search volume growth in the past 6 months. Include current volume and growth rate."
- **API:** Keywords Data API (Trends)
- **Use case:** Identify emerging keyword opportunities before they become competitive

## Long-Tail Expansion
"For the seed keyword [keyword], generate 30 long-tail variations by combining with modifiers: best, top, free, cheap, review, guide, template, example, tool, for beginners, for small business, for enterprise, 2025, how to, what is, vs. Return with estimated search volume."
- **API:** Keywords Data API
- **Use case:** Comprehensive long-tail keyword expansion

## Local Keyword Research
"Find 15 location-based keywords for [service] in [city/region]. Include '[service] near me' variations, '[service] in [city]', and 'best [service] [city]'. Include search volume and local competition data."
- **API:** Keywords Data API
- **Use case:** Local SEO keyword targeting

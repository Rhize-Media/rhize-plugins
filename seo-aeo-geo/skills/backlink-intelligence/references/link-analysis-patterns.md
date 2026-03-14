# DataForSEO Backlink Analysis Prompt Templates

Ready-to-use prompt patterns for backlink analysis with DataForSEO Backlinks API.

## Top-Authority Backlinks
"Identify the top 10 highest-authority backlinks to [domain], grouped by referring domain. Include backlink type, anchor text, and target page."
- **API:** Backlinks API
- **Use case:** Understand the strongest links in the profile

## Blog Content Attracting Links
"Show which blog posts on [domain] attract the most backlinks. List the top 5 by backlink count, include title, referring domains, and anchor types."
- **API:** Backlinks API
- **Use case:** Identify link-worthy content patterns to replicate

## Competitor Link Gap
"Which websites link to my competitors but not to [mydomain]? Use [competitor1] and [competitor2]. Return 15 domains I should target for outreach, sorted by authority."
- **API:** Backlinks API
- **Use case:** Build outreach target lists from competitor profiles

## Broken Pages Wasting Link Equity
"Find internal pages on [domain] that have over 30 backlinks but return 404 or are redirected. Return URL, status code, backlink count, and top referring domains."
- **API:** Backlinks API + OnPage API
- **Use case:** Reclaim link equity from broken or redirected pages

## Backlink Gap Benchmarking
"Compare backlinks between [mydomain] and [competitor]. Show 10 domains linking only to the competitor. Include domain authority and link count."
- **API:** Backlinks API
- **Use case:** Benchmark link profile against competition

## Anchor Text Distribution
"Analyze the anchor text distribution for [domain]. Group by type: branded, naked URL, generic, keyword-rich, long-tail. Flag any over-optimization (single keyword anchor > 10% of total)."
- **API:** Backlinks API
- **Use case:** Detect potential anchor text manipulation risks

## New and Lost Links Monitoring
"Show new backlinks gained and backlinks lost for [domain] in the last 30 days. Sort by referring domain authority. For lost links, include the reason (page removed, nofollow added, etc.)."
- **API:** Backlinks API
- **Use case:** Monitor link acquisition and detect link churn

## Unlinked Brand Mentions
"Find web pages that mention [brand name] but do not link to [domain]. Return the page URL, mention context, and domain authority."
- **API:** Content Analysis API
- **Use case:** Find easy link reclamation opportunities

## Toxic Link Detection
"Identify potentially toxic backlinks to [domain]. Flag links from domains with: spam score > 50%, adult/gambling/pharma content, exact-match anchor text patterns, PBN-like characteristics. Group by risk level."
- **API:** Backlinks API
- **Use case:** Prepare disavow file and protect against penalties

## DataForSEO Authority Scale

DataForSEO uses a 0-1000 scale for domain authority (not the 0-100 scale used by Moz/Ahrefs):

| DataForSEO Rank | Rough Equivalent | Quality Level |
|-----------------|------------------|---------------|
| 0-100 | DA 0-10 | Very low authority |
| 100-300 | DA 10-30 | Low-medium authority |
| 300-500 | DA 30-50 | Medium authority |
| 500-700 | DA 50-70 | High authority |
| 700-900 | DA 70-90 | Very high authority |
| 900-1000 | DA 90-100 | Top-tier domains |

Spam Score uses a 0-100% scale where > 50% indicates high spam risk.

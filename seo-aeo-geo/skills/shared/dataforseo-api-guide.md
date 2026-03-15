# DataForSEO REST API Reference

Direct curl patterns for all DataForSEO endpoints used by SEO/AEO/GEO skills. Use `Bash` with curl to call these endpoints. Credentials are stored in environment variables.

## Authentication

All requests use HTTP Basic Auth:

```bash
AUTH=$(echo -n "$DATAFORSEO_USERNAME:$DATAFORSEO_PASSWORD" | base64)

curl -X POST "https://api.dataforseo.com/v3/{endpoint}" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{ ... }]'
```

**Important:** The request body is a JSON **array** of task objects (not a single object).

---

## OnPage API

Used by: **seo-site-audit**

### Instant Pages (single-page analysis)

```bash
curl -X POST "https://api.dataforseo.com/v3/on_page/instant_pages" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "url": "https://example.com/page",
    "enable_javascript": true,
    "enable_browser_rendering": true,
    "load_resources": true,
    "check_spell": true,
    "validate_micromarkup": true
  }]'
```

**Key response fields** (in `tasks[0].result[0].items[0]`):
- `onpage_score` — overall SEO score (0-100)
- `meta.title`, `meta.description`, `meta.canonical` — meta tags
- `meta.htags` — heading hierarchy (H1-H6)
- `meta.internal_links_count`, `meta.external_links_count`
- `page_timing.largest_contentful_paint` — LCP in ms
- `page_timing.cumulative_layout_shift` — CLS score
- `checks` — object with boolean flags: `no_h1_tag`, `no_title`, `no_description`, `is_https`, `has_micromarkup`, etc.

### Task Post (full site crawl)

```bash
curl -X POST "https://api.dataforseo.com/v3/on_page/task_post" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "target": "example.com",
    "max_crawl_pages": 500,
    "enable_javascript": true,
    "enable_browser_rendering": true,
    "load_resources": true,
    "enable_content_parsing": true,
    "check_spell": true,
    "validate_micromarkup": true
  }]'
```

Returns a `task_id`. Poll results with:
```bash
curl -X GET "https://api.dataforseo.com/v3/on_page/pages/$TASK_ID" \
  -H "Authorization: Basic $AUTH"
```

---

## Backlinks API

Used by: **backlink-intelligence**

### Summary

```bash
curl -X POST "https://api.dataforseo.com/v3/backlinks/summary/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "target": "example.com",
    "include_subdomains": true,
    "internal_list_limit": 10
  }]'
```

**Key response fields** (in `tasks[0].result[0]`):
- `rank` — domain rank (0-1000)
- `backlinks` — total backlink count
- `referring_domains` — unique referring domains
- `referring_main_domains` — unique referring root domains
- `backlinks_spam_score` — spam score
- `broken_backlinks` — count of broken links
- `referring_links_tld` — TLD distribution
- `referring_links_types` — link type distribution (text, image, redirect)
- `referring_links_attributes` — dofollow/nofollow distribution

### Backlinks List

```bash
curl -X POST "https://api.dataforseo.com/v3/backlinks/backlinks/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "target": "example.com",
    "mode": "as_is",
    "limit": 100,
    "order_by": ["rank,desc"],
    "filters": ["dofollow", "=", true]
  }]'
```

**Key response fields** (in `tasks[0].result[0].items[]`):
- `domain_from` — referring domain
- `url_from` — referring page URL
- `url_to` — target page URL
- `anchor` — anchor text
- `rank` — backlink rank
- `dofollow` — boolean
- `first_seen`, `last_seen` — discovery dates

### Referring Domains

```bash
curl -X POST "https://api.dataforseo.com/v3/backlinks/referring_domains/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "target": "example.com",
    "limit": 100,
    "order_by": ["rank,desc"]
  }]'
```

**Key response fields** (in `tasks[0].result[0].items[]`):
- `domain` — referring domain name
- `rank` — domain rank (0-1000)
- `backlinks` — backlink count from this domain
- `backlinks_spam_score` — spam score
- `first_seen`, `lost_date`

### Domain Intersection (link gap analysis)

```bash
curl -X POST "https://api.dataforseo.com/v3/backlinks/domain_intersection/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "targets": {
      "1": "yourdomain.com",
      "2": "competitor.com"
    },
    "limit": 100,
    "order_by": ["1.backlinks,desc"]
  }]'
```

Returns domains that link to one target but not the other — use for link gap analysis.

---

## Keywords Data API

Used by: **keyword-intelligence**

### Search Volume (Google Ads)

```bash
curl -X POST "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "keywords": ["seo tools", "keyword research", "backlink checker"],
    "location_code": 2840,
    "language_code": "en"
  }]'
```

**Key response fields** (in `tasks[0].result[]`):
- `keyword` — the keyword
- `search_volume` — monthly average searches
- `competition` — "HIGH", "MEDIUM", or "LOW"
- `competition_index` — 0-100 scale
- `low_top_of_page_bid`, `high_top_of_page_bid` — CPC estimates
- `monthly_searches[]` — array with `{year, month, search_volume}` trend data

**Limits:** Up to 1000 keywords per request, 80 chars per keyword.

### Keywords for Site

```bash
curl -X POST "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_site/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "target": "example.com",
    "location_code": 2840,
    "language_code": "en"
  }]'
```

Returns keyword ideas based on a domain's content.

---

## DataForSEO Labs API

Used by: **keyword-intelligence**, **serp-intelligence**

### Ranked Keywords

```bash
curl -X POST "https://api.dataforseo.com/v3/dataforseo_labs/google/ranked_keywords/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "target": "example.com",
    "location_code": 2840,
    "language_code": "en",
    "limit": 100
  }]'
```

**Key response fields:**
- `metrics.organic.pos_1` through `pos_91_100` — ranking distribution
- `metrics.organic.etv` — estimated traffic volume
- `metrics.organic.count` — total ranked keywords
- `items[].keyword_data.keyword` — keyword text
- `items[].ranked_serp_element.serp_item.rank_group` — position

### Keyword Suggestions

```bash
curl -X POST "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_suggestions/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "keyword": "project management",
    "location_code": 2840,
    "language_code": "en",
    "include_serp_info": true,
    "limit": 100
  }]'
```

**Key response fields** (in `tasks[0].result[0].items[]`):
- `keyword_data.keyword` — suggested keyword
- `keyword_data.keyword_info.search_volume` — monthly searches
- `keyword_data.keyword_info.competition_level` — competition
- `keyword_data.keyword_info.cpc` — cost per click
- `keyword_properties.keyword_difficulty` — difficulty score

### Domain Rank Overview

```bash
curl -X POST "https://api.dataforseo.com/v3/dataforseo_labs/google/domain_rank_overview/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "target": "example.com",
    "location_code": 2840,
    "language_code": "en"
  }]'
```

**Key response fields** (in `tasks[0].result[0].items[]`):
- `organic.etv` — estimated monthly organic traffic
- `organic.count` — total organic keywords
- `organic.estimated_paid_traffic_cost` — cost to replicate via ads
- `organic.pos_1` through `pos_10` — top-10 keyword counts
- `organic.is_new`, `is_up`, `is_down`, `is_lost` — rank changes

---

## SERP API

Used by: **serp-intelligence**, **aeo-geo-optimization**

### Google Organic Live Advanced

```bash
curl -X POST "https://api.dataforseo.com/v3/serp/google/organic/live/advanced" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "keyword": "best seo tools",
    "location_code": 2840,
    "language_code": "en",
    "device": "desktop",
    "depth": 100
  }]'
```

**Key response fields** (in `tasks[0].result[0]`):
- `item_types` — array of SERP feature types present (e.g., "organic", "featured_snippet", "people_also_ask", "ai_overview")
- `items[]` — individual SERP results:
  - `type` — result type
  - `rank_group` — position
  - `domain` — domain name
  - `url` — page URL
  - `title`, `description` — snippet text
  - `items` (for PAA) — nested questions/answers

**Rate limit:** 2000 calls/minute, 1 task per request.

---

## AI Optimization API

Used by: **aeo-geo-optimization**

### LLM Mentions

```bash
curl -X POST "https://api.dataforseo.com/v3/content_analysis/search/live" \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '[{
    "keyword": "your brand name",
    "search_mode": "as_is",
    "limit": 50
  }]'
```

For tracking brand mentions across LLM responses, use the AI Optimization endpoints when available. The Content Analysis API serves as a fallback for brand mention discovery.

---

## Common Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `location_code` | Geographic targeting (2840 = United States) | varies |
| `language_code` | Language code (e.g., "en") | varies |
| `limit` | Max results per request | 100 |
| `offset` | Pagination offset | 0 |
| `filters` | Array-based filtering | none |
| `order_by` | Sort order (e.g., `["rank,desc"]`) | varies |

## Error Handling

- `status_code: 20000` = success
- `status_code: 40000` = bad request (check parameters)
- `status_code: 40100` = authentication failed
- `status_code: 40200` = insufficient credits
- Always check `tasks[0].status_code` in addition to top-level status

## Rate Limits

- 2000 requests per minute (most endpoints)
- Up to 30 simultaneous requests
- OnPage instant_pages: max 20 tasks per request

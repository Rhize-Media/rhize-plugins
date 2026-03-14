# DataForSEO Audit Prompt Templates

Ready-to-use prompt patterns for SEO auditing with DataForSEO APIs.

## Technical SEO Audit Prompts

### Crawlability Issues
"Audit page [URL] for crawlability issues, including robots.txt restrictions, noindex tags, and broken internal links. Highlight what's preventing Google from indexing or ranking this page."
- **API:** OnPage API
- **Parameters:** URL, crawlability checks enabled

### Meta Tag Validation
"Review page [URL] to check for missing or duplicate meta title and meta description tags, use validate_micromarkup, enable_javascript, and enable_browser_rendering. Report if tags are too long, too short, or missing, and how to fix them."
- **API:** OnPage API
- **Parameters:** URL, micromarkup validation, JavaScript rendering

### Speed and Mobile Analysis
"Analyze page [URL] for speed and mobile usability. Use load_resources, enable_javascript, and enable_browser_rendering. Identify what's slowing it down or making it hard to use on mobile, include measurements, and give practical steps to improve."
- **API:** OnPage API
- **Parameters:** URL, load_resources enabled, mobile rendering

### Internal Link Structure
"Check how well [URL] is connected internally. Use load_resources, enable_javascript, and enable_browser_rendering. Report if it's buried too deep in site structure or lacks internal links that could help search engines find and rank it."
- **API:** OnPage API
- **Parameters:** URL, internal linking analysis

### Keyword Optimization Assessment
"Evaluate [URL] for how well it's optimized for the keyword [keyword]. Analyze title, meta description, headings (H1-H6), internal links, and keyword usage. Extract and parse all content elements. Check for keyword placement and semantic relevance. Identify missing keyword placements and content gaps."
- **API:** OnPage API
- **Parameters:** URL, target keyword, content element extraction

## Full Site Crawl Configuration

When initiating a full site crawl via OnPage API, use these settings:
```json
{
  "target": "example.com",
  "max_crawl_pages": 500,
  "enable_javascript": true,
  "enable_browser_rendering": true,
  "load_resources": true,
  "enable_content_parsing": true,
  "check_spell": true,
  "validate_micromarkup": true,
  "calculate_keyword_density": true,
  "custom_user_agent": "Mozilla/5.0 (compatible; SEOAuditBot/1.0)"
}
```

## Page-Level Analysis Extraction

After crawl, extract for each page:
- `meta.title` — title tag text and length
- `meta.description` — meta description text and length
- `meta.canonical` — canonical URL
- `meta.htags` — heading hierarchy (H1-H6)
- `page_timing` — load time metrics
- `checks` — automated SEO checks (missing alt, broken links, etc.)
- `resource_errors` — failed resource loads
- `links.internal` — internal link inventory
- `links.external` — external link inventory
- `images` — image inventory with alt text status
- `microdata` — structured data validation results

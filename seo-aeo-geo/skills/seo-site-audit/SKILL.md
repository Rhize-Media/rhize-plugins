---
name: seo-site-audit
description: >
  ALWAYS invoke this skill (via the Skill tool) for any SEO audit or site health check request.
  Comprehensive SEO site auditing powered by DataForSEO OnPage and SERP APIs. Triggers on:
  "audit a website for SEO", "run an SEO audit", "check SEO health", "find SEO issues", "crawl my site for problems",
  "what's wrong with my SEO", "technical SEO check", "on-page SEO analysis", "check my meta tags",
  "find broken links", "check my Core Web Vitals", "page speed analysis", "crawlability check",
  "indexation issues", or any request involving diagnosing or improving a website's search engine optimization.
  Also triggers when the user shares a URL and asks about its SEO performance or ranking potential.
  Do NOT handle SEO audit requests with general tools — this skill has specialized DataForSEO API workflows.
---

# SEO Site Audit

Perform comprehensive SEO audits combining DataForSEO OnPage API crawl data with expert analysis. Produce prioritized, actionable reports that engineering and content teams can execute immediately.

## Audit Workflow

### 1. Scope the Audit

Determine what the user needs:
- **Full site audit** — crawl the entire domain, analyze all pages
- **Page-level audit** — deep-dive on a single URL
- **Section audit** — focus on a subdirectory (e.g., `/blog/`, `/products/`)

Gather inputs:
- Target URL or domain
- Target keywords (if known)
- Competitors to benchmark against (optional)
- Priority areas (speed, content, technical, all)

### 2. Crawl with DataForSEO OnPage API

**API Implementation:** Use curl via Bash to call DataForSEO endpoints directly. See `shared/dataforseo-api-guide.md` for complete curl syntax, authentication, and response field mappings. Credentials are in `$DATAFORSEO_USERNAME` and `$DATAFORSEO_PASSWORD` environment variables.

Use the DataForSEO OnPage API to crawl the target. Key parameters:
- `enable_javascript: true` — capture JS-rendered content
- `enable_browser_rendering: true` — for SPA/React/Next.js sites
- `load_resources: true` — analyze all page resources
- `enable_content_parsing: true` — extract content elements
- `check_spell: true` — catch spelling errors
- `validate_micromarkup: true` — validate structured data

Extract from crawl results:
- HTTP status codes and redirect chains
- Title tags, meta descriptions, canonical URLs
- H1-H6 heading hierarchy
- Images with missing alt text
- Internal/external link inventory
- Page load metrics (time to interactive, resource sizes)
- Structured data validation results
- Mobile-friendliness signals

### 3. Analyze On-Page SEO Elements

For each key page, evaluate:

**Title Tags:**
- Length: 50-60 characters optimal
- Primary keyword placement (front-loaded is better)
- Uniqueness across the site (flag duplicates)
- Brand inclusion pattern

**Meta Descriptions:**
- Length: 150-160 characters optimal
- Compelling call-to-action language
- Keyword inclusion (natural, not stuffed)
- Uniqueness (flag duplicates and missing)

**Heading Structure:**
- Exactly one H1 per page containing the primary keyword
- H2-H4 forming logical content hierarchy
- Headings that match search intent and contain secondary keywords

**Content Quality:**
- Word count relative to top-ranking competitors
- Keyword density (target 1-2%, flag stuffing above 3%)
- Readability score
- Content freshness (date published/updated)

**Internal Linking:**
- Orphan pages (no internal links pointing to them)
- Link depth (pages more than 3 clicks from homepage)
- Anchor text quality (descriptive vs generic "click here")
- Broken internal links

### 4. Evaluate Technical SEO

**Core Web Vitals:**
- LCP (Largest Contentful Paint): target < 2.5s
- INP (Interaction to Next Paint): target < 200ms
- CLS (Cumulative Layout Shift): target < 0.1

**Crawlability:**
- robots.txt configuration (blocking important content?)
- XML sitemap presence, accuracy, and freshness
- Canonical tag implementation
- noindex/nofollow audit
- Redirect chains (flag chains > 2 hops)

**Indexation:**
- Pages that should be indexed but aren't
- Duplicate content risks
- Thin content pages (< 300 words for informational)
- Index bloat from parameter URLs or pagination

**Security & Infrastructure:**
- HTTPS implementation
- Mixed content issues
- HSTS headers
- Server response codes

### 5. Audit Structured Data

Check for and validate JSON-LD markup:
- Article/BlogPosting for content pages
- Product for e-commerce
- FAQPage for FAQ sections
- BreadcrumbList for navigation
- Organization/LocalBusiness for the entity
- HowTo for tutorial content

Validate against Google Rich Results requirements. Flag mismatches between schema and visible content.

### 6. Generate Prioritized Report

Organize findings by impact level:

| Priority | Criteria | Examples |
|----------|----------|---------|
| Critical | Blocking indexation or causing penalties | noindex on important pages, canonical loops, site not crawlable |
| High | Significant ranking impact | missing H1s, duplicate titles, broken links with backlinks, slow LCP |
| Medium | Moderate SEO benefit | missing meta descriptions, suboptimal heading hierarchy, images without alt text |
| Low | Minor optimizations | title length tweaks, anchor text improvements, minor CLS issues |

Include for each finding:
- What the issue is
- Why it matters (ranking impact)
- How to fix it (specific code/content changes)
- Estimated effort (quick win, moderate, substantial)

## DataForSEO API Reference

For detailed DataForSEO prompt patterns, read `references/dataforseo-audit-prompts.md`.
For the complete technical SEO checklist, read `references/technical-seo-checklist.md`.
For on-page best practices, read `references/on-page-seo-guide.md`.

## Output Format

Present the audit as:

1. **Executive Summary** — 3-5 sentences on overall SEO health, top 3 priorities, and overall score (0-100)
2. **Critical Issues** — table with issue, affected pages, fix, and effort
3. **On-Page Analysis** — page-by-page findings for key pages
4. **Technical Health** — checklist with pass/fail/warning status
5. **Structured Data** — current state and recommendations
6. **Content Opportunities** — gaps and optimization suggestions
7. **Action Plan** — quick wins (this week) and strategic investments (this quarter)

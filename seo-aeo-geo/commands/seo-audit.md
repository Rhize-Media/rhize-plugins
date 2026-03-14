---
description: Run a comprehensive SEO audit on a website or page
argument-hint: <url> [keyword]
allowed-tools: Read, Grep, Glob, Bash(curl:*), WebFetch, WebSearch
---

Run a comprehensive SEO audit on $ARGUMENTS using the seo-site-audit skill.

## Process

1. **Gather context:** Read the seo-site-audit skill at `${CLAUDE_PLUGIN_ROOT}/skills/seo-site-audit/SKILL.md` and follow its workflow.

2. **Use DataForSEO APIs** to crawl and analyze:
   - OnPage API for crawl data, meta tags, headings, links, resources, and structured data validation
   - SERP API to check current rankings for target keywords
   - Labs API for domain visibility and keyword distribution

3. **Analyze on-page elements:**
   - Title tags (length, keyword placement, uniqueness)
   - Meta descriptions (length, CTA, uniqueness)
   - Heading structure (H1 count, hierarchy, keyword usage)
   - Image alt text coverage
   - Internal linking health
   - Content depth and keyword density

4. **Evaluate technical health:**
   - Core Web Vitals (LCP, INP, CLS)
   - Mobile-friendliness
   - Crawlability (robots.txt, sitemaps, canonicals)
   - HTTPS and security
   - Redirect chains
   - Indexation issues

5. **Check structured data:**
   - Validate existing JSON-LD markup
   - Identify missing schema opportunities
   - Check for rich results eligibility

6. **Check AI visibility:**
   - Does the page appear in Google AI Overviews for target keywords?
   - Is content structured for AI extraction?
   - Are AI crawlers allowed in robots.txt?

7. **Generate prioritized report** with:
   - Executive summary and SEO health score (0-100)
   - Critical, high, medium, low issues table
   - Quick wins (this week) and strategic investments (this quarter)
   - Before/after code snippets for recommended changes

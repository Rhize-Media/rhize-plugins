---
description: Run a technical SEO audit (Core Web Vitals, crawlability, indexation)
argument-hint: <url or domain>
allowed-tools: Read, Grep, Glob, Bash(curl:*), WebFetch
---

Run a focused technical SEO audit on $ARGUMENTS.

## Process

1. Read the seo-site-audit skill at `${CLAUDE_PLUGIN_ROOT}/skills/seo-site-audit/SKILL.md` and focus on technical sections.

2. **Crawl with DataForSEO OnPage API:**
   - `enable_javascript: true`, `enable_browser_rendering: true`, `load_resources: true`
   - Extract HTTP status codes, redirect chains, page load metrics

3. **Core Web Vitals assessment:**
   - LCP (target < 2.5s) — identify LCP element and blockers
   - INP (target < 200ms) — check for heavy JS and interaction delays
   - CLS (target < 0.1) — find elements causing layout shifts

4. **Crawlability check:**
   - robots.txt review (blocking important content?)
   - XML sitemap presence, accuracy, and freshness
   - Canonical tag implementation (self-referencing? conflicts?)
   - noindex/nofollow audit
   - Redirect chain analysis (flag chains > 2 hops)

5. **Indexation analysis:**
   - Pages that should be indexed but have noindex
   - Duplicate content risks (similar titles, thin pages)
   - Index bloat from parameter URLs or pagination
   - Orphan pages not reachable from navigation

6. **Security & infrastructure:**
   - HTTPS implementation
   - Mixed content issues
   - Server response codes
   - HSTS headers

7. **Performance bottlenecks:**
   - Render-blocking resources (CSS, JS)
   - Uncompressed images
   - Unused CSS/JS
   - Font loading strategy

8. **Generate technical audit report** with:
   - Pass/fail/warning checklist
   - Performance metrics with targets
   - Prioritized fix list with code examples
   - Quick wins vs infrastructure changes

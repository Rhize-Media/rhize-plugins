# Technical SEO Checklist

Comprehensive technical SEO checklist for auditing websites.

## Core Web Vitals

| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| LCP (Largest Contentful Paint) | < 2.5s | 2.5s - 4.0s | > 4.0s |
| INP (Interaction to Next Paint) | < 200ms | 200ms - 500ms | > 500ms |
| CLS (Cumulative Layout Shift) | < 0.1 | 0.1 - 0.25 | > 0.25 |

### LCP Optimization
- Optimize hero images (WebP/AVIF, correct sizing, preload)
- Eliminate render-blocking CSS/JS
- Use `font-display: swap` for web fonts
- Implement server-side rendering for critical content
- Use CDN for static assets

### INP Optimization
- Minimize long tasks (break JS into smaller chunks)
- Use `requestIdleCallback` for non-critical work
- Defer third-party scripts
- Optimize event handlers

### CLS Optimization
- Set explicit `width` and `height` on images and videos
- Reserve space for dynamic content (ads, embeds)
- Use `font-display: optional` or `swap` with size-adjust
- Avoid inserting content above existing content

## Crawlability

- [ ] robots.txt exists and is accessible at `/robots.txt`
- [ ] robots.txt does not block important content
- [ ] XML sitemap exists at `/sitemap.xml`
- [ ] Sitemap is submitted to Google Search Console
- [ ] Sitemap excludes noindex pages
- [ ] Sitemap includes `lastmod` dates
- [ ] All important pages are within 3 clicks of homepage
- [ ] No redirect chains longer than 2 hops
- [ ] No redirect loops
- [ ] Server returns proper 404 for missing pages (not soft 404s)

## Canonical Tags

- [ ] Every page has a self-referencing canonical tag
- [ ] Canonical URLs use consistent protocol (HTTPS)
- [ ] Canonical URLs use consistent trailing slash pattern
- [ ] No conflicting canonical signals (canonical vs noindex)
- [ ] Paginated pages canonical to themselves (not page 1)

## Mobile-Friendliness

- [ ] Viewport meta tag is set: `<meta name="viewport" content="width=device-width, initial-scale=1">`
- [ ] Text is readable without zooming (minimum 16px body text)
- [ ] Tap targets are at least 48x48px with adequate spacing
- [ ] No horizontal scrolling on mobile
- [ ] Content fits within the viewport

## Security & Infrastructure

- [ ] HTTPS is enforced (HTTP redirects to HTTPS)
- [ ] No mixed content (HTTP resources on HTTPS pages)
- [ ] HSTS header is set
- [ ] SSL certificate is valid and not expiring soon

## Indexation

- [ ] Important pages return 200 status code
- [ ] No unintentional noindex tags on important pages
- [ ] Thin content pages (< 300 words informational) are identified
- [ ] Duplicate content is managed with canonicals
- [ ] Parameter URLs are handled (canonical or robots.txt)
- [ ] Pagination uses rel="next"/rel="prev" where applicable

## International SEO (if applicable)

- [ ] hreflang tags are implemented for all language versions
- [ ] Each language version has a unique title and description
- [ ] x-default hreflang points to the primary/fallback version
- [ ] hreflang is implemented consistently (HTML head, sitemap, or HTTP header)

## Structured Data

- [ ] Organization schema on homepage
- [ ] BreadcrumbList on all pages
- [ ] Article/BlogPosting on blog content
- [ ] Product on product pages
- [ ] FAQPage on FAQ sections
- [ ] LocalBusiness for local businesses
- [ ] All structured data validates in Google Rich Results Test
- [ ] Schema data matches visible page content

## AI Crawler Configuration

- [ ] Explicit policy for GPTBot in robots.txt
- [ ] Explicit policy for ClaudeBot in robots.txt
- [ ] Explicit policy for PerplexityBot in robots.txt
- [ ] Explicit policy for Google-Extended in robots.txt
- [ ] AI crawler policy aligns with business strategy

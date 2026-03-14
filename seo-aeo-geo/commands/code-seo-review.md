---
description: Review a Next.js/Sanity codebase for SEO implementation issues
argument-hint: [project path]
allowed-tools: Read, Grep, Glob, Edit, Write
---

Audit a Next.js + Sanity codebase for SEO implementation issues using the nextjs-sanity-seo skill.

## Process

1. Read the nextjs-sanity-seo skill at `${CLAUDE_PLUGIN_ROOT}/skills/nextjs-sanity-seo/SKILL.md`.

2. **Scan the codebase** for SEO-critical files:
   - `app/sitemap.ts` or `pages/sitemap.xml.ts` — does it exist? Is it correct?
   - `app/robots.ts` or `public/robots.txt` — does it exist? Are AI crawlers configured?
   - `app/layout.tsx` — is there a default metadata export?
   - `next.config.ts` — are redirects configured from CMS?

3. **Check metadata implementation:**
   - Grep for `generateMetadata` — does every page type have it?
   - Check for `stega: false` in metadata sanityFetch calls (critical for Sanity + Stega)
   - Verify title, description, OG tags, and canonical URLs are set
   - Check for hardcoded vs dynamic metadata

4. **Check structured data:**
   - Grep for `application/ld+json` — are JSON-LD scripts being rendered?
   - Check for Article, FAQ, Breadcrumb, Organization schema
   - Verify schema data matches page content (no mismatches)

5. **Check Sanity schemas:**
   - Look for SEO field types (title override, meta description, noIndex, canonical)
   - Check for author schema with E-E-A-T fields (credentials, sameAs)
   - Look for FAQ schema types
   - Check for redirect document type

6. **Check images:**
   - Grep for `<img` vs `next/image` — are all images using Next.js Image component?
   - Check for alt text patterns (hardcoded vs from CMS)
   - Look for `width`/`height` attributes (prevents CLS)

7. **Check performance patterns:**
   - Font loading (next/font with display: swap?)
   - Dynamic imports for heavy components
   - Image optimization (WebP/AVIF, LQIP placeholders)

8. **Check internal linking:**
   - Are there navigation components with proper `<Link>` elements?
   - Breadcrumb components with structured data?

9. **Generate codebase SEO report** with:
   - Pass/fail checklist for each SEO requirement
   - Code snippets showing current implementation vs recommended
   - Files that need to be created or modified
   - Priority-ordered fix list

10. **Offer to apply fixes** — if the user wants, directly edit files to implement missing SEO patterns.

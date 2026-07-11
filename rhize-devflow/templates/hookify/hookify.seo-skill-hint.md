---
name: seo-skill-hint
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: (app/(.*/)?(metadata|sitemap|robots|opengraph-image|twitter-image)\.(ts|tsx|js)$|/structured-data|/json-ld|/schema-markup|/seo/)
---

🔎 **SEO-critical file edit detected**

You're editing a file that affects search, AI-discovery (AEO/GEO), or social previews. Before finishing, validate against the Rhize SEO skill set:

- `/seo-aeo-geo:code-seo-review` — static review of metadata, structured data, sitemap/robots
- `/seo-aeo-geo:content-optimize` — on-page SEO + AEO/GEO scoring for the live URL
- `/seo-aeo-geo:nextjs-sanity-seo` — Next.js + Sanity metadata patterns
- `/seo-aeo-geo:technical-audit` — Core Web Vitals, crawlability (post-deploy)

**Quick checklist for this edit:**

- `metadata.ts` / `generateMetadata()`: title ≤ 60 chars, description 120–160 chars, canonical set, OG image declared
- `sitemap.ts`: dynamic routes included, `lastModified` plumbed from Sanity `_updatedAt`
- `robots.ts`: dev/preview environments return `noindex`; production allows crawling
- Structured data (`application/ld+json`): valid schema.org type, all required fields populated, no invented properties
- OG/Twitter images: 1200×630, correct MIME type, no PII

After the edit, consider running `/seo-aeo-geo:code-seo-review` on the changed files to catch regressions before they ship.

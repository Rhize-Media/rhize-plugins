# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-04-05T15:28:28.344Z
> Files: 63 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `.gitignore` — Git ignore rules (~146 tok)
- `.mcp.json` (~466 tok)
- `CLAUDE.md` — OpenWolf (~817 tok)
- `eslint.config.mjs` — ESLint flat configuration (~124 tok)
- `next.config.ts` — Declares nextConfig (~42 tok)
- `package.json` — Node.js package manifest (~172 tok)
- `postcss.config.mjs` — Declares config (~26 tok)
- `README.md` — Project documentation (~363 tok)
- `tsconfig.json` — TypeScript configuration (~192 tok)
- `vercel.json` (~53 tok)

## .claude-plugin/

- `plugin.json` (~165 tok)

## .claude/

- `settings.json` (~441 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## commands/

- `flywheel-discover.md` — Process (~337 tok)
- `flywheel-distribute.md` — Process (~370 tok)
- `flywheel-monitor.md` — Process (~556 tok)
- `flywheel-optimize.md` — Process (~409 tok)
- `flywheel-publish.md` — Process (~298 tok)
- `flywheel-research.md` — Process (~500 tok)
- `flywheel-status.md` — Process (~469 tok)

## cypher/

- `schema.cypher` — Content Flywheel — Neo4j Graph Schema (~870 tok)

## docs/plans/

- `2026-04-04-content-flywheel-production-ready.md` — Content Flywheel — Production-Ready Implementation Plan (~7404 tok)

## hooks/

- `flywheel-context.md` — Content Flywheel Context (~392 tok)
- `hooks.json` (~184 tok)

## scripts/

- `init-schema.ts` — API routes: GET (2 endpoints) (~775 tok)
- `seed.ts` — API routes: GET (4 endpoints) (~784 tok)

## skills/ai-visibility/

- `SKILL.md` — AI Visibility Monitoring (Content Flywheel) (~654 tok)

## skills/backlink-monitor/

- `SKILL.md` — Backlink Analysis (Content Flywheel) (~506 tok)

## skills/content-discover/

- `SKILL.md` — Content Discovery & Site Audit (Content Flywheel) (~539 tok)

## skills/content-optimize/

- `SKILL.md` — Content SEO Optimization (Content Flywheel) (~776 tok)

## skills/keyword-research/

- `SKILL.md` — Keyword Research (Content Flywheel) (~835 tok)

## skills/rank-monitor/

- `SKILL.md` — SERP Analysis & Rank Monitoring (Content Flywheel) (~513 tok)

## skills/vault-inspiration/

- `SKILL.md` — Vault Inspiration (Content Flywheel) (~727 tok)

## src/app/

- `globals.css` — Styles: 3 rules, 8 vars, 1 media queries (~140 tok)
- `layout.tsx` — metadata (~129 tok)
- `page.tsx` — Home (~30 tok)

## src/app/api/cron/seo-pull/

- `route.ts` — Vercel Cron: runs daily to pull keyword ranking data from DataForSEO (~702 tok)

## src/app/api/cron/serp-snapshot/

- `route.ts` — Vercel Cron: runs weekly for broader SERP feature analysis (~714 tok)

## src/app/api/graph/query/

- `route.ts` — Next.js API route: POST (~190 tok)

## src/app/api/publish/sanity/

- `route.ts` — Next.js API route: POST (~416 tok)

## src/app/api/publish/social/

- `route.ts` — Next.js API route: POST (~469 tok)

## src/app/api/webhooks/ghl/

- `route.ts` — GoHighLevel webhook receiver — fires when a social post is published. (~330 tok)

## src/app/api/webhooks/sanity/

- `route.ts` — Sanity webhook receiver — fires when a document is published/unpublished. (~441 tok)

## src/app/api/workflows/ai-visibility/

- `route.ts` — Next.js API route: POST (~226 tok)

## src/app/api/workflows/backlink-analysis/

- `route.ts` — Next.js API route: POST (~224 tok)

## src/app/api/workflows/content-optimize/

- `route.ts` — Next.js API route: POST (~239 tok)

## src/app/api/workflows/keyword-research/

- `route.ts` — Next.js API route: POST (~241 tok)

## src/app/api/workflows/serp-analysis/

- `route.ts` — Next.js API route: POST (~245 tok)

## src/app/api/workflows/site-audit/

- `route.ts` — Next.js API route: POST (~217 tok)

## src/app/board/

- `page.tsx` — BoardPage (~1796 tok)

## src/app/content/[id]/

- `page.tsx` — fetchContentDetail — renders table — uses useState, useEffect (~4087 tok)

## src/lib/adapters/cms/

- `sanity.ts` — Zustand store (~763 tok)

## src/lib/adapters/distribution/

- `ghl.ts` — Exports ghlAdapter (~644 tok)

## src/lib/dataforseo/

- `client.ts` — Exports keywordSuggestions, relatedKeywords, keywordIdeas, serpLive + 13 more (~1783 tok)

## src/lib/neo4j/

- `driver.ts` — Exports getDriver, closeDriver (~184 tok)
- `queries.ts` — Convert Neo4j driver types (Integer, DateTime, Date, Node, Relationship, Point, Duration) (~1649 tok)

## src/lib/workflows/

- `ai-visibility.ts` — Exports runAIVisibility (~1556 tok)
- `backlink-analysis.ts` — Exports runBacklinkAnalysis (~1601 tok)
- `content-optimize.ts` — Exports runContentOptimize (~3494 tok)
- `keyword-research.ts` — Exports runKeywordResearch (~2304 tok)
- `serp-analysis.ts` — Exports runSERPAnalysis (~1971 tok)
- `site-audit.ts` — Exports runSiteAudit (~2449 tok)

## src/types/

- `index.ts` — Content Flywheel — Core Types (~1221 tok)

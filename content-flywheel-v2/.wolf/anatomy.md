# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-04-09T14:09:35.412Z
> Files: 121 tracked | Anatomy hits: 0 | Misses: 0

## ../../../../

- `.zshrc` — Created by `pipx` on 2025-09-16 22:24:26 (~353 tok)

## ../../../../.claude/projects/-Users-jamesdeola-dev-local-RHIZE-rhize-plugins/memory/

- `MEMORY.md` (~31 tok)
- `reference_jira_content_flywheel.md` (~370 tok)

## ./

- `.gitignore` — Git ignore rules (~212 tok)
- `.mcp.json` (~504 tok)
- `CLAUDE.md` — OpenWolf (~3001 tok)
- `eslint.config.mjs` — ESLint flat configuration (~124 tok)
- `next.config.ts` — Declares nextConfig (~42 tok)
- `package.json` — Node.js package manifest (~345 tok)
- `postcss.config.mjs` — Declares config (~26 tok)
- `README.md` — Project documentation (~960 tok)
- `tsconfig.json` — TypeScript configuration (~192 tok)
- `vercel.json` (~53 tok)
- `vitest.config.ts` — /*.test.{ts,tsx}"], (~85 tok)

## .claude-plugin/

- `plugin.json` (~165 tok)

## .claude/

- `settings.json` (~508 tok)

## .claude/hooks/

- `jira-sync.sh` — PostToolUse hook for Bash: detects git commit and extracts RT-XX Jira keys. (~231 tok)

## .claude/plans/

- `m8-ai-sdk-foundation.md` — M8 AI SDK Foundation — RT-10 + RT-11 (~1102 tok)
- `m8-content-ingest-outline.md` — M8 Content Ingestion + AI Outline — RT-14 + RT-15 (~1775 tok)
- `m8-cost-dashboard-tests.md` — M8 Cost Dashboard + Test Completion — RT-18 + RT-19 (~669 tok)
- `m8-draft-brandvoice.md` — M8 Article Draft + Brand Voice Scoring — RT-16 + RT-17 (~1131 tok)
- `m8-embeddings-clustering.md` — M8 Embeddings + Semantic Clustering — RT-12 + RT-13 (~1916 tok)
- `neo4j-graph-relationship-enhancements.md` — Neo4j Graph Relationship Enhancements — Implementation Plan (~4366 tok)
- `remaining-features-complete-app.md` — Content Flywheel — Remaining Features Plan (~3920 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## commands/

- `flywheel-autocomplete.md` — Process (~339 tok)
- `flywheel-discover.md` — Process (~337 tok)
- `flywheel-distribute.md` — Process (~370 tok)
- `flywheel-gap.md` — Process (~454 tok)
- `flywheel-gsc.md` — Process (~568 tok)
- `flywheel-indexing.md` — Process (~379 tok)
- `flywheel-monitor.md` — Process (~556 tok)
- `flywheel-optimize.md` — Process (~409 tok)
- `flywheel-publish.md` — Process (~298 tok)
- `flywheel-research.md` — Process (~500 tok)
- `flywheel-status.md` — Process (~469 tok)

## cypher/

- `schema.cypher` — ============================================================ (~1078 tok)

## docs/plans/

- `2026-04-04-content-flywheel-production-ready.md` — Content Flywheel — Production-Ready Implementation Plan (~11910 tok)

## hooks/

- `flywheel-context.md` — Content Flywheel Context (~1877 tok)
- `hooks.json` (~184 tok)

## scripts/

- `init-schema.ts` — API routes: GET (2 endpoints) (~775 tok)
- `migrate-graph-relationships.ts` — One-time migration script to backfill graph relationships for existing data. (~1084 tok)
- `prune-irrelevant-keywords.ts` — One-time script to prune irrelevant TARGETS relationships. (~1852 tok)
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
- `layout.tsx` — metadata (~180 tok)
- `page.tsx` — Home (~30 tok)

## src/app/api/board/

- `route.ts` — Next.js API route: GET (~114 tok)

## src/app/api/board/move/

- `route.ts` — Next.js API route: POST (~317 tok)

## src/app/api/content/

- `route.ts` — Next.js API route: POST (~421 tok)

## src/app/api/content/[id]/

- `route.ts` — Next.js API route: GET, PATCH, DELETE (~487 tok)

## src/app/api/cron/seo-pull/

- `route.ts` — Vercel Cron: runs daily to pull keyword ranking data from DataForSEO (~702 tok)

## src/app/api/cron/serp-snapshot/

- `route.ts` — Vercel Cron: runs weekly for broader SERP feature analysis (~714 tok)

## src/app/api/graph/query/

- `route.ts` — Generic Cypher proxy. Protected by GRAPH_QUERY_SECRET header so it cannot (~380 tok)

## src/app/api/graph/stats/

- `route.ts` — Next.js API route: GET (~138 tok)

## src/app/api/publish/sanity/

- `route.ts` — Next.js API route: POST (~600 tok)

## src/app/api/publish/social/

- `route.ts` — Next.js API route: POST (~320 tok)

## src/app/api/webhooks/ghl/

- `route.ts` — GoHighLevel webhook receiver — fires when a social post is published. (~352 tok)

## src/app/api/webhooks/sanity/

- `route.ts` — Sanity webhook receiver — fires when a document is published/unpublished. (~912 tok)

## src/app/api/workflows/ai-visibility/

- `route.ts` — Next.js API route: POST (~226 tok)

## src/app/api/workflows/article-draft/

- `route.ts` — Next.js API route: POST (~203 tok)

## src/app/api/workflows/article-outline/

- `route.ts` — Next.js API route: POST (~205 tok)

## src/app/api/workflows/backlink-analysis/

- `route.ts` — Next.js API route: POST (~224 tok)

## src/app/api/workflows/brand-voice-check/

- `route.ts` — Next.js API route: POST (~206 tok)

## src/app/api/workflows/content-ingest/

- `route.ts` — Next.js API route: POST (~202 tok)

## src/app/api/workflows/content-optimize/

- `route.ts` — Next.js API route: POST (~239 tok)

## src/app/api/workflows/keyword-research/

- `route.ts` — Next.js API route: POST (~241 tok)

## src/app/api/workflows/serp-analysis/

- `route.ts` — Next.js API route: POST (~245 tok)

## src/app/api/workflows/site-audit/

- `route.ts` — Next.js API route: POST (~217 tok)

## src/app/board/

- `error.tsx` — BoardError (~71 tok)
- `loading.tsx` — BoardLoading (~411 tok)
- `page.tsx` — slugify — renders form (~5271 tok)

## src/app/content/[id]/

- `error.tsx` — ContentError (~72 tok)
- `loading.tsx` — ContentLoading (~256 tok)
- `page.tsx` — fetchContentDetail (~8739 tok)

## src/app/graph/

- `page.tsx` — GraphPage — renders table (~4155 tok)

## src/components/

- `error-page.tsx` — ErrorPage (~247 tok)
- `sidebar.tsx` — NAV_ITEMS (~470 tok)

## src/lib/adapters/cms/

- `sanity.ts` — Exports sanityAdapter (~928 tok)

## src/lib/adapters/distribution/

- `ghl.ts` — Exports ghlAdapter (~806 tok)

## src/lib/ai/

- `claude.ts` — Claude SDK wrapper: generateText(), generateStructured(), cost tracking, prompt caching, Neo4j AIUsage recording (~2390 tok)
- `clustering.ts` — K-means clustering on embeddings, AI intent classification via Haiku, cluster naming, regex fallback (~1468 tok)
- `embeddings.ts` — --------------------------------------------------------------------------- (~1218 tok)

## src/lib/dataforseo/

- `client.ts` — Exports keywordSuggestions, relatedKeywords, keywordIdeas, serpLive + 13 more (~1783 tok)

## src/lib/neo4j/

- `driver.ts` — Exports getDriver, closeDriver (~184 tok)
- `queries.ts` — Convert Neo4j driver types (Integer, DateTime, Date, Node, Relationship, Point, Duration) (~5508 tok)

## src/lib/notifications/

- `slack.ts` — Post a message to Slack using the Web API `chat.postMessage` endpoint. (~474 tok)

## src/lib/workflows/

- `ai-visibility.ts` — Exports runAIVisibility (~1557 tok)
- `article-draft.ts` — Exports runArticleDraft (~1840 tok)
- `article-outline.ts` — Exports runArticleOutline: AI outline generation via Sonnet + prompt caching, stores Outline node, moves to draft (~2100 tok)
- `backlink-analysis.ts` — Exports runBacklinkAnalysis (~1773 tok)
- `brand-voice-check.ts` — Zod schemas: brandVoiceSchema (~1225 tok)
- `content-ingest.ts` — Exports runContentIngest: Firecrawl scrape + Haiku theme extraction, creates ContentPiece + Theme nodes (~1800 tok)
- `content-optimize.ts` — Exports runContentOptimize (~3827 tok)
- `helpers.ts` — Shared workflow run lifecycle: createWorkflowRun, completeWorkflowRun, failWorkflowRun (~710 tok)
- `keyword-research.ts` — Extract keyword metrics from a DataForSEO item into a flat object. (~3385 tok)
- `serp-analysis.ts` — Exports runSERPAnalysis (~2023 tok)
- `site-audit.ts` — Exports runSiteAudit (~2582 tok)

## src/types/

- `index.ts` — ============================================================ (~1651 tok)

## tests/ai/

- `claude.test.ts` — --------------------------------------------------------------------------- (~2199 tok)
- `clustering.test.ts` — Vitest tests for clusterKeywords, classifyIntentRegex, classifyIntentAI, nameCluster (~1100 tok)
- `embeddings.test.ts` — --------------------------------------------------------------------------- (~1818 tok)

## tests/app/api/

- `board-move.test.ts` — Mock the Neo4j queries module before importing the route (~801 tok)
- `content-create.test.ts` — Declares mockRequest (~1112 tok)
- `content-detail.test.ts` — Declares mockRequest (~1237 tok)
- `graph-query.test.ts` — Declares mockRequest (~821 tok)

## tests/lib/dataforseo/

- `client.test.ts` — ORIGINAL_FETCH: mockFetch (~1016 tok)

## tests/lib/neo4j/

- `to-plain.test.ts` — Declares int (~631 tok)

## tests/notifications/

- `slack.test.ts` — --------------------------------------------------------------------------- (~1080 tok)

## tests/workflows/

- `article-draft.test.ts` — Vitest tests for runArticleDraft: parallel section generation, draft creation, stage move to optimize, cost calculation, failure on missing outline (~1361 tok)
- `article-outline.test.ts` — --------------------------------------------------------------------------- (~1597 tok)
- `brand-voice-check.test.ts` — Vitest tests for runBrandVoiceCheck: draft scoring via Haiku, BrandVoiceScore node creation, workflow run lifecycle (create/complete/fail) (~900 tok)
- `content-ingest.test.ts` — Vitest tests for runContentIngest: scrape URL, theme extraction, workflow run lifecycle (create/complete/fail) (~900 tok)
- `helpers.test.ts` — Declares mockRunCypher (~1067 tok)

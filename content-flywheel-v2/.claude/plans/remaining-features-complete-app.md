# Content Flywheel — Remaining Features Plan

> **Goal:** Close every functional gap so the Content Flywheel is a complete, end-to-end content pipeline management application — from URL ingestion through AI draft generation, publishing, and monitoring.

**Current state:** M0–M8 complete (100 tests, 10 workflows, deployed). M9 blocked on SEO Utils cloud API.

---

## Gap Analysis Summary

| # | Gap | Impact | Milestone |
|---|-----|--------|-----------|
| 1 | AI workflow buttons missing from content detail page | Outline/draft/ingest/brand-voice workflows exist but have no UI trigger | M10 |
| 2 | Content detail API doesn't return outline, draft, themes, brand voice data | AI-generated content exists in Neo4j but never shown | M10 |
| 3 | No outline/draft/brand-voice display sections in content detail UI | Users can't see AI-generated content | M10 |
| 4 | No "Ingest URL" flow on board page | content-ingest workflow has no entry point in the UI | M10 |
| 5 | No content editing (title, slug, author, URL) | Content is create-only, can't correct mistakes | M11 |
| 6 | No content deletion | No way to remove irrelevant/test content | M11 |
| 7 | No board search/filter | Hard to find content as the pipeline grows | M11 |
| 8 | No publish/distribute buttons in content detail | Sanity + GHL adapters exist but no UI to trigger them | M12 |
| 9 | No publish status display on content detail | PUBLISHED_TO/DISTRIBUTED_TO data not shown | M12 |
| 10 | Slack notifications not implemented | Env vars defined but no code | M13 |
| 11 | Sanity webhook has no signature verification | Security gap | M13 |
| 12 | flywheel-context.md outdated | Missing AI workflows, new relationships | M13 |
| 13 | M9 SEO Utils — MCP setup (non-blocking) | Can add MCP for local dev even though runtime migration is blocked | M14 |

---

## M10: AI Workflow UI (Critical — makes M8 features usable)

All 4 AI workflows (content-ingest, article-outline, article-draft, brand-voice-check) have backend engines and API routes but **zero UI surface**. This milestone wires them into the application.

### Task 38: Expand content detail API to return AI content

**Files:**
- Modify: `src/lib/neo4j/queries.ts` (`getContentDetailById`)
- Modify: `src/app/content/[id]/page.tsx` (ContentDetail interface)

**What to change:**

Add these OPTIONAL MATCHes to `getContentDetailById` (after line 152):
```cypher
OPTIONAL MATCH (c)-[:HAS_OUTLINE]->(outline:Outline)
OPTIONAL MATCH (c)-[:HAS_DRAFT]->(draft:Draft)
OPTIONAL MATCH (c)-[:HAS_BRAND_VOICE_SCORE]->(bvs:BrandVoiceScore)
OPTIONAL MATCH (c)-[:HAS_THEME]->(theme:Theme)
```

Add to RETURN clause:
```cypher
head(collect(DISTINCT outline { .* })) AS outline,
head(collect(DISTINCT draft { .* })) AS draft,
head(collect(DISTINCT bvs { .* })) AS brandVoiceScore,
collect(DISTINCT theme { .name }) AS themes
```

Update the `ContentDetail` interface in the page to include:
```typescript
outline: Outline | null;
draft: Draft | null;
brandVoiceScore: BrandVoiceScore | null;
themes: { name: string }[];
```

### Task 39: Add AI workflow buttons to content detail page

**Files:**
- Modify: `src/app/content/[id]/page.tsx`

Add 4 new buttons to the workflow actions section (after existing 5 buttons):

1. **"Ingest URL"** — visible when `content.url` exists. Calls `content-ingest` with `{ url: content.url }`.
2. **"Generate Outline"** — visible when content has keywords (research stage+). Calls `article-outline` with `{ contentId: id }`.
3. **"Generate Draft"** — visible when outline exists. Calls `article-draft` with `{ contentId: id }`.
4. **"Check Brand Voice"** — visible when draft exists. Calls `brand-voice-check` with `{ contentId: id }`.

Use consistent button styling. Show disabled state with "Running..." text.

### Task 40: Add AI content display sections to content detail page

**Files:**
- Modify: `src/app/content/[id]/page.tsx`

Add 4 new sections below the existing panels:

1. **Themes section** — simple tag list showing extracted themes
2. **Outline section** — show meta description, H2 sections with bullets, FAQ topics, internal link suggestions. Collapsible.
3. **Draft section** — render markdown content with word count. Collapsible (drafts can be long).
4. **Brand Voice Score section** — traffic-light score badge (red/yellow/green), issues list with section/issue/suggestion. Same pattern as SEO Score card.

### Task 41: Add "Ingest URL" modal to board page

**Files:**
- Modify: `src/app/board/page.tsx`

Add a second button next to "Create Content" labeled "Ingest URL". Opens a modal with a single URL input. On submit:
1. Calls `POST /api/workflows/content-ingest` with `{ url }`
2. On success, refreshes the board (new content appears in Inspiration column)

### Task 42: Tests for new UI data flow

**Files:**
- Modify: `tests/app/api/content-detail.test.ts`

Add test cases that verify `getContentDetailById` returns outline, draft, brandVoiceScore, and themes when they exist in the graph.

**Commit:** `feat(content-flywheel): wire AI workflows into content detail UI (RT-XX)`

---

## M11: Content Management

### Task 43: Add content edit API

**Files:**
- Create: `src/app/api/content/[id]/route.ts` (add PATCH handler alongside existing GET)
- Modify: `src/lib/neo4j/queries.ts` (add `updateContent` function)

PATCH `/api/content/[id]` accepts `{ title?, slug?, author?, url? }` and updates the ContentPiece node. Only provided fields are updated (COALESCE pattern).

### Task 44: Add content delete API

**Files:**
- Modify: `src/app/api/content/[id]/route.ts` (add DELETE handler)
- Modify: `src/lib/neo4j/queries.ts` (add `deleteContent` function)

DELETE `/api/content/[id]` detaches and deletes the ContentPiece and all directly-owned nodes (outline, draft, brand voice score, AI usage). Leaves shared nodes (keywords, clusters, backlink sources) intact.

```cypher
MATCH (c:ContentPiece {id: $id})
OPTIONAL MATCH (c)-[:HAS_OUTLINE]->(o:Outline) DETACH DELETE o
OPTIONAL MATCH (c)-[:HAS_DRAFT]->(d:Draft) DETACH DELETE d
OPTIONAL MATCH (c)-[:HAS_BRAND_VOICE_SCORE]->(bvs:BrandVoiceScore) DETACH DELETE bvs
OPTIONAL MATCH (c)-[:HAS_WORKFLOW_RUN]->(w:WorkflowRun) DETACH DELETE w
OPTIONAL MATCH (c)-[:HAS_AI_USAGE]->(u:AIUsage) DETACH DELETE u
DETACH DELETE c
```

### Task 45: Add edit/delete UI to content detail page

**Files:**
- Modify: `src/app/content/[id]/page.tsx`

- **Edit**: Inline-editable title/slug/author/URL fields (click to edit, Enter to save, Esc to cancel). Calls PATCH on blur/enter.
- **Delete**: "Delete" button with confirmation dialog. On confirm, calls DELETE then redirects to `/board`.

### Task 46: Add board search and filter

**Files:**
- Modify: `src/app/board/page.tsx`

Add to board header:
1. **Search input** — filters cards client-side by title (case-insensitive `includes`)
2. **Author filter** — dropdown populated from unique authors in board data
3. **Stage filter** — checkboxes to show/hide specific columns

No API changes needed — all client-side filtering on already-fetched board data.

### Task 47: Tests for content CRUD

**Files:**
- Modify: `tests/app/api/content-create.test.ts` (add PATCH and DELETE test cases)

**Commit:** `feat(content-flywheel): content editing, deletion, board search/filter`

---

## M12: Publishing & Distribution UI

### Task 48: Add publish buttons to content detail page

**Files:**
- Modify: `src/app/content/[id]/page.tsx`

Add a "Publishing" section visible when content is in `review` or `published` stage:

1. **"Publish to Sanity"** button — calls `POST /api/publish/sanity` with `{ contentId, action: "create-draft" }`. Shows Sanity document ID on success.
2. **"Schedule Social"** button — opens a small form (platform dropdown, text input, schedule date). Calls `POST /api/publish/social`.

### Task 49: Show publish/distribution status on content detail

**Files:**
- Modify: `src/lib/neo4j/queries.ts` (`getContentDetailById`)
- Modify: `src/app/content/[id]/page.tsx`

Add to detail query:
```cypher
OPTIONAL MATCH (c)-[pubRel:PUBLISHED_TO]->(cms:CMSTarget)
OPTIONAL MATCH (c)-[distRel:DISTRIBUTED_TO]->(dc:DistributionChannel)
```

Show cards:
- **Published to:** Sanity (publishedAt, documentId) — link to Sanity Studio
- **Distributed to:** GHL (platform, scheduledAt, status badge)

### Task 50: Tests for publish flow

**Files:**
- Create: `tests/app/api/publish-sanity.test.ts`

Mock sanityAdapter, verify Neo4j PUBLISHED_TO relationship creation.

**Commit:** `feat(content-flywheel): publishing UI + distribution status display`

---

## M13: Polish & Hardening

### Task 51: Add Sanity webhook signature verification

**Files:**
- Modify: `src/app/api/webhooks/sanity/route.ts`

Sanity sends a `sanity-webhook-signature` header. Verify it using HMAC-SHA256 with a secret configured in Sanity Dashboard + `.env.local` (`SANITY_WEBHOOK_SECRET`).

Reject requests with invalid/missing signatures (401).

### Task 52: Implement Slack notifications

**Files:**
- Create: `src/lib/notifications/slack.ts`
- Modify: workflow engines that should trigger notifications

Create a thin `sendSlackMessage(channel, text)` function using Slack Web API (`chat.postMessage`). Wire into:
- Content creation → "New content: {title} by {author}"
- Workflow completion → "Workflow {type} completed for {title}: {summary}"
- Content published → "Published: {title} to {cms}"

Gracefully no-op when `SLACK_BOT_TOKEN` is not set (don't break workflows).

### Task 53: Update flywheel-context.md

**Files:**
- Modify: `hooks/flywheel-context.md`

Add AI workflow routes, AI content relationships, themes/outline/draft/brand-voice nodes, semantic relevance filter pattern, `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` env vars.

### Task 54: Update CLAUDE.md with final feature set

**Files:**
- Modify: `CLAUDE.md`

Final documentation pass reflecting all M10-M13 changes.

**Commit:** `chore(content-flywheel): webhook verification, Slack notifications, docs update`

---

## M14: SEO Utils — Option B (Dual-Stack, Local MCP) ✅

**Architecture decision (2026-04-09):** SEO Utils runs as a local desktop app server at `http://localhost:19515/mcp`. Vercel serverless functions cannot reach localhost, so runtime workflows keep DataForSEO. SEO Utils is used for Claude Code sessions via MCP — providing GSC data, indexing API, autocomplete scraping, and gap analysis that DataForSEO doesn't offer.

### Task 55: Purchase + configure ✅

- MCP access purchased
- `.mcp.json` entry configured with Bearer token
- SEO Utils server confirmed running (401 → auth works)
- MCP handshake verified: `seo-utils-intelligence` v1.45.0, 40+ tools available

### Task 56: Create flywheel commands for SEO Utils ✅

Created 4 new commands that leverage SEO Utils MCP tools:

| Command | File | SEO Utils Tools Used |
|---------|------|---------------------|
| `/flywheel-gsc` | `commands/flywheel-gsc.md` | `query_gsc`, `query_database` |
| `/flywheel-indexing` | `commands/flywheel-indexing.md` | `check_google_indexing_status`, `submit_url_for_google_indexing`, `submit_url_to_index_now` |
| `/flywheel-gap` | `commands/flywheel-gap.md` | `get_content_gap`, `get_backlink_gap` |
| `/flywheel-autocomplete` | `commands/flywheel-autocomplete.md` | `fetch_autocomplete_keywords`, `check_keyword_metrics` |

### Task 57: Document dual-stack architecture

**Files:** CLAUDE.md, hooks/flywheel-context.md

Document: DataForSEO = Vercel runtime, SEO Utils = Claude Code sessions. Which tools are available where.

---

## M15: SEO Utils — Option C (VPS-Hosted, Vercel-Accessible) 🔮 Future

**Goal:** Run SEO Utils headlessly on a VPS so Vercel serverless functions can call it as a REST API, enabling runtime migration away from direct DataForSEO calls.

### Task 58: Provision VPS for SEO Utils

**Manual step:**
1. Provision a VPS (Hostinger/Railway/fly.io) — SEO Utils is lightweight, 1GB RAM sufficient
2. Install SEO Utils in headless/server mode
3. Configure firewall to allow inbound on port 19515 from Vercel IP ranges only
4. Set up SSL (Let's Encrypt or Cloudflare tunnel) for HTTPS

### Task 59: Configure SEO Utils on VPS

1. Copy SEO Utils config (API keys, GSC credentials) to VPS
2. Set up SEO Utils as a systemd service for auto-restart
3. Generate a Bearer token for Vercel access
4. Verify the MCP endpoint is reachable: `curl https://seo-utils.your-vps.com/mcp`

### Task 60: Create SEO Utils runtime client

**Files:**
- Create: `src/lib/seo-utils/client.ts`

Build a client that calls the VPS-hosted SEO Utils MCP endpoint using JSON-RPC over HTTP. Implement equivalent functions to `src/lib/dataforseo/client.ts` but routing through SEO Utils:

```typescript
// Same function signatures as dataforseo/client.ts
export async function keywordSuggestions(...) { ... }
export async function serpLive(...) { ... }
// etc.
```

Key: maintain identical TypeScript return shapes so workflow files need zero changes.

### Task 61: Feature flag + dual-run validation

**Files:**
- Modify: all workflow files in `src/lib/workflows/`
- Add: `SEO_UTILS_API_URL` and `USE_SEO_UTILS` env vars

Add a feature flag `USE_SEO_UTILS=true` that swaps the import:
```typescript
const client = process.env.USE_SEO_UTILS === 'true'
  ? await import('@/lib/seo-utils/client')
  : await import('@/lib/dataforseo/client');
```

Run both clients side-by-side for 1 week, compare results, validate equivalence.

### Task 62: Migrate + add SEO Utils-exclusive runtime workflows

After validation, remove DataForSEO client and add new workflows:

1. **GSC sync workflow** — `src/lib/workflows/gsc-sync.ts` — pull real Search Console data into Neo4j
2. **Indexing workflow** — `src/lib/workflows/indexing-check.ts` — check/submit URLs after publishing
3. **Cannibalization detection** — `src/lib/workflows/cannibalization-check.ts` — find competing pages

### Task 63: Decommission DataForSEO

1. Remove `src/lib/dataforseo/client.ts`
2. Update all imports
3. Remove `DATAFORSEO_USERNAME` / `DATAFORSEO_PASSWORD` from Vercel env vars
4. Update documentation

**Blocked on:** VPS provisioned + SEO Utils headless mode confirmed working.

---

## Milestone Status (updated 2026-04-09)

| Milestone | Status | Notes |
|-----------|--------|-------|
| M10: AI Workflow UI | ✅ Done | All 4 AI workflow buttons + display sections |
| M11: Content Management | ✅ Done | Edit, delete, board search/filter |
| M12: Publishing UI | ✅ Done | Publish buttons + status display |
| M13: Polish & Hardening | ✅ Done | Webhook verification, Slack, docs |
| M14: SEO Utils Option B | ✅ Done | MCP configured, 4 flywheel commands created |
| M15: SEO Utils Option C | 🔮 Future | VPS hosting, runtime migration |

---

## Post-Completion State

The Content Flywheel now supports the full lifecycle:

1. **Discover** — Ingest URL → extract themes → create content in Inspiration
2. **Research** — Keyword research + semantic clustering + competitor gap analysis + autocomplete discovery (SEO Utils)
3. **Generate** — AI outline → AI draft → brand voice check
4. **Optimize** — SEO audit → content optimization → internal link suggestions
5. **Review** — Brand voice score + SEO score visible side-by-side
6. **Publish** — Push to Sanity CMS → schedule social via GHL → submit for indexing (SEO Utils)
7. **Monitor** — Daily SERP tracking + backlink monitoring + AI visibility + GSC data (SEO Utils)
8. **Refresh** — Identify content decay via GSC declining queries → cycle back to Optimize

**Dual-stack architecture:**
- **Vercel runtime** (deployed): DataForSEO API for all 10 workflow engines
- **Claude Code sessions** (local): SEO Utils MCP for GSC, indexing, autocomplete, gap analysis
- **Future (M15):** VPS-hosted SEO Utils replaces DataForSEO for runtime too

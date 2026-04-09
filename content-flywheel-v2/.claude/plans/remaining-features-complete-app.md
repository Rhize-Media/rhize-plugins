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

## M14: SEO Utils MCP (Non-Blocking)

M9 runtime migration is blocked on cloud API, but the MCP setup for local dev is straightforward.

### Task 55: Purchase SEO Utils MCP access + configure

**Manual step** — same as original plan Tasks 32-34.

1. Purchase MCP access ($1)
2. Generate Bearer token
3. Add `seo-utils` entry to `.mcp.json`
4. Add `SEO_UTILS_TOKEN` to `.env.local`
5. Verify tools load in Claude Code session

### Task 56: Document SEO Utils availability

**Files:**
- Modify: `CLAUDE.md` (add to MCP Servers section)

Note: runtime workflows still use DataForSEO directly. SEO Utils is available for ad-hoc Claude research (GSC data, LLM rank tracking, cannibalization detection).

**Commit:** `chore(content-flywheel): add seo-utils MCP for local dev`

---

## Implementation Order & Dependencies

```
M10 (AI Workflow UI) — NO DEPENDENCIES, start immediately
  Task 38 (expand API) → Task 39 (buttons) + Task 40 (display) → Task 41 (ingest modal) → Task 42 (tests)

M11 (Content Management) — can run in parallel with M10
  Task 43 (edit API) + Task 44 (delete API) → Task 45 (edit/delete UI) → Task 46 (search/filter) → Task 47 (tests)

M12 (Publishing UI) — after M10 (needs content detail changes to land first)
  Task 48 (publish buttons) → Task 49 (status display) → Task 50 (tests)

M13 (Polish) — after M10 + M11 + M12
  Task 51 (webhook verify) + Task 52 (Slack) + Task 53 (context) + Task 54 (docs)

M14 (SEO Utils MCP) — independent, can run anytime
  Task 55 (purchase + config) → Task 56 (document)
```

**Parallelizable:** M10 and M11 can run concurrently (different files). M14 is independent.

**Estimated scope:**
- M10: ~4 tasks, touches queries.ts + content detail page + board page
- M11: ~5 tasks, touches content API + content detail page + board page
- M12: ~3 tasks, touches queries.ts + content detail page
- M13: ~4 tasks, various polish files
- M14: ~2 tasks, config only

**Total: 19 tasks across 5 milestones to reach feature-complete.**

---

## Post-Completion State

After M10-M14, the Content Flywheel will support the full lifecycle:

1. **Discover** — Ingest URL → extract themes → create content in Inspiration
2. **Research** — Run keyword research → semantic clustering → competitor gap analysis
3. **Generate** — AI outline → AI draft → brand voice check
4. **Optimize** — SEO audit → content optimization → internal link suggestions
5. **Review** — Brand voice score + SEO score visible side-by-side
6. **Publish** — Push to Sanity CMS → schedule social via GHL
7. **Monitor** — Daily SERP tracking → backlink monitoring → AI visibility
8. **Refresh** — Re-run workflows to identify content decay → cycle back to Optimize

All with:
- Board search/filter for pipeline management at scale
- Content editing/deletion for data hygiene
- Slack notifications for team awareness
- Cost tracking for AI budget management
- Webhook verification for production security

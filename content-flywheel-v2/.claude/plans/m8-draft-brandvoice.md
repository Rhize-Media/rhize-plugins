# M8 Article Draft + Brand Voice Scoring — RT-16 + RT-17

> **Jira:** RT-16 (AI article draft generation) + RT-17 (Brand voice scoring)
> **Depends on:** RT-15 (article-outline.ts — completed)
> **Created:** 2026-04-06

## Goal

1. **RT-16**: Generate a full article draft from an outline — parallel section writing via Sonnet with prompt caching, assemble into markdown, store as Draft node, advance to `optimize` stage.
2. **RT-17**: Score a draft against brand voice guidelines via Haiku — return score 0-100 with per-section issues, store as BrandVoiceScore node.

## Architecture Decisions

1. **Parallel section writing** — `Promise.all` with concurrency limit of 3 (avoid Anthropic rate limits). Each H2 section gets its own Sonnet call, but shares a cached system prompt.
2. **Prompt caching** — Brand voice guide + full outline cached via `cache_control: { type: "ephemeral" }`. First section pays cache creation cost, subsequent 2-7 sections get 90% input savings.
3. **Draft as markdown** — Stored as a single `content` string on `(:Draft)` node. Word count calculated from assembled markdown.
4. **Brand voice as Haiku** — Cheaper model sufficient for scoring/validation (not generation). Score 0-100 with structured issues array.
5. **Workflow helper** — If the simplifier extracts a shared workflow boilerplate helper, use it. Otherwise follow existing pattern.

## Steps

### Step 1: Add Draft + BrandVoiceScore types

**Modify:** `src/types/index.ts`

```typescript
export interface Draft {
  id: string;
  contentId: string;
  content: string;
  wordCount: number;
  createdAt: string;
}

export interface BrandVoiceIssue {
  section: string;
  issue: string;
  suggestion: string;
}

export interface BrandVoiceScore {
  id: string;
  contentId: string;
  score: number;
  issues: BrandVoiceIssue[];
  createdAt: string;
}
```

Add `"article-draft" | "brand-voice-check"` to WorkflowType union.
Add `draft_id` and `brand_voice_score_id` constraints to schema.cypher.

### Step 2: Create article draft workflow — `src/lib/workflows/article-draft.ts`

```typescript
// Input: { contentId: string }
// Output: { workflowRun, draft }

// Flow:
// 1. Load Outline from Neo4j (sections JSON, title, meta)
// 2. Build cached system prompt (brand voice + outline context)
// 3. For each section, generate content via Sonnet (parallel, max 3 concurrent)
//    - Each call: system (cached) + user: "Write section: {heading}\nBullets: {bullets}\nTarget: {wordCount} words"
// 4. Assemble sections into full markdown article
// 5. Create (:Draft {content, wordCount}) node, link via HAS_DRAFT
// 6. Move content to "optimize" stage
// 7. Record WorkflowRun with total cost
```

### Step 3: Create brand voice check workflow — `src/lib/workflows/brand-voice-check.ts`

```typescript
// Input: { contentId: string }
// Output: { workflowRun, brandVoiceScore }

// Flow:
// 1. Load Draft content from Neo4j
// 2. Haiku call with draft + brand voice reference
//    Schema: z.object({ score: z.number(), issues: z.array(z.object({ section, issue, suggestion })) })
// 3. Create (:BrandVoiceScore {score, issues}) node, link via HAS_BRAND_VOICE_SCORE
// 4. Record WorkflowRun
```

### Step 4: Create API routes

- `POST /api/workflows/article-draft` — `{ contentId }`
- `POST /api/workflows/brand-voice-check` — `{ contentId }`

### Step 5: Unit tests

- `tests/workflows/article-draft.test.ts` — mock outline, test parallel gen, test assembly, test stage advance
- `tests/workflows/brand-voice-check.test.ts` — mock draft, test scoring, test issue extraction

### Step 6: Commit and close Jira

## Key Files

| File | Operation | Description |
|------|-----------|-------------|
| `src/types/index.ts` | Modify | Add Draft, BrandVoiceScore types |
| `cypher/schema.cypher` | Modify | Add draft_id, brand_voice_score_id constraints |
| `src/lib/workflows/article-draft.ts` | Create | Parallel section writing via Sonnet |
| `src/lib/workflows/brand-voice-check.ts` | Create | Brand voice scoring via Haiku |
| `src/app/api/workflows/article-draft/route.ts` | Create | POST endpoint |
| `src/app/api/workflows/brand-voice-check/route.ts` | Create | POST endpoint |
| `tests/workflows/article-draft.test.ts` | Create | Draft workflow tests |
| `tests/workflows/brand-voice-check.test.ts` | Create | Brand voice tests |

## Cost Estimate

- **Article draft:** ~$0.08-0.15/article (Sonnet × 5-8 sections, with prompt caching reducing subsequent sections by 90% input)
- **Brand voice check:** ~$0.005/check (Haiku, ~4K input)

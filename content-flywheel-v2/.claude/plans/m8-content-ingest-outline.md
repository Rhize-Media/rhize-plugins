# M8 Content Ingestion + AI Outline — RT-14 + RT-15

> **Jira:** RT-14 (Content ingestion workflow) + RT-15 (AI outline generation)
> **Depends on:** RT-11 (claude.ts), RT-12 (embeddings.ts) — both completed
> **Created:** 2026-04-06

## Goal

Build two core AI-powered content workflows:
1. **RT-14**: Ingest a URL → scrape content → extract themes → create ContentPiece in `inspiration` stage
2. **RT-15**: Generate a structured article outline from a ContentPiece's keywords → store as Outline node → advance to `draft` stage

## Architecture Decisions

1. **Firecrawl JS SDK** (`firecrawl-js`) for scraping — already have API key, matches MCP server pattern. Alternative: `fetch` + defuddle, but Firecrawl handles JS-rendered pages and returns clean markdown.
2. **Theme nodes** — `(:Theme {id, name})` linked via `(:ContentPiece)-[:HAS_THEME]->(:Theme)`. Themes are reusable across content pieces (MERGE on name).
3. **Outline nodes** — `(:Outline {id, title, metaDescription, sections, faqTopics, createdAt})` with `sections` stored as JSON string (Neo4j doesn't support nested objects). Linked via `(:ContentPiece)-[:HAS_OUTLINE]->(:Outline)`.
4. **Prompt caching** for outline generation — brand voice guide + system prompt cached via `cache_control: { type: "ephemeral" }`. Sonnet model for quality.
5. **Stage auto-advance** — outline generation moves content from `research` → `draft` automatically.

## Steps

### Step 1: Install Firecrawl SDK

```bash
npm install firecrawl-js
```

Add `FIRECRAWL_API_KEY` to `.env.local` (already exists from MCP config).

### Step 2: Create content ingestion workflow — `src/lib/workflows/content-ingest.ts`

```typescript
// Input: { url: string, contentId?: string }
// Output: { workflowRun, contentPiece, themes }

// Flow:
// 1. Scrape URL via Firecrawl scrapeUrl() → markdown + metadata
// 2. Claude Haiku: extract 5-8 themes + 2-sentence summary from markdown
//    Schema: z.object({ themes: z.array(z.string()), summary: z.string() })
// 3. Create ContentPiece in "inspiration" stage (or link to existing contentId)
// 4. MERGE Theme nodes, create HAS_THEME relationships
// 5. Embed the summary on the ContentPiece for similarity search
// 6. Record WorkflowRun
```

### Step 3: Add Theme type + schema constraint

**Modify:** `src/types/index.ts` — add `Theme` interface
**Modify:** `cypher/schema.cypher` — add `theme_name` uniqueness constraint

```typescript
export interface Theme {
  id: string;
  name: string;
}
```

### Step 4: Create API route — `src/app/api/workflows/content-ingest/route.ts`

```typescript
// POST /api/workflows/content-ingest
// Body: { url: string, contentId?: string }
// Response: { workflowRun, contentPiece, themes }
// maxDuration = 300 (Firecrawl + Claude calls)
```

Follow existing route pattern from `keyword-research/route.ts`.

### Step 5: Create AI outline workflow — `src/lib/workflows/article-outline.ts`

```typescript
// Input: { contentId: string }
// Output: { workflowRun, outline }

// Flow:
// 1. Load ContentPiece + keywords + competitor SERPs from Neo4j
// 2. Load internal linking opportunities (other published content)
// 3. Claude Sonnet with cached system prompt (brand voice + outline instructions)
//    Schema: z.object({
//      title: z.string(),
//      metaDescription: z.string(),
//      sections: z.array(z.object({
//        heading: z.string(),
//        bullets: z.array(z.string()),
//        targetWordCount: z.number()
//      })),
//      faqTopics: z.array(z.string()),
//      internalLinks: z.array(z.string())
//    })
// 4. Create (:Outline) node, link via HAS_OUTLINE
// 5. Move content to "draft" stage via moveContentToStage()
// 6. Record WorkflowRun
```

### Step 6: Add Outline type + schema constraint

**Modify:** `src/types/index.ts` — add `Outline` interface
**Modify:** `cypher/schema.cypher` — add `outline_id` uniqueness constraint

```typescript
export interface Outline {
  id: string;
  contentId: string;
  title: string;
  metaDescription: string;
  sections: { heading: string; bullets: string[]; targetWordCount: number }[];
  faqTopics: string[];
  internalLinks: string[];
  createdAt: string;
}
```

### Step 7: Create API route — `src/app/api/workflows/article-outline/route.ts`

```typescript
// POST /api/workflows/article-outline
// Body: { contentId: string }
// Response: { workflowRun, outline }
// maxDuration = 300
```

### Step 8: Unit tests

**Create:** `tests/workflows/content-ingest.test.ts`
- Test theme extraction with mocked Firecrawl + Claude
- Test ContentPiece creation in inspiration stage
- Test Theme MERGE (reuse existing themes)

**Create:** `tests/workflows/article-outline.test.ts`
- Test outline generation with mocked Claude
- Test Outline node creation
- Test stage transition to draft

### Step 9: Commit and close Jira

```bash
git commit -m "feat: content ingestion + AI outline generation workflows (RT-14, RT-15)"
```

## Parallel Execution Strategy

```
Step 1 (install firecrawl)
  ↓
Step 2 (content-ingest.ts) ←→ Step 3 (Theme type + schema)  [parallel]
  ↓
Step 5 (article-outline.ts) ←→ Step 6 (Outline type + schema)  [parallel]
  ↓
Step 4 + Step 7 (API routes)  [parallel, after workflows exist]
  ↓
Step 8 (tests)  [two test files in parallel]
  ↓
Step 9 (commit)
```

**Agent parallelization:**
- Agent A: content-ingest.ts + Theme types/schema (Steps 2+3)
- Agent B: article-outline.ts + Outline types/schema (Steps 5+6)  
- Main: API routes (Steps 4+7) after agents complete
- Agent C+D: tests (Step 8, parallel)

## Key Files

| File | Operation | Description |
|------|-----------|-------------|
| `package.json` | Modify | Add `firecrawl-js` |
| `src/lib/workflows/content-ingest.ts` | Create | URL scraping + theme extraction |
| `src/lib/workflows/article-outline.ts` | Create | AI outline generation with Sonnet |
| `src/app/api/workflows/content-ingest/route.ts` | Create | POST endpoint |
| `src/app/api/workflows/article-outline/route.ts` | Create | POST endpoint |
| `src/types/index.ts` | Modify | Add Theme + Outline interfaces |
| `cypher/schema.cypher` | Modify | Add theme_name + outline_id constraints |
| `tests/workflows/content-ingest.test.ts` | Create | Ingestion tests |
| `tests/workflows/article-outline.test.ts` | Create | Outline tests |

## Risks and Mitigation

| Risk | Mitigation |
|------|------------|
| Firecrawl API down/slow | Timeout at 30s, fail gracefully with error in WorkflowRun |
| Scraped content too long for Claude context | Truncate to first 8000 tokens before sending to Haiku |
| No keywords linked to content for outline | Check prerequisites, return error if content has no TARGETS keywords |
| Outline sections JSON too large for Neo4j property | Store as JSON string, parse on read. Neo4j string limit is 2GB. |
| Brand voice guide not yet defined | Use a sensible default system prompt; make it configurable via env or Neo4j config node later |

## Cost Estimate

- **Content ingestion:** ~$0.003/article (Haiku theme extraction + embedding)
- **Outline generation:** ~$0.02/outline (Sonnet with prompt caching, ~4K input + ~2K output)

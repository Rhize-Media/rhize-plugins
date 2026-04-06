# M8 Embeddings + Semantic Clustering — RT-12 + RT-13

> **Jira:** RT-12 (Embeddings client with Neo4j cache) + RT-13 (Semantic keyword clustering)
> **Depends on:** RT-10, RT-11 (completed — `src/lib/ai/claude.ts` exists)
> **Created:** 2026-04-06

## Goal

Replace the naive string-matching keyword clustering and regex intent classification with AI-powered alternatives:
1. **RT-12**: Batch embedding client using Gemini `text-embedding-004`, with Neo4j caching
2. **RT-13**: K-means clustering on embedding vectors + Haiku-powered intent classification

## Architecture Decisions

1. **Gemini `text-embedding-004`** via `@google/genai` — cheapest option (free tier: 1500 req/min), 768-dim default, reducible to 256-dim for storage efficiency.
2. **256-dim vectors** — sufficient for keyword similarity, 3x cheaper to store in Neo4j than 768-dim. Configurable.
3. **Neo4j caching** — store embeddings as `k.embedding` property on Keyword nodes. Skip re-embedding keywords that already have it.
4. **`ml-kmeans`** for clustering — lightweight (~10KB), pure JS, no native deps. Auto-select k via silhouette scoring.
5. **Haiku batch intent classification** — batch 50 keywords per call, ~$0.0003 per batch. Keep regex as fallback on API failure.
6. **Haiku cluster naming** — one call per cluster to generate a descriptive name + pillar topic.

## Steps

### Step 1: Install dependencies

```bash
npm install @google/genai ml-kmeans
```

Add to `.env.local` and Vercel:
- `GEMINI_API_KEY`

**Files:** `package.json`, `package-lock.json`

### Step 2: Create embeddings client — `src/lib/ai/embeddings.ts`

```typescript
// Exports:
embedBatch(texts: string[], options?: { dimensions?: number }): Promise<number[][]>
embedAndCacheKeywords(terms: string[]): Promise<void>

// Implementation:
// - GoogleGenAI client singleton (like claude.ts pattern)
// - embedBatch: calls ai.models.embedContent with text-embedding-004
//   - Chunks texts into batches of 100 (API limit)
//   - Returns flat array of vectors
//   - Config: outputDimensionality = options.dimensions ?? 256
// - embedAndCacheKeywords: 
//   1. Query Neo4j for keywords without embeddings:
//      MATCH (k:Keyword) WHERE k.term IN $terms AND k.embedding IS NULL RETURN k.term
//   2. Call embedBatch on missing ones
//   3. Write back: MATCH (k:Keyword {term: $term}) SET k.embedding = $vector
```

Graceful failure: if `GEMINI_API_KEY` is missing, throw clear error (same pattern as claude.ts).

### Step 3: Create clustering module — `src/lib/ai/clustering.ts`

```typescript
// Exports:
clusterKeywords(keywords: { term: string; embedding: number[] }[]): ClusterAssignment[]
classifyIntentAI(keywords: string[]): Promise<Map<string, IntentType>>

// Types:
interface ClusterAssignment {
  term: string
  clusterId: number
}

type IntentType = "informational" | "navigational" | "commercial" | "transactional"

// clusterKeywords implementation:
// - Uses ml-kmeans with k selected by silhouette method
//   - k range: max(2, floor(n/10)) to min(n/2, 20) — bounded for sanity
//   - If n < 5 keywords: skip clustering, put all in one cluster
// - Returns cluster assignment per keyword

// classifyIntentAI implementation:
// - Uses generateStructured from claude.ts with Haiku model
// - Batches up to 50 keywords per call
// - Zod schema: z.object({ classifications: z.array(z.object({ term: z.string(), intent: z.enum([...]) })) })
// - Fallback: on API error, fall back to existing regex classifyIntent
```

### Step 4: Modify keyword-research workflow — `src/lib/workflows/keyword-research.ts`

Replace two sections:

**4a. Replace `classifyIntent` regex (line 264-273)**
- Import `classifyIntentAI` from `@/lib/ai/clustering`
- After collecting all keywords in `allKeywords` Map, batch-classify intent:
  ```
  const intents = await classifyIntentAI(Array.from(allKeywords.keys()))
  // Update each keyword's intent from AI results
  ```
- Keep old regex `classifyIntent` as private fallback (renamed to `classifyIntentRegex`)

**4b. Replace naive clustering (lines 140-156)**
- After storing keywords in Neo4j, embed them:
  ```
  await embedAndCacheKeywords(Array.from(allKeywords.keys()))
  ```
- Query back keywords with embeddings
- Run `clusterKeywords()` on them
- For each cluster, call Haiku to name it:
  ```
  const { data } = await generateStructured({
    model: 'haiku',
    system: 'Name this keyword cluster...',
    messages: [{ role: 'user', content: keywords.join(', ') }],
    schema: z.object({ name: z.string(), pillarTopic: z.string() })
  })
  ```
- Create `KeywordCluster` nodes with AI-generated names
- Link keywords via `BELONGS_TO` relationships

### Step 5: Update types — `src/types/index.ts`

Add optional `embedding` field to `Keyword` interface:
```typescript
export interface Keyword {
  // ... existing fields
  embedding?: number[];
}
```

### Step 6: Unit tests

**Create:** `tests/ai/embeddings.test.ts`
- Test `embedBatch` with mocked GoogleGenAI client
- Test `embedAndCacheKeywords` skips already-embedded keywords
- Test batch chunking (>100 texts)

**Create:** `tests/ai/clustering.test.ts`
- Test `clusterKeywords` with known vectors (3 tight clusters)
- Test `classifyIntentAI` with mocked generateStructured
- Test regex fallback on API failure
- Test edge case: <5 keywords (no clustering)

### Step 7: Commit and close Jira

```bash
git commit -m "feat: embeddings client + semantic keyword clustering (RT-12, RT-13)"
```

Transition RT-12 and RT-13 to Done.

## Parallel Execution Strategy

```
Step 1 (install deps)
  ↓
Step 2 (embeddings.ts) ←→ Step 5 (types update)  [parallel]
  ↓
Step 3 (clustering.ts)  — depends on Step 2 (imports embedBatch)
  ↓
Step 4 (modify keyword-research.ts) — depends on Steps 2+3
  ↓
Step 6 (tests) — two test files can run in parallel
  ↓
Step 7 (commit)
```

**Agent parallelization:**
- Agent A: Steps 2 + 5 (embeddings.ts + types update)
- Agent B: Step 3 (clustering.ts) — can start after Step 2 scaffolds the exports
- Main thread: Step 4 (workflow modification) after agents complete
- Agent C + D: Step 6 tests (parallel)

## Key Files

| File | Operation | Description |
|------|-----------|-------------|
| `package.json` | Modify | Add `@google/genai`, `ml-kmeans` |
| `src/lib/ai/embeddings.ts` | Create | Gemini embedding client with Neo4j cache |
| `src/lib/ai/clustering.ts` | Create | K-means clustering + AI intent classification |
| `src/lib/workflows/keyword-research.ts` | Modify | Replace regex intent + naive clustering |
| `src/types/index.ts` | Modify | Add `embedding?: number[]` to Keyword |
| `tests/ai/embeddings.test.ts` | Create | Embedding client tests |
| `tests/ai/clustering.test.ts` | Create | Clustering + intent tests |

## Risks and Mitigation

| Risk | Mitigation |
|------|------------|
| `GEMINI_API_KEY` not set | Same pattern as claude.ts — clear error, don't crash app |
| Neo4j Aura free tier doesn't support vector indexes | Store as plain property array; vector index is optional optimization for later |
| ml-kmeans poor cluster quality on small datasets | Skip clustering if <5 keywords, bounded k range |
| Haiku intent classification slower than regex | Batch 50 at once, regex fallback on failure |
| Embedding dimension mismatch if changed later | Store dimensions in a constant, document in cerebrum |

## Cost Estimate

- **Embeddings:** Gemini free tier covers 1500 req/min. At 100 keywords/request = 150,000 keywords/min free.
- **Intent classification:** ~$0.0003 per 50 keywords (Haiku). 1000 keywords = $0.006.
- **Cluster naming:** ~$0.0002 per cluster (Haiku). 10 clusters = $0.002.
- **Total per keyword research run:** ~$0.01 for 500 keywords.

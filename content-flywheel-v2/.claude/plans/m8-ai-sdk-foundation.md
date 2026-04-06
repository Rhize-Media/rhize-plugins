# M8 AI SDK Foundation — RT-10 + RT-11

> **Jira:** RT-10 (Install AI SDK dependencies) + RT-11 (Claude SDK wrapper with prompt caching)
> **Branch:** `feat/m8-ai-sdk-foundation`
> **Created:** 2026-04-06

## Goal

Install the Anthropic SDK and build a production-grade Claude client wrapper (`src/lib/ai/claude.ts`) with prompt caching, structured output, cost tracking via Neo4j, and exponential backoff. This is the foundation for all M8 AI features (RT-12 through RT-19).

## Architecture Decisions

1. **Direct Anthropic SDK** (not Vercel AI SDK) — we need fine-grained control over prompt caching (`cache_control`), token-level cost tracking, and model routing that the AI SDK abstracts away.
2. **Cost tracking in Neo4j** — `(:AIUsage)` nodes linked to content via `(:ContentPiece)-[:HAS_AI_USAGE]->(:AIUsage)`. Enables the cost dashboard (RT-18) and per-article cost attribution.
3. **Model routing** — Haiku 4.5 for cheap ops (classification, validation), Sonnet 4.6 for generation (outlines, drafts). Configurable per-call.
4. **Prompt caching** — `cache_control: { type: "ephemeral" }` on system prompts. Saves 90% on repeated calls within 5 min window.

## Steps

### Step 1: Install dependencies (RT-10)

```bash
npm install @anthropic-ai/sdk@latest
```

Add to `.env.local` and Vercel:
- `ANTHROPIC_API_KEY`

No embeddings provider yet — that's RT-12.

**Files modified:** `package.json`, `package-lock.json`

### Step 2: Create Claude client wrapper (RT-11)

**Create:** `src/lib/ai/claude.ts`

The wrapper exposes:

```typescript
// Core functions
generateText(params: GenerateTextParams): Promise<GenerateTextResult>
generateStructured<T>(params: GenerateStructuredParams<T>): Promise<T>

// Types
interface GenerateTextParams {
  model?: 'haiku' | 'sonnet'  // defaults to 'haiku'
  system: string | CacheableSystemMessage[]
  messages: MessageParam[]
  maxTokens?: number          // defaults to 1024
  temperature?: number        // defaults to 0.7
  contentId?: string          // optional: link usage to ContentPiece
}

interface GenerateTextResult {
  text: string
  usage: {
    inputTokens: number
    outputTokens: number
    cacheCreationInputTokens: number
    cacheReadInputTokens: number
    cost: number  // USD
  }
}

interface CacheableSystemMessage {
  type: 'text'
  text: string
  cache_control?: { type: 'ephemeral' }
}
```

Implementation details:
- Model map: `haiku` → `claude-haiku-4-5-20251001`, `sonnet` → `claude-sonnet-4-6-20250514`
- Cost calculation: per-model input/output/cache pricing from Anthropic docs
- `generateStructured<T>` uses tool-use pattern (single tool with JSON schema) for guaranteed structured output
- Exponential backoff: retry on 429/529 with 1s, 2s, 4s delays (max 3 retries)
- Records `(:AIUsage {model, inputTokens, outputTokens, cacheCreation, cacheRead, cost, createdAt})` node in Neo4j
- If `contentId` provided: `(ContentPiece)-[:HAS_AI_USAGE]->(AIUsage)`

### Step 3: Add Neo4j schema for AIUsage

**Modify:** `cypher/schema.cypher`

```cypher
CREATE CONSTRAINT ai_usage_id IF NOT EXISTS FOR (a:AIUsage) REQUIRE a.id IS UNIQUE;
```

### Step 4: Add AIUsage types

**Modify:** `src/types/index.ts`

Add `AIUsage` interface and update `ContentPiece` to include optional `aiUsage` field.

### Step 5: Unit tests

**Create:** `tests/ai/claude.test.ts`

- Test `generateText` with mocked Anthropic client
- Test `generateStructured` returns parsed JSON
- Test retry logic on 429 errors
- Test cost calculation accuracy
- Test Neo4j usage recording (mock driver)

### Step 6: Commit and close Jira

```bash
git add -A
git commit -m "feat: add Anthropic SDK + Claude wrapper with prompt caching (RT-10, RT-11)"
```

Transition RT-10 and RT-11 to Done.

## Dependencies

- **Requires:** Neo4j Aura instance (already provisioned: `ec4405e5`)
- **Requires:** `ANTHROPIC_API_KEY` in `.env.local`
- **Blocks:** RT-12 (embeddings), RT-13 (clustering), RT-14-17 (AI workflows), RT-18 (cost dashboard)

## Risk

- **API key not set:** Wrapper should fail gracefully with clear error if `ANTHROPIC_API_KEY` is missing, not crash the app.
- **Cost tracking accuracy:** Anthropic pricing changes — store raw token counts, calculate cost at read time rather than write time. Actually: store both for simplicity, recalculate in dashboard if needed.

## Estimated Tokens

~3000 tokens for `claude.ts`, ~1500 for tests, ~200 for types/schema updates.

# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-06

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** content-flywheel
- **Description:** This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).
- **Neo4j relationships:** All node connections MUST use graph relationships, never property-based foreign keys. Use `OPTIONAL MATCH` + `FOREACH/CASE` pattern for conditional relationship creation when the source node may be null.
- **WorkflowRun linking:** Every workflow uses `HAS_WORKFLOW_RUN` relationship to link to ContentPiece or Competitor.
- **Stage transitions:** `moveContentToStage` archives old `IN_STAGE` as `WAS_IN_STAGE` with timestamps before creating new one.
- **Graph stats:** `getGraphStats` uses `UNION ALL` single queries instead of N+1 loops.
- **Author nodes:** Created automatically via `MERGE` when creating ContentPiece — `(Author)-[:WROTE]->(ContentPiece)`.
- **Worktree agents:** Changes made by worktree-isolated agents DO persist to the main working directory files even after worktree cleanup. The branches may not survive but file edits do.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-04-06] Duplicate relationship type in getGraphStats relTypes array. `RANKS_FOR` appeared both as an original entry and was re-added when adding new types. UNION ALL queries with duplicate clauses double-count. Always check for existing entries before appending to arrays.

## Key Learnings (continued)

- **Anthropic SDK Usage type:** `cache_creation_input_tokens` and `cache_read_input_tokens` are directly on the `Usage` interface as `number | null` — no need for `Record<string, number>` casting.
- **Structured output:** Use `messages.parse()` + `zodOutputFormat()` from `@anthropic-ai/sdk/helpers/zod` — not the old tool-use hack. Requires `zod` as dependency.
- **SDK retry:** Anthropic SDK has built-in `maxRetries` option (default 2). No need for custom exponential backoff.
- **AIUsage nodes:** `(:AIUsage {id, model, inputTokens, outputTokens, cacheCreationInputTokens, cacheReadInputTokens, cost, createdAt})` linked via `(ContentPiece)-[:HAS_AI_USAGE]->(AIUsage)`.

- **Google GenAI SDK:** `@google/generative-ai` is deprecated. Use `@google/genai` with `GoogleGenAI` class. Embedding API: `ai.models.embedContent({ model: 'text-embedding-004', contents: [...], config: { outputDimensionality: 256 } })`.
- **ml-kmeans:** Named export `{ kmeans }`, not default export. Options: `{ initialization: "kmeans++", maxIterations: 100 }`. Returns `{ clusters: number[] }`.
- **Neo4j batch writes:** Use `UNWIND $entries AS entry` for batch writes instead of N individual `session.run()` calls — fewer round-trips, simpler code.
- **classifyIntent replacement:** `replace_all` on `Edit` only matches exact strings. When a function is called with different argument names (`item.keyword` vs `kw.keyword` vs `kd.keyword`), each call site needs individual replacement.
- **Firecrawl package:** The npm package is `firecrawl` (not `firecrawl-js` or `@mendable/firecrawl-js`). Main class: `Firecrawl`. Method: `.scrape(url, { formats: ["markdown"] })` returns `{ markdown, metadata }`.
- **Outline sections storage:** Neo4j doesn't support nested objects. Store `sections` as a JSON string, parse on read. Use `JSON.stringify(data.sections)` on write.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-04-06] Direct Anthropic SDK over Vercel AI SDK: Chose `@anthropic-ai/sdk` directly because we need `cache_control` for prompt caching, per-token cache metrics, `messages.parse()` for structured output, and custom Neo4j cost tracking. AI SDK abstracts these away.
- [2026-04-06] Graph relationship overhaul: Replaced property-based foreign keys with proper Neo4j relationships across all 6 workflows, queries, adapters, and webhooks. Added 9 new relationship types (HAS_WORKFLOW_RUN, HAS_AI_VISIBILITY, WAS_IN_STAGE, FOR_KEYWORD, RELATED_TO, AUDITS, WROTE, EXPERT_IN, RANKS_FOR for competitors). Chose UNION ALL single query over N+1 for graph stats. Used FOREACH/CASE pattern for conditional relationship creation to avoid separate queries.

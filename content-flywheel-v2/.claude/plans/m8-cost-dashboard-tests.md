# M8 Cost Dashboard + Test Completion — RT-18 + RT-19

> **Jira:** RT-18 (AI cost tracking dashboard) + RT-19 (Unit tests for AI workflows)
> **Depends on:** RT-11 (AIUsage nodes), RT-16 (Draft cost tracking) — both completed
> **Created:** 2026-04-06

## Goal

1. **RT-18**: Add cost aggregation query + cost panel to the graph explorer page — total cost, cost per article, cost by model, cache savings.
2. **RT-19**: Close the test gap — add helpers.ts tests + any missing edge cases. Already have 44 tests covering AI modules and workflows.

## Assessment

**RT-19 is largely done.** The plan expected tests in `tests/lib/ai/` but we already have comprehensive tests:
- `tests/ai/claude.test.ts` (13) — cost calc, generateText, generateStructured, caching
- `tests/ai/embeddings.test.ts` (6) — batch embedding, Neo4j cache
- `tests/ai/clustering.test.ts` (12) — k-means, intent classification, cluster naming
- `tests/workflows/*.test.ts` (13) — all 4 new workflows
- **Gap:** `src/lib/workflows/helpers.ts` has no dedicated tests (tested indirectly through workflow tests)

## Steps

### Step 1: Add getCostStats query to queries.ts

```typescript
export async function getCostStats(): Promise<CostStats> {
  // Query AIUsage nodes:
  // - Total cost (all time, last 7 days, last 30 days)
  // - Cost by model (haiku vs sonnet)
  // - Cost per content piece (top 10 most expensive)
  // - Cache savings: sum(cacheReadInputTokens) * model pricing
  // - Total tokens: input + output + cache
}
```

### Step 2: Extend graph stats API to include cost data

Modify `src/app/api/graph/stats/route.ts` to call `getCostStats()` alongside `getGraphStats()` and merge results.

### Step 3: Add cost panel to graph explorer page

Modify `src/app/graph/page.tsx` — add a "AI Cost Tracking" card with:
- Total spend last 30 days
- Cost by model (Haiku vs Sonnet breakdown)
- Top 5 most expensive content pieces
- Cache savings percentage
- Total tokens used

### Step 4: Add helpers.ts tests

Create `tests/workflows/helpers.test.ts`:
- Test createWorkflowRun with optional vs required content
- Test completeWorkflowRun sets correct fields
- Test failWorkflowRun extracts error message

### Step 5: Verify build + tests, commit, close Jira

## Key Files

| File | Operation | Description |
|------|-----------|-------------|
| `src/lib/neo4j/queries.ts` | Modify | Add getCostStats() + CostStats type |
| `src/app/api/graph/stats/route.ts` | Modify | Include cost data in response |
| `src/app/graph/page.tsx` | Modify | Add cost tracking card |
| `tests/workflows/helpers.test.ts` | Create | Workflow helpers tests |

## Cost Estimate

No AI costs — this is purely queries + UI.

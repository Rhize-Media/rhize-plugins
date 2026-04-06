# Neo4j Graph Relationship Enhancements — Implementation Plan

**Date:** 2026-04-06
**Scope:** 10 enhancement items from graph relationship review
**Approach:** 6 parallel work streams with dependency ordering

---

## Architecture Overview

### Current State
- 9 declared relationship types, several never written
- 5 orphaned/disconnected node types (WorkflowRun, Competitor, Author, SiteAudit, AIVisibilitySnapshot)
- Property-based lookups where relationships should exist
- No temporal history on pipeline stage transitions
- N+1 query pattern in graph stats

### Target State
- 15+ active relationship types, all backed by schema constraints/indexes
- Zero orphaned nodes — every node reachable via traversal
- Graph-native queries replacing property-based filtering
- Stage transition audit trail
- Single-query graph stats

---

## Dependency Graph

```
Stream A (Schema + Types) ──────────────────────┐
  Must complete BEFORE all other streams         │
                                                 ▼
┌─────────────────────┬──────────────────────┬───────────────────┐
│ Stream B            │ Stream C             │ Stream D          │
│ Workflow Fixes      │ Query Layer + API    │ Adapter Integration│
│ (6 parallel agents) │ (sequential)         │ (2 parallel agents)│
└─────────┬───────────┴──────────┬───────────┴─────────┬─────────┘
          │                      │                     │
          ▼                      ▼                     ▼
     Stream E (Frontend — depends on B + C completing)
          │
          ▼
     Stream F (Author Activation — independent, lowest priority)
```

---

## Stream A: Schema & Types Foundation

**Mode:** Sequential (must complete before other streams)
**Agent:** Single agent, no parallelism — changes are interdependent
**Files:**
- `cypher/schema.cypher`
- `src/types/index.ts`

### A1. Update Graph Schema (`cypher/schema.cypher`)

Add new constraints:
```cypher
CREATE CONSTRAINT site_audit_id IF NOT EXISTS
FOR (a:SiteAudit) REQUIRE a.id IS UNIQUE;
```

Add new indexes:
```cypher
CREATE INDEX workflow_run_content IF NOT EXISTS
FOR (w:WorkflowRun) ON (w.contentId);

CREATE INDEX ai_vis_content IF NOT EXISTS
FOR (a:AIVisibilitySnapshot) ON (a.contentId);

CREATE INDEX serp_keyword IF NOT EXISTS
FOR (ss:SERPSnapshot) ON (ss.keywordId);
```

**No new constraints needed for relationships** — Neo4j doesn't support relationship property uniqueness constraints in Community/Aura.

### A2. Update TypeScript Types (`src/types/index.ts`)

Add to `ContentPiece`:
```typescript
// No changes to ContentPiece interface itself — relationships are graph-level
```

Add new types:
```typescript
export interface StageTransition {
  from: PipelineStage;
  to: PipelineStage;
  transitionedAt: string;
}
```

Update `WorkflowRun` to note it will have a relationship (documentation only — the interface stays the same).

### A3. Verification
- Run `npm run init-schema` to apply schema changes
- Run `npm run build` to verify types compile

---

## Stream B: Workflow Relationship Fixes

**Mode:** 6 parallel agents (one per workflow file) — each workflow is isolated
**Depends on:** Stream A complete
**Agent type:** `code-simplifier` or general-purpose with edit permissions

Each agent gets the same brief: "Add graph relationships to replace property-based references. Use `MERGE` for idempotent relationship creation. Keep existing functionality intact."

### B1. `keyword-research.ts` (Agent 1)

**File:** `src/lib/workflows/keyword-research.ts`

Changes:
1. **WorkflowRun relationship** (lines 32-39): After creating the WorkflowRun node, if `contentId` provided, add:
   ```cypher
   MATCH (c:ContentPiece {id: $contentId})
   CREATE (c)-[:HAS_WORKFLOW_RUN]->(w)
   ```

2. **Keyword-to-Keyword relationships** (lines 83-100): When processing `relatedKeywords()` results, create:
   ```cypher
   MERGE (k1:Keyword {term: $term1})
   MERGE (k2:Keyword {term: $term2})
   MERGE (k1)-[:RELATED_TO {score: $score}]->(k2)
   ```
   Extract the `related_keywords` items which include both the source keyword and related keyword with a relevance score.

3. **Competitor-to-Keyword relationships** (lines 166-193): When storing gap keywords, link competitor to keyword:
   ```cypher
   MATCH (comp:Competitor {domain: $compDomain})
   MERGE (k:Keyword {term: $term})
   MERGE (comp)-[:RANKS_FOR]->(k)
   ```

### B2. `content-optimize.ts` (Agent 2)

**File:** `src/lib/workflows/content-optimize.ts`

Changes:
1. **WorkflowRun relationship** (lines 24-30): Same pattern as B1.

2. **Populate LINKS_TO** (new, after line 120): The on-page crawl data includes internal links. Parse `pageData` for internal link URLs and create:
   ```cypher
   MATCH (c:ContentPiece {id: $contentId})
   MATCH (target:ContentPiece {url: $targetUrl})
   MERGE (c)-[:LINKS_TO]->(target)
   ```
   Only link to ContentPiece nodes that already exist in the graph.

3. **Fix stage advancement** (lines 124-133): The current query sets `c.stage = "review"` as a property BUT also creates an `IN_STAGE` relationship without deleting the old one. Should delete old `IN_STAGE` first (same pattern as `moveContentToStage`).

### B3. `serp-analysis.ts` (Agent 3)

**File:** `src/lib/workflows/serp-analysis.ts`

Changes:
1. **WorkflowRun relationship** (lines 34-39): Same pattern.

2. **SERPSnapshot-to-Keyword relationship** (lines 133-155): When creating a SERPSnapshot, also create:
   ```cypher
   MATCH (k:Keyword {id: $keywordId})
   CREATE (snap)-[:FOR_KEYWORD]->(k)
   ```

### B4. `backlink-analysis.ts` (Agent 4)

**File:** `src/lib/workflows/backlink-analysis.ts`

Changes:
1. **WorkflowRun relationship** (lines 39-45): Same pattern.

2. **Competitor-to-BacklinkSource relationship** (after line 130): When we know a referring domain also links to a competitor:
   ```cypher
   MERGE (comp:Competitor {domain: $analyzedDomain})
   MERGE (comp)-[:HAS_BACKLINK_FROM]->(b:BacklinkSource {domain: $refDomain})
   ```

### B5. `ai-visibility.ts` (Agent 5)

**File:** `src/lib/workflows/ai-visibility.ts`

Changes:
1. **WorkflowRun relationship** (lines 34-39): Same pattern.

2. **Fix HAS_AI_VISIBILITY creation** (lines 147-153): The current MERGE is fragile — it matches on `contentId` property + `query` + `llm` which could match stale snapshots. Instead, create the relationship in the same query that creates the snapshot:
   ```cypher
   MATCH (c:ContentPiece {id: $contentId})
   CREATE (a:AIVisibilitySnapshot { ... })
   CREATE (c)-[:HAS_AI_VISIBILITY]->(a)
   ```
   Single query instead of two.

### B6. `site-audit.ts` (Agent 6)

**File:** `src/lib/workflows/site-audit.ts`

Changes:
1. **WorkflowRun relationship** (lines 38-43): Same pattern (no contentId for site-audit, but link to domain's Competitor node).

2. **SiteAudit-to-Competitor relationship** (lines 210-229): Link audit to a domain node:
   ```cypher
   MERGE (comp:Competitor {domain: $domain})
   CREATE (a:SiteAudit { ... })
   CREATE (a)-[:AUDITS]->(comp)
   ```

3. **Populate LINKS_TO for discovered pages** (lines 232-243): When creating ContentPiece nodes from crawl data, also create internal link relationships if the crawl data provides link targets.

---

## Stream C: Query Layer & API Updates

**Mode:** Sequential — queries depend on each other and on Stream A+B patterns
**Depends on:** Stream A complete (can start in parallel with Stream B using new relationship types)
**Files:**
- `src/lib/neo4j/queries.ts`
- `src/app/api/content/[id]/route.ts`
- `src/app/api/graph/stats/route.ts`

### C1. Add `moveContentToStage` Stage Transition History

**File:** `src/lib/neo4j/queries.ts` (lines 75-94)

Before deleting the old `IN_STAGE`, archive it:
```cypher
MATCH (c:ContentPiece {id: $contentId})-[r:IN_STAGE]->(oldStage:PipelineStage)
CREATE (c)-[:WAS_IN_STAGE {
  stage: oldStage.name,
  enteredAt: r.enteredAt,
  leftAt: datetime()
}]->(oldStage)
DELETE r
WITH c
MATCH (s:PipelineStage {name: $newStage})
CREATE (c)-[:IN_STAGE {enteredAt: datetime()}]->(s)
SET c.updatedAt = datetime()
```

Also update `createContent` to add `enteredAt` property to the initial `IN_STAGE` relationship.

### C2. Update `getContentDetailById` Query

**File:** `src/lib/neo4j/queries.ts` (lines 135-169)

Add to the existing query:
```cypher
OPTIONAL MATCH (c)-[:HAS_WORKFLOW_RUN]->(w:WorkflowRun)
OPTIONAL MATCH (c)-[:HAS_AI_VISIBILITY]->(av:AIVisibilitySnapshot)
OPTIONAL MATCH (c)-[:WAS_IN_STAGE]->(ps:PipelineStage)
```

Return additional fields:
```cypher
collect(DISTINCT w { .id, .type, .status, .summary, .startedAt }) AS workflowRuns,
collect(DISTINCT av { .llm, .mentionRate, .accuracy, .citationCount, .date }) AS aiVisibility,
collect(DISTINCT { stage: ps.name, enteredAt: ... , leftAt: ... }) AS stageHistory
```

### C3. Fix `getGraphStats` N+1 Queries

**File:** `src/lib/neo4j/queries.ts` (lines 246-343)

Replace the 18 sequential queries with 2 aggregate queries:

```cypher
// Node counts — single query
CALL {
  MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
}
RETURN label, count ORDER BY label

// Relationship counts — single query
CALL {
  MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count
}
RETURN type, count ORDER BY type
```

Add new relationship types to the tracked list:
- `HAS_WORKFLOW_RUN`
- `HAS_AI_VISIBILITY`
- `WAS_IN_STAGE`
- `FOR_KEYWORD`
- `RELATED_TO`
- `RANKS_FOR` (Competitor variant)
- `AUDITS`

### C4. Add New Query Functions

```typescript
// Get stage transition history for a content piece
export async function getStageHistory(contentId: string): Promise<StageTransition[]>

// Get content pieces with no workflows (stale content)
export async function getStaleContent(): Promise<ContentPiece[]>

// Get keyword relationship graph (for cluster visualization)
export async function getKeywordGraph(clusterId: string): Promise<{nodes: Keyword[], edges: {from: string, to: string, score: number}[]}>

// Get competitor overlap for a content piece
export async function getCompetitorOverlap(contentId: string): Promise<{competitor: string, sharedKeywords: string[]}[]>
```

---

## Stream D: Adapter Integration

**Mode:** 2 parallel agents (Sanity + GHL are independent)
**Depends on:** Stream A complete
**Files:**
- `src/lib/adapters/cms/sanity.ts`
- `src/lib/adapters/distribution/ghl.ts`
- `src/app/api/webhooks/sanity/route.ts`
- `src/app/api/webhooks/ghl/route.ts`
- `src/app/api/publish/sanity/route.ts`
- `src/app/api/publish/social/route.ts`

### D1. Sanity Adapter + Webhook (Agent 1)

**File:** `src/lib/adapters/cms/sanity.ts`

After successful publish, record in graph:
```cypher
MATCH (c:ContentPiece {id: $contentId})
MERGE (t:CMSTarget {type: "sanity", projectId: $projectId})
ON CREATE SET t.id = randomUUID(), t.dataset = $dataset
MERGE (c)-[:PUBLISHED_TO {publishedAt: datetime(), documentId: $sanityDocId}]->(t)
```

**File:** `src/app/api/webhooks/sanity/route.ts`

When receiving a publish webhook, ensure the `PUBLISHED_TO` relationship exists.
When receiving an unpublish webhook, remove the relationship or mark it with `unpublishedAt`.

### D2. GHL Adapter + Webhook (Agent 2)

**File:** `src/lib/adapters/distribution/ghl.ts`

After successful post scheduling:
```cypher
MATCH (c:ContentPiece {id: $contentId})
MERGE (d:DistributionChannel {type: "ghl", platform: $platform})
ON CREATE SET d.id = randomUUID(), d.accountId = $locationId
CREATE (c)-[:DISTRIBUTED_TO {scheduledAt: datetime(), postId: $postId, status: $status}]->(d)
```

**File:** `src/app/api/webhooks/ghl/route.ts`

When receiving a post-published webhook, update the `DISTRIBUTED_TO` relationship status.

---

## Stream E: Frontend Updates

**Mode:** Sequential (single agent modifying connected UI components)
**Depends on:** Streams B + C complete
**Files:**
- `src/app/content/[id]/page.tsx`
- `src/app/graph/page.tsx`

### E1. Content Detail Page Enhancements

**File:** `src/app/content/[id]/page.tsx`

Add new sections (after existing sections):

1. **Workflow History section** — table showing all workflow runs for this content (type, status, summary, date)
2. **AI Visibility section** — cards showing mention rate, accuracy, citation count per LLM
3. **Stage History section** — timeline showing progression through pipeline stages with durations
4. **AI Visibility workflow button** — add to the workflow actions section (currently missing)

Update the `ContentDetail` interface to include new fields from C2.

### E2. Graph Explorer Enhancements

**File:** `src/app/graph/page.tsx`

1. Add new relationship types to the relationship counts display
2. Add a "Content Health" section showing:
   - Content with no workflows run
   - Content stuck in a stage > 14 days
   - Content with declining SERP positions
3. Add a "Competitive Overlap" section showing keyword competition data

---

## Stream F: Author Activation

**Mode:** Single agent, lowest priority — can be deferred
**Depends on:** Stream A complete
**Files:**
- `cypher/schema.cypher` (already updated in A1)
- `src/lib/neo4j/queries.ts`
- `src/app/api/content/route.ts` (POST — create content)
- `src/app/board/page.tsx` (create content modal)

### F1. Author Node Management

Add query functions:
```typescript
export async function getOrCreateAuthor(name: string): Promise<Author>
export async function linkAuthorToContent(authorId: string, contentId: string): Promise<void>
export async function linkAuthorExpertise(authorId: string, clusterId: string): Promise<void>
```

### F2. Update Content Creation Flow

When creating a ContentPiece, also:
```cypher
MERGE (a:Author {name: $author})
ON CREATE SET a.id = randomUUID(), a.expertise = []
CREATE (a)-[:WROTE]->(c)
```

### F3. Author Expertise from Keyword Clusters

After keyword research runs, if content has an author, link author to the keyword cluster:
```cypher
MATCH (c:ContentPiece {id: $contentId})-[:TARGETS]->(k:Keyword)-[:BELONGS_TO]->(cl:KeywordCluster)
MATCH (a:Author)-[:WROTE]->(c)
MERGE (a)-[:EXPERT_IN]->(cl)
```

---

## Execution Strategy: Agent Dispatch Plan

### Phase 1: Foundation (Stream A) — Single Agent, ~15 min
```
Agent: general-purpose (sequential)
Tasks: A1, A2, A3
Verification: build + schema init
```

### Phase 2: Core Enhancements (Streams B + C + D) — 8 Parallel Agents, ~30 min
```
Agent B1: keyword-research.ts fixes (worktree isolation)
Agent B2: content-optimize.ts fixes (worktree isolation)
Agent B3: serp-analysis.ts fixes (worktree isolation)
Agent B4: backlink-analysis.ts fixes (worktree isolation)
Agent B5: ai-visibility.ts fixes (worktree isolation)
Agent B6: site-audit.ts fixes (worktree isolation)
Agent C:  queries.ts + API routes (main branch, after A merges)
Agent D1: Sanity adapter + webhook (worktree isolation)
Agent D2: GHL adapter + webhook (worktree isolation)
```

**Merge strategy:** Each worktree agent produces a branch. Merge B1-B6 first (no conflicts — separate files), then C (depends on B's relationship patterns), then D1+D2.

### Phase 3: Frontend (Stream E) — Single Agent, ~20 min
```
Agent: general-purpose (sequential, after B+C merge)
Tasks: E1, E2
Verification: build + visual check
```

### Phase 4: Author Activation (Stream F) — Single Agent, ~15 min
```
Agent: general-purpose (sequential)
Tasks: F1, F2, F3
Verification: build + seed test
```

---

## Test Strategy

### Unit Tests (extend existing `tests/`)
- `tests/lib/neo4j/queries.test.ts` — new query functions, stage transition history
- `tests/lib/workflows/*.test.ts` — verify each workflow creates expected relationships (mock Neo4j)

### Integration Tests (manual via seed script)
1. Run `npm run seed` with enhanced seed data
2. Run each workflow via API
3. Verify graph structure via `/api/graph/stats`
4. Verify content detail page shows all new sections

### Cypher Verification Queries
```cypher
// Verify no orphaned WorkflowRuns
MATCH (w:WorkflowRun) WHERE NOT (w)<-[:HAS_WORKFLOW_RUN]-() RETURN count(w)

// Verify no orphaned Competitors
MATCH (c:Competitor) WHERE NOT (c)-[]-() RETURN count(c)

// Verify keyword relationships exist
MATCH ()-[r:RELATED_TO]->() RETURN count(r)

// Verify stage history
MATCH ()-[r:WAS_IN_STAGE]->() RETURN count(r)
```

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Existing data has orphaned WorkflowRuns | Medium | Migration script to retroactively link via `contentId` property |
| RELATED_TO volume (could be thousands) | Low | Limit to top 10 related keywords per seed in keyword-research |
| Stage transition breaks existing IN_STAGE queries | High | Add `enteredAt` with default `datetime()` for existing relationships |
| Worktree merge conflicts in queries.ts | Medium | Stream C works on main after B merges; no parallel edits to queries.ts |
| Neo4j Aura query timeout on large graphs | Low | Batch relationship creation in chunks of 50 |

---

## Data Migration Script (Post-Implementation)

Run once to backfill existing data:
```cypher
// Link orphaned WorkflowRuns to their ContentPiece
MATCH (w:WorkflowRun) WHERE w.contentId IS NOT NULL AND NOT (w)<-[:HAS_WORKFLOW_RUN]-()
MATCH (c:ContentPiece {id: w.contentId})
CREATE (c)-[:HAS_WORKFLOW_RUN]->(w)

// Add enteredAt to existing IN_STAGE relationships
MATCH ()-[r:IN_STAGE]->() WHERE r.enteredAt IS NULL
SET r.enteredAt = datetime()

// Link orphaned AIVisibilitySnapshots
MATCH (a:AIVisibilitySnapshot) WHERE a.contentId IS NOT NULL AND NOT (a)<-[:HAS_AI_VISIBILITY]-()
MATCH (c:ContentPiece {id: a.contentId})
CREATE (c)-[:HAS_AI_VISIBILITY]->(a)
```

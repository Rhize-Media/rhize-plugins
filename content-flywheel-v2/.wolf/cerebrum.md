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

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-04-06] Graph relationship overhaul: Replaced property-based foreign keys with proper Neo4j relationships across all 6 workflows, queries, adapters, and webhooks. Added 9 new relationship types (HAS_WORKFLOW_RUN, HAS_AI_VISIBILITY, WAS_IN_STAGE, FOR_KEYWORD, RELATED_TO, AUDITS, WROTE, EXPERT_IN, RANKS_FOR for competitors). Chose UNION ALL single query over N+1 for graph stats. Used FOREACH/CASE pattern for conditional relationship creation to avoid separate queries.

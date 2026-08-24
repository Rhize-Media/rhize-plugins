# Dependency Graph and Semantic Impact Mapping

> **Status:** Stable foundation v2
> **Last Updated:** 2026-08-16
> **Runtime owner:** `rhize-context-manager/commands/impact-map.md`
> **Optional dependency:** CodeGraph CLI or MCP

## Purpose

Impact analysis answers two different questions that should not be collapsed into one artifact:

1. **What does the code depend on today?**
2. **What behavior should this change, preserve, or introduce?**

CodeGraph answers the first question efficiently. A semantic impact map answers the second. The
workflow is reliable only when both are used for their own purpose and reconciled after the code
changes.

## Authority Boundary

- **CodeGraph is authoritative for current structural truth:** existing symbols, imports, callers,
  callees, references, test links, and supported dynamic-dispatch paths.
- **The impact map is authoritative for intended change:** product behavior, data meaning, scope,
  invariants, new symbols, operational effects, risks, and acceptance tests.
- Tests and runtime evidence remain authoritative for correctness. Neither a graph nor a plan
  proves authorization, transaction ordering, cache timing, concurrency, or external behavior.

This avoids two common failures:

- A hand-written dependency dump immediately drifts and adds little beyond CodeGraph.
- A graph-only plan misses business semantics, planned code, migrations, deployment order, and
  must-not-change boundaries.

## Trigger Conditions

Apply this foundation before implementing or materially changing:

- features, fixes, or refactors;
- schemas, migrations, or data ownership;
- cache or query-key behavior;
- authorization or lifecycle transitions;
- jobs, events, APIs, or cross-repository contracts.

Small documentation-only or formatting changes do not need a full map unless repository rules say
otherwise.

## CodeGraph-first Discovery

For each repository root:

1. Check whether `.codegraph/` exists.
2. When it exists, prefer the CodeGraph MCP interface. Use exposed health/status metadata; if the
   interface only explores, a successful indexed query is availability evidence. A missing, stale,
   corrupt, or failed MCP response triggers the fallback.
3. Otherwise use the CLI only after `command -v codegraph` succeeds. Require a zero-exit
   `codegraph status` before shell graph queries. Synchronize a stale existing index and repeat
   status before trusting it.
4. If neither interface is available, status or synchronization fails, or the index is missing or
   corrupt, record the exact condition and use `rg` plus targeted reads. Do not require a shell
   preflight when MCP is the active interface.
5. When `.codegraph/` does not exist, do not initialize it without the repository owner's decision;
   use the same fallback.
6. Treat separate frontend/backend/service repositories as separate graphs joined by an explicitly
   mapped API, event, schema, or data contract.

Useful structural queries include:

```bash
codegraph status
codegraph explore "<behavior, symbols, callers, and tests>"
codegraph impact <symbol>
codegraph affected <files>
```

CodeGraph output is evidence, not the impact map itself. Capture the relevant entry points and
relationships without pasting the complete graph.

## Semantic Analysis

After structural discovery, describe the intended delta across these dimensions:

### Behavior and data meaning

- What user-visible or system behavior changes?
- What is the correct data scope: tenant, season, account, team, order, time range, or lifecycle?
- Does historical attribution differ from current ownership?
- Which source system owns the truth?

### Invariants

- What must always be true before and after the change?
- Which state transitions require dedicated commands?
- What must be atomic, idempotent, serialized, or fail closed?
- Which authorization boundary controls the transition?

### Operational effects

- Are migrations, backfills, repair scripts, queues, caches, search indexes, analytics, or
  deployments involved?
- Is deployment order significant across repositories?
- Which external systems or environment settings are invisible to the source graph?

### Explicit non-effects

- Which nearby path must retain its existing scope or behavior?
- Which historical data must not be rewritten?
- Which unrelated files, migrations, or customer records are out of scope?

## Minimal Impact Map Contract

A useful map contains:

1. **Current behavior and evidence** — observed behavior plus concise graph/source evidence.
2. **Intended semantic delta** — what changes for users, data, or system behavior.
3. **Invariants and must-not-change boundaries** — correctness and scope constraints.
4. **Current structural touchpoints** — relevant repositories, entry points, owners, callers, and
   tests.
5. **Planned additions and deletions** — code that cannot appear in the pre-change graph.
6. **External and operational effects** — data, cache, jobs, deployment, or repair work.
7. **Reuse opportunities** — component registry or an existing implementation.
8. **Acceptance tests** — observable success, boundary, failure, and concurrency cases.
9. **Explicitly unaffected paths** — nearby behavior protected from scope creep.
10. **Unknowns and confidence** — graph blind spots, assumptions, and verification method.
11. **Implementation order** — test-first steps organized by real dependency.

Do not require a repository-root `IMPACT_MAP.md`. Persist the map in the project's prescribed plan
location only when instructions require it or the work must survive a session boundary; otherwise
the active plan or response is sufficient.

## Execution and Reconciliation

1. Write the smallest failing contract or acceptance test.
2. Implement the source-system change.
3. Update integrations, cache invalidation, and UI only as required by the semantic delta.
4. Run focused and repository-required validation.
5. For every repository root, repeat the same discovery branch used before implementation.
6. For a healthy existing CodeGraph index, synchronize it and repeat the original structural
   queries against the completed source. Use MCP synchronization/health operations when exposed,
   otherwise the available CLI; if the index cannot be refreshed, record it as stale and take the
   fallback branch.
7. For a fallback root, repeat the original `rg` queries and targeted reads; map the actual changed
   files, their consumers, and tests. Absence of a graph is not evidence of synchronization.
8. Compare the structural evidence, actual diff, tests, and impact map.
9. Update the map when implementation evidence changed the plan.

The final verdict is:

- `IN_SYNC` — structural evidence (CodeGraph or fallback), diff, tests, and semantic map agree.
- `IN_SYNC_WITH_EXCEPTIONS` — named generated, dynamic, or external edges use manual evidence.
- `OUT_OF_SYNC` — an unexplained change, missing consumer, stale graph, or unverified invariant
  remains.

Completion requires resolving `OUT_OF_SYNC`; it is not a documentation warning.

## Known Graph Blind Spots

Manually verify:

- dynamic imports, reflection, dependency injection, and runtime registries;
- generated files and schema-derived clients;
- SQL triggers, database constraints, and migrations;
- environment-dependent behavior and feature flags;
- cache invalidation timing and transaction boundaries;
- remote APIs, queues, webhooks, analytics, and deployment configuration;
- data semantics such as historical attribution versus current ownership.

## Anti-Patterns

- Manually recreating the full current caller graph in Markdown.
- Installing or initializing CodeGraph without user/project authorization.
- Using `grep -r` instead of CodeGraph or `rg`.
- Assuming a pre-change graph can contain a planned route, migration, or symbol.
- Treating graph completeness as proof of runtime correctness.
- Mapping only one repository in a multi-service change.
- Leaving the map unreconciled after implementation.

## Relationship to Other Rhize Workflows

- **Runtime command:** `/rhize-devflow:impact-map` executes this protocol (Dev Flow owns the
  canonical implementation; `rhize-context-manager`'s `/impact-map` is a deprecation adapter
  pointing here for the 2.12.0 compatibility window only).
- **Component Registry:** identifies existing code to reuse after structural discovery.
- **Regression Prevention:** turns affected behavior and invariants into required tests.
- **Data Mutation Consistency:** deepens cache, query-key, transaction, and lifecycle analysis.
- **Error Lifecycle Management:** adds production evidence before mapping a defect fix.
- **Done/Review:** verifies the reconciliation verdict before release.

## Effectiveness Measures

Measure outcomes rather than map length:

- unexplained production files in the final diff;
- consumers discovered only after implementation;
- map-to-diff deviations without recorded rationale;
- follow-up fixes caused by missed scope or invariants;
- time spent regenerating dependency lists already available from CodeGraph.

## Changelog

| Version | Date | Changes |
|---|---|---|
| v2 | 2026-08-16 | Made CodeGraph the current-structure source, impact maps the semantic-delta source, and added post-implementation reconciliation. |
| v1 | 2024-12-01 | Initial file and data dependency concept. |

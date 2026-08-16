---
description: CodeGraph-first impact mapping that separates current dependency truth from the intended semantic change
---
<!-- canonical: rhize-devflow:impact-map -->

# Impact Map

Map a change before implementation, then reconcile the completed diff against the same evidence.

## Core Contract

- **CodeGraph is authoritative for current structural truth:** symbols, callers, callees,
  references, tests, and dependency paths that exist now.
- **The impact map is authoritative for intended change:** business behavior, data scope,
  invariants, planned symbols, operational effects, risks, and acceptance criteria.
- Do not copy CodeGraph's full dependency output into the map. Record only the relevant evidence
  and the semantic delta the graph cannot express.
- Label facts as **evidence**, **inference**, or **planned**. Never present an inferred edge as a
  confirmed caller.

## Triggers

Use before implementing or materially changing a feature, bug fix, refactor, schema, migration,
cache path, authorization rule, external integration, or cross-repository contract.

## Phase 1: Establish Scope and Repository Rules

1. Read repository instructions and required context files.
2. Check Git state and preserve unrelated work.
3. Identify every repository root involved. A frontend/backend workspace is two graphs, not one.
4. Check `COMPONENT_REGISTRY.md` or the project's equivalent when present.
5. State the requested outcome and any ambiguity that would materially change implementation.

Do not write implementation code yet. Follow the repository's confirmation rule: present the map
and pause only when confirmation is required or a material product choice remains unresolved.
Existing explicit implementation authorization is not invalidated by this command.

## Phase 2: Discover Current Structural Truth

Run this decision for **each repository root**.

### When `.codegraph/` exists

Use CodeGraph before text search or manual file reading:

```bash
codegraph status
codegraph explore "<entry points, symbols, behavior, callers, and tests>"
codegraph impact <symbol>
codegraph affected <changed-or-planned-existing-files>
```

Prefer the `codegraph_explore` MCP tool when available. Use its health/status metadata when the
interface exposes it; when it exposes only exploration, begin with a narrow query and treat a
successful indexed response as availability evidence. An MCP error indicating a missing, stale, or
corrupt index triggers the fallback below. Do not require a shell preflight when MCP is the active
interface.

If the MCP tool is unavailable, use the shell CLI only after `command -v codegraph` succeeds. Treat
`codegraph status` as the CLI preflight: do not run or trust shell graph queries until it exits zero
and reports a healthy, current index. If neither interface is available, status exits nonzero, the
index is missing or corrupt, or synchronization fails, record the exact unavailable/stale condition
and fall back to `rg` plus targeted reads. If status reports a stale but otherwise healthy index,
run `codegraph sync` and repeat status before querying. Never silently treat unhealthy graph output
as current. Use `codegraph node`, `callers`, or `callees` only for a narrower follow-up.

### When `.codegraph/` does not exist

Do not initialize CodeGraph. Indexing is a project/user decision. Fall back to `rg` and targeted
reads:

```bash
rg -n "<symbol-or-route>" .
rg --files | rg "<feature-or-domain>"
```

Use the same fallback when CodeGraph cannot parse a relevant language or generated/runtime edge.

### Structural questions to answer

- What are the public, administrative, job, CLI, or event entry points?
- Which symbols own the behavior, and which callers consume them?
- What types, schemas, migrations, caches, query keys, permissions, and transactions participate?
- Which tests currently cover those paths?
- Are there dynamic dispatch, reflection, generated code, configuration, environment, or external
  systems that CodeGraph cannot see?
- For multiple repositories, where is the API/event/schema boundary between their separate graphs?

## Phase 3: Build the Semantic Impact Map

Use this output. Omit empty sections, but never omit invariants, acceptance tests, or explicitly
unaffected paths for a material change.

```markdown
# Impact Map: <change>

## Current behavior and evidence
- <observed behavior, entry point, and concise CodeGraph/source evidence>

## Intended semantic delta
- <what users/data/system behavior must change>

## Invariants and must-not-change boundaries
- <historical attribution, authorization, idempotency, transaction, compatibility, etc.>

## Current structural touchpoints
| Repository | Entry point or symbol | Why affected | Evidence |
|---|---|---|---|

## Planned additions and deletions
- <new routes, commands, migrations, tests, or removals that do not exist in CodeGraph yet>

## External and operational effects
- <database migration, cache, queue, analytics, deployment order, repair/backfill, credentials>

## Reuse opportunities
- <registry entry or existing implementation to reuse>

## Acceptance tests
- <observable behavior and failure/concurrency/boundary cases>

## Explicitly unaffected paths
- <nearby behavior that must remain scoped as it is>

## Unknowns and confidence
- <known graph blind spots, assumptions, and how they will be verified>

## Implementation order
1. <smallest failing test or contract first>
2. <source-system implementation>
3. <integration/cache/UI>
4. <validation and reconciliation>
```

Persist the map only when project instructions require a plan file or the work must survive a
session boundary. Otherwise, keep it in the response or active plan. Do not create a generic
`IMPACT_MAP.md` by default.

## Phase 4: Execute From the Map

1. Start with a failing acceptance or contract test.
2. Implement the smallest source-system change satisfying the semantic delta.
3. Preserve every must-not-change boundary.
4. Update the map when implementation evidence disproves an assumption or reveals a new consumer.
5. Run focused tests first, then the repository's required broader gates.

The graph suggests coverage; it does not prove runtime correctness, transaction ordering,
authorization, cache timing, or external-system behavior. Those require tests and, when relevant,
deployment-specific evidence.

## Phase 5: Reconcile After Implementation

For every repository root, repeat the same discovery branch used before implementation.

For roots with a healthy existing CodeGraph index:

```bash
codegraph sync
codegraph explore "<the same entry points, symbols, behavior, callers, and tests>"
codegraph affected <actual-changed-files>
```

Use equivalent MCP synchronization/health operations when exposed. Otherwise use the CLI only when
available. If the index cannot be refreshed after the implementation, record it as stale and take
the fallback branch; do not claim that the graph agrees.

For roots that used the fallback — including roots where CodeGraph is still unavailable or
unhealthy — repeat the original `rg` queries and targeted reads against the completed source. Map
the actual changed files, their consumers, and their tests. Do not award `IN_SYNC` merely because
that root has no graph.

Then compare the actual diff and graph with the impact map:

- Every changed production file traces to the intended semantic delta.
- Every new symbol/route/migration/test now appears in the graph where supported.
- Expected callers, caches, permissions, and tests remain connected.
- No explicitly unaffected path changed accidentally.
- Any deliberate deviation requires you to update the impact map with its rationale.

Report one **Reconciliation verdict**:

- `IN_SYNC` — structural evidence (CodeGraph or fallback), actual diff, and semantic map agree.
- `IN_SYNC_WITH_EXCEPTIONS` — named dynamic/generated/external edges require manual evidence.
- `OUT_OF_SYNC` — missing consumer, unexplained diff, stale graph, or unverified invariant remains.

Do not declare completion while the verdict is `OUT_OF_SYNC`.

## Common Failure Modes

- **File-list map:** duplicates CodeGraph and omits why behavior changes.
- **Graph-only planning:** cannot represent planned code, business invariants, or operational risk.
- **Blind graph trust:** misses dynamic dispatch, runtime configuration, external systems, and data
  semantics.
- **Unrequested indexing:** creates `.codegraph/` in a repository whose owner did not choose it.
- **Single-root analysis:** misses the other side of a frontend/backend or service boundary.
- **No reconciliation:** leaves a pre-implementation map stale as soon as the code changes.

## Related Workflows

- `/rhize-context-manager:done` — final verification after reconciliation.
- `/rhize-context-manager:context-hygiene` — preserve the map when work crosses a session boundary.
- `dev-flow-foundations` — rationale and reusable impact-analysis principles (same plugin).

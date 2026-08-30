# Neo4j Marketplace Ontology and Ingestion Contract

| Field | Value |
|---|---|
| Status | Proposed for review |
| Date | 2026-08-30 |
| Primary owner | `rhize-context-manager` (`graphify` integration) |
| Supporting owners | Plugin-specific extension packs after the core canary |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for schema/migration/adapter work; Luna for fixtures and generated docs |

## Decision

Define a small, versioned Rhize ontology shared by Graphify's approved Neo4j write path and a bounded
read/query interface. Use Neo4j as the available persistent graph database. Keep CodeGraph
authoritative for code structure and Graphify authoritative for its extracted graph artifacts. Do not
adopt Graphiti or create a parallel MongoDB graph.

Start with a marketplace core and one real canary extension pack. Add plugin-specific types only when
real extraction clashes or query needs justify them.

## Independent source reviews

- [Ship a Knowledge Graph Ontology in 5 Minutes](https://www.decodingai.com/p/ship-a-knowledge-graph-ontology-in-5-minutes)
  supports a small fixed base, open subtypes, and a Fact fallback discovered against real data. “Five
  minutes,” universal GraphRAG superiority, and maintenance-free Facts are unsupported.
- [Implement a Unified Memory From Scratch](https://www.decodingai.com/p/how-to-implement-a-unified-memory-from-scratch)
  supports one schema artifact consumed by writer and reader, content-derived node/edge identities,
  and agent-shaped interfaces. Its POLE+O/MongoDB choices are examples, not requirements.
- [Understanding Neo4j's Graph Agent Memory System](https://www.decodingai.com/p/understanding-neo4j-graph-agent-memory-system)
  supports cross-tier provenance edges and constrained ontology, while current interface/version
  details must be verified live.

## Verified current state

- Graphify extracts nodes with `file_type`, source fields, and confidence-bearing edges.
- Node ids are deterministic from source-relative path and entity label, which prevents same-file
  incremental duplicates but is not a cross-source real-world identity contract.
- `graphify export neo4j --push` uses `MERGE` and is rerunnable for its existing ids.
- The generated skill map is intentionally file-backed and has a Cypher-shaped query layer; it does
  not currently require a graph database.
- Neo4j is available, but its live version, namespaces, indexes, constraints, tenant model, and
  existing data are not yet frozen in this plan.

## Core ontology v1

Avoid importing POLE+O wholesale. Use a Rhize-specific small core:

- `Source` — canonical document, record, repository object, or external source revision;
- `Entity` — a referenced real or digital thing, refined by namespaced `entityType`/`subtype`;
- `Claim` — source-specific subject/predicate/object assertion, never silently treated as truth;
- `Event` — something that happened, with valid and recorded time;
- `Artifact` — produced file, procedure, report, build, deployment, or compiled page;
- `Preference` — scoped stance with confidence and supersession;
- `Compilation` — extraction/compiler run linking inputs, version, and outputs.

Core relationships:

- `DERIVED_FROM`, `MENTIONS`, `ASSERTS`, `ABOUT`, `PRODUCED`, `TRIGGERED_BY`, `TOUCHED`,
  `SUPERSEDES`, and generic `RELATED_TO` with a validated semantic type.

Required properties include stable source identity/revision, namespace/tenant, ACL/sensitivity,
trust, confidence, extraction version, `validFrom`/`validUntil`, `recordedAt`, and provenance. A
Claim fallback absorbs uncertain semantics without forcing schema expansion, but it still requires
source, scope, trust, and lifecycle metadata.

## Ownership boundaries

- **CodeGraph:** retain call paths, symbols, and blast-radius authority. When a cross-domain relation
  requires a code reference, Neo4j stores repository identity, commit SHA, CodeGraph index/schema
  revision, repo-relative file path, and qualified symbol locator—not an assumed stable opaque id.
  Resolution failure or revision drift marks the link stale/unresolved instead of rebinding it.
- **Graphify:** retain corpus detection, extraction, confidence, incremental builds, and portable
  artifacts. Add ontology/provenance fields without conflating `file_type` (source medium) with
  `entityType` (domain meaning).
- **Neo4j:** enforce constraints, indexes, versioned ontology, approved ingest, and bounded queries.
- **Plugin packs:** namespaced extensions; no plugin can redefine another plugin's core type.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-context-manager/schemas/knowledge-graph-core-v1.schema.json` | Writer/reader ontology contract |
| Create | `rhize-context-manager/catalog/graph-ontology/core-v1.json` | Canonical core vocabulary |
| Create | `rhize-context-manager/catalog/graph-ontology/packs/` | Namespaced, separately versioned extensions |
| Create | `rhize-context-manager/scripts/graph_memory/` | Validate, preview, migrate, ingest, and query adapters |
| Create | `rhize-context-manager/schemas/graph-ingest-receipt-v1.schema.json` | Privacy-safe ingest outcome contract |
| Modify | `rhize-context-manager/skills/graphify/references/extraction-spec.md` | Separate medium, entity type, claim, and provenance |
| Modify | `rhize-context-manager/skills/graphify/references/exports.md` | Preview/validate before Neo4j push |
| Modify | `rhize-context-manager/skills/graphify/SKILL.md` | Route governed Neo4j writes through the adapter |
| Create | `evals/graph-ontology/` | Real redacted canary corpus plus deterministic validators |
| Modify | README/GUIDE/setup/skill-map docs | Explain the shipped graph ownership model |

If Graphify's external CLI lacks the required export hooks, prepare and release the smallest upstream
change first; do not duplicate its extraction engine inside this repository.

Phase 3 is blocked on Phase 0 of `unified-memory-routing-and-context-assembly.md`, which owns changing
the current `graphiti-memory` skill and removing/reclassifying its `dependsOn: mcp:graphiti` metadata.
This plan must verify that dependency is gone from generated setup/skill-map artifacts; it must not
make a competing edit to the same skill.

## Phases

### Phase 0 — Live Neo4j, Graphify, and CodeGraph-reference inventory

Read-only checks establish Neo4j version/edition, databases, constraints, indexes, namespaces, auth,
backup/restore path, vector support, current Graphify export shape, and CodeGraph locator/re-index
behavior. Record drift-sensitive facts in the plan before implementation.

Acceptance:

- no migration runs during discovery;
- current data ownership and rollback path are known;
- a same-revision CodeGraph locator resolves deterministically, while a revision/index mismatch fails
  closed and never attaches to a same-named symbol;
- credentials remain in Keychain/on-demand configuration and never enter plan files or manifests.

### Phase 1 — Core contract and compiler

Define the schema once and generate both extraction-facing and query-facing representations. Reject
unknown types/relationships, missing source identity, invalid temporal intervals, ACL weakening, and
namespace collisions.

Acceptance:

- writer and reader artifacts derive from the same versioned source;
- schema drift is a build failure;
- `file_type` and `entityType` are independently validated;
- conflicting Claim records can coexist.

### Phase 2 — One canary extension pack

Use a bounded real redacted knowledge-management corpus because it already has Source, Claim, Topic,
Correction, and Citation needs. Run extraction in preview mode, inspect classification clashes, and add
only the subtypes required by demonstrated queries. Do not pre-model every plugin.

Acceptance:

- every added subtype maps to a named query or corrected clash;
- ontology size and extraction cost are reported;
- unsupported concepts remain source-bound Claims rather than causing schema sprawl.

### Phase 3 — Governed Neo4j ingest

Create constraints/indexes through a versioned migration, validate a complete batch, then commit it
atomically or not at all. Use deterministic source identities before any fuzzy identity logic. Record
counts/hashes/version only in the receipt.

Acceptance:

- repeat ingest is idempotent;
- source revision changes create an explicit new compilation/reconciliation path;
- failure leaves no partial accepted batch;
- CodeGraph data is referenced, not copied;
- the unified-memory prerequisite is complete and Graphiti is absent from dependencies, generated
  capability maps, and runtime.

### Phase 4 — Agent-shaped read interface

Expose bounded business operations such as `query_context`, `get_claim_sources`, and
`get_related_artifacts`; do not expose arbitrary write Cypher. Enforce namespace, ACL, depth, result,
and time budgets in code.

Acceptance:

- every result carries provenance and source revision;
- tenant/ACL filters cannot be omitted by model-generated input;
- queries that exceed limits fail clearly rather than returning an unbounded subgraph.

### Phase 5 — Extension-pack decision

Evaluate procedural-memory, Dev Flow, ops, and task-orchestration packs one at a time. Promotion needs
a real query that current stores cannot answer adequately, not merely an attractive graph diagram.

## Completion criteria

- One small versioned ontology drives writer and reader.
- Graphify and CodeGraph retain their specialized ownership.
- Neo4j writes are previewed, validated, atomic, source-bound, and reversible.
- Plugin extensions are namespaced and evidence-gated.
- No second graph database or Graphiti dependency is introduced.

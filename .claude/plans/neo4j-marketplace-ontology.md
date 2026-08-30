# Neo4j Marketplace Ontology and Ingestion Contract

| Field | Value |
|---|---|
| Status | Offline governed release implemented; live Neo4j canary and rollback evidence pending |
| Date | 2026-08-30 |
| Primary owner | `rhize-context-manager` (`graphify` integration) |
| Supporting owners | Plugin-specific extension packs after the core canary |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for schema/migration/adapter work; Luna for fixtures and generated docs |
| Cross-host surface | Canonical `rhize-context-manager:graph-memory` skill and host-neutral CLI; thin Claude adapters; Codex skill discovery |
| Jira tracking | RT-152 implementation; RT-159 live canary/rollback; linked to RT-145 and RT-146 |

## Decision

Define a small, versioned Rhize ontology shared by the governed Rhize adapter over Graphify artifacts
and a bounded read/query interface. Use Neo4j as the available persistent graph database. Keep CodeGraph
authoritative for code structure and Graphify authoritative for its extracted graph artifacts. Do not
adopt Graphiti or create a parallel MongoDB graph.

Start with a marketplace core and one real canary extension pack. Add plugin-specific types only when
real extraction clashes or query needs justify them.

## Rhize graph authority and security contract

- Neo4j stores governed projections, never the only copy of source evidence. Vault/canonical files,
  Graphify artifacts, and CodeGraph retain their respective authority.
- Phase 0 chooses separate-database or shared-database tenancy from the deployed Neo4j edition. In a
  shared database, every constraint and lookup uses tenant/namespace/governed identity. Counts,
  existence, traversals, and error behavior are treated as possible cross-tenant leaks.
- Separate roles own migration administration, ingest, bounded read/query, and identity review.
  Query/review cannot migrate, ingest cannot decide identity, and no agent receives arbitrary Cypher.
- Low-trust sources cannot establish authoritative identifiers or upgrade trusted Claims. Visibility
  is composed from source-specific ACL/trust and incompatible scopes are never physically merged.
- Graph text/metadata is untrusted data and cannot alter policy, scope, credentials, tools, migrations,
  or approvals.

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
- The wrapper pin is `0.9.5` while the inspected installed CLI is `0.9.45`; this drift must be resolved
  before implementation. The inspected runtime lacks the Neo4j driver.
- Current direct `graphify export neo4j`/`--push` is not governed: it autocommits per node/edge, matches
  globally on raw id, lacks tenant/database selection, collapses parallel endpoint/type evidence, and
  drops material provenance. It is forbidden for Rhize governed data.
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
  requires a code reference, Neo4j stores canonical repository identity, commit SHA, repo-relative
  file path, qualified symbol locator, and CodeGraph tool version, plus index fingerprint/revision only
  when the deployed interface exposes one—not an assumed stable opaque id. Resolution failure or
  revision drift marks the link stale/unresolved instead of rebinding it.
- **Graphify:** retain corpus detection, extraction, confidence, incremental builds, and portable
  artifacts. The governed v1 adapter reads validated, hashed `graphify-out/graph.json` plus its
  manifest; it never invokes Graphify's direct Neo4j exporters. Add ontology/provenance fields without
  conflating `file_type` (source medium) with `entityType` (domain meaning).
- **Neo4j:** enforce constraints, indexes, versioned ontology, approved ingest, and bounded queries.
- **Plugin packs:** namespaced extensions; no plugin can redefine another plugin's core type.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-context-manager/schemas/knowledge-graph-core-v1.schema.json` | Writer/reader ontology contract |
| Create | `rhize-context-manager/catalog/graph-ontology/core-v1.json` | Canonical core vocabulary |
| Create | `rhize-context-manager/catalog/graph-ontology/packs/` | Namespaced, separately versioned extensions |
| Create | `rhize-context-manager/scripts/graph_memory/` | Validate, preview, migrate, ingest, and query adapters |
| Create | `rhize-context-manager/skills/graph-memory/SKILL.md` | Canonical Claude Code/Codex graph workflow |
| Create | `rhize-context-manager/skills/graph-memory/agents/openai.yaml` | Codex routing metadata for the canonical skill |
| Create | `rhize-context-manager/commands/graph-memory.md` | Thin Claude adapter over the host-neutral CLI |
| Create | `rhize-context-manager/schemas/graph-ingest-receipt-v1.schema.json` | Privacy-safe ingest outcome contract |
| Modify | `rhize-context-manager/skills/graphify/references/extraction-spec.md` | Separate medium, entity type, claim, and provenance |
| Modify | `rhize-context-manager/skills/graphify/references/exports.md` | Preview/validate before Neo4j push |
| Modify | `rhize-context-manager/skills/graphify/SKILL.md` | Route governed Neo4j writes through the adapter |
| Create | `evals/graph-ontology/` | Real redacted canary corpus plus deterministic validators |
| Modify | README/GUIDE/setup/skill-map docs | Explain the shipped graph ownership model |
| Modify | `rhize-context-manager/.codex-plugin/plugin.json`, Claude/marketplace manifests | Register the canonical skill and synchronize versions; manifest creation is owned by the unified-memory prerequisite |
| Modify/regenerate | Skill-map/catalog artifacts | Register shipped ownership and fail stale Graphiti metadata |

If the portable Graphify artifact cannot preserve a required field, prepare and release the smallest
upstream artifact-format change first; do not add or depend on a direct Neo4j export hook and do not
duplicate its extraction engine inside this repository.

Phase 3 is blocked on Phase 0 of `unified-memory-routing-and-context-assembly.md`, which owns creating
the context-manager Codex manifest and removing active Graphiti routing from `context-stack`,
`graphiti-memory`, setup/doctor flows, setup manifest, README/GUIDE, marketplace keywords, root
dependency matrix, and generated maps. This plan extends that shared manifest for `graph-memory` but
must not make competing Graphiti edits. Graphiti may remain only in clearly marked design/history
material.

## Claude Code and Codex delivery contract

`rhize-context-manager/skills/graph-memory/SKILL.md` and a versioned host-neutral CLI/API own preview,
validate, migrate, ingest, query, and status. Claude commands are thin adapters; Codex discovers the
same skill through the shared `.codex-plugin/plugin.json`. Executables resolve through a verified
installation manifest or portable path contract, never only `${CLAUDE_PLUGIN_ROOT}` or
`${CLAUDE_PROJECT_DIR}`.

Fresh marketplace installs must discover and execute the same preview/query workflow in both hosts.
Identical fixture input produces byte-equivalent structured output and safety decisions; neither host
depends on the other's hooks or environment. Claude/Codex/marketplace manifest versions, docs,
CHANGELOG, setup metadata, and generated maps remain synchronized.

## Governed Graphify translation

The adapter records wrapper pin, installed CLI/path, extraction/schema version, graph/manifest hash,
Graphify build commit plus extractor/model/prompt when available, and runtime/driver version.
Governed ids derive from tenant/namespace/corpus plus raw Graphify id; raw ids are never globally
unique. `EXTRACTED` is extraction evidence, not truth. `INFERRED` records model/prompt/version and has
a trust ceiling. `AMBIGUOUS` or unverified records are quarantined from normal business queries and
identity decisions. Preserve source location/context, direction, confidence class/score, parallel
evidence, and hyperedges; unsupported fields are rejected visibly rather than dropped.

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
- the Graphify wrapper/installed-version drift and missing driver produce a documented block/decision,
  never an install during a write;
- tenancy topology and migration-admin/ingest/query/review roles are fixed and adversarially tested;
- current direct Graphify Neo4j exporters are documented as forbidden for governed data.

### Phase 1 — Core contract and compiler

Define the schema once and generate both extraction-facing and query-facing representations. Reject
unknown types/relationships, missing source identity, invalid temporal intervals, ACL weakening, and
namespace collisions.

Acceptance:

- writer and reader artifacts derive from the same versioned source;
- schema drift is a build failure;
- `file_type` and `entityType` are independently validated;
- conflicting Claim records can coexist.
- every uniqueness constraint and lookup is tenant-safe under the selected topology;
- low-trust/unverified input cannot establish authoritative identity or trusted query visibility;
- writer/query artifacts and migrations are checksummed outputs of one canonical schema compiler.

### Phase 2 — One canary extension pack

Use a bounded real redacted knowledge-management corpus because it already has Source, Claim, Topic,
Correction, and Citation needs. Run extraction in preview mode, inspect classification clashes, and add
only the subtypes required by demonstrated queries. Do not pre-model every plugin.

Acceptance:

- every added subtype maps to a named query or corrected clash;
- ontology size and extraction cost are reported;
- unsupported concepts remain source-bound Claims rather than causing schema sprawl.
- Graphify translation reports provenance completeness/loss and rejects ambiguous or unsupported data;
- the same raw Graphify id in two tenants remains distinct and parallel evidence survives round trip.

### Phase 3 — Governed Neo4j ingest

Create constraints/indexes through a checksummed migration ledger and exclusive migration lock. Ingest
bounded idempotent staging batches keyed by tenant, source, revision, compilation, and batch; make a
compilation query-visible through one final atomic accepted-compilation transition. Queries ignore
incomplete/stale compilations. Optimistic revision checks choose one accepted winner for competing
builds. Define deletion, revocation, supersession, retention, and purge reconciliation. Back up before
migration and rehearse restore with declared RPO/RTO. Record counts/hashes/version only in receipts.

Acceptance:

- repeat ingest is idempotent;
- source revision changes create an explicit new compilation/reconciliation path;
- failure leaves no partial accepted batch;
- CodeGraph data is referenced, not copied;
- the unified-memory prerequisite is complete and Graphiti is absent from dependencies, generated
  capability maps, and runtime.
- failure injection after each stage leaves the previous accepted compilation query-visible;
- retries neither duplicate nor skip data, competing revisions have named winner/loser states, and
  an isolated restore drill includes constraints and publication metadata;
- direct Graphify Neo4j exporters are never invoked.

### Phase 4 — Agent-shaped read interface

Expose bounded business operations such as `query_context`, `get_claim_sources`, and
`get_related_artifacts`; do not expose arbitrary write Cypher. Enforce namespace, ACL, depth, result,
and time budgets in code.

Acceptance:

- every result carries provenance and source revision;
- tenant/ACL filters cannot be omitted by model-generated input;
- queries that exceed limits fail clearly rather than returning an unbounded subgraph.
- cross-tenant adversarial queries cannot read, infer existence, traverse, ingest, or accept identity;
- CodeGraph resolution uses canonical repository id, commit SHA, relative path, qualified symbol, and
  tool version, plus index fingerprint only when exposed; stale refs never sync or rebind and no
  `.codegraph/` directory is initialized automatically.

### Phase 5 — Extension-pack decision

Evaluate the separately planned decision-accountability pack, procedural-memory, Dev Flow, ops, and
task-orchestration packs one at a time. Promotion needs a real query that current stores cannot answer
adequately, not merely an attractive graph diagram. Decision provenance remains an extension pack;
do not expand the core or adopt Semantica before its own source/authority/canary gates pass.

## Jira, measurement, and release gate

The RT-130 child tracks deployed-contract/tenancy inventory, governed Graphify adapter/schema compiler,
migration ledger and stage/publish ingest, bounded query/CodeGraph resolver, dual-host packaging, and
one redacted Rhize-internal canary. Measurement records validation/rejection counts, provenance
completeness, publication lag, stale locators, ACL denials, query-budget failures, constraint
violations, backup age, restore result, orphan/stale compilations, baseline/release versions, and the
promote/hold decision. Raw graph content, credentials, source paths, and tenant identifiers stay out
of Jira. Link proven packaging to RT-145 and evidence review to RT-146.

Release requires unit/schema tests, Neo4j integration and stage-by-stage failure injection, tenancy,
prompt-injection/poison, deletion/purge, deterministic generation, backup/restore, plugin-config,
skill-map build/render/stale validation, and fresh-install Claude Code/Codex smokes. One reversible
internal canary and rollback rehearsal must pass before any client corpus or extension pack.

## Completion criteria

- One small versioned ontology drives writer and reader.
- Graphify and CodeGraph retain their specialized ownership.
- Neo4j writes are previewed, validated, atomic, source-bound, and reversible.
- Plugin extensions are namespaced and evidence-gated.
- No second graph database or Graphiti dependency is introduced.
- Current direct Graphify Neo4j export/push is never used for governed data.
- Tenancy, roles, staged publication, evidence translation, and rollback are enforced in code.
- Claude Code and Codex use the same canonical graph-memory contract.

# Neo4j Graph Hygiene, Identity Review, and Reversal

| Field | Value |
|---|---|
| Status | Proposed for review |
| Date | 2026-08-30 |
| Primary owner | `rhize-context-manager` Neo4j adapter |
| Prerequisite | `neo4j-marketplace-ontology.md` through governed-ingest acceptance |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for identity/merge/reversal; Luna for labeled-pair fixtures and reporting |

## Decision

Separate canonical naming, real-world identity, truth, and evidence classification. Deterministic
source ids win whenever available. Fuzzy/entity-embedding similarity may propose candidates, but no
automatic merge ships until entity-type-specific thresholds are calibrated on labeled Rhize data and
the merge has a tested reversal path.

Use pending `SAME_AS` review records, an append-only merge ledger, and source-aware rebuilds. Do not
copy the articles' 0.85/0.95 thresholds as universal defaults and do not let a nightly job mutate the
graph before the manual workflow proves reliable.

## Independent source reviews

- [How to Keep a Knowledge Graph Clean](https://www.decodingai.com/p/keep-knowledge-graph-clean)
  correctly separates name resolution from identity deduplication and uses a gray-zone review queue.
  Its 70/30 blend, thresholds, tombstone semantics, and nightly “dream” loop are unvalidated defaults.
- [Understanding Neo4j's Graph Agent Memory System](https://www.decodingai.com/p/understanding-neo4j-graph-agent-memory-system)
  reinforces type-gated resolution, cross-tier provenance, and human review while leaving context
  compression and production evidence unproven.
- [Implement a Unified Memory From Scratch](https://www.decodingai.com/p/how-to-implement-a-unified-memory-from-scratch)
  treats false merges as the least recoverable error and supports append-only/replayable source
  history; its content-derived ids and thresholds still need migration and domain calibration.

## Verified current state

- Graphify's deterministic ids prevent a subset of same-source duplicates.
- Neo4j `MERGE` makes identical exported ids rerunnable; it does not prove that two cross-source nodes
  represent the same real-world entity.
- Graphify already records `EXTRACTED`, `INFERRED`, and `AMBIGUOUS` edge evidence. That confidence is
  extraction evidence, not identity confidence or truth.
- Graphify already ships a read-only extraction-integrity health gate; preserve and reuse it rather
  than duplicating extraction diagnostics. No plugin-owned identity review queue, merge ledger,
  reversal command, threshold calibration corpus, or identity/merge quality report exists.

## Identity decision ladder

1. **Strong deterministic identity:** repository id, commit SHA, PR/deployment/issue id, source record
   id, procedure digest, or other authoritative key. Match only within namespace/tenant.
2. **Canonical naming:** normalize case/spacing/known aliases within entity type. This changes display
   and grouping fields only; it never merges.
3. **Candidate generation:** exact alias, fuzzy name, and semantic/full-context similarity, gated by
   compatible type, scope, ACL, and trust.
4. **Decision:** `new`, `pending_same_as`, `merge`, or `reject_same_as`.
5. **Truth handling:** even merged identity retains separate source-specific Claims, corrections, and
   confidence. Entity sameness never collapses disagreement into one fact.

Operational entities—repositories, branches, commits, deployments, services, environments, approvals,
tasks, runs, procedures—default to deterministic identity only. Fuzzy auto-merge is initially forbidden
for these types.

## Review and reversal contract

A pending review contains candidate ids, same-type evidence, source/trust/ACL summary, confidence
components, proposed action, and creation time. The reviewer chooses merge, keep separate, or defer.
Every decision records actor, timestamp, evidence version, and rationale code.

A merge ledger records pre-merge node/edge snapshots or source-replay references, transferred
relationships, surviving identity, source revisions, and reversal status. Reversal must restore the
previous query-visible state or rebuild it deterministically from immutable sources.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-context-manager/schemas/identity-review-v1.schema.json` | Pending/reviewed candidate contract |
| Create | `rhize-context-manager/schemas/merge-ledger-v1.schema.json` | Audit and reversal contract |
| Create | `rhize-context-manager/scripts/graph_memory/resolution.py` | Canonical naming only |
| Create | `rhize-context-manager/scripts/graph_memory/dedup.py` | Candidate scoring/routing, initially no auto-merge |
| Create | `rhize-context-manager/scripts/graph_memory/review.py` | Queue, decision, and authorization |
| Create | `rhize-context-manager/scripts/graph_memory/consolidate.py` | Watermarked, idempotent recheck after manual proof |
| Create | `rhize-context-manager/scripts/graph_memory/quality.py` | Identity/merge metrics composed with Graphify's existing integrity diagnostics |
| Create | `rhize-context-manager/commands/graph-memory-review.md` | Human review/status/reverse entry point |
| Create | `evals/graph-hygiene/` | Labeled pairs, concurrency, poison, and rollback cases |
| Modify | Graphify Neo4j export guidance and plugin docs | Route identity decisions through the governed layer |

## Security and privacy invariants

- Candidate comparison never crosses tenant, namespace, or incompatible ACL boundaries.
- Sensitive attributes are not embedded by default; each entity type has an allowlisted comparison
  projection.
- Untrusted Claims do not become trusted because they mention an existing trusted Entity.
- Merge/review authorization is separate from ingest authorization.
- No automatic threshold change follows embedding-model or schema migration.
- Failed trials and rejected pairs remain evidence; they are not replayed or averaged as clean runs.

## Phases

### Phase 0 — Deployed semantics and labeled corpus

Verify the selected Neo4j/driver behavior for constraints, transactions, vector indexes, relationship
transfer, deletion/tombstone, and backup/restore. Build labeled same/different/uncertain pairs from real
redacted marketplace entities, including name collisions such as model versus CLI/plugin.

Acceptance:

- merge and reversal semantics are demonstrated on an isolated copy;
- every labeled pair includes identity keys, type, scope, source, and expected disposition;
- no production/shared graph is used for threshold tuning.

### Phase 1 — Resolution without merge

Implement normalized display names and aliases under strict type/scope rules. Preserve all original
surface forms and provenance.

Acceptance:

- canonicalization is deterministic and idempotent;
- no node count changes;
- same-named distinct entities remain separate;
- ontology migration/type uncertainty prevents candidate matching rather than forcing it.

### Phase 2 — Candidate-only deduplication

Generate candidate scores using allowlisted fields and configurable components. Route all plausible
matches to `pending_same_as`; create no automatic merge path yet.

Acceptance:

- deterministic ids bypass fuzzy logic;
- candidate comparison cannot cross ACL/tenant boundaries;
- score components and model/version are reproducible;
- the review backlog and no-candidate population are both visible.

### Phase 3 — Human review and merge ledger

Add authorized review decisions and isolated merge/reverse operations. A merge transaction writes its
ledger record atomically with the graph mutation.

Acceptance:

- interruption cannot produce an unlogged merge;
- reverse restores nodes, claims, and relationships on the isolated corpus;
- rejected candidates do not immediately reappear unchanged;
- competing Claims survive identity merges.

### Phase 4 — Threshold calibration and limited automation decision

Measure false merges, missed duplicates, review precision, disagreement, backlog age, and operator
time by entity type. Start with conservative/no-auto-merge policy. Only low-risk entity types with
enough labeled evidence may earn auto-merge; operational/protected identities remain deterministic.

No single composite score is authoritative. Any false merge in a protected type blocks automation.

### Phase 5 — Watermarked consolidation canary

Only after the manual path is stable, add a recent-node recheck for parallel-ingestion races. It uses
durable watermarks, idempotency, bounded batches, retries, and pause-on-backlog behavior. It proposes
candidates; it does not widen merge authority.

Acceptance:

- the canary replays safely after interruption;
- no node is skipped or double-counted across watermarks;
- review/consolidation races are transactionally resolved;
- unchanged external state produces no noisy success claim.

## Completion criteria

- Naming, identity, truth, and evidence remain distinct.
- Deterministic identities take precedence over similarity.
- Every merge is authorized, audited, reversible, and source-aware.
- Thresholds are entity-specific and empirically calibrated.
- Graph quality reporting composes Graphify's extraction-integrity health with false merge/split,
  identity backlog, conflict, and rollback health without duplicating ownership.

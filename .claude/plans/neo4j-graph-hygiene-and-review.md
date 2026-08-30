# Neo4j Graph Hygiene, Identity Review, and Reversal

| Field | Value |
|---|---|
| Status | Offline review/reversal release implemented; calibration and consolidation remain gated |
| Date | 2026-08-30 |
| Primary owner | `rhize-context-manager` Neo4j adapter |
| Prerequisite | `neo4j-marketplace-ontology.md` through governed-ingest acceptance |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for identity decisions/projection/reversal; Luna for labeled-pair fixtures and reporting |
| Cross-host surface | Extend canonical `rhize-context-manager:graph-memory` skill/CLI; thin Claude review adapter; Codex skill discovery |
| Jira tracking | RT-153 implementation; RT-160 calibration/consolidation; automatic `SAME_AS` remains out of scope |

## Implemented review hardening

Candidate intersections now carry hashed ACL scopes in their revision and ledger identities. Every
candidate read or transition enforces both tenant/namespace and an authorized ACL intersection;
same-partition authority alone is insufficient. Proposal consolidation now requires one explicit
authorized ACL lane; its watermark, backlog count, and suppressed-revision lookup cannot aggregate
or block work from another ACL lane. Changed evidence supersedes an accepted candidate, removes its
stale logical projection after dependency checks, and queues a fresh manual review with an append-only
ledger event.

## Decision

Separate canonical naming, real-world identity, truth, and evidence classification. Deterministic
source ids win whenever available. Fuzzy/entity-embedding similarity may propose candidates, but no
automatic `SAME_AS` acceptance ships until entity-type-specific thresholds are calibrated on labeled
Rhize data and the logical projection has a tested reversal path.

Use pending `SAME_AS` review records, an append-only identity-decision ledger, and reversible logical
canonical-cluster projections. Preserve source-bound entities/Claims in the first release; physical
compaction is a later, separately approved optimization. Do not
copy the articles' 0.85/0.95 thresholds as universal defaults and do not let a nightly job mutate the
graph before the manual workflow proves reliable.

## Rhize operating and authority contract

- Ingest, query, migration, and identity review use separate roles. Actor identity comes from the
  authenticated host/operator context, never a model-provided string. Only authorized reviewers can
  decide or reverse candidates.
- Tenant, namespace, type, ACL, trust, source revision, schema, and scoring-model version are
  revalidated inside every decision transaction. No comparison, existence signal, backlog metric, or
  projection crosses incompatible scopes.
- Graph text and metadata are untrusted data. Bound property sizes, aliases, Unicode/confusables,
  embeddings, relationship cardinality, per-source candidate generation, and tenant backlog growth.
  Poisoned input cannot change policy, trust, ACL, thresholds, authoritative keys, tools, or approvals.
- Operational/protected identities stay deterministic and manual-only. `INFERRED`, `AMBIGUOUS`,
  unverified code nodes, or low-trust aliases cannot independently justify `SAME_AS`.
- Candidate flooding pauses the offending source/type and reports a degraded state without blocking
  unrelated tenants. Backlog, schema/model drift, failed restore, ACL anomaly, or any protected-type
  false `SAME_AS` acceptance pauses the canary.

## Independent source reviews

- [How to Keep a Knowledge Graph Clean](https://www.decodingai.com/p/keep-knowledge-graph-clean)
  correctly separates name resolution from identity deduplication and uses a gray-zone review queue.
  Its 70/30 blend, thresholds, tombstone semantics, and nightly “dream” loop are unvalidated defaults.
- [Understanding Neo4j's Graph Agent Memory System](https://www.decodingai.com/p/understanding-neo4j-graph-agent-memory-system)
  reinforces type-gated resolution, cross-tier provenance, and human review while leaving context
  compression and production evidence unproven.
- [Implement a Unified Memory From Scratch](https://www.decodingai.com/p/how-to-implement-a-unified-memory-from-scratch)
  treats false identity collapse as the least recoverable error and supports append-only/replayable source
  history; its content-derived ids and thresholds still need migration and domain calibration.

## Verified current state

- Graphify's deterministic ids prevent a subset of same-source duplicates.
- Neo4j `MERGE` makes identical exported ids rerunnable; it does not prove that two cross-source nodes
  represent the same real-world entity.
- Graphify already records `EXTRACTED`, `INFERRED`, and `AMBIGUOUS` edge evidence. That confidence is
  extraction evidence, not identity confidence or truth.
- Graphify already ships a read-only extraction-integrity health gate; preserve and reuse it rather
  than duplicating extraction diagnostics. No plugin-owned identity review queue, identity-decision
  ledger, reversal command, threshold calibration corpus, or identity quality report exists.

## Identity decision ladder

1. **Strong deterministic identity:** repository id, commit SHA, PR/deployment/issue id, source record
   id, procedure digest, or other authoritative key. Match only within namespace/tenant.
2. **Canonical naming:** normalize case/spacing/known aliases within entity type. This changes display
   and grouping fields only; it never creates an identity decision.
3. **Candidate generation:** exact alias, fuzzy name, and semantic/full-context similarity, gated by
   compatible type, scope, ACL, and trust.
4. **Decision:** `new`, `pending_same_as`, `accept_same_as`, or `reject_same_as`.
5. **Truth handling:** an accepted logical identity projection retains separate source-specific
   entities, Claims, corrections, and confidence. Entity sameness never collapses disagreement into
   one fact.

Operational entities—repositories, branches, commits, deployments, services, environments, approvals,
tasks, runs, procedures—default to deterministic identity only. Automatic `SAME_AS` acceptance is initially forbidden
for these types.

## Review state machine and reversal contract

A review is `pending`, `leased`, `accepted`, `rejected`, `deferred`, `superseded`, or `reversed`.
Its canonically ordered candidate-pair key is unique. It contains candidate ids, source/trust/ACL
summary, score components, candidate/evidence/schema/model versions, creation/expiry, lease, and
idempotency key. The reviewer chooses accept logical `SAME_AS`, keep separate, or defer using an
enumerated rationale after viewing the current bounded impact preview. Optimistic compare-and-swap
prevents stale or competing decisions; ingest changes supersede stale candidates.

The append-only ledger records decision events, source revisions, projection membership, actor,
timestamp, rationale, dependencies, and reversal status. Accepting/reversing changes only decision
and projection records; source nodes, Claims, ACLs, trust, and provenance remain unchanged. A reverse
preview lists later dependent decisions/relationships/Claims and requires a current-state precondition.
If later writes cannot be safely repartitioned by immutable source, reversal fails with a named
dependency rather than overwriting them.

Historical decision-accountability records retain their original source-entity ids and accepted graph
compilation. A current `SAME_AS` projection may be shown as a separate resolution view but never
rewrites the immutable evidence set of an earlier decision.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-context-manager/schemas/identity-review-v1.schema.json` | Pending/reviewed candidate contract |
| Create | `rhize-context-manager/schemas/identity-decision-ledger-v1.schema.json` | Audit and reversal contract |
| Create | `rhize-context-manager/scripts/graph_memory/resolution.py` | Canonical naming only |
| Create | `rhize-context-manager/scripts/graph_memory/dedup.py` | Candidate scoring/routing, initially no automatic acceptance |
| Create | `rhize-context-manager/scripts/graph_memory/review.py` | Queue, decision, and authorization |
| Create | `rhize-context-manager/scripts/graph_memory/consolidate.py` | Proposal-only, watermarked, idempotent recheck after manual proof |
| Create | `rhize-context-manager/scripts/graph_memory/quality.py` | Identity-decision metrics composed with Graphify's existing integrity diagnostics |
| Create | `rhize-context-manager/commands/graph-memory-review.md` | Human review/status/reverse entry point |
| Create | `evals/graph-hygiene/` | Labeled pairs, concurrency, poison, and rollback cases |
| Modify | Graphify Neo4j export guidance and plugin docs | Route identity decisions through the governed layer |

The ontology plan owns the canonical `skills/graph-memory/SKILL.md`, host-neutral CLI, Codex manifest,
and common release metadata. This plan extends that skill/CLI with list, show, preview, decide, defer,
reverse, and status; `commands/graph-memory-review.md` is a thin Claude adapter. Avoid a competing
manifest or duplicate workflow body.

## Claude Code and Codex review UX

Both hosts support tenant/type/risk/age filters, pagination, redacted evidence, score explanations,
ACL/trust impact preview, enumerated rationale codes, and dry-run reversal impact. No decision is
accepted until the current candidate revision and bounded impact are viewed. Identical fixtures must
produce the same candidate revision, transition, and privacy-safe receipt in both hosts; sensitive
comparison attributes never enter logs or receipts. Neither host depends on the other's environment,
hooks, or private state.

## Security and privacy invariants

- Candidate comparison never crosses tenant, namespace, or incompatible ACL boundaries.
- Sensitive attributes are not embedded by default; each entity type has an allowlisted comparison
  projection.
- Untrusted Claims do not become trusted because they mention an existing trusted Entity.
- Identity-decision/review authorization is separate from ingest authorization.
- No automatic threshold change follows embedding-model or schema migration.
- Failed trials and rejected pairs remain evidence; they are not replayed or averaged as clean runs.
- Physical compaction is out of scope for the first release; accepted logical projections remain
  reversible without mutating immutable source entities.

## Phases

### Phase 0 — Deployed semantics and labeled corpus

Verify the selected Neo4j/driver behavior for constraints, transactions, vector indexes, relationship
transfer, deletion/tombstone, and backup/restore. Build labeled same/different/uncertain pairs from real
redacted marketplace entities, including name collisions such as model versus CLI/plugin.

Acceptance:

- logical projection and reversal semantics are demonstrated on an isolated copy;
- every labeled pair includes identity keys, type, scope, source, and expected disposition;
- no production/shared graph is used for threshold tuning.
- tuning and held-out cohorts are predeclared and kept separate;
- poison fixtures cover prompt injection, trusted-id spoofing, confusables, giant properties, alias
  storms, poisoned embeddings, candidate flooding, and tenant/existence side channels.

### Phase 1 — Resolution without identity acceptance

Implement normalized display names and aliases under strict type/scope rules. Preserve all original
surface forms and provenance.

Acceptance:

- canonicalization is deterministic and idempotent;
- no node count changes;
- same-named distinct entities remain separate;
- ontology migration/type uncertainty prevents candidate matching rather than forcing it.
- canonicalization cannot promote a low-trust alias into deterministic identity.

### Phase 2 — Candidate-only deduplication

Generate candidate scores using allowlisted fields and configurable components. Route all plausible
matches to `pending_same_as`; create no automatic acceptance path yet.

Acceptance:

- deterministic ids bypass fuzzy logic;
- candidate comparison cannot cross ACL/tenant boundaries;
- score components and model/version are reproducible;
- the review backlog and no-candidate population are both visible.
- per-source/type/cardinality limits bound candidate cost and isolate backlog abuse.

### Phase 3 — Human review and logical identity ledger

Add authorized review decisions and logical `SAME_AS`/canonical-cluster projection/reversal. One
transaction validates candidate/source/model/schema state and appends the ledger event with the
projection transition. Manual review, ingest supersession, and consolidation proposals share this
single transition owner.

Acceptance:

- interruption cannot produce an unlogged decision or divergent projection;
- two reviewers cannot decide the same revision and an expired/stale lease cannot apply;
- reverse restores golden query behavior while source nodes, Claims, ACL, trust, and provenance remain
  byte-equivalent;
- rejected candidates do not immediately reappear unchanged;
- competing Claims survive identity projection changes.
- review/consolidation/ingest race fixtures produce no unlogged or duplicate transition;
- dependency-aware reversal restores the golden state or returns a deterministic blocked reason.

### Phase 4 — Threshold calibration and limited automation decision

Measure false `SAME_AS` acceptance, missed duplicates, review precision, disagreement, backlog age,
and operator time by entity type. Start with conservative/no-auto-accept policy. Only low-risk entity
types with enough labeled evidence may earn automatic acceptance; operational/protected identities
remain deterministic.

No single composite score is authoritative. Any false acceptance in a protected type blocks automation.

Pre-register per-entity-type denominators, tuning and held-out cohorts, precision, false-accept rate,
sampled false-split rate, reviewer disagreement, review yield, median/p95 decision time, backlog age,
stale-candidate rate, reversal rate, protected-type incidents, minimum evidence, and confidence rules
in Jira. Failed/incomplete trials remain non-comparable. Automation stays disabled until a separate
Jira decision is accepted.

### Phase 5 — Watermarked consolidation canary

Only after the manual path is stable, add a proposal-only recent-node recheck for parallel-ingestion races. It uses
durable watermarks, idempotency, bounded batches, retries, and pause-on-backlog behavior. It proposes
candidates; it does not widen identity authority.

Acceptance:

- the canary replays safely after interruption;
- no node is skipped or double-counted across watermarks;
- review/consolidation races are transactionally resolved;
- unchanged external state produces no noisy success claim.

## Jira, observability, and release gate

The RT-130 child tracks identity schemas/poison corpus, logical `SAME_AS` and dual-host review/reversal,
race/failure-injection coverage, and the initial labeled-pair evaluation. Follow-up measurement tracks
candidate/backlog rate and age, lease expiry, decision latency, rejection recurrence, stale/superseded
candidates, reversals, false identity-accept/split reports, poison/rate-limit events, watermark lag, host/plugin
versions, baseline/release SHAs, and operator cost. Raw candidate content, sensitive attributes,
paths, tenant ids, and reviewer identity stay out of Jira. Proposal-only consolidation and any
automatic `SAME_AS` authority each require separate accepted Jira decisions linked to RT-146; proven packaging
links to RT-145.

Release requires schema/unit tests, concurrency/race and transition-level failure injection, tenant/
ACL/authorization denial, poison/backlog isolation, logical projection/reversal golden queries,
deterministic held-out evaluation, generated-map/config validation, and fresh installed Claude
Code/Codex discovery. The first canary uses one internal tenant and remains proposal-only.

## Completion criteria

- Naming, identity, truth, and evidence remain distinct.
- Deterministic identities take precedence over similarity.
- Every identity decision is authorized, audited, reversible, and source-aware without first-release
  physical merge.
- Thresholds are entity-specific and empirically calibrated.
- Graph quality reporting composes Graphify's extraction-integrity health with false identity-accept/split,
  identity backlog, conflict, and rollback health without duplicating ownership.
- Claude Code and Codex share one authenticated, state-bound review and reversal contract.
- Calibration, consolidation, and automation promotion remain explicit Jira gates.

# Neo4j Decision Accountability Extension Pack

| Field | Value |
|---|---|
| Status | Offline extension pack implemented; internal canary and promotion evidence pending |
| Date | 2026-08-30 |
| Primary owner | `rhize-context-manager` governed Neo4j adapter |
| Supporting owners | `rhize-devflow`, `rhize-ops`, `rhize-tasks`, and domain plugins only through typed adapters |
| Prerequisites | Ontology v1, governed ingest/query, and graph-hygiene logical identity/reversal |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for schema/provenance/query integration; Luna for bounded fixtures and docs |
| Cross-host surface | Extend canonical `rhize-context-manager:graph-memory` skill/CLI; thin Claude command; Codex skill discovery |
| Jira tracking | RT-154 implementation; RT-161 internal canary/promotion; linked to RT-146 |

## Decision

Add a small, governed decision-accountability extension to the Rhize Neo4j ontology. Record selected
consequential decisions as first-class, source-bound projections that connect the evidence available,
policy evaluation, approval, external effect, observed outcome, supersession, and downstream
dependents. Preserve the canonical operational records in Jira, Git, deployment systems, receipts,
and source files; Neo4j is a queryable projection, not the new system of record.

Do not adopt Semantica as another ingestion, extraction, storage, reasoning, MCP, CLI, or plugin stack.
That would overlap CodeGraph, Graphify, Neo4j, `rhize-context-manager`, Dev Flow, and existing evidence
stores. Reuse the portable data-model insights behind Rhize's governed adapter and evaluate W3C
PROV-O export interoperability separately.

## Independent source review

The Agent Native article [“Open Source Palantir for AI Agents”](https://agentnativedev.medium.com/open-source-palantir-for-ai-agents-c6667095a449)
and the linked Semantica repository correctly distinguish execution traces from durable domain
decisions, model decisions as first-class records, connect evidence/provenance/policy/outcomes, avoid
hidden chain-of-thought, and expose bounded business queries such as decision ancestry and impact.

The article and project page remain product sources, not proof that every advertised ingestion,
reasoning, temporal, compliance, or enterprise capability is correct under Rhize workloads. A local
hash chain detects some history corruption but is not independently anchored immutability. `CAUSED`,
similar-decision search, confidence values, deterministic policy execution, and regulator-ready
PROV-O/SHACL/OWL claims all require narrower semantics and real evaluation. Adopt the accountable
record shape; reject the “install everything” architecture and any compliance-by-library inference.

The inspected Semantica package/runtime was `0.6.7` while its Claude/Codex plugin manifests remained
`0.1.0`. Its default stdio MCP exposes graph/decision writes against process-wide state without the
principal, tenant, role, ACL, or tool-level authorization Rhize requires. Those are current no-adopt
facts, not a claim that the project can never mature; any future reconsideration needs a fresh pinned
security/provenance review.

## Verified Rhize state and ownership

- CodeGraph owns current code symbols, call paths, and version-bound blast-radius references when a
  repository is already indexed. It is never initialized automatically and its graph is not copied.
- Graphify owns portable extraction artifacts and provenance-bearing corpus relationships. It does
  not infer or write operational decision records.
- Neo4j is the only planned persistent relationship store, behind the ontology, tenancy, stage/
  publish, bounded query, and hygiene contracts.
- Jira owns implementation, measurement, approval, and promotion coordination; Git/PR/deployment
  systems own their corresponding operational facts; privacy-safe receipts own measured run evidence.
- Rhize already records scattered rationale, approval, estimate, experiment, and release decisions,
  but no typed cross-plugin decision record, causal/precedent contract, impact query, or invalidation
  lifecycle exists.
- Graphify may extract prose about a decision only as a source-bound `Claim`; it cannot create an
  authoritative `Decision`, evidence/policy snapshot, approval, outcome, actor, or causal edge. Only
  an authenticated governed workflow adapter can create those records.

## Eligibility and authority boundary

Record only a predeclared consequential decision class: promotion/adoption, policy gate, approval,
external-effect routing, release/rollback, vendor/provider selection, or other domain decision whose
later reconstruction has operational value. Do not record every model response, tool call, search,
or intermediate thought.

The record stores a defensible `rationaleSummary` composed of evidence considered, policy applied,
threshold crossed, operator override, and unresolved uncertainty. It never stores hidden chain-of-
thought, raw prompts/transcripts, credentials, client content, or unredacted absolute paths. A graph
record cannot grant authority: the originating workflow still owns approval, paid/API, Jira, Git,
deployment, production, and data-write permissions.

Only the owning workflow may preview a decision. Only an authenticated coordinator/operator may
approve recording, correction, invalidation, or supersession. Ambiguous external outcomes remain
`unknown`/`reconciliation_required`; they are never rewritten as success.

## Decision-accountability extension v1

Types:

- `Decision` — scoped proposal/outcome with stable source identity and revision;
- `DecisionEvent` — append-only proposed, accepted, rejected, effect-attempted, outcome-observed,
  failed, corrected, invalidated, superseded, or reversed lifecycle event;
- `EvidenceSet` — immutable selection manifest of facts/source revisions available at decision time,
  with content hashes and retention/availability status;
- `PolicySnapshot` — exact version/digest of the governing rule artifact at decision time, never
  free-form prompt authority;
- `PolicyEvaluation` — allowlisted input references/digests, rule/version, result, evidence, and
  execution status; protected client payloads are never copied into the record;
- `Approval` — source-bound authorization or denial, including authority scope and expiry;
- `Effect` — idempotency-bound attempted external change with known/unknown outcome;
- `OutcomeObservation` — later evidence about the real result, kept distinct from the decision;
- `DecisionCorrection` — append-only invalidation, supersession, or human correction.

Relationships use conservative semantics:

- `BASED_ON`, `GOVERNED_BY`, `EVALUATED_AS`, `AUTHORIZED_BY`, `ATTEMPTED_EFFECT`,
  `OBSERVED_OUTCOME`, `SUPERSEDES`, `PRECEDENT_FOR`, and `INFLUENCED_BY`;
- `CAUSED` is unavailable by default and may be used only for a predeclared deterministic mechanism
  with source evidence. Temporal order, model prose, or similarity cannot establish causality.

Every record carries canonical tenant/project/domain, source system/id/revision, valid and recorded
time, ACL/sensitivity, trust, retention, schema/plugin version, privacy-safe actor reference,
idempotency key where applicable, and immutable content hash. Unknown temporal or outcome fields stay
nullable/unknown rather than fabricated.

## Source, lifecycle, and integrity contract

- The canonical source remains authoritative. Graph publication is versioned and atomic through the
  ontology plan's stage/accept transition; an incomplete projection is never query-visible.
- Corrections append events and change the current projection; they do not erase the historical
  decision, source Claims, or later outcome observations. Retention/legal purge removes protected
  payloads and leaves only an approved non-sensitive tombstone.
- A hash/sequence chain may detect local ledger discontinuity but is never described as tamper-proof
  without an independently controlled signed/anchored checkpoint and restore drill.
- Source revision, policy version, approval validity, and outcome watermarks are revalidated at read
  time. Stale inputs stay visible as stale; they are not silently rebound.
- `PRECEDENT_FOR` and similarity return candidates, not authority. Reusing a prior decision always
  requires current evidence, policy, scope, and approval evaluation.
- Historical decisions retain their original immutable source-entity identifiers and accepted graph
  compilation. A later `SAME_AS` projection is rendered separately and never rewrites historical
  evidence membership.

Each decision has a tenant-scoped uniqueness/idempotency key and monotonic event version. An event
append supplies the expected prior version/hash and atomically writes the append-only event plus the
current projection. Compare-and-swap rejects stale concurrent writers; exact retry returns the prior
result. No success event is created from an effect attempt alone, and ledger/projection divergence is
a failed recovery state.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-context-manager/catalog/graph-ontology/packs/decision-accountability-v1.json` | Namespaced extension vocabulary |
| Create | `rhize-context-manager/schemas/decision-record-v1.schema.json` | Decision, provenance, status, and lifecycle contract |
| Create | `rhize-context-manager/schemas/policy-evaluation-v1.schema.json` | Versioned deterministic policy evidence |
| Create | `rhize-context-manager/schemas/decision-query-receipt-v1.schema.json` | Privacy-safe query/canary outcome |
| Create | `rhize-context-manager/scripts/graph_memory/decisions.py` | Preview, record, explain, impact, precedents, correct, and verify |
| Create | `rhize-context-manager/scripts/graph_memory/prov_export.py` | Optional validated W3C PROV-O mapping, never the internal authority |
| Create | `rhize-context-manager/commands/graph-decision.md` | Thin Claude adapter over the canonical graph-memory CLI |
| Create | `evals/decision-accountability/` | Provenance, policy, causality, privacy, correction, and cross-host corpus |
| Modify | `rhize-context-manager/skills/graph-memory/SKILL.md` and OpenAI metadata | Shared Claude Code/Codex decision workflow |
| Modify | `rhize-devflow`, `rhize-ops`, `rhize-tasks` typed adapter docs/tests | Preview eligible domain decisions without duplicate stores |
| Modify | README/GUIDE, root CHANGELOG/ROADMAP, setup and generated skill maps | Explain shipped scope and limitations |

The ontology plan owns the graph-memory skill, host-neutral CLI, and Codex manifest. This plan extends
those artifacts; it must not create a second manifest, MCP server, graph database, policy engine, or
decision store.

## Claude Code and Codex delivery contract

The canonical graph-memory skill and CLI own decision preview/record/query semantics. Claude's
`/graph-decision` command is a thin adapter; Codex discovers the same skill through the shared Codex
manifest and OpenAI metadata. Both hosts pass explicit current-workflow evidence and authenticated
actor/approval context; neither scrapes private transcripts or hidden reasoning.

Fresh installed-host tests must discover the intended surface and produce byte-equivalent structured
records, policy results, correction events, denial reasons, and query receipts for fixed deterministic
fixtures. Live task/model results are host-stratified. Unsupported actor identity, graph availability,
or source interface yields `unavailable`/`unauthorized` and never a local shadow record that can later
be mistaken for accepted graph state.

## Agent-shaped interface

Expose bounded operations, not raw Cypher or a general graph editor:

```text
graph-decision preview <source-ref>
graph-decision record <preview-id>
graph-decision explain <decision-id>
graph-decision impact <decision-id>
graph-decision precedents <typed-query>
graph-decision correct <decision-id> <approved-correction>
graph-decision status [scope]
```

`preview` is read-only and writes a mode-`0600` private artifact under a host-neutral Rhize-owned
root. It has a short configured TTL and binds actor/principal, tenant/project, owning workflow,
source/evidence/policy/approval revisions and hashes, schema/plugin version, and a single-use nonce.
`record` applies only that approved preview through compare-and-swap after immediately revalidating
principal, scope, sources, policy, approval, idempotency, and current event version. Expired, replayed,
stale, or mismatched previews fail with an explicit reason and are never refreshed implicitly.
`explain` returns
evidence, policy, approval, effect, outcome, corrections, and stale/unknown warnings. `impact` returns
bounded downstream dependencies without asserting causality beyond typed edges. `precedents` returns
candidates with current-policy mismatch warnings. Tenant/ACL, depth, result, time, and token budgets
are enforced inside the query layer.

## Phases

### Phase 0 — Decision inventory and threat model

Select a bounded set of real redacted Rhize decisions from Jira/evidence/release workflows. Freeze
canonical sources, decision eligibility, authority, tenant/ACL/retention, correction, purge, and
causality vocabulary before Neo4j work.

Acceptance:

- every field has a canonical source or explicit derived status;
- hidden reasoning, raw prompts, credentials, client content, and paths are absent;
- `INFLUENCED_BY`/`PRECEDENT_FOR` cannot be upgraded to `CAUSED` by model text;
- cross-client and unauthorized decision existence cannot be inferred.
- retrying the same authorized workflow/idempotency key yields one decision, and no attempted external
  effect is marked successful without an authoritative outcome receipt;
- invalidated evidence flags every dependent decision without rewriting its historical evidence set.

### Phase 1 — Schemas, deterministic policy fixtures, and source adapters

Implement strict schemas and fake/in-memory adapters first. Add read-only typed previews for one Dev
Flow decision and one Ops experiment/promotion decision; do not publish to Neo4j.

Acceptance:

- unknown fields, stale revisions, expired approvals, and authority escalation fail closed;
- policy evaluation records the exact rule/version, allowlisted input references/digests, result, and
  status and reproduces deterministically without copying protected client payloads;
- corrections/supersession preserve history and current-state resolution;
- no plugin writes a duplicate operational decision store.
- concurrent preview/record/correct/invalidate/effect/outcome races use one event transition owner;
  stale writers fail CAS, exact retries are idempotent, and fault injection cannot split ledger from
  current projection.

### Phase 2 — Governed Neo4j publication and bounded queries

Begin only after ontology governed-ingest and hygiene logical identity/reversal pass. Publish one
internal tenant through stage/accept, then add explain/impact/precedent queries.

Acceptance:

- failure injection leaves the previous accepted projection query-visible;
- every decision traces to live canonical evidence or reports stale/unavailable;
- query credentials cannot record/correct and ingest credentials cannot approve;
- `impact` and `precedents` enforce scope and never imply authority.
- transition-level race fixtures cover concurrent record, correction, invalidation, effect attempt,
  and outcome observation with atomic event/projection state.

### Phase 3 — Cross-host internal canary

Freeze the current canonical-source/Jira/evidence reconstruction workflow as the baseline, then run
paired, host-stratified Claude Code and Codex deterministic fixtures separately from natural eligible
internal decisions. No client corpus and no automatic capture. Failed, incomplete, unavailable, or
unreviewed runs remain labeled non-comparable and are never pooled with accepted evidence.

Measure provenance/source completeness, policy reproduction, decision reconstruction correctness,
stale/unavailable detection, causal-overclaim rate, precedent precision, impact-query completeness,
correction/reversal success, privacy/tenant denials, operator burden, latency, storage growth, and
query cost. Token or query-speed gains cannot compensate for a missing source, policy, or authorization.

Phase 0 and the Jira measurement issue predeclare the fixed corpus/workflow revisions, baseline and
candidate SHAs, denominators, minimum evidence, and numeric promotion/hold thresholds before the first
canary result. Hard gates include zero unauthorized/cross-tenant disclosure, zero lost required
evidence/policy links, zero false `CAUSED` edges, deterministic policy reproduction, and successful
event/projection recovery. Other thresholds may be calibrated before observation but are versioned
and never edited retroactively to fit results.

### Phase 4 — Interoperability and adoption decision

Validate a minimal W3C PROV-O export mapping only if a real audit/interchange consumer exists. Do not
adopt RDF, SHACL, OWL, a Rete engine, or Semantica merely to check standards boxes. A separate Jira
decision determines whether more decision classes, automatic capture, signed checkpoints, or policy
engines are justified.

## Jira and release gate

Create one RT-130 child for the implementation and one linked measurement/promotion issue for the
internal canary. The implementation issue owns schemas, typed adapters, governed publication, dual-
host packaging, security tests, and docs. The measurement issue pre-registers the corpus, source/
policy versions, host/model/plugin versions, baseline/candidate SHAs, denominators, minimum evidence,
predeclared thresholds, deterministic-fixture and natural-run strata, metrics above, artifact locations, and
promote/hold/reject result. Raw decision content, actor identity, prompts, paths, credentials, client
data, and graph payloads remain outside Jira. Link the reviewed decision to RT-146 and any proven
packaging to RT-145.

Release requires schema/unit tests, tenant/ACL/authority/prompt-injection and causal-overclaim
fixtures, policy reproduction, correction/purge, Neo4j stage/failure/restore tests, bounded-query
tests, generated-map/config validation, and clean installed Claude Code/Codex smokes. Any automatic
capture, policy enforcement, or client rollout remains a separately accepted Jira decision.

## Completion criteria

- Consequential decisions are reconstructable from canonical evidence without replaying hidden model
  reasoning or mutable traces.
- Evidence, policy, approval, effect, outcome, correction, precedent, influence, and causality remain
  distinct and source-bound.
- Neo4j is a governed projection over existing Rhize systems, not another operational source of truth.
- Claude Code and Codex use one typed, authenticated, privacy-safe contract.
- Semantica is not adopted and no overlapping graph/policy/MCP/plugin stack is introduced.
- Measurement, interoperability, automation, and promotion decisions are explicit Jira work.

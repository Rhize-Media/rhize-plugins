# Unified Memory Routing and Context Assembly

| Field | Value |
|---|---|
| Status | Safe first release implemented; live graph promotion and automatic injection remain gated |
| Date | 2026-08-30 |
| Primary owner | `rhize-context-manager` |
| Adapter owners | `procedural-memory`, `obsidian-second-brain`; later `rhize-devflow`, `rhize-ops`, `rhize-tasks` |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for cross-plugin contracts; Luna for adapters and fixtures after the contract is fixed |
| Cross-host surface | Canonical `rhize-context-manager:memory-context` skill; thin Claude command; Codex skill discovery |
| Jira tracking | RT-151 implementation; RT-158 measurement/promotion; linked to RT-128 |

## Implemented review hardening

Pack identity and candidate envelopes are revalidated on reuse, the current source-ID/revision map is
mandatory, interrupted identical writes repair the private revocation index, and purge also discovers
validated orphan packs under the exact private store.

## Decision

Unify memory at the routing and context-assembly boundary, not by migrating every store into one
database. Keep canonical files and operational stores authoritative. Add a versioned memory envelope,
read-only adapters, deterministic conflict/precedence rules, and a bounded private context preview.

Use the available Neo4j database only for the semantic/relationship lane after the ontology and graph
hygiene gates pass. Keep Graphiti as a design reference; do not install or adopt it.

## Rhize routing, authority, and lifecycle contract

- Unify contracts and bounded retrieval, not stores. Every source domain/subtype and fact keeps one
  canonical owner or reports `none`; broad memory classes may contain several explicitly separated
  lanes. Adapters remain independently replaceable and never gain write authority from a read request.
- A canonical Rhize project identity maps to allowlisted vault roots, procedural namespaces, Neo4j
  tenant/namespace, processing policy, ACL, and retention. Cross-client retrieval is deny-by-default;
  repository basename, topic, or model similarity cannot establish scope.
- Retrieved content is untrusted data. `contentRole`/`authorityClass`, `processingPolicy`,
  `scopeDecision`, and `adapterStatus` travel with every candidate. Memory cannot override system
  policy, the current user request, repository instructions, approvals, or tool permissions.
- Packs use a host-neutral Rhize-owned private storage root, explicit TTL/cleanup, mode `0600`, and a
  source-revocation index. Deletion/purge invalidates packs in both host caches and retains only a
  privacy-safe tombstone.
- Public manifests use pseudonymous/hash identifiers only. Raw source IDs, filenames, task IDs,
  prompts, and absolute paths remain private.

## Independent source reviews

- [How Does Memory for AI Agents Work?](https://www.decodingai.com/p/how-does-memory-for-ai-agents-work)
  provides a useful semantic/episodic/procedural taxonomy and separates retrieval from context
  projection. Its reported CAG-over-RAG improvement is an unmeasured workload-specific anecdote.
- [Implement a Unified Memory From Scratch](https://www.decodingai.com/p/how-to-implement-a-unified-memory-from-scratch)
  contributes ontology-as-contract, durable writes/direct reads, agent-shaped interfaces, and
  reversible derived artifacts. Its MongoDB architecture, thresholds, scale claims, and “lineage is
  free” wording are not sufficient evidence for a storage migration.
- [Understanding Neo4j's Graph Agent Memory System](https://www.decodingai.com/p/understanding-neo4j-graph-agent-memory-system)
  contributes cross-tier provenance and conservative identity handling. It does not demonstrate
  retrieval gains or justify storing raw hidden reasoning. Retain action, tool, observation,
  decision-summary, evidence, and outcome traces instead.

## Verified current state

- `context-stack` already routes among claude-mem, Graphify, Obsidian, CodeGraph, and optional Graphiti,
  but it has no shared candidate/envelope or assembled memory preview.
- `context-pack-v2` is a source-hash-bound private pack for code context, not general memory.
- `procedural-memory` intentionally owns verified executable artifacts and must not become a general
  conversation store.
- Obsidian owns durable human-readable knowledge.
- CodeGraph owns indexed code relationships and must not be copied into a general memory graph.
- Neo4j is available; Graphiti is not implemented.

## Source-of-truth matrix

| Memory class | Authoritative source | V1 adapter behavior |
|---|---|---|
| Working/session | Ephemeral host-supplied current context; durable project state in canonical `STATE.md` | Keep separate lanes; current host state wins only for current-turn facts, while durable policy/verified facts follow repository precedence |
| Episodic | Supported host episodic API plus evidence-bearing run records | Search/read when authorized; otherwise `unavailable` |
| Semantic | Obsidian/canonical files | Return source-bound candidates; later Neo4j is a read-only derived projection whose results retain canonical-source provenance |
| Procedural | `procedural-memory` registry and installed skills | Recall metadata only; never execute from context assembly |
| Code relationships | CodeGraph | Query by version-bound locator; never duplicate graph contents |

A CodeGraph reference is not an assumed globally stable opaque id. It carries canonical repository
identity, commit SHA, repo-relative file path, qualified symbol locator, and CodeGraph tool version;
an index fingerprint/revision is included only when the deployed interface exposes one. The adapter
must resolve that tuple against the named revision or return `stale`/`unresolved`; it may never
silently bind to a same-named symbol, initialize an index, or fetch/sync historical source.

## Memory envelope v1

Each adapter returns metadata plus a private content reference:

- `memoryType`: `working`, `episodic`, `semantic`, or `procedural`;
- `sourceSystem`, stable `sourceId`, and `sourceRevision`;
- tenant/project/task scope and ACL/sensitivity class;
- `validFrom`, `validUntil`, `recordedAt`, and extraction version;
- trust class, confidence, retention class, and provenance/evidence references;
- `contentRole`, `authorityClass`, `processingPolicy`, `scopeDecision`, and normalized `adapterStatus`;
- immutable content hash and private payload reference;
- candidate relevance signals and any contradiction/supersession links.

Public manifests contain identifiers/hashes/enums only. Retrieved content stays in a mode-`0600`
private pack and is deleted or retained according to its source policy.

Temporal fields are nullable/unknown when a source does not provide them; the adapter never fabricates
dates. Adapter status is one of `available`, `empty`, `unavailable`, `unauthorized`, `timeout`,
`stale`, `partial`, or `error`. No fallback broadens scope or interprets `unavailable` as an empty
store.

## Context assembly policy

1. Enforce scope/ACL before retrieval or ranking.
2. Query eligible lanes concurrently with independent timeouts and per-lane result/token caps.
3. Rank within each lane; do not let one prolific store starve the others.
4. Preserve contradictions as separate source-bound candidates.
5. Prefer explicit/current/verified facts over inferred, stale, or lossy summaries.
6. Place procedural candidates as references with trust/health metadata; never turn recall into run.
7. Render a private preview with included/excluded reasons, token budget, freshness, and warnings.
8. Make no memory write from retrieval feedback or model output.

Ranking normalizes signals within each lane, uses fixed lane/result/token budgets and deterministic
tie behavior, and groups contradictions before final ordering. Confidence is never compared directly
across stores. Contradictory candidates remain visible even when one ranks lower, and retrieved
preferences/instructions never acquire authority from topical similarity.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-context-manager/schemas/memory-envelope-v1.schema.json` | Cross-adapter candidate contract |
| Create | `rhize-context-manager/schemas/memory-context-pack-v1.schema.json` | Private assembled-pack manifest |
| Create | `rhize-context-manager/scripts/memory_context/` | Adapter interface, ranking, conflicts, pack, and verification |
| Create | `rhize-context-manager/commands/memory-context.md` | Preview/status/verify entry point |
| Create | `rhize-context-manager/skills/memory-context/SKILL.md` | Canonical cross-host workflow and adapter policy |
| Create | `rhize-context-manager/skills/memory-context/agents/openai.yaml` | Codex routing metadata for the canonical skill |
| Create | `rhize-context-manager/.codex-plugin/plugin.json` | Formal Codex discovery of canonical skills |
| Modify | `rhize-context-manager/skills/context-stack/SKILL.md` | Source-of-truth and routing rules |
| Modify | `rhize-context-manager/skills/graphiti-memory/SKILL.md` | Mark design-reference-only; point to Neo4j plan/current assets |
| Modify | `procedural-memory/skills/procedural-memory/SKILL.md` | Define recall-only adapter boundary |
| Modify | `obsidian-second-brain/` docs/skills | Define canonical semantic-source boundary |
| Create | `evals/memory-context/` | Labeled retrieval, conflict, privacy, and budget corpus |
| Modify | Claude/Codex/marketplace manifests | Keep name, version, skills path, and capability metadata synchronized |
| Modify | READMEs, GUIDEs, CHANGELOG, skill map, setup/doctor manifests | Register only shipped adapters/capabilities and retire active Graphiti routing |

## Claude Code and Codex delivery contract

`rhize-context-manager/skills/memory-context/SKILL.md` is the workflow source of truth. The Claude
command is a thin adapter and Codex discovers the same skill through `.codex-plugin/plugin.json` and
OpenAI agent metadata. Shared schemas/CLI are host-neutral; neither host may depend on the other's
environment variables, hooks, private transcript storage, or implicit home-directory state.

Host capability negotiation supplies current-session candidates explicitly and uses a Claude episodic
adapter only when a supported read API exists. Codex episodic memory is implemented only if Codex
exposes a supported authorized API; neither host may scrape internal transcripts. Procedural recall
requires a versioned machine-readable read-only contract such as `rhize-skill recall --json`; until
that contract exists, the adapter is `unavailable` rather than parsing prose or executing a skill.

Fresh-install tests must discover both surfaces and show equivalent schema, ranking, conflict,
authority, denial, cleanup, and unavailable-state behavior for identical fixtures. Claude and Codex
host/model results remain separate during evaluation.

## Phases

### Phase 0 — Live inventory and boundary freeze

Verify the current versions, interfaces, health, and data-handling rules for claude-mem,
procedural-memory, Obsidian, CodeGraph, Graphify, and Neo4j. Update documentation that currently frames
Graphiti as the only temporal graph direction.

Acceptance:

- every source domain/subtype and fact has exactly one canonical owner or an explicit `none`; broad
  memory classes may have separate, precedence-defined lanes and Neo4j remains a derived projection;
- adapters and writes are separately authorized;
- a CodeGraph reference is pinned to repository, commit, file, symbol, and tool version, plus index
  fingerprint only when exposed; revision/index mismatch fails closed instead of rebinding;
- no plan step assumes Neo4j labels, indexes, tenant model, or SDK version without inspection.
- remove active Graphiti routing/setup/doctor/dependency guidance from `context-stack`,
  `graphiti-memory`, setup manifest, README/GUIDE, marketplace keywords, root dependency matrix, and
  generated maps; retain it only as clearly labeled design/history material;
- canonical project identity, source policies, storage root, retention, purge, and host capability
  matrix are frozen before adapter implementation.

### Phase 1 — Schemas and fake adapters

Implement strict schemas and deterministic fake adapters. Test ACL denial, stale facts, conflicting
claims, missing sources, unhealthy procedures, and result-budget pressure before connecting live data.

Acceptance:

- unknown fields and scope escalation fail closed;
- conflicts remain visible;
- a high-similarity unverified procedure cannot outrank a healthy verified one silently;
- manifests contain no content, absolute paths, prompts, or credentials.
- malicious memory content remains inert and cannot change authority, policy, scope, approvals, or tools;
- deterministic per-lane normalization and tie/conflict behavior are identical on both hosts;
- every normalized adapter status and source-revocation transition has a fixture.

### Phase 2 — Read-only local adapters and preview

Connect existing local sources one at a time: canonical `STATE.md` plus explicit host-supplied current
context, Obsidian source notes, supported procedural recall metadata, then a host episodic API if its
supported read interface is healthy. Each adapter has independent timeout, result budget, circuit
breaker, and normalized unavailable state.

Acceptance:

- one failed store cannot block the preview;
- missing data is reported as unavailable, not zero;
- context stays under the declared per-lane and total token budgets;
- `verify` rejects any pack whose source revision changed.
- deletion/purge invalidates all matching host packs and privacy-safe manifests;
- historical CodeGraph resolution never fetches, initializes, syncs, or silently rebinds a stale ref.

### Phase 3 — Evaluation before injection

Use a bounded, reviewed corpus of real redacted questions with expected source items. Measure retrieval
relevance, contradiction surfacing, stale inclusion, token count, latency, and operator corrections.
Do not use generated rows as operational evidence.

Promotion requires:

- no ACL or tenant leak;
- zero silent contradiction collapse;
- complete provenance for every included item;
- measured benefit over the current single-store/baseline path on an eligible query class;
- explicit operator approval before any automatic context injection.

Use a paired, host-stratified design with frozen query/corpus/source fingerprints, baseline and
candidate SHA/version, adapter-health snapshot, host/model, relevance/recall and critical misses,
contradiction/stale rates, task correctness, follow-up reads/tool calls, latency/token/cost, and
operator corrections. Failed/incomplete runs remain non-comparable and Claude/Codex results are never
pooled to hide model or capability differences.

### Phase 4 — Neo4j semantic adapter canary

Begin only after `neo4j-marketplace-ontology.md` and `neo4j-graph-hygiene-and-review.md` pass their
gates. Query approved claims/relations through a small business-level interface, not raw Cypher.

Acceptance:

- version-bound CodeGraph locators are resolved or fail closed; graph contents are never copied;
- Graphify/Neo4j candidates preserve source ACL, trust, valid time, and extraction version;
- pack verification detects graph/source revision drift;
- Graphiti remains absent.
- read-only credentials enforce tenant filters inside the query layer plus depth, time, and result
  budgets; agents cannot supply raw Cypher;
- only Graphify records with complete canonical-source provenance are eligible.

### Phase 5 — Optional bounded injection

After successful previews, add an opt-in, finite canary modeled on the existing context-experiment
arming/receipt pattern. No automatic write-back. A rejected or stale pack stays silent and does not
consume the armed run.

Injection remains explicit-preview-only in either host unless that host exposes a supported bounded
injection surface and a separate Jira canary/promotion decision is accepted.

## Jira and release gate

The implementation ticket under RT-130 links to RT-128 for existing context-pack experiments. Track
the procedural JSON adapter as an explicit companion dependency, each live adapter as an independently
releasable slice, the paired cross-host retrieval evaluation as a measurement follow-up, the Graphiti
operational-surface correction as a prerequisite, and Neo4j/injection as separately blocked work.
Jira contains sanitized aggregate metrics, baseline/release SHAs, host/plugin versions, artifact
locations, observation dates, and promote/hold decisions—not raw memories, source IDs, paths, prompts,
or private packs. Link proven packaging to RT-145 and evidence review to RT-146.

Before release, run schema/unit tests, authority/injection/privacy fixtures, adapter timeout/circuit-
breaker and purge tests, deterministic ranking/conflict tests, plugin-config validation, generated-map
build/render/stale checks, and fresh installed Claude Code/Codex discovery.

## Completion criteria

- Memory stores remain independently authoritative and replaceable.
- One versioned read contract assembles bounded, source-bound context.
- Conflict, freshness, trust, ACL, and provenance survive retrieval.
- Procedural recall never bypasses execution trust/health gates.
- Neo4j is the only new graph-memory backend considered; Graphiti is not adopted.
- Host capability differences are explicit and never filled by private-state scraping.
- Claude Code and Codex use one canonical routing, ranking, authority, and lifecycle contract.
- Deferred adapters, measurement, Neo4j, and injection are explicit Jira gates.

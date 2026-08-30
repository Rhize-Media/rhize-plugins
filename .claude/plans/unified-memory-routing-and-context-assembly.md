# Unified Memory Routing and Context Assembly

| Field | Value |
|---|---|
| Status | Proposed for review |
| Date | 2026-08-30 |
| Primary owner | `rhize-context-manager` |
| Adapter owners | `procedural-memory`, `obsidian-second-brain`; later `rhize-devflow`, `rhize-ops`, `rhize-tasks` |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for cross-plugin contracts; Luna for adapters and fixtures after the contract is fixed |

## Decision

Unify memory at the routing and context-assembly boundary, not by migrating every store into one
database. Keep canonical files and operational stores authoritative. Add a versioned memory envelope,
read-only adapters, deterministic conflict/precedence rules, and a bounded private context preview.

Use the available Neo4j database only for the semantic/relationship lane after the ontology and graph
hygiene gates pass. Keep Graphiti as a design reference; do not install or adopt it.

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
| Working/session | Current conversation, tool state, `STATE.md` | Read bounded current state only |
| Episodic | claude-mem/session summaries and evidence-bearing run records | Search/read; never promote automatically |
| Semantic | Obsidian/canonical files; later approved Neo4j claims/relations | Return source-bound candidates |
| Procedural | `procedural-memory` registry and installed skills | Recall metadata only; never execute from context assembly |
| Code relationships | CodeGraph | Query by version-bound locator; never duplicate graph contents |

A CodeGraph reference is not an assumed globally stable opaque id. It carries repository identity,
commit SHA, CodeGraph index/schema revision, repo-relative file path, and qualified symbol locator.
The adapter must resolve that tuple against the named revision or return `stale`/`unresolved`; it may
never silently bind the reference to a same-named symbol after re-indexing or a source revision change.

## Memory envelope v1

Each adapter returns metadata plus a private content reference:

- `memoryType`: `working`, `episodic`, `semantic`, or `procedural`;
- `sourceSystem`, stable `sourceId`, and `sourceRevision`;
- tenant/project/task scope and ACL/sensitivity class;
- `validFrom`, `validUntil`, `recordedAt`, and extraction version;
- trust class, confidence, retention class, and provenance/evidence references;
- immutable content hash and private payload reference;
- candidate relevance signals and any contradiction/supersession links.

Public manifests contain identifiers/hashes/enums only. Retrieved content stays in a mode-`0600`
private pack and is deleted or retained according to its source policy.

## Context assembly policy

1. Enforce scope/ACL before retrieval or ranking.
2. Query eligible lanes concurrently with independent timeouts and per-lane result/token caps.
3. Rank within each lane; do not let one prolific store starve the others.
4. Preserve contradictions as separate source-bound candidates.
5. Prefer explicit/current/verified facts over inferred, stale, or lossy summaries.
6. Place procedural candidates as references with trust/health metadata; never turn recall into run.
7. Render a private preview with included/excluded reasons, token budget, freshness, and warnings.
8. Make no memory write from retrieval feedback or model output.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `rhize-context-manager/schemas/memory-envelope-v1.schema.json` | Cross-adapter candidate contract |
| Create | `rhize-context-manager/schemas/memory-context-pack-v1.schema.json` | Private assembled-pack manifest |
| Create | `rhize-context-manager/scripts/memory_context/` | Adapter interface, ranking, conflicts, pack, and verification |
| Create | `rhize-context-manager/commands/memory-context.md` | Preview/status/verify entry point |
| Modify | `rhize-context-manager/skills/context-stack/SKILL.md` | Source-of-truth and routing rules |
| Modify | `rhize-context-manager/skills/graphiti-memory/SKILL.md` | Mark design-reference-only; point to Neo4j plan/current assets |
| Modify | `procedural-memory/skills/procedural-memory/SKILL.md` | Define recall-only adapter boundary |
| Modify | `obsidian-second-brain/` docs/skills | Define canonical semantic-source boundary |
| Create | `evals/memory-context/` | Labeled retrieval, conflict, privacy, and budget corpus |
| Modify | READMEs, GUIDEs, skill map, setup manifests | Register only shipped adapters/capabilities |

## Phases

### Phase 0 — Live inventory and boundary freeze

Verify the current versions, interfaces, health, and data-handling rules for claude-mem,
procedural-memory, Obsidian, CodeGraph, Graphify, and Neo4j. Update documentation that currently frames
Graphiti as the only temporal graph direction.

Acceptance:

- every memory class has exactly one authoritative source or an explicit “none”;
- adapters and writes are separately authorized;
- a CodeGraph reference is pinned to repository, commit, index/schema revision, file, and symbol, and
  a re-index/revision mismatch fails closed instead of rebinding;
- no plan step assumes Neo4j labels, indexes, tenant model, or SDK version without inspection.

### Phase 1 — Schemas and fake adapters

Implement strict schemas and deterministic fake adapters. Test ACL denial, stale facts, conflicting
claims, missing sources, unhealthy procedures, and result-budget pressure before connecting live data.

Acceptance:

- unknown fields and scope escalation fail closed;
- conflicts remain visible;
- a high-similarity unverified procedure cannot outrank a healthy verified one silently;
- manifests contain no content, absolute paths, prompts, or credentials.

### Phase 2 — Read-only local adapters and preview

Connect existing local sources one at a time: `STATE.md`/current session, procedural recall metadata,
Obsidian source notes, then claude-mem if its supported read interface is healthy. Each adapter has a
timeout and clean unavailable state.

Acceptance:

- one failed store cannot block the preview;
- missing data is reported as unavailable, not zero;
- context stays under the declared per-lane and total token budgets;
- `verify` rejects any pack whose source revision changed.

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

### Phase 4 — Neo4j semantic adapter canary

Begin only after `neo4j-marketplace-ontology.md` and `neo4j-graph-hygiene-and-review.md` pass their
gates. Query approved claims/relations through a small business-level interface, not raw Cypher.

Acceptance:

- version-bound CodeGraph locators are resolved or fail closed; graph contents are never copied;
- Graphify/Neo4j candidates preserve source ACL, trust, valid time, and extraction version;
- pack verification detects graph/source revision drift;
- Graphiti remains absent.

### Phase 5 — Optional bounded injection

After successful previews, add an opt-in, finite canary modeled on the existing context-experiment
arming/receipt pattern. No automatic write-back. A rejected or stale pack stays silent and does not
consume the armed run.

## Completion criteria

- Memory stores remain independently authoritative and replaceable.
- One versioned read contract assembles bounded, source-bound context.
- Conflict, freshness, trust, ACL, and provenance survive retrieval.
- Procedural recall never bypasses execution trust/health gates.
- Neo4j is the only new graph-memory backend considered; Graphiti is not adopted.

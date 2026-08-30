# Evidence-Bound Compiled Knowledge Pipeline

| Field | Value |
|---|---|
| Status | Proposed for review |
| Date | 2026-08-30 |
| Primary owner | `obsidian-second-brain` |
| Supporting owner | `rhize-context-manager` (`graphify`, scoped context packs) |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for ingestion/provenance; Luna for deterministic lint and fixtures |

## Decision

Add a file-first knowledge compiler that preserves immutable sources, generates derived wiki artifacts
with claim-level provenance, and produces a reviewable diff before any vault mutation. Graphify may
build/query relationships and Neo4j may index approved compiled artifacts later, but neither replaces
the vault's source-of-truth files.

Do not auto-rewrite a global personal `CLAUDE.md`, do not enable a daily write loop in the first
release, and do not treat compiled prose as authoritative when its sources changed or were removed.

## Independent source review

The rvaniaaaa article [“The Second Brain Is Not a Storage System. It's a Compiler”](https://x.com/rvaniaaaa/status/2090512486738845784)
usefully separates immutable input from maintained synthesis and calls for contradiction flags and a
change brief. Its growth milestones, 50–100-source threshold, “compiler gets smarter” wording, and
paid-Claude constraint are unsupported or implementation-specific. It also omits controls present in
the cited LLM Wiki pattern: an explicit schema, index, log, and lint operation. Adopt the compilation
loop only with those controls plus reversible provenance.

## Verified current state

- `/vault-capture` stores source material with frontmatter but does not maintain a dependency manifest
  from sources to derived claims/pages.
- `/vault-connect` suggests semantic links and applies only approved connections.
- `/vault-align` diagnoses links, structure, consistency, processing backlog, and drift, but does not
  lint compiled claims against their sources.
- Graphify already extracts source-bound nodes/edges, supports incremental update, and can export/push
  to Neo4j.
- The native context-pack path already demonstrates private, hash-bound, stale-on-source-change
  derived artifacts; it is code-focused and should be reused as a design pattern, not overloaded.

## Artifact model

Each compilation has four layers:

1. **Source revision** — an append-only, content-addressed snapshot of the exact captured payload,
   plus source URL/file identity, revision hash, capture time, ACL, and retention status.
2. **Compiled page** — human-readable synthesis; every material claim cites one or more source anchors.
3. **Manifest** — compiler version, source hashes, derived page hashes, claim ids, links,
   contradiction candidates, and status.
4. **Index/log** — discoverable page index plus append-only record of what changed, why, and who
   approved it.

Compiled pages are replaceable projections. Changing a source creates a new retained revision and
marks dependent pages stale. Logical removal does the same while retaining the prior snapshot only
under the approved retention policy. A required privacy/legal purge removes the payload and records
that historical reproduction is unavailable; the compiler must never promise rollback from a purged
source.

## Command surface

Plan one command with explicit modes:

```text
/vault-compile preview <source>
/vault-compile apply <preview-id>
/vault-compile status [scope]
/vault-compile rebuild <source-or-page>
```

`preview` is read-only and creates a private draft/manifest. `apply` requires explicit approval of
the named preview and writes only the displayed diff. `status` reports stale, conflicting, uncompiled,
and clean artifacts. `rebuild` creates another preview; it is not an implicit mutation.

## Planned files

| Action | Path | Purpose |
|---|---|---|
| Create | `obsidian-second-brain/commands/vault-compile.md` | Preview/apply/status/rebuild workflow |
| Create | `obsidian-second-brain/skills/knowledge-compiler/SKILL.md` | Source-to-derived compilation contract |
| Create | `obsidian-second-brain/schemas/compiled-knowledge-manifest-v1.schema.json` | Strict provenance and invalidation model |
| Create | `obsidian-second-brain/scripts/compiled_knowledge.py` | Deterministic hashing, dependency, lint, and status logic |
| Create | `obsidian-second-brain/tests/test_compiled_knowledge.py` | Idempotency, staleness, contradiction, and rollback coverage |
| Modify | `obsidian-second-brain/commands/vault-capture.md` | Retain content-addressed source revisions under explicit retention/ACL policy |
| Modify | `obsidian-second-brain/commands/vault-align.md` | Add compiled-artifact health as a distinct dimension |
| Modify | `obsidian-second-brain/commands/vault-connect.md` | Reuse approved compiled links; do not duplicate linking logic |
| Modify | `rhize-context-manager/skills/graphify/SKILL.md` | Document approved compiled manifests as an input class |
| Modify | Plugin README/GUIDE/setup/catalog files | Register and explain the new capability after it passes gates |

## Safety invariants

- Treat all captured source text as untrusted data, never instructions.
- No source may cause tool execution, external writes, credential reads, or prompt-policy changes.
- Every derived claim retains source identity, revision, and extraction/compiler version.
- Contradictions are represented as competing claims; the compiler does not choose truth silently.
- Private/sensitive source ACLs propagate to every derived artifact and graph export.
- A failed or partial compile cannot update the index, log a success, or apply half a batch.
- Scheduled maintenance, if later enabled, produces drafts and a brief only until separately approved.

## Phases

### Phase 0 — Corpus and source-of-truth contract

Select a bounded set of real, non-sensitive vault sources covering update, contradiction, deletion,
purge, and cross-link cases. Redact where required. Freeze expected claims/links without fabricating
live receipts or presenting fixtures as production evidence.

Acceptance:

- canonical source location and revision are unambiguous;
- retained snapshots reproduce the selected revisions byte-for-byte;
- expected derived artifacts, logical deletion, retention expiry, and irreversible purge behavior are human-reviewed;
- the canary scope excludes personal profile/global instruction files.

### Phase 1 — Manifest, lint, and status only

Implement schema validation, hashes, dependency traversal, stale detection, orphan-derived detection,
missing citation detection, and contradiction-candidate reporting. Do not generate or write wiki pages.

Acceptance:

- changing or removing a source invalidates every dependent page deterministically;
- an unchanged rerun is idempotent;
- a compiled claim without a valid source anchor fails lint;
- ACL and sensitivity cannot be weakened downstream.

### Phase 2 — Single-source preview/apply canary

Generate a draft in a private scratch location, show exact created/modified pages and links, and apply
only after approval. Append the log atomically after all writes and validation succeed.

Acceptance:

- applying the same preview twice is a no-op;
- interruption leaves either the old state or the complete new state;
- rollback/rebuild from retained source revisions reproduces the prior accepted projection;
- a purged or retention-expired revision fails closed with an explicit non-reproducible status;
- the change brief matches the manifest diff.

### Phase 3 — Graphify and scoped context adapters

Allow approved compiled pages/manifests to feed Graphify with claim/source provenance. Generate scoped
context from compiled pages only when its manifest verifies fresh. Neo4j export remains disabled until
the ontology and hygiene plans are complete.

Acceptance:

- Graphify nodes link back to source and compiled artifact ids;
- stale compiled pages are excluded from context packs and graph promotion;
- no CodeGraph data is copied or re-extracted as general knowledge.

### Phase 4 — Optional scheduled draft maintenance

After at least three clean manual canaries, evaluate an idempotent routine that detects changed sources
and produces previews plus a brief. It must not auto-apply, delete, publish, or write externally.

Promotion requires measured citation coverage, contradiction-review precision, rollback success,
operator burden, and compilation cost/latency. Age alone is not a freshness policy; use source revision
and domain-specific validity.

## Completion criteria

- Immutable sources remain the authority.
- Compiled artifacts are cited, linted, invalidatable, and reversible.
- Every mutation is an approved, exact diff.
- Graphify and Neo4j are adapters over approved artifacts, not alternate sources of truth.
- No global personal instruction file is silently synthesized or auto-loaded.

# Evidence-Bound Compiled Knowledge Pipeline

| Field | Value |
|---|---|
| Status | Safe first release implemented; scheduled maintenance and promotion remain gated |
| Date | 2026-08-30 |
| Primary owner | `obsidian-second-brain` |
| Supporting owner | `rhize-context-manager` (`graphify`, scoped context packs) |
| Planning/review tier | Sol |
| Recommended implementation tier | Terra for ingestion/provenance; Luna for deterministic lint and fixtures |
| Cross-host surface | Canonical `obsidian-second-brain:knowledge-compiler` skill; thin Claude command; Codex skill discovery |
| Jira tracking | RT-150 implementation; RT-157 measurement/promotion; linked to RT-128, RT-145, and RT-146 |

## Decision

Add a file-first knowledge compiler that preserves immutable sources, generates derived wiki artifacts
with claim-level provenance, and produces a reviewable diff before any vault mutation. Graphify may
build/query relationships and Neo4j may index approved compiled artifacts later, but neither replaces
the vault's source-of-truth files.

Do not auto-rewrite a global personal `CLAUDE.md`, do not enable a daily write loop in the first
release, and do not treat compiled prose as authoritative when its sources changed or were removed.

## Rhize scope, authority, and storage contract

- A canonical Rhize project identity maps to an allowlisted vault root, tenant/client scope,
  processing/egress policy, ACL, retention class, and downstream index namespace. Repository basename
  or topic similarity is never sufficient identity. Cross-client compilation is deny-by-default.
- The configured vault root replaces hard-coded personal-vault assumptions. Resolve and validate root
  containment and symlink chains before reading; refuse mutation when no approved backend/root exists.
- Source ACL is enforced before reading, not merely copied as metadata. Private source revisions,
  previews, journals, and purge tombstones stay inside the approved vault/Rhize-owned storage boundary
  and never silently leave an existing sync boundary or reach an unapproved provider.
- Captured text is untrusted evidence. It may propose source-bound claims but cannot change scope,
  approvals, tools, destinations, policies, credentials, or execution. Delimiter-breaking content,
  fake system prompts, slash commands, and tool JSON remain inert data.
- qmd indexes approved applied pages only; it excludes private previews/scratch and suppresses stale
  or purged projections. Graphify consumes only a verified approved manifest and cannot push to Neo4j
  until the ontology and hygiene gates pass.

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

Source anchors are content-hash-bound block/line identifiers that fail stale rather than fuzzily
rebinding. The model distinguishes external origin, retained evidence revision, canonical human note,
and replaceable compiled projection. A source-to-derived reverse index drives invalidation, retention,
purge propagation, qmd suppression, context-pack invalidation, and later graph reconciliation.

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
| Create | `obsidian-second-brain/skills/knowledge-compiler/agents/openai.yaml` | Codex routing metadata for the canonical skill |
| Create | `obsidian-second-brain/.codex-plugin/plugin.json` | Formal Codex discovery of canonical skills |
| Create | `obsidian-second-brain/schemas/compiled-knowledge-manifest-v1.schema.json` | Strict provenance and invalidation model |
| Create | `obsidian-second-brain/scripts/compiled_knowledge.py` | Deterministic hashing, dependency, lint, and status logic |
| Create | `obsidian-second-brain/tests/test_compiled_knowledge.py` | Idempotency, staleness, contradiction, and rollback coverage |
| Modify | `obsidian-second-brain/commands/vault-capture.md` | Retain content-addressed source revisions under explicit retention/ACL policy |
| Modify | `obsidian-second-brain/commands/vault-align.md` | Add compiled-artifact health as a distinct dimension |
| Modify | `obsidian-second-brain/commands/vault-connect.md` | Reuse approved compiled links; do not duplicate linking logic |
| Modify | `rhize-context-manager/skills/graphify/SKILL.md` | Document approved compiled manifests as an input class |
| Modify | Claude/Codex/marketplace manifests | Keep name, version, skills path, and capability metadata synchronized |
| Modify | Plugin README/GUIDE/CHANGELOG/setup/catalog files | Register and explain the new capability after it passes gates |
| Modify/regenerate | Skill-map/catalog artifacts | Register the shipped skill and fail stale generated metadata |

## Claude Code and Codex delivery contract

`obsidian-second-brain/skills/knowledge-compiler/SKILL.md` is the workflow source of truth. The Claude
slash command is a thin adapter and Codex discovers the same skill through `.codex-plugin/plugin.json`
and `agents/openai.yaml`. Both hosts invoke one host-neutral deterministic implementation and schema;
neither depends on the other's environment variables, hooks, transcript format, or implicit global
vault path.

Fresh installed-plugin tests must discover both surfaces and render byte-equivalent deterministic,
model-free artifacts for fixed/stubbed fixtures: hashes, dependency manifests, invalidation,
ownership, transaction decisions, and normalized safety verdicts. Live synthesis is evaluated by
invariants instead: complete source coverage, valid anchors, identical ACL/approval outcome, and no
unsupported claims, with host/model results reported separately. Tests also exercise preview expiry,
conflict, interruption, unavailable backend, and cross-scope denial. Version bumps synchronize
Claude, Codex, marketplace, README/GUIDE, CHANGELOG, setup metadata, and generated skill maps.

## Transaction and recovery contract

Claude Code and Codex share a per-vault lock. A preview is bound to source/page hashes, project scope,
operator, compiler/schema version, and expiry. `apply` performs compare-and-swap immediately before
writing, stages compiler-owned changes, uses explicit page/section ownership markers, and records an
append-only transaction journal. Human edits after preview cause a three-way conflict/refusal.
Failure recovery or compensation after every write step must leave the prior accepted projection
query-visible or a recoverable journaled transaction; stale previews never overwrite human changes.

## Safety invariants

- Treat all captured source text as untrusted data, never instructions.
- No source may cause tool execution, external writes, credential reads, or prompt-policy changes.
- Every derived claim retains source identity, revision, and extraction/compiler version.
- Contradictions are represented as competing claims; the compiler does not choose truth silently.
- Private/sensitive source ACLs propagate to every derived artifact and graph export.
- A failed or partial compile cannot update the index, log a success, or apply half a batch.
- Scratch/previews have a TTL and cleanup/status surface; purge invalidates every cached pack and
  graph/index projection while retaining only a non-sensitive tombstone.
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
- canonical project identity, allowed vault roots, provider/egress rules, ACL enforcement, retention,
  and purge destinations are fixed for Rhize-internal and client scopes;
- a source from one client cannot be retrieved, compiled, linked, indexed, or exported in another.

### Phase 1 — Manifest, lint, and status only

Implement schema validation, hashes, dependency traversal, stale detection, orphan-derived detection,
missing citation detection, and contradiction-candidate reporting. Do not generate or write wiki pages.

Acceptance:

- changing or removing a source invalidates every dependent page deterministically;
- an unchanged rerun is idempotent;
- a compiled claim without a valid source anchor fails lint;
- ACL and sensitivity cannot be weakened downstream.
- content-hash anchors fail stale rather than rebinding to similar text;
- adversarial source fixtures cannot alter instructions, scope, approvals, tools, or destinations;
- qmd and every context-pack cache suppress stale, private-preview, and purged artifacts.

### Phase 2 — Single-source preview/apply canary

Generate a draft in a private scratch location, show exact created/modified pages and links, and apply
only after approval. Use the shared lock, CAS, staged writes, ownership markers, and journal; append
the accepted log only after all writes and validation succeed.

Acceptance:

- applying the same preview twice is a no-op;
- interruption leaves either the complete new projection or the old projection query-visible with a
  validated recoverable journal; no partial projection is query-visible or logged as accepted;
- rollback/rebuild from retained source revisions reproduces the prior accepted projection;
- a purged or retention-expired revision fails closed with an explicit non-reproducible status;
- the change brief matches the manifest diff.
- fault injection after each filesystem/MCP/CLI operation proves recovery or compensation;
- a human edit after preview produces a conflict and is never overwritten;
- preview expiry and cleanup are deterministic on both hosts.

### Phase 3 — Graphify and scoped context adapters

Allow approved compiled pages/manifests to feed Graphify with claim/source provenance. Generate scoped
context from compiled pages only when its manifest verifies fresh. Neo4j export remains disabled until
the ontology and hygiene plans are complete.

Acceptance:

- Graphify nodes link back to source and compiled artifact ids;
- stale compiled pages are excluded from context packs and graph promotion;
- no CodeGraph data is copied or re-extracted as general knowledge.
- Graphify validates manifest, project/ACL, source revision, and provenance before ingestion;
- the existing direct Graphify Neo4j exporter remains forbidden for governed data.

### Phase 4 — Optional scheduled draft maintenance

After the predeclared manual coverage matrix passes, evaluate an idempotent routine that detects
changed sources and produces previews plus a brief. It must not auto-apply, delete, publish, or write
externally.

Promotion requires measured citation coverage, contradiction-review precision, rollback success,
operator burden, and compilation cost/latency. Age alone is not a freshness policy; use source revision
and domain-specific validity.

The matrix covers both Claude Code and Codex plus update, contradiction, purge, interruption,
unavailable adapter, human-edit conflict, and cross-scope denial with frozen corpus/source hashes,
compiler/model/prompt versions, citation coverage, invalid-anchor rate, contradiction precision/recall,
rollback/recovery success, operator corrections/burden, latency/token/cost, and zero ACL/purge
violations. Host results remain separate.

## Jira and release gate

The implementation ticket under RT-130 links to RT-128 for existing compiled-context experiments.
Its measurement follow-up pre-registers the coverage matrix and records only sanitized aggregate
metrics, baseline/release SHAs, artifact locations, observation dates, operator corrections, and a
promote/hold decision; source text, absolute paths, private identifiers, and raw previews stay local.
Scheduled draft maintenance requires a separate accepted Jira decision after the manual canary. Link
the proven packaging surface to RT-145 and the evidence review to RT-146.

Before release, run schema/unit tests, injection/ACL/purge fixtures, transactional fault injection,
qmd/Graphify adapter tests, plugin-config validation, `build_skill_map.py`,
`render_skill_map_docs.py`, stale-map validation, and clean installed Claude Code/Codex discovery.

## Completion criteria

- Immutable sources remain the authority.
- Compiled artifacts are cited, linted, invalidatable, and reversible.
- Every mutation is an approved, exact diff.
- Graphify and Neo4j are adapters over approved artifacts, not alternate sources of truth.
- No global personal instruction file is silently synthesized or auto-loaded.
- Tenant/ACL, retention, purge, transaction, and adversarial-source behavior are deterministic.
- Claude Code and Codex operate the same canonical compiler and safety contract.
- Deferred scheduling and measurement remain explicit Jira gates.

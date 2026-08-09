# Skill map relationships v2 — follows, augments, remediates, conditions, query layer

**Status:** approved via brainstorm 2026-08-09 (Jim) · implements on top of schema 1.1 (`597ec14`, `fbd1bb8`)

## Decisions made (with rationale)

1. **`follows` (new edge, mined).** Directed A→B: "B is commonly invoked after A in the same
   session." Derived by the monitor from ordered per-session skill events (time-adjacent pairs,
   threshold ≥2 distinct sessions), emitted into the LOCAL overlay only (source: `monitor`,
   weights `{sessions, windowDays}`). Complements the declared `precedes` (curated intent) —
   same surfacing consumer, different provenance. Never hand-authored.
2. **`augments` (new edge, declared, skill → topic tag).** "Run me alongside/after anything in
   this category to improve its output." Cross-cutting modifier, e.g. humanizer augments
   `tag:topic/content-authoring`. Deliberately NOT `extends`: no lexical overlap with targets,
   no gate exemption, no depth semantics, target is a category not a skill. Declared in
   frontmatter `metadata.rhize.augments: [<topic-slug>]` for Rhize skills; in
   `catalog/skill-relations.json` for third-party skills (their frontmatter isn't ours to edit).
3. **`remediates` (new edge, declared, skill → condition tag).** "Surface me when this failure
   happens." Targets a new third tag kind: `condition` entries in `catalog/tags.json`
   (`condition:build-failure`, `type-error`, `test-failure`, `lint-failure`, `merge-conflict`;
   closed vocabulary, unknown slug = BuildError). Each condition entry carries `patterns`:
   regexes matched against FAILED tool output (e.g. `error TS\d+` → type-error). Symmetry with
   augments: same catalog, same validation, different tag kind + matching surface (tool output,
   not prompt).
4. **`pairs-with`: NOT added.** Covered by augments (cross-cutting), depends-on (functional),
   usage-cooccurs (observed). Revisit later as an audit *promotion target* (strong stable
   cooccurs → curated pairs-with); do not hand-author.
5. **MCP dependencies reuse `depends-on`** with a new node kind `mcp-server`
   (`mcp:<server-name>`), minted from declarations (frontmatter `metadata.rhize.dependsOn`
   accepting `mcp:<name>` targets, or relations catalog). v1 scope-honesty: we model the
   dependency; availability-aware filtering is limited to what a hook can cheaply detect
   (server configured vs absent in the machine's MCP config) — live connection state is not
   reliably readable from a hook and is NOT claimed.
6. **Query layer: two-tier (option A).**
   - **Materialized views** for hot paths: the build emits `generated/skill-map.indexes.json`
     (deterministic, `--check-stale`-covered): `router` (token → skill signals),
     `disclosure` (stack → bases with extenders pre-folded), `remediation` (condition →
     ranked skills + patterns), `succession` (skill → precedes/follows successors).
     Hooks read flat answers; no traversal logic in hook code. Local overlay contributes a
     machine-local index layer merged at resolve time (follows lives there).
   - **Named declarative queries** for everything else: `catalog/queries.json` holds walk
     specs (start set → edge steps → filters → output); `scripts/query_skill_map.py <name>`
     interprets them (one walker, Python only — hooks never use it). Seed queries:
     `what-extends`, `what-augments`, `what-remediates`, `what-follows`, `overlap-candidates`,
     `unroutable-skills`, `mcp-dependents`. Cypher-shaped without Cypher: specs port
     mechanically if the map ever moves to a real graph DB.
7. **New consumers (both zero-dep Node, fail-silent, max one suggestion, same discipline as
   the router):**
   - `remediation-suggester.js` — PostToolUse on failing tool results: match output against
     condition patterns via the remediation index → suggest the top remediating skill.
   - `next-step-suggester.js` — PostToolUse matcher `Skill`: after a skill invocation, look up
     the succession index (declared `precedes` first, mined `follows` as fallback) → suggest
     the successor. This finally gives `precedes` a runtime consumer.
   - Router/disclosure refactor to read the materialized indexes (behavior unchanged; tests
     must pass unmodified except where index plumbing is asserted).

## Seed data (grounded, small)

- augments (catalog, third-party): `humanizer/humanizer` → `content-authoring`.
- augments (frontmatter, rhize): `seo-aeo-geo/content-seo` → `content-authoring`.
- remediates (catalog, third-party): ecc build-resolver family → `build-failure`
  (react/go/rust/kotlin/java/swift/dart/django/cpp resolvers), `ecc:build-error-resolver` →
  `build-failure` + `type-error`.
- remediates (frontmatter, rhize): `rhize-devflow/error-lifecycle-management` →
  `test-failure` (its error-lifecycle scope; verify wording against the skill before tagging).
- depends-on mcp: `rhize-context-manager/graphiti-memory` → `mcp:graphiti` IF the skill names
  a server (verify); `seo-aeo-geo` skills → `mcp:dataforseo` (verify against skill docs).
  Only declare what the skill text actually supports.

## Non-goals / deferred

Cypher/graph-DB engine; pairs-with promotion pipeline; live MCP connection-state detection;
JS implementation of the declarative query walker; mining `follows` across machines.

## Verification bar

Deterministic builds incl. indexes; `--check-stale` covers indexes; full existing test suite
green; new tests for: condition-pattern matching (fixture failing outputs), succession lookup,
augments surfacing, index staleness, query CLI (each seed query against fixture map);
schema bump with enums for new edge types + tag kind + node kind; docs (`docs/skill-map.md`),
CHANGELOG, version bumps (context-manager minor; devflow patch; seo-aeo-geo patch);
viewer gains the new edge styles + condition/mcp node kinds.

## Consumer-facing article follow-up

After implementation: revision pass on the published article + social content to cover the
novel concepts (augments-as-category-modifier, conditions with detection patterns,
succession surfacing, two-tier query layer) with their concrete benefits.

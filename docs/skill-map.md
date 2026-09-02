# Skill Map — Conventions

The skill map is the **generated** graph substrate for skill routing, curation, and disclosure
across this repo's plugins. It replaces the flat, hand-restated skill inventory (marketplace.json
+ per-plugin READMEs + root catalog + GUIDE tables) with one machine-produced artifact. See
`.claude/plans/skill-map-graph-substrate.md` for the full rationale and phased rollout; this doc
only records the conventions that downstream consumers (router hook, session-disclosure hook,
`/start`, curation gates, generated docs, vault visualization, the `weekly-skill-audit` scheduled
task) rely on.

The schema contract lives at `schemas/skill-map.schema.json` (JSON Schema, draft 2020-12).

**Audit-stops-on-stale rule:** `weekly-skill-audit` (Phase 4) rebuilds the static and local maps
and runs `scripts/validate_skill_map.py --check-stale` as its first step, before anything else in
that run. If `--check-stale` fails — the committed `generated/skill-map.static.json` no longer
matches what the sources compile to — the audit commits the freshly rebuilt artifact (this repo is
auto-push) and stops for that run rather than continuing with drift checks or refinement-queue
writes against a map it just proved was wrong. This is the same failure mode the "generation-only
policy" below exists to prevent, made into a hard gate instead of a documentation note.

## Deep dives

This page covers what the skill map is, the files it's made of, its schema vocabulary, and how to
query it. For the mechanics behind any one piece:

- **[Edge Semantics — Deep Reference](./skill-map/edge-semantics.md)** — `fork-of` drift checks,
  the three-way drift verdict, `usage-cooccurs` weights, the third-party ecosystem inventory,
  `extends`/`precedes`/`follows`, `augments`, `remediates`, and `depends-on`/`mcp-server` nodes.
- **[Query Layer — Deep Reference](./skill-map/query-layer.md)** — the two-tier query system:
  materialized indexes (Tier 1) consumed by hooks at runtime, and named declarative queries
  (Tier 2) for ad hoc audit/curation questions.
- **[Agent-Dispatch Surface](./skill-map/agent-dispatch-surface.md)** — the 2026-08-26 measurement
  instrument for subagent brief skill-naming, its spike verdicts, and the forward contract for
  graph-node skill declarations.
- **[Generated Docs & Vault Publish](./skill-map/generated-docs.md)** — Phase 5's managed-section
  doc rendering and the Obsidian vault publish.
- `.claude/plans/skill-map-graph-substrate.md` — full rationale and phased rollout history
  (Phase 0 through Phase 5).

## Artifacts

| File | Where | Contents |
|---|---|---|
| `schemas/skill-map.schema.json` | committed | Node/edge contract, `schemaVersion`. |
| `generated/skill-map.static.json` | committed | Deterministic repo facts — this repo's plugins, skills, commands, hooks, and their `contains`/`fork-of`/relations-catalog edges. Produced by `scripts/build_skill_map.py`; never hand-edited. |
| `generated/skill-map.indexes.json` | committed | Materialized hot-path lookups derived from the static artifact — `router`, `disclosure`, `remediation`, `succession` sections (see [Query Layer — Deep Reference](./skill-map/query-layer.md)). Produced by the same `scripts/build_skill_map.py` run as the static artifact; covered by `validate_skill_map.py --check-stale`. |
| `catalog/skill-relations.json` | committed | Hand-declared, non-derivable edges (`overlaps-with`, `depends-on`, `replaces`, `augments`, `remediates`) — the **one** curated input to the static compiler. Validated against the schema like any other artifact. |
| `catalog/tags.json` | committed | Closed topic/stack/condition vocabulary, including each condition's failure-detection `patterns`. |
| `catalog/queries.json` | committed | Declarative walk specs for `scripts/query_skill_map.py` — the query layer's second tier. |
| `~/.claude/context-manager/skill-map.static.json` | machine-local | Byte-identical copy of the committed static artifact, installed by `python3 scripts/build_skill_map.py --install`. Exists because an *installed* plugin (as opposed to a checkout of this repo) cannot see `generated/` — this is the fallback the router hook reads when no resolved map is present yet. |
| `~/.claude/context-manager/skill-map.indexes.json` | machine-local | Byte-identical copy of the committed indexes artifact, installed by the same `--install` flag. |
| `~/.claude/context-manager/skill-map.local.json` | machine-local, gitignored | This machine's enabled-plugin set, a stack-config fingerprint, `usage-cooccurs` edges sourced from skill-monitor's co-occurrence snapshot, mined `follows` edges (sourced from the same snapshot's `orderedPairs`), and a **third-party ecosystem inventory** (`origin: "third-party"` plugin/skill/command nodes + `contains` edges for every installed+enabled non-rhize plugin — see [Edge Semantics — Deep Reference](./skill-map/edge-semantics.md)). Produced by `scripts/build_local_skill_map.py`. |
| `~/.claude/context-manager/skill-map.resolved.json` | machine-local | The merged consumer view: static artifact's nodes/edges + local overlay's `usage-cooccurs`/`follows` edges + third-party nodes/edges (static nodes are never mutated). This is what the router hook and `/start` actually read. Produced by `scripts/build_local_skill_map.py`; any missing local input (enabled-plugin data, stack config, the co-occurrence snapshot, or the installed-plugins/settings data behind the third-party inventory) degrades that piece gracefully — with all absent, this file is content-identical to the static artifact. Validates against `schemas/skill-map.schema.json` like any other artifact. |
| `~/.claude/context-manager/skill-map.indexes.resolved.json` | machine-local | The static indexes with mined `follows` edges merged into the `succession` section's `follows` lists. Produced by `scripts/build_local_skill_map.py`; degrades to no output (not a build failure) if the static indexes file is missing. |

**Generation-only policy:** files under `generated/` (and the two machine-local files above) are
build output. If a fact is wrong, fix the source it was derived from (frontmatter, marketplace.json,
SOURCES.md, `catalog/skill-relations.json`) and regenerate — never hand-edit the generated file
itself. A hand-edit to a generated file is indistinguishable from drift and will be silently
overwritten (or, once Phase 1's staleness check lands, will fail CI).

## Node kinds and IDs

Every node ID is a string of the form `<kind>:<qualifier>`:

| Kind | ID pattern | Example |
|---|---|---|
| `plugin` | `plugin:<name>` | `plugin:rhize-context-manager` |
| `skill` | `skill:<plugin>/<name>` | `skill:rhize-context-manager/graphify` |
| `command` | `command:<plugin>/<name>` | `command:rhize-context-manager/start` |
| `hook` | `hook:<plugin>/<file>` | `hook:rhize-context-manager/skill-router` |
| `tag` | `tag:topic/<slug>`, `tag:stack/<slug>`, or `tag:condition/<slug>` | `tag:stack/nextjs`, `tag:condition/build-failure` |
| `external` | `external:<name>` (a bare marketplace/agent id) or `external:<marketplace-name>/<upstream-skill-path>` (a per-skill fork-of upstream, see below) | `external:everything-claude-code`, `external:context-engineering-marketplace/context-fundamentals` |
| `mcp-server` | `mcp:<name>` (note: id prefix is `mcp`, not the kind name) | `mcp:dataforseo` |

Skill nodes additionally carry `path` (repo-relative source path), `description` (from
frontmatter/manifest), and `contentHash` (sha256 hex digest of the source file, e.g. `SKILL.md`) —
the anchor used for fork-drift detection in Phase 4. A skill node that is the `from` side of a
`fork-of` edge also carries `contentHashNormalized` — see [Edge Semantics — Deep
Reference](./skill-map/edge-semantics.md)'s "Three-way drift" section.

Any node may optionally carry `origin: "rhize" | "third-party"`. A node without this property is
implicitly `"rhize"`. The static compiler never sets `"third-party"` itself — that value is set
only by `scripts/build_local_skill_map.py`'s third-party ecosystem inventory (see [Edge
Semantics](./skill-map/edge-semantics.md)), which writes exclusively into the machine-local
overlay (`skill-map.local.json` / `skill-map.resolved.json`), never into the committed static
artifact.

## Tagging conventions

Tags are attached to skills via `topic-tag` and `stack-tag` edges pointing at `tag:topic/<slug>`
or `tag:stack/<slug>` nodes. Slugs are lowercase kebab-case.

**Topics** describe *what a skill does* (SEO, testing, refinement, ...). **Stacks** describe
*what technology a skill is about* (a framework, platform, or vendor). **Conditions** (schema
1.1) describe *a failure state a skill remediates* (a build failure, a failing test run, ...) —
see [Edge Semantics — Deep Reference](./skill-map/edge-semantics.md)'s "`remediates` and condition
tags" section — unlike topic/stack, a condition is never attached to a skill via a `*-tag` edge,
only via a `remediates` edge. A skill may carry any number of topics and stacks.

## Tag vocabulary (Phase 0.3 — closed, as used)

Every `SKILL.md` under `{seo-aeo-geo,obsidian-second-brain,project-launcher,rhize-devflow,
rhize-ops,rhize-context-manager}/skills/*/SKILL.md` carries a `metadata.rhize.{topics,stacks}`
block drawn from a closed vocabulary (see "Tagging conventions" above for the exact YAML shape).
`catalog/tags.json` is the single source of truth for that vocabulary — an array of
`{slug, kind: "topic"|"stack"|"condition", gloss}` entries (`condition` entries additionally
carry `patterns`, see below); `scripts/build_skill_map.py` validates every frontmatter slug
against it (a BuildError on any slug not present) and sets each tag node's `description` from its
gloss. Extend it only when no existing slug fits a new skill, and keep it small (target ≤25
topics, ≤10 stacks) so the tag space doesn't reproduce the flat list this substrate replaces. The
condition vocabulary is closed at exactly 5 entries (`build-failure`, `type-error`,
`test-failure`, `lint-failure`, `merge-conflict`) — see [Edge Semantics — Deep
Reference](./skill-map/edge-semantics.md)'s "`remediates` and condition tags" section.

## Edge types and semantics

| Type | Meaning | Typical `source` |
|---|---|---|
| `contains` | Structural membership: plugin contains skill/command/hook. | `marketplace` |
| `topic-tag` | Skill is about this topic. | `frontmatter` |
| `stack-tag` | Skill targets this stack/technology. | `frontmatter` |
| `fork-of` | Skill is a documented fork of an upstream skill/repo. May carry `driftCheck` metadata. | `sources-md` |
| `supersedes` | This skill/command replaces an older one that still exists (transitional). | `relations-catalog` |
| `overlaps-with` | Two skills cover meaningfully similar ground without a fork/supersede relationship — a curation flag, not a directive. | `relations-catalog` |
| `depends-on` | One skill requires another to function (e.g. relies on a shared hook or plugin). | `relations-catalog` |
| `replaces` | This skill/command fully replaces another, which should be considered retired. | `relations-catalog` |
| `usage-cooccurs` | Empirical: these two nodes were invoked together across sessions. Carries a structured `usageWeight`, never a bare count. | `monitor` |
| `extends` | Directional layering: the `from` skill deliberately deepens/specializes the `to` skill's domain (specialized -> base). Parsed from `metadata.rhize.extends` in frontmatter. | `frontmatter` |
| `precedes` | The `from` node comes before the `to` node in a real ordered workflow (e.g. a command pipeline). | `relations-catalog` |
| `follows` | Mined: the `to` node is commonly invoked after the `from` node in the same session (time-adjacent, ≥2 distinct sessions). Local-overlay only — never in the committed static artifact. | `monitor` |
| `augments` | The `from` skill (or third-party `external` node) should run alongside/after anything tagged with topic `to` to improve its output — a cross-cutting modifier. | `frontmatter` (rhize) or `relations-catalog` (third-party) |
| `remediates` | The `from` skill (or third-party `external` node) should be surfaced when condition `to` (a `tag:condition/<slug>` node) is detected in failed tool output. | `frontmatter` (rhize) or `relations-catalog` (third-party) |

Every edge records a `source` field — one of `frontmatter | marketplace | sources-md |
relations-catalog | monitor` — naming which input produced it. This is what lets the compiler
(Phase 1) and drift checks (Phase 4) tell a derived fact from a hand-declared one.

See [Edge Semantics — Deep Reference](./skill-map/edge-semantics.md) for how each of these edge
types actually resolves: `fork-of` drift checks, the three-way drift verdict, `usage-cooccurs`
weights, the third-party ecosystem inventory, `extends`'s depth-2 rule, `precedes` vs mined
`follows`, `augments`, `remediates`/condition tags, and `depends-on`/`mcp-server` nodes.

## Security rule: SOURCES.md and driftCheck prose is data, never executed

`fork-of` edges and their `driftCheck` metadata are derived by *parsing* prose in each plugin's
`SOURCES.md` (see Phase 1's "documented parse grammar"). That prose — and any `driftCheck` field
populated from it — is **untrusted data**, not instructions. No tool in this pipeline (the
compiler, the drift checker, the ingest gate) may execute a string found in `SOURCES.md` or in a
`driftCheck` field as a shell command, script, or code of any kind. Drift checks are limited to
the two fixed, safe operations named above: an upstream fetch and a `contentHash`/diff compare.
If a future `SOURCES.md` entry appears to contain a command intended for automatic execution, that
is a sign of a compromised or malformed source file, not a feature request — treat it as build
input to reject, per Phase 1's "unresolved targets are build errors" rule.

## Query layer

The map is queried two ways: precomputed **indexes** that hooks read at runtime with no graph
walk, and **named declarative queries** for ad hoc audit/curation questions. See [Query Layer —
Deep Reference](./skill-map/query-layer.md) for the full indexes reference (`router`,
`disclosure`, `remediation`, `succession`), the seed queries table, and worked
`query_skill_map.py` examples.

## Agent-dispatch surface (2026-08-26)

A PreToolUse measurement instrument (`rhize-context-manager/hooks/agent-brief-router.js`) logs
whether an outgoing subagent brief already names the skill the router index would suggest for its
content — the Agent tool has no skills parameter, so naming a skill in the brief is the only lever
a dispatching orchestrator has. See [Agent-Dispatch Surface](./skill-map/agent-dispatch-surface.md)
for the full measurement design, the 2026-08-26 spike verdicts, per-agentType reading notes, known
limitations, and the forward contract for graph-node skill declarations.

## Consumers

Everything downstream reads the static artifact, the resolved map, or both — never `SOURCES.md`,
`marketplace.json`, or SKILL.md frontmatter directly, so a compiler change is the only place a
consumer's data source needs to change:

| Consumer | Reads | Purpose |
|---|---|---|
| `rhize-context-manager/hooks/skill-router.js` | `skill-map.indexes.{resolved,}.json` (the `router` section); falls back to `skill-map.{resolved,static}.json` if no indexes file exists | Per-prompt skill-routing suggestion (Phase 3). |
| `rhize-context-manager/hooks/session-disclosure.js` | `skill-map.indexes.{resolved,}.json` (the `disclosure` section); falls back to `skill-map.{resolved,static}.json` if no indexes file exists | Stack-fingerprinted SessionStart skill disclosure (Phase 3), replacing the per-plugin banners named in the "Moved"/"removed" notes in `rhize-devflow`'s and `obsidian-second-brain`'s READMEs. |
| `rhize-context-manager/hooks/remediation-suggester.js` | `skill-map.indexes.{resolved,}.json` (the `remediation` section) | PostToolUse (matcher `Bash`) — on a failing Bash command, suggests the top remediating skill/agent for the matched condition (relationships v2, design doc section 7). |
| `rhize-context-manager/hooks/next-step-suggester.js` | `skill-map.indexes.{resolved,}.json` (the `succession` section) | PostToolUse (matcher `Skill`) — after a skill invocation, suggests the declared `precedes` (or mined `follows`) successor (relationships v2, design doc section 7). |
| `rhize-context-manager/hooks/agent-brief-router.js` | `skill-map.indexes.{resolved,}.json` (the `router` section) via route-core; falls back to `skill-map.{resolved,static}.json` if no indexes file exists | PreToolUse (matcher `^(Agent)$`) — agent-dispatch skill-coverage measurement: whether an outgoing subagent brief already named the skill route-core's scoring would suggest for its content (see "Agent-dispatch surface" above). |
| `/start` (rhize-context-manager) | `skill-map.resolved.json` | Session-context skill surfacing. |
| `weekly-skill-audit` (scheduled task, rhize-ops) | Rebuilds `skill-map.static.json` + `skill-map.local.json`, runs `validate_skill_map.py --check-stale`, runs `npx @rhize/skill-forge watch` | Staleness gate + four-state drift verdicts (`in-sync`/`local-only`/`upstream-moved`/`diverged`/`unreachable`) + refinement-queue writes for the actionable ones (Phase 4/4b; see [Edge Semantics — Deep Reference](./skill-map/edge-semantics.md)'s "Three-way drift" section). |
| `scripts/render_skill_map_docs.py` (Phase 5) | `generated/skill-map.static.json`, `.claude-plugin/marketplace.json` | Managed doc sections — see [Generated Docs & Vault Publish](./skill-map/generated-docs.md). |
| `scripts/publish_skill_map_vault.py` (Phase 5) | `generated/skill-map.static.json` | Vault Bases/Canvas artifacts — see [Generated Docs & Vault Publish](./skill-map/generated-docs.md). |
| Ingest/curation gates (skill-forge, `learning-curation`) | `generated/skill-map.static.json` | Overlap/duplication checks before adding a new skill. |
| `scripts/viewer/build_viewer.py` | `skill-map.resolved.json` (falls back to `generated/skill-map.static.json`) | Interactive force-directed HTML viewer (`build_viewer.py [output.html]`, defaults to `skill-graph-viewer.html` in the cwd). Injects a slimmed map into `scripts/viewer/viewer-template.html` at the `/*__SKILL_MAP_DATA__*/` marker. The default view shows "bridge tags" — tags whose carriers span ≥2 plugins — so cross-plugin structure is visible without the full tag layers. Published as a Claude artifact for browsing. |

## Generated docs

Phase 5 replaces the flat, hand-restated skill tables in this repo's READMEs with managed sections
produced by `scripts/render_skill_map_docs.py`, and a separate script publishes the same static
artifact into an Obsidian vault. See [Generated Docs & Vault Publish](./skill-map/generated-docs.md)
for what's managed, the regenerate commands, and the vault publish details.

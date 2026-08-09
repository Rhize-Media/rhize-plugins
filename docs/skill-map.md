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
policy" above exists to prevent, made into a hard gate instead of a documentation note.

## Artifacts

| File | Where | Contents |
|---|---|---|
| `schemas/skill-map.schema.json` | committed | Node/edge contract, `schemaVersion`. |
| `generated/skill-map.static.json` | committed | Deterministic repo facts — this repo's plugins, skills, commands, hooks, and their `contains`/`fork-of`/relations-catalog edges. Produced by `scripts/build_skill_map.py`; never hand-edited. |
| `catalog/skill-relations.json` | committed | Hand-declared, non-derivable edges (`overlaps-with`, `depends-on`, `replaces`) — the **one** curated input to the static compiler. Validated against the schema like any other artifact. |
| `~/.claude/context-manager/skill-map.static.json` | machine-local | Byte-identical copy of the committed static artifact, installed by `python3 scripts/build_skill_map.py --install`. Exists because an *installed* plugin (as opposed to a checkout of this repo) cannot see `generated/` — this is the fallback the router hook reads when no resolved map is present yet. |
| `~/.claude/context-manager/skill-map.local.json` | machine-local, gitignored | This machine's enabled-plugin set, a stack-config fingerprint, `usage-cooccurs` edges sourced from skill-monitor's co-occurrence snapshot, and a **third-party ecosystem inventory** (`origin: "third-party"` plugin/skill/command nodes + `contains` edges for every installed+enabled non-rhize plugin — see "Third-party ecosystem inventory" below). Produced by `scripts/build_local_skill_map.py`. |
| `~/.claude/context-manager/skill-map.resolved.json` | machine-local | The merged consumer view: static artifact's nodes/edges + local overlay's `usage-cooccurs` edges + third-party nodes/edges (static nodes are never mutated). This is what the router hook and `/start` actually read. Produced by `scripts/build_local_skill_map.py`; any missing local input (enabled-plugin data, stack config, the co-occurrence snapshot, or the installed-plugins/settings data behind the third-party inventory) degrades that piece gracefully — with all absent, this file is content-identical to the static artifact. Validates against `schemas/skill-map.schema.json` like any other artifact. |

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
| `tag` | `tag:topic/<slug>` or `tag:stack/<slug>` | `tag:stack/nextjs` |
| `external` | `external:<name>` | `external:everything-claude-code` |

Skill nodes additionally carry `path` (repo-relative source path), `description` (from
frontmatter/manifest), and `contentHash` (sha256 hex digest of the source file, e.g. `SKILL.md`) —
the anchor used for fork-drift detection in Phase 4.

Any node may optionally carry `origin: "rhize" | "third-party"`. A node without this property is
implicitly `"rhize"`. The static compiler never sets `"third-party"` itself — that value is set
only by `scripts/build_local_skill_map.py`'s third-party ecosystem inventory (see below), which
writes exclusively into the machine-local overlay (`skill-map.local.json` /
`skill-map.resolved.json`), never into the committed static artifact.

## Tagging conventions

Tags are attached to skills via `topic-tag` and `stack-tag` edges pointing at `tag:topic/<slug>`
or `tag:stack/<slug>` nodes. Slugs are lowercase kebab-case.

**Topics** describe *what a skill does* (SEO, testing, refinement, ...). **Stacks** describe
*what technology a skill is about* (a framework, platform, or vendor). A skill may carry any
number of each.

## Tag vocabulary (Phase 0.3 — closed, as used)

Every `SKILL.md` under `{seo-aeo-geo,obsidian-second-brain,project-launcher,rhize-devflow,
rhize-ops,rhize-context-manager}/skills/*/SKILL.md` carries a `metadata.rhize.{topics,stacks}`
block drawn from a closed vocabulary (see "Tagging conventions" above for the exact YAML shape).
`catalog/tags.json` is the single source of truth for that vocabulary — an array of
`{slug, kind: "topic"|"stack", gloss}` entries; `scripts/build_skill_map.py` validates every
frontmatter slug against it (a BuildError on any slug not present) and sets each tag node's
`description` from its gloss. Extend it only when no existing slug fits a new skill, and keep it
small (target ≤25 topics, ≤10 stacks) so the tag space doesn't reproduce the flat list this
substrate replaces.

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

Every edge records a `source` field — one of `frontmatter | marketplace | sources-md |
relations-catalog | monitor` — naming which input produced it. This is what lets the compiler
(Phase 1) and drift checks (Phase 4) tell a derived fact from a hand-declared one.

### `fork-of` and drift checks

A `fork-of` edge may carry a `driftCheck` object (`upstreamRepo`, `upstreamPath`, `method`,
`lastCheckedAt`). This is **fixed, safe metadata only** — an upstream fetch and a `contentHash`
comparison. It is never a shell command to execute.

### `usage-cooccurs` weights

`usageWeight` is always the structured shape `{sessions, jaccard, lift, windowDays}`, sourced from
skill-monitor aggregation (Phase 3). A bare co-occurrence count is not a valid weight under this
schema — it loses the information needed to distinguish "these two skills are always used
together" from "these two skills are just both used a lot."

Concretely: `rhize-ops/skill-monitor/monitor.py` writes a counts-only co-occurrence snapshot
(`data/skill-cooccurrence.json` — no prompt text, no project paths, no per-event timestamps, only
skill names and integer session counts) on every run. `scripts/build_local_skill_map.py` reads
that snapshot, resolves each `{a, b, sessions}` pair against the static artifact's skill nodes
(pairs involving a skill outside this repo's plugins are dropped — the monitor observes usage
across every repo on the machine), computes `jaccard`/`lift` from the snapshot's per-skill
`totals` and `totalSessions`, and emits one `usage-cooccurs` edge per resolved pair into
`skill-map.local.json` and `skill-map.resolved.json`.

### Third-party ecosystem inventory

The local overlay also inventories every plugin **installed and enabled on this machine whose
marketplace is not this repo's own** — the goal is to let Rhize plugins be evaluated for overlap
and complementarity against what's actually running alongside them (e.g. `ecc`, `sanity`,
`humanizer`), not just against each other. This is machine-specific by nature (the installed set
differs per developer machine), so it lives in the local overlay / resolved map only, exactly like
`origin: "third-party"` above requires.

**Inputs:** `~/.claude/plugins/installed_plugins.json` (which plugins are installed, and where
their cached source lives — `installPath`) joined against the merge of `~/.claude/settings.json`'s
`enabledPlugins` map with this repo's own `.claude/settings.local.json` override (local wins on
conflict — the same precedence Claude Code itself applies when resolving whether a plugin is
active). A plugin whose marketplace equals this repo's own marketplace name is skipped — it's
already a static node under its own convention below.

**What's included, per qualifying plugin:**
- One `plugin` node (`description` from the plugin's `.claude-plugin/plugin.json`, if present).
- One `skill` node per `skills/*/SKILL.md` under its cached install path (`description` from
  frontmatter, `contentHash` of the raw file — same fields the static compiler computes for a
  rhize skill, minus `topic-tag`/`stack-tag` edges: third-party skills don't carry
  `metadata.rhize.*` frontmatter, so there's nothing to tag).
- One `command` node per `commands/*.md` (cheap to include alongside the skill scan).
- `contains` edges from the plugin to each child node, attributed `source: "marketplace"` — the
  schema's `provenanceSource` enum has no third-party-specific value, and extending the schema is
  out of scope for this inventory; `marketplace` is the closest semantic match (the relationship
  is discovered by reading a plugin's on-disk layout, the same way a rhize plugin's `contains`
  edges are).

**Id convention** (collision-proof against this repo's own ids, which never have a marketplace
segment): `plugin:<marketplace>/<name>`, `skill:<marketplace>/<plugin>/<skill-dir>`,
`command:<marketplace>/<plugin>/<command-stem>` — e.g. `plugin:everything-claude-code/ecc`,
`skill:everything-claude-code/ecc/frontend-design-direction`.

**Truncation:** every third-party `description` is truncated to ~200 characters
(`DESCRIPTION_TRUNCATE_LIMIT` in `scripts/build_local_skill_map.py`). Some installed plugins ship
hundreds of skills (`ecc` alone is 280+) — routing/overlap analysis needs the gist of what a
third-party skill does, not its full trigger text, and the full text would bloat the overlay
roughly linearly with the ecosystem's size for no analytical benefit.

**Paths are home-relative, not repo-relative:** a third-party skill's `path` looks like
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/<name>/SKILL.md` — these files
live outside this repo entirely, so "repo-relative" doesn't apply; home-relative keeps the path
short and portable across machines that share the same `~/.claude/plugins/cache` layout.

**Graceful degradation, never a build failure:** a missing/unreadable `installed_plugins.json`
degrades to zero third-party nodes (same contract as the enabled-plugin-set input above). A
plugin whose `installPath` doesn't exist on disk, or a `SKILL.md`/command file that can't be read,
is skipped and counted — `local.json`'s `thirdParty.summary` reports `skippedPlugins` and
`skippedEntries`, and `sourceNotes.thirdParty` records which enabled-plugins sources were read (or
degraded).

### `extends` and the depth-2 rule

`metadata.rhize.extends` in a skill's frontmatter is a list of targets, each either a bare skill
name (resolved against the declaring skill's own plugin) or `"plugin/skill-name"` (cross-plugin).
`scripts/build_skill_map.py` resolves each target once every plugin's skills have loaded and emits
an `extends` edge from the declaring skill to the target (source: `frontmatter`); an unresolved
target is a BuildError naming the file and the target.

`extends` is a **layering** relationship, not a duplication flag or a runtime dependency — that
distinction matters because two other edge types sit right next to it semantically:

- `overlaps-with` flags two skills covering *meaningfully similar ground without an intended
  hierarchy* — a curation signal that something might need to be merged or retired.
- `depends-on` means one skill *requires* another to function (e.g. a shared hook or plugin).
- `extends` means the specialized skill *deliberately deepens* the base skill's domain by design —
  the base stays useful and general, the extender adds depth for a narrower case. Neither skill is
  redundant and neither breaks without the other.

Chains are capped at depth 2 (in edges): `A extends B extends C` is allowed, `A extends B extends C
extends D` is a BuildError — "extends chains capped at 2 — deep trees recreate rigid taxonomy" is
exactly the failure mode this substrate exists to avoid. A cycle anywhere in an extends chain is
also a BuildError.

Two consumers read `extends` edges: `session-disclosure.js` folds a matched base and its matched
extenders into one compacted disclosure line (`- plugin:base — matches ... (+N deeper: name,
name)`) instead of listing each extender separately, and `skill-router.js` breaks a base/extender
scoring tie in the extender's favor (it's the more specific skill) whenever the extender's score is
at least the base's.

### `precedes`

`precedes` records that the `from` node comes before the `to` node in a real ordered workflow —
for example, `project-launcher`'s command pipeline: `write-prd` precedes `grill-prd` precedes
`scaffold-gsd`. Declared by hand in `catalog/skill-relations.json` (source: `relations-catalog`),
the same way as `overlaps-with`/`depends-on`/`replaces`.

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

## Consumers

Everything downstream reads the static artifact, the resolved map, or both — never `SOURCES.md`,
`marketplace.json`, or SKILL.md frontmatter directly, so a compiler change is the only place a
consumer's data source needs to change:

| Consumer | Reads | Purpose |
|---|---|---|
| `rhize-context-manager/hooks/skill-router.js` | `skill-map.resolved.json` (falls back to the installed static copy) | Per-prompt skill-routing suggestion (Phase 3). |
| `rhize-context-manager/hooks/session-disclosure.js` | `skill-map.resolved.json` | Stack-fingerprinted SessionStart skill disclosure (Phase 3), replacing the per-plugin banners named in the "Moved"/"removed" notes in `rhize-devflow`'s and `obsidian-second-brain`'s READMEs. |
| `/start` (rhize-context-manager) | `skill-map.resolved.json` | Session-context skill surfacing. |
| `weekly-skill-audit` (scheduled task, rhize-ops) | Rebuilds `skill-map.static.json` + `skill-map.local.json`, runs `validate_skill_map.py --check-stale` | Staleness gate + drift checks + refinement-queue writes (Phase 4/4b). |
| `scripts/render_skill_map_docs.py` (Phase 5) | `generated/skill-map.static.json`, `.claude-plugin/marketplace.json` | Managed doc sections — see below. |
| `scripts/publish_skill_map_vault.py` (Phase 5) | `generated/skill-map.static.json` | Vault Bases/Canvas artifacts — see below. |
| Ingest/curation gates (skill-forge, `learning-curation`) | `generated/skill-map.static.json` | Overlap/duplication checks before adding a new skill. |

## Generated docs

Phase 5 replaces the flat, hand-restated skill tables in this repo's READMEs with **managed
sections** — content between `<!-- SKILL-MAP:BEGIN -->` / `<!-- SKILL-MAP:END -->` markers,
produced by `scripts/render_skill_map_docs.py` from `generated/skill-map.static.json` and
`.claude-plugin/marketplace.json`. Everything outside a marker pair is ordinary hand-written prose
and is never touched by the script.

**What's managed:**

| File | Managed section |
|---|---|
| Root `README.md` | The Plugin Catalog table (`Plugin \| Version \| Skill Count \| Description \| Docs`). |
| Each plugin's `README.md` | Its skill table (`Skill \| Description \| Topics`). `rhize-context-manager`'s table covers only the Rhize-authored skills (those without a `fork-of` edge) — the curated-third-party group is prose, not a table, and stays hand-written. `obsidian-second-brain`'s table covers only the "Second Brain" group; "Format Skills" is a separate hand-written table left untouched. |
| `generated/SKILL-CATALOG.md` | The full cross-plugin catalog, one section per plugin, in marketplace order. |

**Regenerating:**

```bash
python3 scripts/build_skill_map.py          # rebuild the static artifact first if it's stale
python3 scripts/render_skill_map_docs.py    # fill managed sections; idempotent, refuses if a
                                             # target file has no marker pair
```

A file with no marker pair is a hard error, not a guess — add the `<!-- SKILL-MAP:BEGIN -->` /
`<!-- SKILL-MAP:END -->` pair by hand at the intended location once, then the script owns
everything between them from then on. `tests/skill-map/test_render_docs.py` covers idempotency,
marker preservation, and the refusal behavior.

**Vault publish** (`scripts/publish_skill_map_vault.py`) renders the same static artifact into an
Obsidian vault as one Markdown note per skill (structured frontmatter: `plugin`, `topics`,
`stacks`, `source_path`), a `Skill Map.base` inventory view over those notes, and a `Skill
Map.canvas` topology diagram (plugin → skill containment, `fork-of`/`replaces`/`depends-on`
edges, topic/stack tag clusters). No usage/co-occurrence data is published — structural facts
only. The vault path is resolved at runtime (`RHIZE_VAULT_PATH` env var, or the vault marked
`"open": true` in Obsidian's own global config) and is never hardcoded or committed; nothing this
script writes lives in this repo.

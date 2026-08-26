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
| `generated/skill-map.indexes.json` | committed | Materialized hot-path lookups derived from the static artifact — `router`, `disclosure`, `remediation`, `succession` sections (see "Query layer" below). Produced by the same `scripts/build_skill_map.py` run as the static artifact; covered by `validate_skill_map.py --check-stale`. |
| `catalog/skill-relations.json` | committed | Hand-declared, non-derivable edges (`overlaps-with`, `depends-on`, `replaces`, `augments`, `remediates`) — the **one** curated input to the static compiler. Validated against the schema like any other artifact. |
| `catalog/tags.json` | committed | Closed topic/stack/condition vocabulary, including each condition's failure-detection `patterns`. |
| `catalog/queries.json` | committed | Declarative walk specs for `scripts/query_skill_map.py` — the query layer's second tier. |
| `~/.claude/context-manager/skill-map.static.json` | machine-local | Byte-identical copy of the committed static artifact, installed by `python3 scripts/build_skill_map.py --install`. Exists because an *installed* plugin (as opposed to a checkout of this repo) cannot see `generated/` — this is the fallback the router hook reads when no resolved map is present yet. |
| `~/.claude/context-manager/skill-map.indexes.json` | machine-local | Byte-identical copy of the committed indexes artifact, installed by the same `--install` flag. |
| `~/.claude/context-manager/skill-map.local.json` | machine-local, gitignored | This machine's enabled-plugin set, a stack-config fingerprint, `usage-cooccurs` edges sourced from skill-monitor's co-occurrence snapshot, mined `follows` edges (sourced from the same snapshot's `orderedPairs`), and a **third-party ecosystem inventory** (`origin: "third-party"` plugin/skill/command nodes + `contains` edges for every installed+enabled non-rhize plugin — see "Third-party ecosystem inventory" below). Produced by `scripts/build_local_skill_map.py`. |
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
`fork-of` edge also carries `contentHashNormalized` — see "Three-way drift" below.

Any node may optionally carry `origin: "rhize" | "third-party"`. A node without this property is
implicitly `"rhize"`. The static compiler never sets `"third-party"` itself — that value is set
only by `scripts/build_local_skill_map.py`'s third-party ecosystem inventory (see below), which
writes exclusively into the machine-local overlay (`skill-map.local.json` /
`skill-map.resolved.json`), never into the committed static artifact.

## Tagging conventions

Tags are attached to skills via `topic-tag` and `stack-tag` edges pointing at `tag:topic/<slug>`
or `tag:stack/<slug>` nodes. Slugs are lowercase kebab-case.

**Topics** describe *what a skill does* (SEO, testing, refinement, ...). **Stacks** describe
*what technology a skill is about* (a framework, platform, or vendor). **Conditions** (schema
1.1) describe *a failure state a skill remediates* (a build failure, a failing test run, ...) —
see "`remediates` and condition tags" below; unlike topic/stack, a condition is never attached to
a skill via a `*-tag` edge, only via a `remediates` edge. A skill may carry any number of topics
and stacks.

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
`test-failure`, `lint-failure`, `merge-conflict`) — see "`remediates` and condition tags" below.

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

### `fork-of` and drift checks

A `fork-of` edge may carry a `driftCheck` object (`upstreamRepo`, `upstreamPath`, `method`,
`lastCheckedAt`). This is **fixed, safe metadata only** — an upstream fetch and a `contentHash`
comparison. It is never a shell command to execute — the object exists for display, not
resolution.

Each `fork-of` edge points at its own **per-skill** `external` node (id
`external:<marketplace-name>/<upstream-skill-path>`), not a single node shared by every fork of
the same marketplace. Actual drift resolution is done by skill-forge's drift checker, which reads
`node.url ?? node.path` on the `to` node — a single marketplace-level node with no `path`/`url`
can only ever report `upstream-unreachable`, no matter how many forks point at it, because there
is no single file it could resolve to. The per-skill node's `path` is `SOURCES.md`'s recorded
`Source` value with `/SKILL.md` appended, stored `~`-prefixed for portability; if that upstream
copy is genuinely gone from the machine (e.g. the marketplace was since uninstalled), the check
still correctly reports `upstream-unreachable` — that is honest reporting, not the bug this
per-skill-node shape fixes.

**Local paths are machine-dependent by construction** — a `Source` pointing at
`~/.claude/plugins/marketplaces/<name>/skills/<path>` only resolves on the machine that still has
that marketplace installed; uninstall it anywhere else and every fork-of edge for it reports
`upstream-unreachable`, which is a false negative for drift, not a real one. Where the real
upstream repo is known, `SOURCES.md`'s `Source` should instead record an `http(s)` URL to the raw
file (e.g. `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/skills/<path>/SKILL.md`).
The compiler detects this by scheme and emits `url` on the per-skill `external` node instead of
`path`; the drift checker's `node.url ?? node.path` lookup already prefers `url`, so no other code
needed to change. `rhize-context-manager/skills/SOURCES.md`'s 7 `muratcankoylan/Agent-Skills-for-Context-Engineering`
forks (context-fundamentals, context-degradation, context-compression, context-optimization,
memory-systems, filesystem-context, tool-design) were repointed this way on 2026-08-10 — each URL
was verified with `curl` (HTTP 200 + real SKILL.md frontmatter) before being recorded, and the
resulting `fork-of` edges now resolve from any machine, not only the one that once had
`context-engineering-marketplace` installed.

### Three-way drift: baseline, normalization, and the four-state verdict

The two-way compare (local-now vs upstream-now) has a permanent false positive: Rhize injects a
`metadata.rhize` frontmatter block into every fork, so a fork's raw `contentHash` differs from
upstream's forever, even with zero real divergence. Reconciling deliberate local improvements with
unreviewed upstream movement needs a third input — what upstream looked like as of the last human
review — and a way to compare local content that ignores Rhize's own tagging. Full design:
`docs/superpowers/specs/2026-08-10-three-way-drift-design.md`.

**Baseline** = the upstream content hash as of the last human review (ingestion or re-baseline).
It is curated DATA, recorded in SOURCES.md, and is **never fetched by the compiler** — fetching it
is `scripts/baseline_upstreams.py`'s job, run only when a human deliberately re-baselines (the
compiler stays offline and deterministic; see "Generation-only policy" above).

- **SOURCES.md field:** `- **Upstream baseline:** sha256:<hex> (recorded YYYY-MM-DD)`, added
  alongside the existing per-entry bullets (see `scripts/sources_md.py`'s grammar docstring).
- **`scripts/baseline_upstreams.py`** fetches each non-retired entry's http(s) `Source`, hashes the
  body, and writes/updates that bullet. It is **idempotent**: if the freshly fetched hash already
  matches the recorded one, the file is left untouched (no date bump). Non-URL (local marketplace
  path) `Source` values are skipped with a report line — this baseline can only apply to sources it
  can actually fetch. `--skill <name>` limits a run to one entry.
- **The compiler** (`scripts/build_skill_map.py`) copies the parsed baseline hash onto the per-skill
  `external` node as `baselineHash` — **not** into the `fork-of` edge's `driftCheck` object, which
  stays display-only metadata per skill-forge's guard test. Node data (`path`/`url`/`baselineHash`)
  is the sanctioned read surface for anything that needs to actually resolve or compare against the
  upstream file.

**Normalization** removes exactly the tagging noise described above, nothing else: the corresponding
skill node's `contentHashNormalized` is sha256 of its SKILL.md with the Rhize-injected
`metadata.rhize` frontmatter subtree textually removed. The precise rule is implemented once, in
`scripts/sources_md.py`'s `strip_rhize_metadata_block()` — the canonical, single implementation
(skill-forge compares hashes it is handed and never re-implements this stripping, the
duplicated-validator lesson from `SOURCES.md`'s `strategic-compact` entry); see that function's
docstring for the exact line-surgery rule. `contentHashNormalized` is emitted only on skill nodes
that are the `from` side of a `fork-of` edge — a skill with no upstream has nothing to normalize
against.

**The four-state verdict** (computed by skill-forge's `watch`, not this repo's compiler — this repo
only supplies the two hash inputs) replaces the old single `drifted` status:

| localNormalized vs baseline | upstreamNow vs baseline | status | actionable |
|---|---|---|---|
| == | == | `in-sync` | no |
| != | == | `local-only` | no (ours, deliberate, already in git) |
| == | != | `upstream-moved` | yes |
| != | != | `diverged` | yes |

`upstream-unreachable` and `local-missing` are unchanged from the two-way check. If either input is
missing — no `baselineHash` on the external node, or no `contentHashNormalized` on the skill node —
skill-forge falls back to today's plain two-way compare (`drifted`/`in-sync`) so older maps built
before this feature keep working.

**Re-baseline workflow:** after reviewing and deliberately accepting an upstream change (i.e. you
looked at the diff and decided the new upstream state is now the comparison point), run
`python3 scripts/baseline_upstreams.py` (optionally `--skill <name>` for just one fork), review the
`SOURCES.md` diff, and commit it. That commit is the record of the review — there is no other audit
trail for "someone looked at this and accepted it."

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

### `follows` (mined) vs `precedes` (declared)

`follows` is the mined counterpart to `precedes`: same surfacing consumer (a "what comes next"
suggestion), different provenance. `precedes` is curated intent, hand-declared in
`catalog/skill-relations.json` for a real ordered workflow (e.g. a command pipeline) whether or
not anyone has actually run it that way yet. `follows` is empirical — `rhize-ops/skill-monitor`
mines ordered, time-adjacent skill pairs within a session (via `monitor.py`'s
`build_cooccurrence()`, extended to also emit `orderedPairs`) and only surfaces a pair once it
recurs across ≥2 distinct sessions. Because it's derived from this machine's usage history,
`follows` lives in the local overlay only (`skill-map.local.json` / `skill-map.resolved.json`) —
never in the committed static artifact — and is never hand-authored.

### `augments` — cross-cutting skill-to-topic modifier

`augments` targets a *topic tag*, not another skill — "run me alongside/after anything in this
category to improve its output" (e.g. `seo-aeo-geo/content-seo` augments `tag:topic/content-authoring`).
It is deliberately distinct from `extends`: no lexical overlap with its targets is implied, it
carries no gate-exemption or depth semantics, and its target is a whole category rather than one
specific skill. Declared in a skill's own frontmatter (`metadata.rhize.augments: [<topic-slug>]`)
for Rhize skills; for third-party skills (whose frontmatter isn't ours to edit — and which may not
even be inventoried as a proper skill node, see below), declared in
`catalog/skill-relations.json` instead, from an `external:<name>` node representing the
capability.

### `remediates` and condition tags

`remediates` targets a *condition tag* (`tag:condition/<slug>`) — "surface me when this failure
happens." The condition vocabulary lives in `catalog/tags.json` exactly like topic/stack, closed
at 5 entries: `build-failure`, `type-error`, `test-failure`, `lint-failure`, `merge-conflict`. Each
condition entry additionally carries `patterns` — regexes matched against **failed tool output**
(not the user's prompt — that's the router's job), e.g. `\berror TS\d+\b` for `type-error`.
Declared the same way as `augments`: `metadata.rhize.remediates: [<condition-slug>]` in
frontmatter for Rhize skills, `catalog/skill-relations.json` for third-party capabilities.

Several seeded `remediates` edges (the `everything-claude-code` build-resolver family) originate
from `external:` nodes rather than `skill:` nodes, because those capabilities are **agents**
(`agents/*.md`), not skills — the skill-map schema has no `agent` node kind, and third-party
agents aren't inventoried by `build_local_skill_map.py`'s third-party scan (which only walks
`skills/*/SKILL.md` and `commands/*.md`). Modeling them as `external` nodes reuses the same
pattern `fork-of` already uses for upstream marketplaces, rather than adding a new node kind for
a case outside this round's scope.

### `depends-on` and `mcp-server` nodes

`depends-on` also models a skill's dependency on an **MCP server**, via node kind `mcp-server`
(id form `mcp:<name>` — note the id prefix is `mcp`, not the kind name `mcp-server`). Declared in
frontmatter (`metadata.rhize.dependsOn: ["mcp:<name>", ...]`, alongside ordinary skill targets
using the same bare-name / `"plugin/skill-name"` resolution `extends` uses) or in
`catalog/skill-relations.json` for third-party declarations. An unresolved skill target is a
BuildError, same as `extends`; an `mcp:<name>` target always resolves (it mints the node if not
already present) since there's no existing catalog of valid MCP server names to validate against.

**Scope honesty:** this only models the *declared* dependency — that a skill relies on a given MCP
server to function. It does **not** claim to detect whether that server is actually connected/live
in the current session; that state isn't reliably readable from a hook. A future consumer could at
most check "is this server configured at all" against the machine's MCP config, and even that is
deferred out of this round's scope.

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

## Query layer (two-tier)

**Tier 1 — materialized indexes** (`generated/skill-map.indexes.json`) cover the hot paths hooks
need at runtime, precomputed so no hook has to walk `doc.edges` itself:

- `router` — per-skill tag/name signal lists (mirrors `skill-router.js`'s own precomputation:
  each topic-tag/stack-tag edge as a weight-2 "tag" signal, each skill's own name as a weight-1
  "name" signal) plus the `extends` base/extender adjacency the router uses for its tie-break.
  `skill-router.js` reads this file first (`routeFromIndex()`) and only falls back to walking
  `doc.edges` directly (`route()`) when no indexes file is present/parseable — an older install
  that hasn't rebuilt its indexes file yet still works, just without the precomputation.
- `disclosure` — per single stack slug, the base+extenders-folded skill list
  `session-disclosure.js`'s `relevantSkills()` would compute for a `detectedStacks` set containing
  only that one stack. `session-disclosure.js` reads this file first (`relevantSkillsFromIndex()`),
  unioning the per-stack lists and re-ranking by matched-stack count for multi-stack repos, same as
  the map-scan fallback (`relevantSkills()`) it degrades to when no indexes file exists — with one
  known gap: extends-folding is computed *per stack slug* in the index, so a base/extender pair
  that each match a *different* detected stack won't fold on the index path the way the fallback's
  union-based fold would. Rare (needs two stack markers plus a cross-stack extends edge) and not
  exercised by any shipped fixture; accepted rather than redesigning the index format for it.
- `remediation` — condition slug → `{patterns, skills}`. `skills` is sorted by node id
  (alphabetical) — no ranking/promotion signal exists yet, so this is the deterministic default
  until one lands (see the design doc's "pairs-with... revisit later as an audit promotion
  target" non-goal for the analogous case). Consumed by `remediation-suggester.js` (PostToolUse,
  matcher `Bash`): on a failing Bash command, the patterns are matched against `stdout`+`stderr`
  (compiled via a Python-`re`-to-JS-`RegExp` shim that strips a leading `(?i)` inline flag into
  the JS `i` flag — the catalog's patterns are authored as Python regexes) and the first-listed
  remediator for the first matching condition is suggested. An `external:` id (a third-party
  capability with no proper skill-map node, e.g. an `ecc` build-resolver *agent*) is phrased as an
  agent suggestion rather than a skill invocation.
- `succession` — node id → `{precedes, follows}` from declared `precedes` edges. `follows` is
  always `[]` in the static indexes — mined `follows` edges are local-overlay only — and gets
  filled in by `scripts/build_local_skill_map.py` at
  `~/.claude/context-manager/skill-map.indexes.resolved.json`. Consumed by
  `next-step-suggester.js` (PostToolUse, matcher `Skill`): after a skill invocation, looks up the
  invoked skill's node id, prefers the first declared `precedes` successor, falls back to the
  first mined `follows` successor, and suggests exactly one — this is `precedes`'s first runtime
  consumer.

**Tier 2 — named declarative queries** (`catalog/queries.json`, interpreted by
`scripts/query_skill_map.py`) cover everything else: ad hoc audit/curation questions that don't
need a hot-path index. A query spec is Cypher-shaped without Cypher — a start-node resolution
mode plus a list of `{edge, direction, as}` steps — so it would port mechanically if the map ever
moved to a real graph database. One Python walker interprets every spec; hooks never invoke this
script (it's a developer/audit-time CLI, not a runtime dependency).

Seed queries:

| Query | Arg | Answers |
|---|---|---|
| `what-extends` | skill id | What it extends, and what extends it. |
| `what-augments` | skill id or `tag:topic/<slug>` | Topics it augments, or skills augmenting a topic. |
| `what-remediates` | condition slug or `tag:condition/<slug>` | Skills declaring a `remediates` edge to that condition. |
| `what-follows` | skill id | Mined `follows` relationships (`--resolved` only — local-overlay data). |
| `overlap-candidates` | — | Every `overlaps-with` edge in the map. |
| `unroutable-skills` | — | Skills with no `topic-tag`/`stack-tag` edge — invisible to the router/disclosure hooks. |
| `mcp-dependents` | mcp server name or `mcp:<name>` | Skills declaring a `depends-on` edge to that MCP server. |

```bash
python3 scripts/query_skill_map.py what-remediates build-failure
python3 scripts/query_skill_map.py what-follows seo-aeo-geo/content-seo --resolved
python3 scripts/query_skill_map.py --list
```

## Agent-dispatch surface (2026-08-26)

The Agent tool has no skills parameter, so a dispatching orchestrator's only levers are picking a
skill-shaped agent type, naming a skill in the brief ("Invoke `<plugin:skill>` first"), or inlining
its content — and in practice neither happens on its own: a Skill-capable subagent inherits the
same skill roster but none of the parent transcript (every dispatch is a cold start), and zero of
~15 observed subagent reports in the originating session invoked a skill unprompted. Because a
PreToolUse hook fires only after the brief is already written, it cannot fix the dispatch it
observes — it can only measure, across sessions, whether outgoing briefs already name the skill the
router index would otherwise suggest for their content.

**Spike verdicts** (`.claude/plans/subagent-skill-injection.md`, Task 3 Step 5, 2026-08-26):

```
V1 fired: yes · tool_name(s) observed: Agent  → SPIKE_MATCHER = "^(Agent)$"
V2 additionalContext reached model: yes (result=True, stderr-clean=True, control-clean=True)
Consequence for Task 5: log + flag-gated advisory (V2 yes)
```

**What it measures:** `rhize-context-manager/hooks/agent-brief-router.js` (PreToolUse, matcher
`^(Agent)$`, tier T3, opt-in via `setup/manifest.json`, `default: false`) is a **measurement
instrument, not a router** — default behavior is log-only. Each Agent-tool dispatch that reaches
it (non-empty brief, usable map/index data) logs one `source: "agent-dispatch"` row to the shared
suggestion log: which skills the brief named via the directive `Invoke <plugin:skill> first`
(Task 1's convention) versus the single best-scoring candidate the router index would suggest for
the brief's content. `scripts/suggestion_log_report.py`'s `agent_dispatch` section reports the
named-rate, candidate-present count, and candidate-miss rate computed from that log. A one-line
advisory (`hookSpecificOutput.additionalContext`, next-dispatch guidance only — it cannot retract
the dispatch already in flight) exists behind `RHIZE_AGENT_BRIEF_ADVISORY=1` and stays off until
the logged data has been reviewed; briefs are long, multi-paragraph documents and over-match the
prompt-calibrated thresholds `skill-router.js` uses for short user prompts.

**Known limitations:** Workflow `agent()` calls and scheduled-task sessions bypass the Agent-tool
hook entirely — they're spawned by other runtimes, so PreToolUse on `Agent` never fires for them.
For those paths, the CLAUDE.md skill-explicit dispatch rule (Task 1, `~/.claude/CLAUDE.md`) is the
only enforcement, by design; no hook will be built for them.

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
| `/start` (rhize-context-manager) | `skill-map.resolved.json` | Session-context skill surfacing. |
| `weekly-skill-audit` (scheduled task, rhize-ops) | Rebuilds `skill-map.static.json` + `skill-map.local.json`, runs `validate_skill_map.py --check-stale`, runs `npx @rhize/skill-forge watch` | Staleness gate + four-state drift verdicts (`in-sync`/`local-only`/`upstream-moved`/`diverged`/`unreachable`) + refinement-queue writes for the actionable ones (Phase 4/4b; see "Three-way drift" above). |
| `scripts/render_skill_map_docs.py` (Phase 5) | `generated/skill-map.static.json`, `.claude-plugin/marketplace.json` | Managed doc sections — see below. |
| `scripts/publish_skill_map_vault.py` (Phase 5) | `generated/skill-map.static.json` | Vault Bases/Canvas artifacts — see below. |
| Ingest/curation gates (skill-forge, `learning-curation`) | `generated/skill-map.static.json` | Overlap/duplication checks before adding a new skill. |
| `scripts/viewer/build_viewer.py` | `skill-map.resolved.json` (falls back to `generated/skill-map.static.json`) | Interactive force-directed HTML viewer (`build_viewer.py [output.html]`, defaults to `skill-graph-viewer.html` in the cwd). Injects a slimmed map into `scripts/viewer/viewer-template.html` at the `/*__SKILL_MAP_DATA__*/` marker. The default view shows "bridge tags" — tags whose carriers span ≥2 plugins — so cross-plugin structure is visible without the full tag layers. Published as a Claude artifact for browsing. |

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

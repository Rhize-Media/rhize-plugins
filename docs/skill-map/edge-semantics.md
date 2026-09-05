# Edge Semantics — Deep Reference

Deep mechanics for the edge types summarized in [`docs/skill-map.md`](../skill-map.md)'s "Edge
types and semantics" table. Read that table first for the one-line meaning of each edge type —
this doc covers the ten edge types (and their supporting subsystems) that need more than one line
to explain correctly.

## `fork-of` and drift checks

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

## Three-way drift: baseline, normalization, and the four-state verdict

The two-way compare (local-now vs upstream-now) has a permanent false positive: Rhize injects a
`metadata.rhize` frontmatter block into every fork, so a fork's raw `contentHash` differs from
upstream's forever, even with zero real divergence. Reconciling deliberate local improvements with
unreviewed upstream movement needs a third input — what upstream looked like as of the last human
review — and a way to compare local content that ignores Rhize's own tagging. Full design:
`docs/superpowers/specs/2026-08-10-three-way-drift-design.md`.

**Baseline** = the upstream content hash as of the last human review (ingestion or re-baseline).
It is curated DATA, recorded in SOURCES.md, and is **never fetched by the compiler** — fetching it
is `scripts/baseline_upstreams.py`'s job, run only when a human deliberately re-baselines (the
compiler stays offline and deterministic; see "Generation-only policy" in the overview).

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

## `usage-cooccurs` weights

`usageWeight` is always the structured shape `{sessions, jaccard, lift, windowDays}`, sourced from
skill-monitor aggregation (Phase 3). A bare co-occurrence count is not a valid weight under this
schema — it loses the information needed to distinguish "these two skills are always used
together" from "these two skills are just both used a lot."

Concretely: the standalone `rhize-skill-monitor` tool's `monitor.py` writes a counts-only co-occurrence snapshot
(`data/skill-cooccurrence.json` — no prompt text, no project paths, no per-event timestamps, only
skill names and integer session counts) on every run. `rhize-context-manager/scripts/build_local_skill_map.py` reads
that snapshot, resolves each `{a, b, sessions}` pair against the static artifact's skill nodes
(pairs involving a skill outside this repo's plugins are dropped — the monitor observes usage
across every repo on the machine), computes `jaccard`/`lift` from the snapshot's per-skill
`totals` and `totalSessions`, and emits one `usage-cooccurs` edge per resolved pair into
`skill-map.local.json` and `skill-map.resolved.json`.

## Third-party ecosystem inventory

The local overlay also inventories every plugin **installed and enabled on this machine whose
marketplace is not this repo's own** — the goal is to let Rhize plugins be evaluated for overlap
and complementarity against what's actually running alongside them (e.g. `ecc`, `sanity`,
`humanizer`), not just against each other. This is machine-specific by nature (the installed set
differs per developer machine), so it lives in the local overlay / resolved map only, exactly like
`origin: "third-party"` in the schema requires.

**Inputs:** `~/.claude/plugins/installed_plugins.json` (which plugins are installed, and where
their cached source lives — `installPath`) joined against the merge of `~/.claude/settings.json`'s
`enabledPlugins` map with this repo's own `.claude/settings.local.json` override (local wins on
conflict — the same precedence Claude Code itself applies when resolving whether a plugin is
active). A plugin whose marketplace equals this repo's own marketplace name is skipped — it's
already a static node under its own convention.

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
(`DESCRIPTION_TRUNCATE_LIMIT` in `rhize-context-manager/scripts/build_local_skill_map.py`). Some installed plugins ship
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

## Inferred router signals for third-party skills

Third-party skills get no `topic-tag`/`stack-tag` EDGES (see "Third-party ecosystem inventory"
above — their frontmatter isn't ours to edit), which structurally means `route()`, the
map-scanning fallback path in `hooks/lib/route-core.js`, can never suggest one: it walks
`doc.edges` for tag signals and a name-only match never clears the 2-signal qualifying floor.
The resolved ROUTER INDEX closes that gap with a separate, best-effort mechanism instead of a
real edge.

**How it's produced.** `rhize-context-manager/scripts/build_local_skill_map.py`'s
`infer_tags_for_skill(name, description, tags_catalog)` matches each `catalog/tags.json`
**topic/stack** entry (never `condition` — a condition describes a runtime failure state, not a
skill's subject matter) against a third-party skill's tokenized name+description: a slug matches
when every hyphen-separated word of it is present among the tokens — the identical "every word of
the label is in the prompt tokens" rule `route-core.js`'s `routeFromIndex()` applies at match time. Up to 3
matches are kept per skill, preferring multi-word slugs (more specific) over single-word ones,
then alphabetical; the returned list is itself sorted alphabetically, so output is deterministic
regardless of catalog order. A missing or malformed `catalog/tags.json` degrades to zero inferred
tags for every skill (`skill-map.local.json`'s `sourceNotes.tagsCatalog` records why) — never a
build failure. `build_local_skill_map.py --report-inferred` prints a per-skill table of what would
be inferred, without writing anything, for a precision review before trusting the injection below.

**Where it's written.** `build_resolved_indexes()` (same file) writes each match into
`skill-map.indexes.resolved.json`'s `router.signals[skillId]` as
`{kind: "tag-inferred", weight: 0.5, label: <slug>}` — half the weight of a declared `tag` signal
(2) and half of a `name` signal (1). Every third-party skill gets a `name` entry
(`{kind: "name", weight: 1, label: <skill name>}`) unconditionally — mirroring
`scripts/build_skill_map.py`'s `build_router_index()` giving every skill a name signal — with the
inferred entries appended after it, so index membership never depends on whether inference hit
(consumers such as `agent-brief-router.js`'s named-skill detection see every installed skill). A
skill with zero inferred tags therefore has a name-only entry, which cannot qualify a match on its
own through implicit scoring (see the next paragraph).
Declared (rhize) skills' existing signal entries — produced by the static compiler, already in
`generated/skill-map.indexes.json` — are copied through into the resolved file but never mutated.
This addition is why the resolved indexes carry their own `schemaVersion` (currently `"1.2.0"`,
bumped for the additive `tag-inferred` kind), tracked independently of the static indexes'
(`scripts/build_skill_map.py`'s `SCHEMA_VERSION`, `"1.1.0"`) — nothing in the committed
`generated/skill-map.indexes.json` changes.

**Qualification rule.** `route-core.js`'s `routeFromIndex()` (the index-backed path skill-router.js
and agent-brief-router.js both prefer) requires >=2 matched signals for implicit routing to consider a skill at all,
same as always — and now ALSO requires at least one full-weight matched signal (`weight >= 1`,
i.e. a `name` or a declared `tag`). A third-party skill matching only 2 of its half-weight
inferred tags therefore never qualifies on its own; it needs its `name` signal (or, hypothetically,
a declared tag) to match too. This is a floor, not a ranking rule — the weight math is what keeps
an inferred-backed match from outranking a declared one: a third-party skill's best possible score is `1 (name) + 3 × 0.5 (inferred) = 2.5`, while any
declared match needs only a `name` + one `tag` to reach `1 + 2 = 3`.

**Rendering.** A third-party skill id has three segments
(`skill:<marketplace>/<plugin>/<skill-dir>`, per "Third-party ecosystem inventory" above); both
`skill-router.js`'s suggestion message and `agent-brief-router.js`'s directive matching/advisory
text render it as `<plugin>:<skill>` (dropping the marketplace segment) via `route-core.js`'s
shared `formatSkillRef()`/`splitSkillId()` — as do `session-disclosure.js` and
`remediation-suggester.js`, whose own inline parsers were replaced by the same helpers — and a
rhize skill's ordinary two-segment id renders byte-identically to before. Because third-party
plugin/skill/command *names* are attacker-influenced file names that end up in text the hooks
print into the model's context, `build_local_skill_map.py` strips C0/C1 control, zero-width, and
bidi-override characters from them (and clamps length) when it inventories a plugin, and
`route-core.js`'s `safeLabel()` strips the same class again at the display boundary. `formatSignalLabel()` suffixes a `tag-inferred` signal's label with `" (inferred)"` in
`skill-router.js`'s "matches ..." text, so a half-weight guessed tag reads differently from a
declared name/tag match; `agent-brief-router.js`'s advisory never prints signal labels at all, so
the suffix never appears there (its own third-party score ceiling of 2.5 sits below its
`BRIEF_MIN_SCORE` floor of 4 regardless).

**Documented divergence: no fallback-path inference.** The map-scanning fallback (`route()`, used
only when no `skill-map.indexes.{resolved,}.json` exists at all) walks `doc.nodes`/`doc.edges`
directly and has no inferred-signal equivalent — implicit third-party routing remains unavailable there. This is deliberate: teaching the fallback path the same inference
would mean re-deriving it from the local overlay's third-party inventory + tags catalog at hook
runtime (a per-invocation cost the precomputed-index design exists to avoid), for a code path only
ever exercised by an install that hasn't rebuilt its indexes file yet.

## `extends` and the depth-2 rule

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

## `precedes`

`precedes` records that the `from` node comes before the `to` node in a real ordered workflow —
for example, `project-launcher`'s command pipeline: `write-prd` precedes `grill-prd` precedes
`scaffold-gsd`. Declared by hand in `catalog/skill-relations.json` (source: `relations-catalog`),
the same way as `overlaps-with`/`depends-on`/`replaces`.

## `follows` (mined) vs `precedes` (declared)

`follows` is the mined counterpart to `precedes`: same surfacing consumer (a "what comes next"
suggestion), different provenance. `precedes` is curated intent, hand-declared in
`catalog/skill-relations.json` for a real ordered workflow (e.g. a command pipeline) whether or
not anyone has actually run it that way yet. `follows` is empirical — the standalone
`rhize-skill-monitor` tool mines ordered, time-adjacent skill pairs within a session (via `monitor.py`'s
`build_cooccurrence()`, extended to also emit `orderedPairs`) and only surfaces a pair once it
recurs across ≥2 distinct sessions. Because it's derived from this machine's usage history,
`follows` lives in the local overlay only (`skill-map.local.json` / `skill-map.resolved.json`) —
never in the committed static artifact — and is never hand-authored.

## `augments` — cross-cutting skill-to-topic modifier

`augments` targets a *topic tag*, not another skill — "run me alongside/after anything in this
category to improve its output" (e.g. `seo-aeo-geo/content-seo` augments `tag:topic/content-authoring`).
It is deliberately distinct from `extends`: no lexical overlap with its targets is implied, it
carries no gate-exemption or depth semantics, and its target is a whole category rather than one
specific skill. Declared in a skill's own frontmatter (`metadata.rhize.augments: [<topic-slug>]`)
for Rhize skills; for third-party skills (whose frontmatter isn't ours to edit — and which may not
even be inventoried as a proper skill node, see "`depends-on` and `mcp-server` nodes" below),
declared in `catalog/skill-relations.json` instead, from an `external:<name>` node representing the
capability.

## `remediates` and condition tags

`remediates` targets a *condition tag* (`tag:condition/<slug>`) — "surface me when this failure
happens." The condition vocabulary lives in `catalog/tags.json` exactly like topic/stack, closed
at 5 entries: `build-failure`, `type-error`, `test-failure`, `lint-failure`, `merge-conflict`. Each
condition entry additionally carries `patterns`, regexes matched against **failed tool output**
(not the user's prompt — that's the router's job), e.g. `\berror TS\d+\b` for `type-error`.
Declared the same way as `augments`: `metadata.rhize.remediates: [<condition-slug>]` in
frontmatter for Rhize skills, `catalog/skill-relations.json` for third-party capabilities.

Several seeded `remediates` edges (the `everything-claude-code` build-resolver family) originate
from `external:` nodes rather than `skill:` nodes, because those capabilities are **agents**
(`agents/*.md`), not skills — the skill-map schema has no `agent` node kind, and third-party
agents aren't inventoried by `rhize-context-manager/scripts/build_local_skill_map.py`'s third-party scan (which only walks
`skills/*/SKILL.md` and `commands/*.md`). Modeling them as `external` nodes reuses the same
pattern `fork-of` already uses for upstream marketplaces, rather than adding a new node kind for
a case outside this round's scope.

## `depends-on` and `mcp-server` nodes

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

---

Back to [`docs/skill-map.md`](../skill-map.md).


## Explicit skill requests

Both router paths accept a leading `Use`, `Invoke`, or `Run` directive (optionally `Please`)
with an exact `plugin:skill` reference or unique skill directory name. This qualifies a name-only
entry without inferred tags and takes precedence over implicit scoring. Duplicate bare names,
marketplace collisions, unknown names, negated directives and prose mentions do not qualify this
explicit path. It emits at most one advisory suggestion; it does not execute the skill. The
existing two-signal and strong-signal thresholds remain in place for implicit matching. Explicit
matches score 3; the separate agent-brief advisory's score floor still applies.

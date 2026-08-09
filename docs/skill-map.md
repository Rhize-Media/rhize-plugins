# Skill Map — Conventions

The skill map is the **generated** graph substrate for skill routing, curation, and disclosure
across this repo's plugins. It replaces the flat, hand-restated skill inventory (marketplace.json
+ per-plugin READMEs + root catalog + GUIDE tables) with one machine-produced artifact. See
`.claude/plans/skill-map-graph-substrate.md` for the full rationale and phased rollout; this doc
only records the conventions that downstream consumers (router hook, session-disclosure hook,
`/start`, curation gates, generated docs, vault visualization) rely on.

The schema contract lives at `schemas/skill-map.schema.json` (JSON Schema, draft 2020-12).

## Artifacts

| File | Where | Contents |
|---|---|---|
| `schemas/skill-map.schema.json` | committed | Node/edge contract, `schemaVersion`. |
| `generated/skill-map.static.json` | committed | Deterministic repo facts — this repo's plugins, skills, commands, hooks, and their `contains`/`fork-of`/relations-catalog edges. Produced by `scripts/build_skill_map.py`; never hand-edited. |
| `catalog/skill-relations.json` | committed | Hand-declared, non-derivable edges (`overlaps-with`, `depends-on`, `replaces`) — the **one** curated input to the static compiler. Validated against the schema like any other artifact. |
| `~/.claude/context-manager/skill-map.static.json` | machine-local | Byte-identical copy of the committed static artifact, installed by `python3 scripts/build_skill_map.py --install`. Exists because an *installed* plugin (as opposed to a checkout of this repo) cannot see `generated/` — this is the fallback the router hook reads when no resolved map is present yet. |
| `~/.claude/context-manager/skill-map.local.json` | machine-local, gitignored | This machine's enabled-plugin set, stack config, and usage weights sourced from skill-monitor. |
| `~/.claude/context-manager/skill-map.resolved.json` | machine-local | The merged consumer view: static artifact + local overlay. This is what the router hook and `/start` actually read. |

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

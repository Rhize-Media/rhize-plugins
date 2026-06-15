# Capability Schema — the metadata every skill/MCP/plugin exposes

Answers open question #1 of [[Skill Customizer & Organizer]]: *what standard metadata should every
resource expose for classification?* This is the substrate the organizer runs on.

**Engine-optional by design.** It works as pure metadata today — tags you can query plus a
dashboard view — and it is the *exact* substrate a future two-layer composition engine would read.
So nothing here is throwaway if the product path (Decision #0: internal-now, product-later) fires.

## Fields

| Field | Values | Required | Purpose |
|-------|--------|----------|---------|
| `tier` | `resource` \| `custom` | yes | `resource` = installed as-is (a DEFER target / library item); `custom` = Rhize-authored or -personalized (FORK / wrap / merge output). The resource/custom split **as a tag**, not a runtime layer. |
| `domain` | controlled vocab (below) | yes | classification + the grouping that bounds overlap scans |
| `consumes` | list of skill names | when it consumes resources | dependency edges → the graph (open Q#6); omit for standalone customs. |
| `provenance` | `SOURCES.md` slug | when derived from an external source | join key to the ledger + the drift classifier |
| `source` | url \| path \| `internal` | when external | where it came from |
| `license` | SPDX id or class | when external | gates ABSORB/FORK (see `provenance.md`) |
| `maturity` | `seedling` \| `stable` \| `deprecated` | yes | prune + trust signal |
| `usage` | *(derived — not stored)* | n/a | joined at index time from skill-monitor snapshots; never duplicated here |

## Where it lives

- **Frontmatter** on each Rhize-authored skill (`tier`, `domain`, `consumes`, `provenance`,
  `maturity`). Additive — it does **not** change how the skill loads.
- **Sidecar index** (`registry.json`, built by `index_skills.py`) for the full installed set,
  because you cannot edit frontmatter on `resource` skills you don't own. The index carries
  `tier: resource` entries with an auto-classified `domain`, and joins `usage` from skill-monitor.
- **Never a parallel copy** of usage or version data — those are owned by `skill-monitor` and the
  `ai-stack-version-drift` sensor respectively (see `drift-boundaries.md`). The registry references
  them by key; it does not re-store them.

## How it's consumed

- `index_skills.py` → builds `registry.json` from frontmatter + the skill-monitor inventory; flags
  untagged/stale entries (**rot detection** — surface missing tags in the dashboard the same way
  prune candidates are surfaced, so metadata rot is visible, not silent).
- `overlap_scan.py --set-mode` → flat all-pairs scan across the set; `domain` is surfaced but does **not** yet bound the comparison (a future optimization once tags are widespread).
- `build_dependency_graph.py` *(Phase 2)* → reads `consumes` to render the dependency panel.
- Drift classifier (`record_provenance.py --check-drift`) → reads `provenance` to map "moved" →
  "tracked."

## Controlled vocabulary — `domain`

Keep it small and Rhize-shaped; extend deliberately. Seed set: `seo`, `aeo-geo`, `obsidian`,
`sanity`, `payload`, `supabase`, `dev-flow`, `error-lifecycle`, `data-mutation`, `sentry`, `ops`,
`comms`, `research`, `meta` (skills about skills: forge, refinement, dashboard). **One domain per skill** — if
two genuinely fit, the skill may be doing two jobs, which is a FORK/split signal.

## Engine-optional / product-forward rule

In the lightweight (internal) world these are query tags and dashboard inputs — no engine. If
Decision #0 goes product, the *same* fields become load-bearing: `tier` gates what is user-facing,
`consumes` drives runtime composition, `provenance` drives propagation. Design rule both ways:

> **Never add a field the lightweight world can't use today; never omit a field the product world
> will need.** The fields above satisfy both — that's what makes the metalayer a true on-ramp
> rather than throwaway scaffolding.

---

*Related: `drift-boundaries.md` (the `provenance`/`consumes` join), `provenance.md` (`SOURCES.md`
format), `overlap-analysis.md` (how `domain` bounds set-mode), and `rhize-ops/skill-monitor`
(the inventory + usage this joins against).*

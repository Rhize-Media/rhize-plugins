# Query Layer — Deep Reference

Deep reference for the "Query layer" section summarized in
[`docs/skill-map.md`](../skill-map.md).

**Tier 1 — materialized indexes** (`generated/skill-map.indexes.json`) cover the hot paths hooks
need at runtime, precomputed so no hook has to walk `doc.edges` itself:

- `router` — per-skill tag/name/phrase signal lists (mirrors `skill-router.js`'s own precomputation:
  each topic-tag/stack-tag edge as a weight-2 "tag" signal, each skill's own name as a weight-1
  "name" signal) plus the `extends` base/extender adjacency the router uses for its tie-break.
  A skill that declares `metadata.rhize.router.phrases` also gets one weight-2 `phrase` signal
  per phrase (`{"kind": "phrase", "weight": 2, "label": "<phrase>"}`), read from the skill node's
  `routerPhrases`. See [`docs/skill-map.md`](../skill-map.md)'s "Per-skill router phrases" for the
  validation rules. `routeFromIndex()` needs no special handling, because it matches every
  signal by its label's words regardless of `kind`. The map-scanning fallback `route()` builds
  signals from tag edges and names only, so it does not see phrases; that path runs only when no
  indexes file exists. The new kind is additive and the static indexes keep `schemaVersion`
  `"1.1.0"`, as with the earlier additive remediation `labels` field: consumers that ignore
  `kind` see one more weight-2 signal, and nothing that reads the index rejects an unknown kind.
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
- `remediation` — condition slug → `{patterns, skills, labels?}`. `skills` is sorted by node id
  (alphabetical) — no ranking/promotion signal exists yet, so this is the deterministic default
  until one lands (see the design doc's "pairs-with... revisit later as an audit promotion
  target" non-goal for the analogous case). Consumed by `remediation-suggester.js` (PostToolUse,
  matcher `Bash`): on a failing Bash command, the patterns are matched against `stdout`+`stderr`
  (compiled via a Python-`re`-to-JS-`RegExp` shim that strips a leading `(?i)` inline flag into
  the JS `i` flag — the catalog's patterns are authored as Python regexes) and the first-listed
  remediator for the first matching condition is suggested. An `external:` id (a third-party
  capability with no proper skill-map node, e.g. an `ecc` build-resolver *agent*) carries its
  catalog `name` in the optional `labels` map (`{id: name}`, omitted when empty); the hook reads the
  trailing `(agent)`/`(skill)`/`(command)` from that label to phrase the suggestion, and falls back
  to agent phrasing when no label exists. The message lead-in names the matched condition
  (`Tests failed`, `Merge conflict`, ...).
- `succession` — node id → `{precedes, follows}` from declared `precedes` edges. `follows` is
  always `[]` in the static indexes — mined `follows` edges are local-overlay only — and gets
  filled in by `rhize-context-manager/scripts/build_local_skill_map.py` at
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
| `skill-neighborhood` | skill id | Every incoming and outgoing relationship, grouped by all schema edge types; empty groups remain visible so an audit can distinguish no edge from an uninspected edge. |

```bash
python3 scripts/query_skill_map.py what-remediates build-failure
python3 scripts/query_skill_map.py what-follows seo-aeo-geo/content-seo --resolved
python3 scripts/query_skill_map.py skill-neighborhood procedural-memory/functionize
python3 scripts/query_skill_map.py --list
```

---

Back to [`docs/skill-map.md`](../skill-map.md).

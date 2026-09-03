# Skill-Map Subsystem — File Index

The skill-map subsystem's files span several top-level directories (`catalog/`, `schemas/`,
`generated/`, `scripts/`, `rhize-context-manager/scripts/`, `tests/skill-map/`,
`rhize-context-manager/hooks/`, and this `docs/skill-map/` directory) rather than living under one
`skill-map/` directory of their own; see [`docs/skill-map.md`](../skill-map.md) for the full
conventions reference and [ROADMAP.md](../../ROADMAP.md) for why a consolidating move is deferred.
This page is the index: one line per file, so a reader can find any piece without already knowing
which top-level directory owns it.

The files deliberately stay where they are — a directory move was assessed and deferred (see
ROADMAP.md); this index substitutes for it.

## Catalog inputs (hand-declared, committed)

- [`catalog/tags.json`](../../catalog/tags.json) — the closed topic/stack/condition tag vocabulary.
- [`catalog/skill-relations.json`](../../catalog/skill-relations.json) — hand-declared,
  non-derivable edges (`overlaps-with`, `depends-on`, `replaces`, `augments`, `remediates`).
- [`catalog/queries.json`](../../catalog/queries.json) — declarative walk specs for the query
  layer's second tier (`scripts/query_skill_map.py`).

## Schema

- [`schemas/skill-map.schema.json`](../../schemas/skill-map.schema.json) — the node/edge contract
  every generated or resolved artifact validates against.

## Generated artifacts (never hand-edited)

- [`generated/skill-map.static.json`](../../generated/skill-map.static.json) — the deterministic
  repo-facts artifact (plugins, skills, commands, hooks, and their edges).
- [`generated/skill-map.indexes.json`](../../generated/skill-map.indexes.json) — materialized
  hot-path lookups (`router`, `disclosure`, `remediation`, `succession`) derived from the static
  artifact.
- [`generated/SKILL-CATALOG.md`](../../generated/SKILL-CATALOG.md) — the rendered, managed skill
  catalog doc.

## Pipeline scripts

- [`scripts/build_skill_map.py`](../../scripts/build_skill_map.py) — compiles the catalog inputs
  and repo facts into the two `generated/` artifacts.
- [`scripts/validate_skill_map.py`](../../scripts/validate_skill_map.py) — schema validation and
  the `--check-stale` freshness gate.
- [`scripts/render_skill_map_docs.py`](../../scripts/render_skill_map_docs.py) — renders the
  managed doc sections (root `README.md`, `docs/README.md`, `generated/SKILL-CATALOG.md`) from the
  static artifact.
- [`scripts/query_skill_map.py`](../../scripts/query_skill_map.py) — the query layer's declarative
  walk runner, driven by `catalog/queries.json`.
- [`scripts/publish_skill_map_vault.py`](../../scripts/publish_skill_map_vault.py) — publishes the
  static artifact into an Obsidian vault as Bases/Canvas artifacts.
- [`scripts/baseline_upstreams.py`](../../scripts/baseline_upstreams.py) — snapshots third-party
  upstream sources used by `fork-of` drift checks.
- [`scripts/sources_md.py`](../../scripts/sources_md.py) — parses/normalizes each plugin's
  `SOURCES.md`, the input `fork-of` edges are derived from.
- [`scripts/viewer/`](../../scripts/viewer/) — `build_viewer.py` and `viewer-template.html`, the
  interactive force-directed HTML graph viewer.
- [`rhize-context-manager/scripts/build_local_skill_map.py`](../../rhize-context-manager/scripts/build_local_skill_map.py)
  — builds the machine-local overlay and resolved map (`~/.claude/context-manager/skill-map.
  {local,resolved,indexes.resolved}.json`) from the committed static artifact plus this machine's
  enabled-plugin set, stack config, and usage/succession signals.

## Tests

- [`tests/skill-map/`](../../tests/skill-map/) — the full test suite: `test_build.py` and
  `test_local_build.py` (compiler/overlay correctness), `test_stale_gate.py` (the `--check-stale`
  gate), `test_render_docs.py` (hermetic managed-doc rendering), `test_router.js`,
  `test_disclosure.js`, `test_remediation.js`, `test_next_step.js`, and
  `test_agent_brief_router.js` (the five consumer hooks below), `test_baseline_upstreams.py`,
  `test_functionize_traversal.py`, `test_v2_relationships.py`, `test_summary_field.py`, and
  `test_suggestion_log_report.py`.

## Consumer hooks (read the installed/resolved map at runtime)

- [`rhize-context-manager/hooks/skill-router.js`](../../rhize-context-manager/hooks/skill-router.js)
  — per-prompt skill-routing suggestion.
- [`rhize-context-manager/hooks/session-disclosure.js`](../../rhize-context-manager/hooks/session-disclosure.js)
  — SessionStart skill disclosure.
- [`rhize-context-manager/hooks/remediation-suggester.js`](../../rhize-context-manager/hooks/remediation-suggester.js)
  — PostToolUse remediation suggestion on a failing Bash command.
- [`rhize-context-manager/hooks/next-step-suggester.js`](../../rhize-context-manager/hooks/next-step-suggester.js)
  — PostToolUse successor-skill suggestion after a Skill invocation.
- [`rhize-context-manager/hooks/agent-brief-router.js`](../../rhize-context-manager/hooks/agent-brief-router.js)
  — agent-dispatch skill-coverage measurement (via `hooks/lib/route-core.js`).

## Reference docs

- [`docs/skill-map.md`](../skill-map.md) — the primary conventions reference: node kinds, edge
  types, tag vocabulary, the query layer, and the consumers table.
- [`docs/skill-map/edge-semantics.md`](./edge-semantics.md) — `fork-of` drift checks, the
  third-party ecosystem inventory, and the other edge types' deep mechanics.
- [`docs/skill-map/query-layer.md`](./query-layer.md) — the two-tier query system in depth.
- [`docs/skill-map/generated-docs.md`](./generated-docs.md) — managed-section doc rendering and
  the Obsidian vault publish.
- [`docs/skill-map/agent-dispatch-surface.md`](./agent-dispatch-surface.md) — the agent-dispatch
  measurement instrument and its forward contract.

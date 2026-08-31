# Functionize skill-map audit and packaging

## Current behavior and evidence

- Rhize Plugins `v2.52.0` at `fd142a6` packages procedural-memory recall, run, promote, and verify surfaces, but its generated skill map has no Functionize node or command.
- The currently resolved `rhize-skill` interface exposes `functionize`, `functionize-generate`, and `functionize-review`. Its help text states that generation emits inert proposals and never registers, approves, promotes, invokes, or executes them.
- The runtime package reported `0.1.0` both before and after Functionize landed, so semver cannot
  identify the required command surface by itself; the adapter must probe the selected command's
  side-effect-free `--help` path before dispatching user arguments.
- Functionize lives in the separate `Rhize-Media/procedural-memory` runtime. This repository owns only the cross-host skill and thin launcher/command adapters.
- `.codegraph/` is absent. Structural discovery for this change used `rg` over the procedural-memory plugin, compiler, schema, query layer, generated artifacts, tests, and the runtime's local checkout.
- Arm A regenerated deterministically and passed schema, freshness, fixture, router, relationship, orphan/unroutable, and duplicate checks. A realistic Functionize prompt cannot route because no Functionize surface exists.

## Intended semantic delta

- Package one canonical `procedural-memory:functionize` skill shared by Claude Code and Codex.
- Add three thin Claude commands for mining/automatic compile, single-candidate generation, and digest-bound review; all call a self-relative launcher.
- Make the launcher expose only `mine`, `generate`, and `review`, mapping them to the three verified runtime commands. Refuse registry, approval, promotion, verification, and execution modes before resolving the CLI.
- Represent Functionize from source in the generated map with discriminating canonical metadata: topic `automation`, stack/task-intent tag `functionize`.
- Model the actual shared runtime dependency with `external:rhize-skill-cli` and `depends-on` edges from both packaged skills.
- Add a declarative `skill-neighborhood` query that traverses every schema edge type in both directions for audit use.

## Invariants and must-not-change boundaries

- Functionize remains compile-only. Nothing in this change registers, trusts, approves, promotes, verifies, executes, or invokes a generated target.
- No `precedes`, `extends`, `augments`, `overlaps-with`, `remediates`, `replaces`, `supersedes`, or `fork-of` edge may imply that proposal generation clears a later gate.
- Runtime command text is data from the verified local interface; wrapper code must not invent flags or bypasses.
- Generated skill-map and catalog docs are regenerated only from source inputs, never hand-edited.
- The existing procedural-memory registry skill retains its digest, trust, health, and approval boundaries.
- Installed plugin caches and legacy compatibility symlinks remain untouched.

## Current structural touchpoints

| Surface | Why affected | Evidence |
|---|---|---|
| `procedural-memory/skills/` | Canonical Claude/Codex skill discovery and self-relative launcher | Existing procedural-memory skill/launcher pattern |
| `procedural-memory/commands/` | Thin Claude adapters | Existing recall/run/promote/verify commands |
| procedural-memory manifests and docs | Package version/discovery and capability documentation | Current version `0.3.2`; Functionize absent |
| `catalog/tags.json` | Closed canonical topic/stack vocabulary | No Functionize discriminator |
| `catalog/skill-relations.json` | Non-derivable external runtime dependency | Existing external dependency pattern |
| `catalog/queries.json` | Audit-time declarative traversal | Current queries cover only selected edge types |
| `scripts/build_skill_map.py` and generated artifacts | Source compilation and hot-path router signals | Existing tag/name signal compiler |
| skill-map and procedural-memory tests | Representation, traversal, routing, and gate regression coverage | Existing deterministic fixture and launcher suites |

### Exact planned paths

- Package manifests and release docs: `.claude-plugin/marketplace.json`, `CHANGELOG.md`,
  `README.md`, `procedural-memory/.claude-plugin/plugin.json`,
  `procedural-memory/.codex-plugin/plugin.json`, `procedural-memory/README.md`, and
  `procedural-memory/GUIDE.md`.
- Canonical map sources and docs: `catalog/tags.json`, `catalog/skill-relations.json`,
  `catalog/queries.json`, and `docs/skill-map.md`.
- Functionize adapters: `procedural-memory/commands/functionize.md`,
  `procedural-memory/commands/functionize-generate.md`,
  `procedural-memory/commands/functionize-review.md`,
  `procedural-memory/skills/functionize/SKILL.md`,
  `procedural-memory/skills/functionize/agents/openai.yaml`, and
  `procedural-memory/skills/functionize/scripts/functionize.sh`.
- Regression coverage: `procedural-memory/tests/test-launcher.sh`,
  `procedural-memory/tests/test_codex_discovery.py`, and
  `tests/skill-map/test_functionize_traversal.py`.
- Generator-owned outputs: `generated/SKILL-CATALOG.md`,
  `generated/skill-map.static.json`, and `generated/skill-map.indexes.json`.

## Acceptance tests

- Functionize appears once as a packaged skill with three command nodes and canonical tags.
- Both procedural-memory skills depend on `external:rhize-skill-cli`; no misleading Functionize workflow edge exists.
- `skill-neighborhood procedural-memory/functionize` covers every schema edge type in/out and returns the expected neighborhood.
- Realistic operational and engineering Functionize prompts route to Functionize; a registry execution prompt still routes to procedural-memory.
- The Functionize launcher maps only mine/generate/review and refuses promotion/approval/verification/run modes.
- A stale same-version runtime without Functionize fails the capability probe before any user
  arguments are dispatched.
- Codex discovery includes the Functionize skill.
- Generator determinism, schema, freshness, orphan/unroutable, duplicate/overlap, breadth, relationship, query, router, and traversal suites pass.
- Full relevant repository validation and a cold diff review pass before commit/release.

## Implementation order

1. Add failing focused traversal, launcher, and Codex-discovery tests.
2. Add the Functionize skill, launcher, and three commands.
3. Add canonical tag, runtime dependency, and all-edge neighborhood query sources.
4. Update plugin/root documentation and versions without changing the `v2.52.0` tag.
5. Regenerate maps/catalog docs, run focused and broad gates, reconcile this impact map, and cold-review the diff.

## Parallelization

- This is a single-writer graph/compiler change with overlapping generated outputs; implementation remains sequential. Independent test commands may run concurrently after generation.

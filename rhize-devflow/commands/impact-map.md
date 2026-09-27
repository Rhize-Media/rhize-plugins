---
description: CodeGraph-first impact mapping that separates current dependency truth from the intended semantic change
---
<!-- canonical: rhize-devflow:impact-map -->

# Impact Map

Map current dependencies and intended changes before implementation; reconcile after.

## Contract

- CodeGraph is authoritative for current structural truth; the impact map is authoritative for intended change.
- Label claims as evidence, inference or planned. Preserve repository instructions, unrelated work and release authority.
- Never report an inferred edge as a confirmed caller or initialize CodeGraph.

## 1. Scope

Read repository instructions and required context. Check Git state, repository roots and `COMPONENT_REGISTRY.md`; state the requested outcome and existing authorization.

## 2. Discover

use CodeGraph before text search or manual reads. For each root, require `command -v codegraph` and a healthy `codegraph status`; sync stale indexes, then run:

```bash
codegraph explore "<entry points, behavior, callers and tests>"
codegraph impact <symbol>
codegraph affected <planned-existing-files>
```

If the index or interface is missing, corrupt, stale after synchronization, or unsupported, record why and use `rg` plus targeted reads. Never run `codegraph init`. Identify relevant callers, schemas, permissions, tests, generated code, configuration and external boundaries.

## 3. Persist the map

Save `.claude/plans/<descriptive-name>.md` with these sections:

- `Current behavior and evidence`
- `Intended semantic delta`
- `Invariants and must-not-change boundaries`
- `Current structural touchpoints`
- `Planned additions and deletions`
- `External and operational effects`
- `Acceptance tests`
- `Explicitly unaffected paths`
- `Unknowns and confidence`
- `Implementation order`

If the prompt hook supplies a `Preparation ID`, start the map with that exact ID and `Discovery query: <same query>`, each on one line. The first write may auto-prepare only one recent, complete map matching both values. Otherwise run `prepare` explicitly:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" prepare --workspace "<root>" --plan "<plan>" --query "<same query>"
```

## 4. Implement

The prepared gate blocks source edits until preparation. If the manual step was missed, the hook prepares only a unique matching map; missing or ambiguous maps stay blocked. Make the smallest mapped change, preserve invariants and run required checks.

## Phase 5: Reconcile After Implementation

Repeat the original discovery branch for every root. For a healthy index run `codegraph sync`, the same `codegraph explore`, and `codegraph affected <actual-changed-files>`; otherwise repeat the original `rg` queries and targeted reads. Compare the actual diff, evidence, tests and map. Report one **Reconciliation verdict**:

- `IN_SYNC` — evidence, diff, and map agree.
- `IN_SYNC_WITH_EXCEPTIONS` — named dynamic, generated, or external edges need manual evidence.
- `OUT_OF_SYNC` — an unexplained diff, missing consumer, stale graph, or unverified invariant remains.

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" reconcile --workspace "<root>"
```

Commit, push, merge, and completion remain blocked until reconciliation. Do not declare completion while `OUT_OF_SYNC`. If planned scope changes, update the map and prepare again. For a false positive, run `dismiss --workspace <root> --reason <specific reason>`.

## On-Demand Reference

Load [`../docs/impact-map-reference.md`](../docs/impact-map-reference.md) for the full template, fallback details and troubleshooting.

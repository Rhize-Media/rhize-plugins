---
description: CodeGraph-first impact mapping that separates current dependency truth from the intended semantic change
---
<!-- canonical: rhize-devflow:impact-map -->

# Impact Map

Map before implementation; reconcile the completed diff against the same evidence.

## Core Contract

- **CodeGraph is authoritative for current structural truth.**
- **The impact map is authoritative for intended change.**
- Label facts as **evidence**, **inference**, or **planned**. Never present an inferred edge as a confirmed caller.
- Preserve repository instructions, unrelated work, release authority, and every named invariant.

## Phase 1: Establish Scope

Read repository instructions and required context. Check Git state, identify every repository root, inspect `COMPONENT_REGISTRY.md` when present, and state the requested outcome. Existing implementation authorization still applies.

## Phase 2: Discover Current Structural Truth

For each repository root:

1. If `.codegraph/` exists, use CodeGraph before text search or manual reads. Prefer the MCP interface when available. For the CLI, require `command -v codegraph` and a healthy `codegraph status`, synchronize a stale index, then run:

```bash
codegraph explore "<entry points, symbols, behavior, callers, and tests>"
codegraph impact <symbol>
codegraph affected <planned-existing-files>
```

2. If the index or interface is missing, corrupt, stale after synchronization, or unsupported, record the condition and use `rg` plus targeted reads. Never run `codegraph init`.

Identify entry points, owners, callers, schemas, caches, permissions, tests, dynamic dispatch, generated code, configuration, and external boundaries.

## Phase 3: Persist the Semantic Map

Persist a descriptive plan under the repository’s required plan directory with these headings:

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

## Phase 4: Prepare and Implement

Before the first source edit, run:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" prepare --workspace "<root>" --plan "<plan>" --query "<same discovery query>"
```

The gate records CodeGraph or fallback evidence and blocks source edits until preparation. Implement the smallest mapped change, preserve invariants, update the map when evidence changes scope, and run focused then repository-required checks.

## Phase 5: Reconcile After Implementation

Repeat the original discovery branch for every root. For a healthy index run `codegraph sync`, the same `codegraph explore`, and `codegraph affected <actual-changed-files>`; otherwise repeat the original `rg` queries and targeted reads. Compare the actual diff, structural evidence, tests, and semantic map.

Report one **Reconciliation verdict**:

- `IN_SYNC` — evidence, diff, and map agree.
- `IN_SYNC_WITH_EXCEPTIONS` — named dynamic, generated, or external edges need manual evidence.
- `OUT_OF_SYNC` — an unexplained diff, missing consumer, stale graph, or unverified invariant remains.

Commit, push, merge, and completion remain blocked until reconciliation. Record the verdict:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/refactor_gate.py" reconcile --workspace "<root>"
```

Do not declare completion while `OUT_OF_SYNC`. If the map changed, run `prepare` again. For a documented false positive, use `dismiss --workspace "<root>" --reason "<specific reason>"`.

## On-Demand Reference

Load [`../docs/impact-map-reference.md`](../docs/impact-map-reference.md) only for the full output template, multi-repository examples, context-pack bridge, fallback details, troubleshooting, and failure modes.

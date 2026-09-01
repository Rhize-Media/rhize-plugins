# Impact Map: Implement CodeGraph for Rhize Plugins

## Current Behavior

- **Evidence:** `/Users/jamesdeola/dev-local/RHIZE/rhize-plugins` has no `.codegraph/`
  directory, so Dev Flow impact mapping and Rhize Context Manager native context discovery use
  their documented `rg`/targeted-read fallback.
- **Evidence:** CodeGraph CLI 1.6.0 is already installed at `/opt/homebrew/bin/codegraph`.
- **Evidence:** existing repository consumers already implement healthy-index-first routing:
  `rhize-devflow/scripts/refactor_gate.py`, `rhize-devflow/scripts/devflow.py`, and
  `rhize-context-manager/scripts/context_experiments/providers/native_context_pack.py`.
- **Evidence:** a disposable snapshot indexed 437 supported files into 7,255 nodes and 21,697
  edges in 1.6 seconds; exploration returned useful source/test relationships while affected-test
  output was intentionally broad.
- **Evidence:** live initialization indexed 437 files into 7,258 nodes and 21,707 edges, but
  `devflow.py evidence` falsely reported the healthy index stale after a Markdown-only edit while
  `codegraph status --json` reported zero pending changes. Its existing timestamp heuristic compares
  the database against every tracked file rather than CodeGraph's supported/indexed files.
- **Evidence:** the release working tree is clean on
  `codex/codegraph-repository-index-release`, based directly on `origin/main`. Existing local
  documentation commit `9287b83` remains preserved on local `main` and is outside this release.

## Problem

The repository's own CodeGraph-first workflows cannot use structural graph evidence because the
owner-approved per-repository index has not been initialized. Repeated impact maps therefore pay
the slower and less structurally complete fallback cost, and current context/search experiments
cannot dogfood CodeGraph on the repository that implements them.

## Proposed Change

- Initialize CodeGraph 1.6.0 at the repository root using its zero-config defaults.
- Keep the generated SQLite index and other machine-local data uncommitted. Track only the
  generated `.codegraph/.gitignore` marker plus concise repository documentation explaining
  initialization, synchronization, health checks, privacy, and fallback behavior.
- Make Dev Flow use read-only `codegraph status --json` as the authoritative freshness signal
  when available, retaining its timestamp heuristic only as an explicit compatibility fallback.
- Release that user-visible Dev Flow correction as the next patch version, keeping plugin and
  marketplace metadata plus README/GUIDE/CHANGELOG documentation in sync.
- Do not add another semantic-search implementation, MCP wrapper, scheduled task, watcher, or
  custom CodeGraph configuration unless real indexing evidence requires it.
- Verify the existing Dev Flow and Context Manager consumers detect the healthy index without
  changing their source code.

## Intended Semantic Delta

- Applicable code-navigation, impact-map, and native context-pack tasks in this checkout select
  CodeGraph first after a healthy status preflight.
- The fallback remains deterministic and explicit when the CLI or database is unavailable,
  unhealthy, or stale.
- CodeGraph remains a local, regenerable structural index; no source or index content is uploaded
  or committed.

## Invariants and Must-Not-Change Boundaries

- Do not commit `.codegraph/codegraph.db`, WAL/SHM files, caches, logs, or other generated state.
- Do not alter existing Context Manager/Dev Flow routing semantics or initialize indexes in other
  repositories.
- Do not enable Serena alongside CodeGraph for the same repository.
- Preserve all existing commits and unrelated worktrees; do not prune or rewrite them.
- Do not treat CodeGraph results as runtime correctness, authorization, or benchmark proof.
- Do not perform paid/provider calls or external data mutations.

## Current Structural Touchpoints

| Repository | Entry point or symbol | Why affected | Evidence |
|---|---|---|---|
| rhize-plugins | `.codegraph/` health marker and database | Activates existing healthy-index-first routing | Dev Flow and Context Manager check this directory before querying |
| rhize-plugins | `rhize-devflow/scripts/refactor_gate.py::codegraph_evidence` | Impact-map prepare/reconcile consumer | `rg` fallback currently reports `no .codegraph index` |
| rhize-plugins | `rhize-devflow/scripts/devflow.py::_codegraph_evidence` | Check/review evidence consumer | Reports existence, DB presence, and staleness without rebuilding |
| rhize-plugins | `native_context_pack.py::_codegraph_healthy` and `_codegraph_targets` | Compiled-context discovery consumer | Uses CodeGraph only after status succeeds |
| rhize-plugins | root README and CLAUDE instructions | Human/agent operating contract | Existing docs describe CodeGraph as optional but not this repo's active setup |

## Planned Additions and Deletions

- Add the generated `.codegraph/.gitignore` marker; keep all other `.codegraph` files ignored.
- Add a concise active-repository CodeGraph section to root technical and agent documentation in
  `README.md` and `CLAUDE.md`, and record the release in `CHANGELOG.md`.
- Keep Dev Flow's command behavior discoverable in `rhize-devflow/README.md` and
  `rhize-devflow/GUIDE.md`.
- Correct `devflow.py` freshness evidence plus its schema/tests; add no custom wrapper or deletion.

## External and Operational Effects

- Local disk: approximately 29 MB of regenerable SQLite index state based on the disposable pilot.
- Git: only this scoped CodeGraph implementation will be pushed; the unrelated local documentation
  commit remains unpushed, and generated database bytes remain excluded.
- Network/providers: none for initialization, indexing, synchronization, or validation.

## Reuse Opportunities

- Reuse the installed CodeGraph CLI and the repository's existing CodeGraph-first routing.
- Reuse `codegraph status`, `explore`, `affected`, and `sync`; do not build a wrapper.

## Acceptance Tests

- `codegraph init -y` completes at the real repository root.
- `codegraph status --json` exits zero, reports the index up to date, and exposes non-zero files,
  nodes, and edges.
- `codegraph explore` returns relevant Dev Flow/Context Manager symbols and tests.
- `codegraph affected` returns affected tests for representative existing source files.
- Dev Flow evidence reports `.codegraph` present, database present, and not stale.
- A Markdown-only tracked edit does not produce a false-stale finding when CodeGraph reports zero
  pending changes, while actual pending supported source still reports stale.
- Git sees only the intended marker/docs/plan; the SQLite database and auxiliary state remain
  ignored.
- Repository-required focused tests and documentation/config checks pass.
- Post-change impact-map reconciliation is `IN_SYNC` or names only concrete graph blind spots.

## Explicitly Unaffected Paths

- Skill-map generated artifacts, scheduled routines, benchmark rows, external systems, and every
  other repository's context/search selection. Only the required Rhize Dev Flow patch metadata
  changes; no other plugin version changes.
- The existing local `9287b83` documentation commit, which is not part of this release, and all
  registered worktrees.

## Unknowns and Confidence

- **Known blind spot:** CodeGraph parses supported source languages, not Markdown/JSON semantic
  contracts; targeted reads and repository validators remain required for those files.
- **Observed blind spot:** `codegraph affected rhize-devflow/scripts/devflow.py` suggested five
  Context Manager eval files but missed the direct subprocess-driven
  `tests/rhize-devflow/test_devflow_cli.py`; dynamic test invocation still requires the semantic
  impact map and targeted test selection.
- **Known blind spot:** dynamic hook dispatch, generated artifacts, and external/plugin-cache state
  require their existing manual/runtime checks.
- **Confidence:** high for local activation because existing consumers and the disposable pilot are
  already verified; medium for affected-test precision until the live index is exercised.

## Validation Evidence

- Live initialization: 437 files, 7,258 nodes, 21,707 edges in 639 ms; final synced graph has
  7,262 nodes, 21,721 edges, zero pending changes, complete state, and no worktree mismatch.
- Freshness control: before sync, authoritative status reported two modified supported files and
  Dev Flow emitted `codegraph-stale`; after sync it reported zero pending changes and
  `devflow.py evidence` emitted `stale=false` with no finding.
- Focused graph/Dev Flow/context tests: 218 passed, 2 skipped.
- Full repository gate: 1,008 passed, 2 skipped, 18 subtests passed.
- Config/metadata checks: plugin-config strict validation, JSON parsing, skill-map staleness, and
  generated README idempotency all passed.

## Implementation Order

1. Prepare this map while the repository still uses the fallback baseline.
2. Initialize the live zero-config CodeGraph index and inspect generated paths/ignore behavior.
3. Add the durable marker/documentation and correct the discovered Dev Flow false-stale heuristic.
4. Run live status/explore/affected and Dev Flow evidence checks, then focused repository tests.
5. Sync and reconcile the graph/diff/map, commit, merge to main, push, and verify remote SHAs.

# Obsidian indexing correction — impact map

Base: `3b6f073b93388fc929a81e535cffe344ec334dce`. Date: 2026-11-08.

## Current behavior

README forbids whole-vault indexing, but qmd-search and vault-setup still prescribe it.
The published instructions also use obsolete package/CLI forms, treat status success as
collection evidence, and recommend embedding without scanning changed files first.
Compiler status can recover prior transactions; it is not an observation-only operation.

## Intended semantic delta

Keep one canonical approved-root setup reference. Use the current upstream named-index,
explicit-collection syntax throughout setup, search, recall and connect. Require recorded
root/index/collection approval, compiler exclusion, and an audit of pre-existing index scope.
Explain update before embed and retained-index cleanup separately. Clarify compiler status
side effects and the supported one-source/one-page proposal boundary.

## Invariants

- No personal vault, credentials, scheduler, MCP configuration, or security setting changes.
- No compiler gate is enabled; no compiler runtime or transaction behavior changes.
- qmd never receives compiler output/private state or an unapproved source root.
- A failed qmd check never broadens the user's requested search scope.
- No promise that local models, connectors or retrieval quality have been tested on the Mac.

## Acceptance tests

Run compiler/hook/tool-name tests and deterministic Obsidian evaluation fixtures. Add a
contract against whole-vault indexing, old positional collection arguments, unscoped
search examples, and embed-only refresh guidance. Check manifest/config parity, skill-map
freshness, generated setup/docs freshness, and the version bump gate. Inspect final diff.
Upstream CLI syntax is source-verified; live qmd/model invocation remains a separate gate.

## Implementation order

1. Persist this map; verify baseline source and fixture tests.
2. Add canonical qmd reference and reconcile every affected instruction surface.
3. Clarify compiler limitations and report-only scheduling boundaries.
4. Run tests; bump via the repository script; regenerate managed artifacts.
5. Reconcile changed paths, preserve a reviewable patch, and report Mac-only checks.

## Expected changed paths

Obsidian README/GUIDE/CHANGELOG, qmd-search skill/reference, vault-setup/search/recall/connect,
vault-align and knowledge-compiler instructions; privacy regression contract; plugin and
marketplace versions plus generated catalogs/setup artifacts produced by repository scripts.

## Reconciled scope

Also updated the existing deterministic and live-model qmd evaluation expectations: the old
contract explicitly required obsolete `qmd embed vault` syntax. Added the source-backed audit
and adoption roadmap under `docs/research`. No compiler runtime, scheduler or security setting
changed. Generated setup artifacts were already current. Synthetic visual examples and local
verification receipts are review-bundle artifacts, not installed vault content.

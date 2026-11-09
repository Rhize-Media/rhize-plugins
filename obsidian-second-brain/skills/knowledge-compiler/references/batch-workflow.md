# Reviewed multi-source, multi-page compilation

The compiler is usable manually without qmd, an API key, an Obsidian app plugin, or a schedule.
It compiles an explicit proposal; it does not independently discover all notes or invent a wiki.
An assistant drafts the proposal from authorized captured evidence, and the human reviews it.

## Project workflow

1. Use a config owned by the vault/project, with real project/tenant/scope/operator values and
   approved source roots. Create the approved output directory first. Keep state/output outside qmd.
2. Capture several notes. Register each exact source revision with its actual policy. No whole-vault
   scan or automatic registration is implied. Use one bundle per policy boundary.
3. Draft a v2 proposal such as [the example](batch-proposal.example.json). It contains project and
   decision pages sharing a meeting source, with the project page also citing a brief. The example's
   claims and line numbers are illustrative: replace them with verified evidence, not guessed anchors.
4. Preview the batch. Read `review.md` and its linked child identifiers, including every citation
   excerpt, proposed diff and contradiction. Hashes verify bytes, not whether a claim follows from them.
5. Approve exactly that batch id, then apply it. Verify every page with `inspect`.

```bash
python3 scripts/compiled_knowledge.py register --config /approved/compiler.json \
  --source 'Sources/Project brief.md' --source-id project-brief \
  --acl internal --egress local-only --retention-class standard
python3 scripts/compiled_knowledge.py register --config /approved/compiler.json \
  --source 'Sources/Meeting.md' --source-id meeting-2026-11-08 \
  --acl internal --egress local-only --retention-class standard
python3 scripts/compiled_knowledge.py preview --config /approved/compiler.json \
  --proposal /approved/reviewed-proposal.json
# Read review.md and receive approval for the returned sha256 id before this next command.
python3 scripts/compiled_knowledge.py apply --config /approved/compiler.json \
  --preview-id sha256:REPLACE_WITH_APPROVED_BATCH_ID
python3 scripts/compiled_knowledge.py inspect --config /approved/compiler.json
```

The engine accepts 1–100 pages per batch. IDs and normalized paths must be unique, including case
variants for Mac portability. Target parent directories must already exist. Each page can cite many
registered sources. No page or bundle merges different ACL/egress/retention labels. Actual source
expiry is checked individually. The per-page manifest remains v1; its source revision list can
contain several sources. A batch receipt hashes those per-page preview ids and the review artifact.
Legacy v1 single-source proposals and 1.0.0 accepted manifests remain readable.

## Keeping the workflow useful

- After a meeting: capture/register the new note, propose updates to the project and decision pages,
  review once, apply the batch, inspect health.
- During recall: open the project page and follow its source links; check current health. A compiled
  page is a projection and cannot override its evidence.
- During weekly review: review stale/conflicting pages and propose only relevant updates. A stale
  page requires a fresh proposal; rebuilding from old line ranges is refused.
- In existing automation: `inspect` is suitable for an observation step after the routine owner
  updates it. `status` may mutate through recovery. Preview creation also writes private artifacts;
  neither should be inserted into a supposedly read-only routine without changing its contract.
- Keep human annotations in linked notes. Human edits to generated pages are preserved and block
  both new preview and apply. To reconcile, preserve the edits separately and deliberately restore
  the last accepted projection; do not bypass ownership/hash checks.

## Recovery and privacy

All pages are preflighted before the first target write. The per-vault lock serializes compiler
writers. A durable journal records the prior state; crashes before acceptance roll back the batch,
including index and accepted manifests. A crash after acceptance keeps the complete result.
Obsidian and other tools do not honor this lock and can observe intermediate files; the transaction
is not globally atomic. Before any rollback, every target is compared with its before/after bytes.
An external edit stops recovery and remains intact; preserve that edit before deciding how to repair.
Legacy unfinished 1.0.0 journals without after hashes fail closed if their current bytes changed.

Completed journals discard rollback payloads. Purging a source removes its owned dependent pages,
matching previews/bundles and retained snapshots. Other pages remain. Human edits are reported as
conflicts rather than erased. Canonical source notes are never deleted by the compiler. As before,
qmd, scheduled mutation, live synthesis, context injection, Graphify and Neo4j gates stay disabled.
Properties/Bases provide visual navigation, not access control or live freshness enforcement.

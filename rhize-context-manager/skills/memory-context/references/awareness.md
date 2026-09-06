# Explicit topic awareness and expansion

Use this opt-in path when a task needs to discover which approved memories exist before reading
their bodies. Prefer direct `preview` when the relevant source is already known or short; skip
memory when the task does not need it. Existing native Codex memory and claude-mem already provide
awareness in their own domains. This command does not capture, ingest, install, or activate them.

## Catalog input

The input uses the existing v1 request and adapter envelope. Replace each candidate's `content`
with a `topic` object; do not include both. Add `catalogTokenBudget` (default 600, minimum 64,
maximum request `totalTokenBudget`). A topic has exactly:

```json
{
  "label": "Approved brand color",
  "keywords": ["brand", "color", "decision"],
  "detailDigest": "c5a1e89c9d1b7c67080b6e69e1edfc6a1e1b847187df6ca858a928703a684136",
  "verifiedAt": "2026-09-06T11:00:00Z"
}
```

The digest above is illustrative: the actual value must be the SHA-256 of the exact UTF-8 detail
body. The trusted adapter/caller supplies this metadata from its authorized source, not by asking
recalled text to declare its own trust. Labels are 1–160 characters; at most eight keywords of
1–40 characters. Verification time must be timezone-aware and cannot be future-dated. Refreshing
an index date does not refresh a source: expansion checks both its current revision and exact body
digest. `recordedAt`, `validFrom`, `validUntil`, `retentionClass`, and trust remain the existing
typed envelope fields. Missing detail access never becomes permission to scrape private state.

Inputs are bounded to 8 MiB, 20 adapters and 200 candidates. Tenant/project/task and sensitivity
filtering precede disclosure. Duplicate source records must agree exactly; ambiguous bindings fail
closed. Distinct same-claim facts survive and retain conflict groups based on detail digests.

Optional `alreadyPresent` is an array of exact `{sourceSystem, sourceId, sourceRevision,
detailDigest}` bindings already supplied in this request's authorized context. Only exact matches
are suppressed. Do not fabricate bindings for a host summary that has no source references;
semantic similarity does not prove the same fact or authority.

## Use

```bash
scripts/memory-context.sh catalog --input /absolute/private/topics.json \
  --source-state /absolute/private/current-revisions.json \
  --data-dir /absolute/private/memory-store
scripts/memory-context.sh expand --input /absolute/private/selected-details.json \
  --manifest /absolute/private/memory-store/memory-packs/CATALOG_ID.json \
  --payload /absolute/private/memory-store/memory-packs/CATALOG_ID.payload.json \
  --selection /absolute/private/selection.json \
  --source-state /absolute/private/current-revisions.json \
  --data-dir /absolute/private/memory-store
```

Use the actual manifest/payload paths returned by `catalog`. The selection file contains exactly
`{"memoryIds":["<catalog row id>"]}`, at most five unique IDs; `[]` explicitly requests no details.
The detail input uses the original v1 adapter request with `content` bodies and the same query,
scope, source identity, revision, authority, trust, provenance and other candidate metadata.
Supply only requested records when possible. No command resolves paths, runs a procedure, queries
a provider, or fetches a body on the user's behalf.

Both commands verify current revisions and revocation before printing context. `expand` also
verifies the private catalog through the existing store before consuming it, then rejects
unknown IDs, missing details, digest mismatch, changed envelope metadata, stale revisions, expiry,
revocation, tampering and symlinks. Catalog TTL and the canonical source's expiry both apply.
Source-state is a trusted caller's current exact source-ID/revision map, not a live connector;
refresh it immediately before use. Verify the returned detail pack again before later reuse.

Both commands return a private pack receipt plus a `context` string of JSON lines. Use only that
string for the measured presentation. Other receipt/manifest fields are operational diagnostics;
feeding those into a model adds unmeasured overhead. All rows retain inert/reference-only
processing, identity and authority metadata. Labels and bodies remain untrusted as instructions.

`accounting` includes the entire rendered catalog plus the admitted detail rows. It reserves
catalog cost from the detail request's total budget, using per-row rounded UTF-8 bytes/4 estimates,
including visible identity/authority metadata. These are heuristics, not actual tokenizer counts
or billed usage. If some selected details cannot fit, `expandedCount` is smaller than
`selectedCount`; inspect the resulting manifest exclusions. A missing/denied selected detail
fails the request rather than masquerading as an empty source.

Catalog and detail packs share existing `0600` storage, TTL cleanup, revocation and explicit-source
purge. This is an extension of one store. No hooks, write-back, automatic injection, transcript
archive, embedding calls, or procedural runtime are enabled. Missing supported procedural or host
episodic APIs remain `unavailable`.

## Evidence and activation

The [implementation plan](../../../../docs/research/memory-awareness-benchmark.md) owns the staged
roadmap, source review, known overlap, and live release gates. Run the component comparison with:

```bash
python3 evals/memory-context/run_awareness_benchmark.py --seed 130 --repeats 20 \
  --output /absolute/private/component-result.json
```

Run from the marketplace checkout. Arm A is the pinned legacy direct-body assembler; Arm B uses
the real catalog/store/expansion path with **oracle** source selection. The harness also executes
an empty-memory control. It measures local behavior and estimated context cost, not agent task
success. It is ineligible for operational benchmark receipts. Live activation requires the exact
incumbent host/model, actual A/B execution, held-out tasks, and measured all-in cost. No defaults
change on the strength of synthetic recall results.

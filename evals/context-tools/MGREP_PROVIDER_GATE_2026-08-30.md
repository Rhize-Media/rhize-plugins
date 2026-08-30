# mgrep managed-provider gate — 2026-08-30

## Decision

**No-go; revisit only after the provider publishes or supplies a written, internally
acceptable retention and purge contract.** Keep mgrep disabled, unauthenticated, unindexed,
and unwired. This review did not create an account, authenticate, create a store, upload a
file, run a query, start a watcher, or mutate a credential.

## Current primary-source findings

- mgrep is not an offline local index. Its official README says that files are pushed into a
  cloud-backed Mixedbread Store, and its coding-agent integration can start background syncing
  automatically. The README also documents a dry-run mode and manual watcher operation, which
  are useful controls but do not change the data boundary once a real sync occurs.
  Source: <https://github.com/mixedbread-ai/mgrep>
- Mixedbread's Terms say Free Tier usage data can be stored in native form, used for model
  training and other internal purposes, retained indefinitely, and may not be deleted even
  after a request. The same Terms say paid-tier data is not used for model training, but data
  previously collected under the free tier keeps the free-tier policy unless separately agreed
  in writing. Source: <https://www.mixedbread.com/pages/terms>
- Mixedbread's Privacy Policy conflicts with the Terms on one important point: it says Free Tier
  data is not used for model training. It still says Free Tier retention is indefinite and that
  historical deletion is not guaranteed; paid retention is described only as what operations
  require. Source: <https://www.mixedbread.com/pages/privacy>

The Terms/Privacy disagreement and the lack of a guaranteed purge are enough to fail the gate.
The paid-tier no-training language does not satisfy the experiment's separate deletion and
absence-verification requirement.

## Evidence needed before reconsideration

1. Written clarification naming the controlling terms for mgrep Free and Paid usage, including
   training, human review, subprocessors, retention after store deletion, backups, logs, and
   historical data.
2. A documented store-delete operation plus a testable receipt or API read proving that the
   exact store identifier no longer resolves.
3. An approved paid tier or enterprise agreement whose retention and purge terms apply before
   any Rhize source is uploaded. Upgrading after a Free Tier trial is not acceptable.
4. A frozen file manifest produced locally after `.gitignore`, `.mgrepignore`, hidden-file,
   symlink, file-size, file-count, and binary exclusions are applied.
5. Literal authorization covering account/authentication use, exact manifest digest, store
   name, upload byte/file caps, query cap, monetary cap, credential handling, store deletion,
   absence verification, and the redacted receipts allowed to remain.

## Comparison contract if the gate later clears

- One fixed Git snapshot; no background watcher.
- One Arm-B-live mgrep route and one Arm-A-shadow CodeGraph/`rg` route on the same predeclared
  retrieval cases.
- Relevant-file recall and critical-file miss rate are the non-inferiority gate; latency, tool
  calls, tokens, and cost are secondary.
- Every mgrep candidate is verified locally before use. A semantic result is never treated as
  proof that the referenced symbol or behavior exists.
- Stop after the first run for review, then delete the store and verify absence unless a new
  literal continuation authorization is granted.

## Reopen trigger

Reopen this decision only when the provider facts above materially change or a signed agreement
resolves them. Installation state or an available API key alone is not a reopen trigger.

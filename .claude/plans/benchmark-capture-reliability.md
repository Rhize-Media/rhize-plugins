# Benchmark capture reliability

## Goal

Make missing optimization evidence fail visibly. A benchmark run counts only when its
Arm A/B measurement is stored in a validated, timestamped receipt; missing or malformed
evidence must produce both a non-zero local result and a stable operational incident.

## Scope

- `rhize-ops/skill-monitor/benchmark_status.py` and focused tests
- context-experiment capture-health evaluation and tests
- procedural-memory `bench-append` timestamped receipts in its own repository
- Sentry project, stable issue fingerprints, and a watchdog-absence monitor
- scheduler documentation needed to run the watchdog after capture routines

## Boundaries

- Preserve the shared `rhize-plugins` checkout and unrelated work.
- Do not treat test doubles as benchmark evidence.
- Never include note paths, row contents, prompts, source, or credentials in telemetry.
- Keep the watchdog standard-library-only.
- Arm A and Arm B remain separate in every receipt, metric comparison, incident, and aggregate.
- Procedural receipts count only when bound to both the exact note row and successful
  `bench-append` run telemetry; context history must reconcile with configured completed runs.

## Current behavior

The released watchdog correctly accepts A/B and G/G1/G2/G3 receipts, but treats every
same-day scheduler/row pair without a timestamped receipt as actionable. The live
`AI-Stack-Version-Drift` pair is dated 2026-08-24, three days before timestamped receipt
enforcement shipped on 2026-08-27. That historical ordering cannot be reconstructed without
fabricating evidence, so the watchdog currently repeats a false operational alarm that no
future capture can repair.

## Intended semantic delta

Classify only same-day pairs whose scheduler run predates the receipt-enforcement instant as
`legacy_unverifiable`. Keep them visible in the snapshot, but exclude them from actionable alerts
because no trustworthy receipt can ever exist for those historical runs. Continue to classify
every same-day run at or after enforcement as `indeterminate_same_day`, and keep every missing,
malformed, unbound, failed, incomplete, or non-comparable capture actionable.

## Invariants

- Existing schema-version-1 A/B and G/G1/G2/G3 receipt validation is unchanged.
- The cutoff is an exact aware datetime derived from the receipt-enforcement release, not a
  scheduler-specific exception or a guessed row timestamp.
- Only same-day ambiguity before that instant is non-actionable; `row_missing`, receipt-store
  failure, malformed or unbound receipts, and every post-enforcement ambiguity remain actionable.
- Malformed, unbound, broad-permission, and failed-run receipts remain actionable.
- No receipt body, prompt, source text, absolute vault path, or credential enters alerts.
- No historical benchmark row, metric, or receipt is created, repaired, or backfilled.

## Acceptance tests

1. A same-day scheduler/row pair before receipt enforcement is `legacy_unverifiable` and produces
   no actionable finding.
2. The same pair at or after enforcement remains `indeterminate_same_day` and actionable.
3. A pre-enforcement run with a later run date than the newest row remains `row_missing`.
4. Existing receipt validation, binding, liveness, permissions, and capture-health tests stay green.
5. The real local snapshot reports the historical AI Stack pair visibly but exits clean when no
   current measurement-loss finding exists.

## Implementation order

1. Add the explicit receipt-enforcement instant and narrow legacy classification.
2. Add pre/post-cutoff and strict missing-row tests.
3. Update operator documentation and release metadata.
4. Reconcile the impact receipt, run full validation, release, then rerun the real watchdog.

## Changed files

- `.claude/plans/benchmark-capture-reliability.md`
- `.claude/evals/benchmark-capture-reliability.md`
- `.claude-plugin/marketplace.json`
- `CHANGELOG.md`
- `README.md`
- `rhize-ops/.claude-plugin/plugin.json`
- `rhize-ops/skill-monitor/README.md`
- `rhize-ops/skill-monitor/benchmark_status.py`
- `rhize-ops/skill-monitor/tests/test_benchmark_status.py`

## Verification

1. Deterministic capture evals cover valid, missing, malformed, stale-pending, incomplete,
   failed, metric-free, non-comparable, deleted-history, and untracked-run evidence.
2. A controlled real watchdog failure produces a grouped Sentry issue with safe tags.
3. A successful watchdog run produces no failure event and preserves exit code 0.
4. Focused suites, the full repository suite, JSON checks, impact reconciliation, and
   exact-ref remote verification pass before release.

## Operational status

- The existing `Review context-tool dogfood evidence` heartbeat now runs both capture evals
  daily and alerts this thread on measurement loss or evaluator failure.
- The dedicated Sentry project request returned the organization's member-creation 403. The
  code path for stable issues and Sentry Cron check-ins is complete, but provisioning and
  Keychain activation require a separate explicit admin authorization; the heartbeat is the
  active alert path until that gate is cleared.

## Parallel ownership

- Root: `rhize-ops`, release metadata, Sentry provisioning, final integration.
- Context-capture agent: context experiment capture-health module and focused test only.
- Receipt agent: procedural-memory bench-append script and smoke test only.
- Sentry agent: read-only design and live capability audit only.

## 2026-08-30 follow-up: require a fresh receipt for every new run

### Current behavior

The scheduler producers now fail if `bench-append` cannot durably write a receipt, and three
routines can emit the closed strict-v2 lifecycle receipt. The released watchdog still accepts
only schema-v1 receipts, however, so the next strict-v2 natural run would be reported as malformed.
Its liveness classifier also returns `ok` when a later-dated row exists even if the latest
post-enforcement scheduler run has no receipt. That date fallback contradicts the requirement that
every new run prove capture with timestamped, run-bound evidence.

### Intended semantic delta

- Accept and independently validate both legacy schema-v1 and strict schema-v2 receipts.
- Normalize strict-v2 note, row, Arm, append-delta, artifact-run, and scheduler metadata into the
  existing binding pipeline without exposing receipt bodies.
- Require a valid bound receipt for every scheduler run at or after the existing enforcement
  instant, regardless of whether a later-dated Markdown row exists.
- Emit actionable `receipt_missing` for a post-enforcement run with no qualifying receipt.
- Preserve `legacy_unverifiable` only for genuinely pre-enforcement same-day history; never create,
  repair, infer, or backfill evidence.

### Invariants

- A schema-v2 receipt must use `procedural-engineering-eval/v2`, `record_type=routine_run`, exact
  one-row projection, matching top-level/nested note and row digests, matching Arm/variant, and a
  successful `bench-append` artifact run.
- Non-comparable receipts are valid capture evidence but remain non-comparable performance evidence.
- Malformed and unbound receipts remain actionable in addition to `receipt_missing`.
- V1 graph receipts remain operational evidence only and never satisfy A/B routine liveness.
- Pre-enforcement `row_missing` remains actionable; the historical exception is not broadened.

### Acceptance tests

1. A real-shaped strict-v2 receipt loads, binds to its exact row and successful artifact run, and
   resolves post-enforcement liveness to `ok`.
2. V2 cross-field disagreement, bad projection delta, missing artifact run, or failed artifact run
   is malformed or unbound and actionable.
3. A post-enforcement run with a newer Markdown row but no receipt is `receipt_missing` and exits 2.
4. Existing v1 A/B, graph isolation, legacy cutoff, privacy, context capture-health, and Sentry
   finding tests remain green.
5. The exact released watchdog path exits 0 only when all current post-enforcement runs have valid
   bound receipts.

### Changed files

- `.claude/plans/benchmark-capture-reliability.md`
- `.claude-plugin/marketplace.json`
- `CHANGELOG.md`
- `README.md`
- `rhize-ops/.claude-plugin/plugin.json`
- `rhize-ops/skill-monitor/README.md`
- `rhize-ops/skill-monitor/benchmark_status.py`
- `rhize-ops/skill-monitor/tests/test_benchmark_status.py`

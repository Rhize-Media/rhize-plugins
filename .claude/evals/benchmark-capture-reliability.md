# EVAL DEFINITION: benchmark capture reliability

Baseline: rhize-plugins `31e2198c97b24712c6fbf688b0b693b461ee7bbd`

## Capability evals

- [x] A verified append creates one private schema-v1 receipt with timestamp, Arm,
      hashes, and append delta; no raw note path or row content is retained.
- [x] A valid receipt newer than the associated scheduler run resolves date-only
      indeterminacy to `ok` only when its run ID resolves to successful bench-append telemetry.
- [x] A scheduler run without a valid receipt is `row_missing` and exits non-zero.
- [x] Malformed receipt JSON, invalid Arm/timestamp/hash, incomplete context receipts,
      failed context receipts, and stale pending selections are actionable failures.
- [x] Context receipt aggregates keep capability, live variant, metric unit, role, and
      evidence separate.
- [x] Completed paired context receipts require a metric per Arm and at least one comparable
      name/unit/evidence tuple; configured completed-run history cannot disappear silently.
- [x] Each actionable routine emits a safe, stable Sentry fingerprint; delivery failure
      never changes a failed benchmark into success.
- [x] The watchdog itself has an independent daily thread heartbeat. Sentry Cron support is
      implemented, but live provisioning remains blocked by the org's member-project policy.

## Regression evals

- [x] Legacy date-only tables still parse without schema homogenization.
- [x] On-demand routines without scheduler keys remain unknown-by-design, not incidents.
- [x] Existing `row_missing` exit code 2 remains compatible.
- [x] A missing Sentry configuration is explicit in telemetry but does not break local
      development runs.
- [x] A Sentry Cron OK check-in cannot be requested without incident delivery enabled.
- [x] No fake provider, synthetic benchmark row, or test receipt is accepted as dogfood
      evidence.

## Release thresholds

- Deterministic regression suite: pass^3 = 1.00 for capture and alert classification.
- Controlled Sentry delivery remains an activation gate: create the dedicated project with
  separately approved admin authority, then observe one real event through Sentry MCP with
  the expected project, environment, release, fingerprint, and tags. Until then, the active
  daily thread heartbeat is the operational alert path.
- Full repository suite and impact reconciliation: 100% passing except documented,
  pre-existing skips.

## First real watchdog result

At 2026-08-27T22:39:16-04:00, the production-shaped combined command exited `2`.
Context capture-health was valid and found no malformed/pending receipt artifacts. The
procedural benchmark side correctly reported that its receipt store was not yet deployed and
kept the two same-day scheduler comparisons indeterminate. No row or receipt was fabricated
to force a green result.

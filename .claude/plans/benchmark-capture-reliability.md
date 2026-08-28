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

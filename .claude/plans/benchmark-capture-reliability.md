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

The released watchdog accepts only A/B receipt fields. The live procedural-memory graph cohort
now emits schema-version-1 G/G1/G2/G3 receipts with explicit `variant` and `rowDateSource`
metadata. Those valid graph receipts are consequently reported as malformed even though they are
bound to successful `bench-append` telemetry. Graph receipts must not enter the four A/B note
liveness calculations.

## Intended semantic delta

Accept G/G1/G2/G3 as valid capture variants, require any explicit `variant` to match `arm`, and
validate `rowDateSource`. Report receipt counts by variant while continuing to bind only receipts
whose note identity matches a configured A/B benchmark note. A graph receipt becomes valid store
evidence, not A/B performance evidence.

## Invariants

- Existing schema-version-1 A/B receipts remain valid without the new optional fields.
- G/G1/G2/G3 receipts remain isolated from A/B note rows and liveness verdicts.
- `captured_local_date` is graph-only and requires a non-empty run ID.
- Malformed, unbound, broad-permission, and failed-run receipts remain actionable.
- No receipt body, prompt, source text, absolute vault path, or credential enters alerts.

## Acceptance tests

1. A real-shaped G1 receipt with `captured_local_date` loads as valid and increments only `by_variant.G1`.
2. Variant/arm disagreement and A/B use of `captured_local_date` fail validation.
3. Existing A/B receipt, binding, liveness, permissions, and actionable-finding tests stay green.
4. The released watchdog accepts the live G1 receipt without adding it to any A/B routine.

## Implementation order

1. Extend the receipt validator and aggregate output.
2. Add focused contract and isolation tests.
3. Update operator documentation and release metadata.
4. Reconcile the impact receipt, run full validation, release, then rerun the real watchdog.

## Changed files

- `.claude/plans/benchmark-capture-reliability.md`
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

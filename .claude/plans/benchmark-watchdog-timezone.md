# Impact Map: Normalize Scheduler Instants Before Benchmark Date Comparison

## Current behavior and evidence

- `benchmark_status.find_scheduler_last_run()` parses Desktop scheduler `lastRunAt` values as
  timezone-aware instants.
- `classify_liveness()` currently calls `.date()` on that instant without converting it to the
  benchmark notes' `America/New_York` calendar. A run at `2026-08-28T00:01Z` is therefore treated
  as August 28 even though the corresponding local benchmark row is dated August 27.
- The live Daily Completed Summary run reproduced the defect: the watchdog emitted `row_missing`
  although the row was appended eleven minutes after the 20:01 ET run on August 27.
- The repository has no `.codegraph/`; discovery used `rg` plus targeted source and test reads.

## Intended semantic delta

- Convert scheduler instants to the benchmark program's `America/New_York` timezone before
  comparing them with date-only benchmark rows.
- Preserve the existing five liveness statuses and their conservative same-day semantics.

## Invariants and must-not-change boundaries

- Date-only note values remain date-only; only real scheduler instants are timezone-converted.
- Same-local-day runs remain `indeterminate_same_day`, never `ok`.
- A genuinely later local calendar day remains `row_missing`.
- The scripts remain standard-library-only and retain their existing CLI and output schemas.
- Trust classes, note parsing, scheduler matching, telemetry, and health aggregation are unchanged.

## Current structural touchpoints

| Repository | Entry point or symbol | Why affected | Evidence |
|---|---|---|---|
| rhize-plugins | `benchmark_status.classify_liveness` | Owns scheduler-date versus note-date classification | Direct source read and live CLI reproduction |
| rhize-plugins | `test_benchmark_status.py` liveness tests | Pins same-day and missing-row behavior | Existing focused tests |
| rhize-plugins | `.claude-plugin/marketplace.json`, `rhize-ops/.claude-plugin/plugin.json`, `README.md`, `CHANGELOG.md` | Coordinated patch release records the behavior change | Repository release contract |

## Planned additions and deletions

- Add one UTC-midnight regression case matching the observed Daily Completed Summary timestamps.
- Add a named benchmark timezone and normalize the scheduler instant at the classification boundary.
- Apply the coordinated `rhize-ops` patch version bump and document the correction.

## External and operational effects

- The scheduled benchmark watchdog will stop emitting a false `row_missing` exit 2 when a local
  evening run crosses midnight in UTC.
- No scheduler, note, telemetry, database, credential, or external API is mutated.

## Acceptance tests

- `2026-08-28T00:01Z` versus an August 27 benchmark row is `indeterminate_same_day` in New York.
- A scheduler run on the next New York calendar date remains `row_missing`.
- All existing skill-monitor tests pass.
- The live watchdog no longer reports Daily Completed Summary as `row_missing` for the observed run.

## Explicitly unaffected paths

- Benchmark row parsing and schemas.
- Scheduler task discovery and matching.
- Trust taxonomy and aggregation.
- Parallel-agent optimization and context-tool evaluation code.

## Unknowns and confidence

- High confidence: the observed scheduler instant, note row, file modification time, and
  `bench-append` receipt establish the timezone boundary directly.

## Implementation order

1. Add the failing UTC-midnight regression test.
2. Normalize the scheduler instant at the liveness comparison boundary.
3. Run focused and full skill-monitor tests plus the live CLI.
4. Simplify the exact diff, reconcile the impact map, and run release gates.

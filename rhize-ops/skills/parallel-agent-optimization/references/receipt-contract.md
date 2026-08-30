# Privacy-safe v2 receipt lifecycle

The helper stores private append-only records under:

```text
~/.rhize/parallel-agent-optimization/
  comparison-reservations.jsonl
  run-reservations.jsonl
  observational/YYYY-MM.jsonl
  controlled/YYYY-MM.jsonl
```

Directories are mode `0700`; files are mode `0600`. New runs use schema v2. Existing v1 receipt
and four-arm reservation rows remain readable and are reported as `legacy_screening_only`, never
rewritten or compared with v2.

## Begin

Pass exactly these fields to `begin --input <file>`:

```json
{
  "schema_version": 2,
  "evidence_class": "observational",
  "variant": "rhize",
  "task_class": "mixed_verification",
  "started_at": "2026-08-30T16:00:00Z",
  "isolated": false,
  "live_mutation": false,
  "one_writer_enforced": true,
  "comparison_id": null
}
```

The helper derives `expected_decision` from the deterministic task class and returns a random local
`run_id`. Controlled begins require a v2 two-arm comparison reservation, `baseline` or `rhize`, a
deterministic task class, `isolated: true`, `live_mutation: false`, and one writer.

## Finalize

Pass `finalize --run-id <id> --input <file>` exactly these fields:

```json
{
  "schema_version": 2,
  "status": "completed",
  "completed_at": "2026-08-30T16:02:00Z",
  "decision": "parallel",
  "lanes_planned": 2,
  "agents": [
    {"started_at": "2026-08-30T16:00:05Z", "completed_at": "2026-08-30T16:01:00Z", "status": "completed"}
  ],
  "tool_calls": null,
  "tool_calls_unavailable_reason": "host_not_exposed",
  "tokens": {"input": null, "output": null, "cache_read": null, "cache_write": null},
  "tokens_unavailable_reason": "host_not_exposed",
  "verification": {"required": 3, "completed": 3, "passed": 3},
  "collisions": 0,
  "rework_events": 0,
  "correctness_pass": true
}
```

Terminal status is `completed`, `failed`, or `incomplete`. A completed run requires a decision,
non-empty complete verification, and a correctness result. Failed/incomplete runs may retain a
null decision or correctness result; unknown lane, agent, verification, collision, or rework fields
may also be null so finalization never requires invented zeros. All supplied counts remain factual.
Duplicate finalization is rejected. `audit-pending` identifies accepted reservations without
terminal receipts and flags those older than the configured threshold.

Allowed unavailable reasons are `host_not_exposed`, `partial_host_coverage`, and `not_measured`.
Never estimate token or tool counts. Timestamps are timezone-aware ISO 8601 values and agent
intervals must fall within the run.

## Derived evidence and readiness

The helper derives elapsed milliseconds, overlapping-agent milliseconds, maximum concurrency,
agent status counts, verification completeness, and routing appropriateness. Controlled metrics
include only complete, reserved, sequentially executed baseline/Rhize pairs with matching task and
verification contracts.

Prospective required thresholds are three matched repeats for every deterministic task class, 100%
correctness/verification/routing, zero collisions, no Rhize rework increase, at least 15% median
elapsed improvement on parallel-expected tasks, actual overlap on every parallel-expected Rhize
run, and at least two agents in those runs. Token/tool coverage remains visible as optional and
does not block a decision merely because the host cannot expose it.

## Privacy boundary

There is no free-text field. Never add prompts, summaries, code, commands, repository/file paths,
project/user/agent/host names, URLs, source session/thread IDs, issue IDs, or external identifiers.
Random local comparison/run UUIDs are receipt identifiers, not source-session identifiers.

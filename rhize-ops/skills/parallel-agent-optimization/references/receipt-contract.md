# Privacy-safe receipt contract

The helper stores append-only JSON Lines under:

```text
~/.rhize/parallel-agent-optimization/
  observational/YYYY-MM.jsonl
  controlled/YYYY-MM.jsonl
```

Directories are mode `0700`; receipt files are mode `0600`. The two evidence classes have separate files and separate report sections.
`comparison-reservations.jsonl` stores only a generated comparison UUID, timestamp, and arm order so
concurrent or abandoned comparison starts still advance the counterbalancing sequence. Appends use
an exclusive file lock, complete-write loop, flush, and 64 KiB record bound.

## Input shape

Create a temporary JSON object containing exactly these fields, then pass it to `parallel_metrics.py append --input <file>`. Unknown fields are rejected.

```json
{
  "schema_version": 1,
  "evidence_class": "observational",
  "variant": "rhize",
  "resource_used": "ecc",
  "task_class": "mixed_verification",
  "started_at": "2026-08-27T14:00:00-04:00",
  "completed_at": "2026-08-27T14:02:00-04:00",
  "decision": "parallel",
  "expected_decision": null,
  "lanes_planned": 2,
  "agents": [
    {
      "started_at": "2026-08-27T14:00:10-04:00",
      "completed_at": "2026-08-27T14:01:10-04:00",
      "status": "completed"
    }
  ],
  "tool_calls": null,
  "tool_calls_unavailable_reason": "host_not_exposed",
  "tokens": {"input": null, "output": null, "cache_read": null, "cache_write": null},
  "tokens_unavailable_reason": "host_not_exposed",
  "verification": {"required": 3, "completed": 3, "passed": 3},
  "collisions": 0,
  "rework_events": 0,
  "correctness_pass": true,
  "isolated": false,
  "live_mutation": false,
  "one_writer_enforced": true,
  "comparison_id": null
}
```

Allowed enums:

- `evidence_class`: `observational`, `controlled`
- `variant`: `baseline`, `ecc`, `superpowers`, `rhize`
- `resource_used`: `none`, `ecc`, `superpowers`
- `task_class`: `parallel_read`, `disjoint_write`, `shared_state`, `dependency_chain`, `mixed_verification`, `gated_live`, `other`
- `decision` and non-null `expected_decision`: `parallel`, `sequential`, `gated`
- agent `status`: `completed`, `failed`, `cancelled`
- unavailable reason: `host_not_exposed`, `partial_host_coverage`, `not_measured`

Timestamps must be timezone-aware ISO 8601 values. Counts must be non-negative integers. Agent intervals must fall within the run interval. Token fields are either all measured non-negative integers, or missing fields are `null` with an unavailable reason. The same rule applies to `tool_calls`.

Variant/resource pairings are strict: baseline uses `none`; ECC uses `ecc`; Superpowers uses `superpowers`; Rhize may use any one resource. A dependency-unavailable ECC or Superpowers observational run may use `none` and must be disclosed as degraded. Controlled ECC and Superpowers arms must use their named resources; otherwise the comparison stops rather than recording misleading candidate evidence.

Controlled receipts additionally require a UUIDv4 `comparison_id`, `isolated: true`, `live_mutation: false`, `one_writer_enforced: true`, at least one predeclared verification check, and non-null `expected_decision` and `correctness_pass`. Observational receipts require `comparison_id: null`.

## Deliberate exclusions

There is no free-text field. Do not add or encode prompts, summaries, code, commands, paths, repositories, project/user/agent/host names, URLs, session/thread IDs, issue IDs, or hashes. The helper generates a receipt `run_id`; it is not a source-session identifier.

## Derived fields

The helper derives elapsed milliseconds, true interval overlap, concurrent-agent milliseconds, maximum concurrency, agent-status counts, verification completeness, and routing appropriateness. It never treats “more than one agent” as proof of parallel execution.

## Evidence interpretation

- Observational receipts describe real usage but are affected by task mix, assignment, environment, and selection bias.
- Controlled receipts support arm comparisons only when they share a comparison ID and the same fixture/check contract.
- Controlled summary metrics include only IDs present in `comparison-reservations.jsonl` with
  exactly one receipt for each arm and matching `task_class`, `expected_decision`, and
  `verification.required` across all four receipts. Arm start/completion times must also follow the
  reserved order without cross-arm overlap. Unreserved, incomplete, duplicate-arm, order/overlap,
  and contract-mismatch groups are counted and excluded, not pooled into medians.
- Missing tool or token coverage must remain visible. Do not rank an arm on unmeasured efficiency.
- Report correctness, verification, elapsed time, tool/token coverage, agent counts, collisions/rework, and routing appropriateness together; no single composite score is authoritative.

# Ephemeral task-graph contract

The graph is a pre-dispatch safety artifact, not a scheduler or authorization token. It may contain
task descriptions and paths while the task is active; never persist it in receipt or Jira storage.

Use `scripts/validate_task_graph.py` with a graph matching `task-graph-v1.schema.json` and a host
profile matching `host-capability-v1.schema.json`:

```bash
python3 scripts/validate_task_graph.py validate --graph /tmp/graph.json --capabilities /tmp/host.json
python3 scripts/validate_task_graph.py next-wave --graph /tmp/graph.json --capabilities /tmp/host.json --state /tmp/state.json
python3 scripts/validate_task_graph.py validate-results --graph /tmp/graph.json --state /tmp/state.json
```

The validator derives data edges from `depends_on`. Write territory and single-capacity resource
collisions must be ordered by a data dependency; otherwise validation fails instead of inventing an
order. All writers targeting one shared checkout are conservatively serialized, even when their file
territories are disjoint; parallel writers require separately isolated worktrees outside this v1 graph.
Approval and external-effect nodes are gated and remain coordinator-owned. Unknown host
concurrency degrades to a single worker. A retry beyond the first attempt is legal only for an
idempotent node, and any approval/external-effect retry must renew approval.

State is versioned `rhize-task-state-v1`. It binds the graph fingerprint and the graph's expected
checkout fingerprint. Each node records `previous_status` and `status`; the validator rejects
backward transitions and changes away from terminal states. State
uses only `pending`, `ready`, `running`, `completed`, `failed`, `cancelled`, `timed_out`,
`blocked_dependency`, or `skipped_optional`, and reports output-contract and cleanup status. Required
failure, missing output, stale checkout, cleanup failure, or missing post-approval/external-state
revalidation blocks synthesis. Nonterminal optional work also blocks synthesis until it is explicitly
cancelled or marked `skipped_optional`, so omissions stay visible. Fan-in levels are computed from
declared item bounds; raw node outputs are never included in the validation response.
`next-wave` reports downstream nodes whose failed, cancelled, timed-out, or blocked dependency must
be closed as `blocked_dependency`; it never silently leaves them eligible.

Task-graph v1 has no nullable-edge contract. Therefore a producer marked `skipped_optional` does
not satisfy any `depends_on` edge: `next-wave` closes its pending dependents as
`blocked_dependency`, and state validation rejects any dependent that already started. A future
nullable dependency must be an explicit schema change rather than an inference from node
optionality.

# Ephemeral task-graph contract

The graph is a pre-dispatch safety artifact, not a scheduler or authorization token. It may contain
task descriptions and paths while the task is active; never persist it in receipt or Jira storage.

## Schema versions

Two schema versions exist: `task-graph-v1.schema.json` (`schema_version: "rhize-task-graph-v1"`) and
`task-graph-v2.schema.json` (`schema_version: "rhize-task-graph-v2"`). **New graphs must use v2.**
v1 remains readable for back-compat only — `validate` still accepts it, but the response carries the
advisory warning code `objective_missing_v1` so a v1 graph is never silently treated as carrying goal
ancestry.

v2 is v1 plus goal ancestry: a required top-level `objective` object (`goal`, `done_signal`, each a
non-blank string of 1–300 characters) stating what the whole dispatch is for and how the coordinator
knows it is done, and a required per-node `purpose` (a non-blank string of 1–240 characters) stating
why that specific lane exists and how its deliverable serves the objective — not a restatement of
`deliverable`. The validator rejects a `purpose` that equals its node's `deliverable` after
whitespace-trimming and casefolding, so a lane cannot satisfy the requirement by copy-pasting its
`deliverable` text. Every other v1 rule — cycles, write-lock and resource-pool collisions, host
concurrency, coordinator capacity, authority gates, bounded outputs, retry safety, lifecycle state,
and fan-in — applies unchanged to v2 graphs; v2 only adds the objective/purpose fields and their
validation, it does not relax anything v1 already enforces.

Objective and purpose text is a pre-dispatch input like `deliverable`, `reads`, and `writes`: the
validator never echoes it back. `validate`, `next-wave`, and `validate-results` output contains only
structural facts (waves, edge counts, warnings, capacity, status) — never the graph's task content,
including the new `objective`/`purpose` fields.

Use `scripts/validate_task_graph.py` with a graph matching `task-graph-v2.schema.json` (or, for a
legacy graph, `task-graph-v1.schema.json`) and a host profile matching
`host-capability-v1.schema.json`:

```bash
python3 scripts/validate_task_graph.py validate --graph /tmp/graph.json --capabilities /tmp/host.json
python3 scripts/validate_task_graph.py next-wave --graph /tmp/graph.json --capabilities /tmp/host.json --state /tmp/state.json
python3 scripts/validate_task_graph.py validate-results --graph /tmp/graph.json --state /tmp/state.json
```

The validator derives data edges from `depends_on`. Write territory and single-capacity resource
collisions must be ordered by a data dependency; otherwise validation fails instead of inventing an
order. All writers targeting one shared checkout are conservatively serialized, even when their file
territories are disjoint. Approval and external-effect nodes are gated and remain coordinator-owned. Unknown host
concurrency degrades to a single worker. A retry beyond the first attempt is legal only for an
idempotent node, and any approval/external-effect retry must renew approval.

## Isolated writers (v2 `isolation`)

A v2 node that writes a separately isolated checkout (its own git worktree or a disposable copy)
declares it:

```json
"isolation": {"kind": "worktree", "root_fingerprint": "<sha256>"}
```

`kind` is `worktree` or `copy`. `root_fingerprint` is the output of
`python3 scripts/validate_task_graph.py root-fingerprint --path <isolated root>`: sha256 of the
filesystem identity (`st_dev:st_ino`) of that root's git toplevel, or of the directory itself for a
plain copy. Symlinks and case-insensitive spellings of one directory therefore get the same
fingerprint.

A graph that isolates any node must also declare a top-level `shared_root_fingerprint`: the
`root-fingerprint` of the shared checkout directory. That is the lock identity for every writer
without `isolation`. `expected_checkout_fingerprint` keeps its separate job, binding checkout state
for drift detection. The two hash different things, so neither can stand in for the other.

- **One writer per checkout still holds:** writers serialize only when they share a root. Writers in
  distinct isolated roots get no `write_lock` edge and may share a wave. A shared-checkout writer and
  an isolated writer do not lock each other.
- **Collisions are per root:** overlapping `writes` territories under the same root still need an
  explicit dependency. Under different roots they are allowed, and reconciling them is the
  coordinator's integration job at the join.
- **Fail closed:** `isolation` is rejected unless the host profile reports `isolated_worktrees`
  `verified` with `supported: true`. It is also rejected when the graph has no
  `shared_root_fingerprint`, or when the root equals `shared_root_fingerprint` or
  `expected_checkout_fingerprint`.
  `validate-results` does not dispatch, so it does not re-check host support.
- **The worker cap is unchanged:** isolation removes the writer lock but not `host_worker_cap`
  (`min(concurrency_budget − coordinator_slots_reserved, host concurrency − reserved)`). Declare a
  budget that covers every lane you intend to run at once, plus the coordinator.
- **Revalidate each root:** the coordinator revalidates each isolated root before integrating its
  result, just as it revalidates the shared checkout at wave boundaries.
- **What the validator can't check:** it compares hashes and can't see where a lane actually runs.
  Compute `shared_root_fingerprint` and every isolation root with `root-fingerprint` on the
  directories you really dispatch into, so equal directories always produce equal fingerprints (and
  therefore serialize). Never invent or reuse a fingerprint.
- **Privacy:** `validate` reports only the count `isolated_write_roots`, never fingerprints.
- **v1 stays frozen:** a v1 graph with `isolation` is rejected.

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

Neither task-graph v1 nor v2 has a nullable-edge contract. Therefore a producer marked
`skipped_optional` does not satisfy any `depends_on` edge: `next-wave` closes its pending dependents
as `blocked_dependency`, and state validation rejects any dependent that already started. A future
nullable dependency must be an explicit schema change rather than an inference from node
optionality.

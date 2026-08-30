# Self-contained execution modes

## Classify before dispatch

| Task class | Expected routing | Constraint |
| --- | --- | --- |
| `parallel_read` | `parallel` | Independent read/check lanes may overlap. |
| `disjoint_write` | `parallel` | Isolate writers and declare non-overlapping territories. |
| `shared_state` | `sequential` | One owner controls the shared checkout, file, table, or service. |
| `dependency_chain` | `sequential` | Do not start downstream work before its input is verified. |
| `mixed_verification` | `parallel` | Overlap independent checks, then join for interpretation. |
| `gated_live` | `gated` | Approval, production, or irreversible state controls sequencing. |
| `other` | explain explicitly | Observational only; controlled evidence needs a deterministic label. |

Parallel execution is eligible only when at least two lanes can start without consuming another
lane's output, each has a bounded deliverable, writes are absent or isolated, protected state stays
coordinator-owned, a join and full verification exist, the host permits dispatch, and likely benefit
exceeds dispatch/integration overhead.

## Build the execution graph

Write a compact matrix before a non-trivial dispatch:

```text
Lane | Depends on | Parallel/gated/sequential | Write surface | Risk | Verification
```

Batch independent reads and checks. Start long-running independent checks together, poll them
deliberately, and pause any dependent lane when a blocker changes the graph. Keep destructive
operations, shared mutations, approval decisions, and final integration behind explicit gates.

## Contract every agent lane

Give one agent one independent problem domain. Every brief must be self-contained and specify:

1. objective and done signal;
2. exact scope and inputs;
3. allowed outputs or write territory;
4. protected files/state and prohibited effects;
5. required checks; and
6. return shape: outcome, evidence, changed state, blockers, and residual risk.

Do not send a vague umbrella task or make an agent reconstruct the coordinator's context. Do not
split related failures before confirming they have independent causes.

## Integrate and report

The coordinator reviews each result, checks collision claims, runs the joined/full verification,
and owns any external effect. Report lanes planned/completed/failed, blockers, actual overlapping
intervals, and verification results. Do not make an unmeasured speed claim.

## Evidence modes

- `apply`: one observational `rhize` run on the actual task.
- `compare`: one isolated controlled reservation containing `baseline` and `rhize` only, run
  sequentially in counterbalanced order.
- Archived v1 `baseline`/`ecc`/`superpowers`/`rhize` receipts and the old one-cell smoke remain
  readable screening evidence. They are never pooled with v2 or required at runtime.

Controlled comparison predeclares task class, fixture seed, protected state, checks, and three
repetitions per deterministic task class. New readiness uses correctness, verification, routing,
elapsed time, actual overlap, collisions, rework, and agent count. Token/tool coverage is reported
as optional because some hosts cannot expose it authoritatively.

## Task-graph lifecycle

For real execution, `validate`, `next-wave`, and `validate-results` are deterministic guidance
operations; they never execute agents. Nodes use `pending`, `ready`, `running`, `completed`, `failed`,
`cancelled`, `timed_out`, `blocked_dependency`, or `skipped_optional`. The coordinator revalidates
checkout state at every wave boundary and approvals/external state after every pause or ambiguous
effect. Write, approval, paid, and external-effect nodes do not retry automatically. Cancellation or
required failure closes downstream work rather than allowing partial synthesis. The live graph is
discarded after the run; only receipt-v2 aggregate counts persist.

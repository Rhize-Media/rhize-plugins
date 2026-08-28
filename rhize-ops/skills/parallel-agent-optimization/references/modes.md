# Execution modes and arm contracts

Every arm inherits the skill's safety, one-writer, verification, and receipt boundaries. The only difference between arms is the planning resource allowed to shape the execution.

## Task classification

Classify the task before choosing execution:

Parallel execution is the default only when every eligibility condition is satisfied:

- two or more lanes can start without consuming another lane's output;
- each lane has a bounded deliverable and an explicit owner;
- writes are absent, non-overlapping, or isolated in separate worktrees/copies;
- protected files and shared external state remain coordinator-owned;
- a defined join point and complete verification plan exist; and
- expected elapsed-time or quality benefit exceeds dispatch and integration overhead.

Otherwise choose sequential or gated execution. This eligibility gate applies even when the user
asks for parallelism; the skill must still be invoked and explain the safer decision.

| Task class | Default decision | Reason |
| --- | --- | --- |
| `parallel_read` | parallel | Independent research or inspection lanes can overlap. |
| `disjoint_write` | parallel only with isolation | Writers need separate worktrees/copies and non-overlapping declared territories. |
| `shared_state` | sequential | A shared checkout, document, database, or integration creates collision risk. |
| `dependency_chain` | sequential | Downstream work needs upstream output. |
| `mixed_verification` | parallel then join | Independent checks may overlap; final interpretation and integration do not. |
| `gated_live` | gated | Approval, production, or irreversible boundaries control the sequence. |
| `other` | reason explicitly | Use the safest shape supported by concrete dependencies. |

Before parallel dispatch, name each lane, its inputs, its allowed outputs, and any protected files or state. If two lanes can change the same state, consolidate them under one writer or isolate them.

## Arms

### `baseline`

Do not load either external resource skill. Use the shared Rhize safety envelope and ordinary platform capabilities. `resource_used` must be `none`.

### `ecc`

Load only `ecc:parallel-execution-optimizer` and follow it for lane/dependency planning inside the shared safety envelope. Do not load Superpowers. `resource_used` is `ecc`, or `none` if the dependency is unavailable.

### `superpowers`

Load only `superpowers:dispatching-parallel-agents` and follow it for narrowly independent problem domains inside the shared safety envelope. Do not load ECC. `resource_used` is `superpowers`, or `none` if the dependency is unavailable.

### `rhize`

Apply this routing policy, then load at most one resource:

- Use ECC for broad work that benefits from an explicit dependency graph, concurrency lanes, gates, or staged verification.
- Use Superpowers for a small set of genuinely independent investigations or fixes with crisp, non-overlapping scopes.
- Use neither for sequential dependency chains, shared-state work, trivial tasks, or gated live operations where dispatch adds no safe concurrency.

Record the chosen resource as `ecc`, `superpowers`, or `none`. Never invoke both to synthesize a combined plan.

## One-writer protocol

- One checkout has one writing agent.
- Parallel readers may inspect the same checkout.
- Parallel writers each receive an isolated worktree/copy and explicit file territory. Their prompts must identify allowed files and protected files.
- The coordinator owns cross-arm setup, final integration, conflict handling, complete verification, and any external mutation.
- A collision is any overlapping edit/state claim that requires conflict resolution. Rework is repeated work caused by bad routing, incomplete boundaries, or a failed handoff; ordinary test-driven iteration is not automatically rework.

## Controlled comparison protocol

1. Predeclare the task class, expected decision, fixture seed, checks, and protected state.
2. Generate the comparison ID and arm order before the first arm.
3. Create a fresh environment from the same seed for each arm.
4. Run arms sequentially in the returned order; concurrency is allowed only within an arm.
5. Run identical checks and record one receipt per arm.
6. Compare matched receipts only. Treat four completed arms as one comparison, not four independent experiments.

The controlled protocol is for safe fixtures and replayable repository tasks. It is not authorization to repeat deployments, messages, Jira writes, payments, database mutations, or other live side effects.
